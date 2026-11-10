"""Хранилище: заявки, занятые слоты и состояние диалогов (FSM) в одной БД.

В проде это PostgreSQL (DATABASE_URL, например от Neon), локально — SQLite-файл.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey
from sqlalchemy import (
    BigInteger, Column, Date, DateTime, Integer, MetaData, String, Table, Text,
    and_, insert, inspect, select, text, update,
)
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

metadata = MetaData()

requests_table = Table(
    "requests", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    # Для заявок с сайта user_id пустой: клиента в Telegram мы ещё не знаем.
    Column("user_id", BigInteger),
    Column("username", String(64)),
    Column("full_name", String(256)),
    Column("service_id", String(64), nullable=False),
    Column("service_title", String(128), nullable=False),
    Column("details", Text),
    Column("file_id", String(256)),
    Column("booking_date", Date, index=True),
    Column("start_hour", Integer),
    Column("hours", Integer),
    # new — новая заявка, cancelled — отменена (слот освобождается)
    Column("status", String(16), nullable=False, default="new"),
    # bot — заявка из Telegram-бота, site — с сайта
    Column("source", String(16), nullable=False, default="bot", server_default="bot"),
    Column("contact_name", String(128)),
    Column("contact", String(128)),
    Column("comment", Text),
)

# Колонки, которых не было в первой версии таблицы requests: их добавляет Repository.create_schema.
_ADDED_COLUMNS = {
    "source": "VARCHAR(16) NOT NULL DEFAULT 'bot'",
    "contact_name": "VARCHAR(128)",
    "contact": "VARCHAR(128)",
    "comment": "TEXT",
}

fsm_table = Table(
    "fsm_state", metadata,
    Column("key", String(255), primary_key=True),
    Column("state", String(255)),
    Column("data", Text, nullable=False, default="{}"),
)


def make_engine(database_url: str) -> AsyncEngine:
    """Создаёт движок. Понимает строки вида postgres://...?sslmode=require (Neon, Render, Supabase)."""
    url = make_url(database_url)
    connect_args: dict[str, Any] = {}
    if url.drivername in ("postgres", "postgresql", "postgresql+psycopg2", "postgresql+psycopg"):
        url = url.set(drivername="postgresql+asyncpg")
    if url.drivername == "postgresql+asyncpg":
        query = dict(url.query)
        sslmode = query.pop("sslmode", None)
        query.pop("channel_binding", None)  # asyncpg не понимает этот параметр
        if sslmode and sslmode != "disable":
            connect_args["ssl"] = "require"
        url = url.set(query=query)
    return create_async_engine(url, connect_args=connect_args, pool_pre_ping=True)


@dataclass
class Booking:
    id: int
    booking_date: date
    start_hour: int
    hours: int
    username: str | None
    full_name: str | None
    user_id: int | None
    source: str = "bot"
    contact_name: str | None = None
    contact: str | None = None

    @property
    def end_hour(self) -> int:
        return self.start_hour + self.hours


class SlotTaken(Exception):
    """Выбранное время уже занято."""


class Repository:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine
        # Бот работает одним процессом: замок защищает «проверить слот → записать»
        # от двух одновременных заявок на одно время.
        self._booking_lock = asyncio.Lock()

    async def create_schema(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
            await conn.run_sync(self._upgrade_requests)

    @staticmethod
    def _upgrade_requests(conn) -> None:
        """Доводит таблицу requests, созданную прежней версией бота, до текущей схемы."""
        columns = {c["name"]: c for c in inspect(conn).get_columns("requests")}
        for name, ddl in _ADDED_COLUMNS.items():
            if name not in columns:
                conn.execute(text(f"ALTER TABLE requests ADD COLUMN {name} {ddl}"))
        if columns["user_id"]["nullable"]:
            return
        if conn.dialect.name == "postgresql":
            conn.execute(text("ALTER TABLE requests ALTER COLUMN user_id DROP NOT NULL"))
        else:  # SQLite не умеет снимать NOT NULL: пересоздаём таблицу и переносим строки
            names = ", ".join(c.name for c in requests_table.columns)
            conn.execute(text("DROP INDEX IF EXISTS ix_requests_booking_date"))
            conn.execute(text("ALTER TABLE requests RENAME TO requests_old"))
            requests_table.create(conn)
            conn.execute(text(f"INSERT INTO requests ({names}) SELECT {names} FROM requests_old"))
            conn.execute(text("DROP TABLE requests_old"))

    async def bookings_between(self, start: date, end: date) -> list[Booking]:
        """Активные брони с датой в [start, end]."""
        q = select(requests_table).where(and_(
            requests_table.c.booking_date >= start,
            requests_table.c.booking_date <= end,
            requests_table.c.status != "cancelled",
        )).order_by(requests_table.c.booking_date, requests_table.c.start_hour)
        async with self.engine.connect() as conn:
            rows = (await conn.execute(q)).mappings().all()
        return [
            Booking(
                id=r["id"], booking_date=r["booking_date"], start_hour=r["start_hour"],
                hours=r["hours"], username=r["username"], full_name=r["full_name"],
                user_id=r["user_id"], source=r["source"],
                contact_name=r["contact_name"], contact=r["contact"],
            )
            for r in rows
        ]

    async def add_request(self, *, booking: tuple[date, int, int] | None = None, **fields: Any) -> int:
        """Сохраняет заявку. Для брони проверяет, что слот свободен, иначе SlotTaken."""
        values = dict(fields, created_at=datetime.now(timezone.utc), status="new")
        if booking is None:
            async with self.engine.begin() as conn:
                res = await conn.execute(insert(requests_table).values(**values))
                return res.inserted_primary_key[0]

        day, start_hour, hours = booking
        async with self._booking_lock:
            for b in await self.bookings_between(day, day):
                if b.start_hour < start_hour + hours and start_hour < b.end_hour:
                    raise SlotTaken
            values.update(booking_date=day, start_hour=start_hour, hours=hours)
            async with self.engine.begin() as conn:
                res = await conn.execute(insert(requests_table).values(**values))
                return res.inserted_primary_key[0]

    async def cancel_request(self, request_id: int) -> bool:
        async with self.engine.begin() as conn:
            res = await conn.execute(
                update(requests_table)
                .where(and_(requests_table.c.id == request_id, requests_table.c.status != "cancelled"))
                .values(status="cancelled")
            )
            return res.rowcount > 0


class DbFSMStorage(BaseStorage):
    """Хранит состояние диалога aiogram в той же БД, чтобы оно переживало перезапуск."""

    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    @staticmethod
    def _key(key: StorageKey) -> str:
        return ":".join(str(p) for p in (
            key.bot_id, key.chat_id, key.user_id, key.thread_id,
            key.business_connection_id, key.destiny,
        ))

    async def _row(self, key: StorageKey) -> Mapping[str, Any] | None:
        async with self.engine.connect() as conn:
            res = await conn.execute(select(fsm_table).where(fsm_table.c.key == self._key(key)))
            return res.mappings().first()

    async def _upsert(self, key: StorageKey, **values: Any) -> None:
        k = self._key(key)
        async with self.engine.begin() as conn:
            res = await conn.execute(update(fsm_table).where(fsm_table.c.key == k).values(**values))
            if res.rowcount == 0:
                row = {"key": k, "state": None, "data": "{}"}
                row.update(values)
                await conn.execute(insert(fsm_table).values(**row))

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        value = state.state if isinstance(state, State) else state
        await self._upsert(key, state=value)

    async def get_state(self, key: StorageKey) -> str | None:
        row = await self._row(key)
        return row["state"] if row else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        await self._upsert(key, data=json.dumps(dict(data), ensure_ascii=False))

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        row = await self._row(key)
        return json.loads(row["data"]) if row and row["data"] else {}

    async def close(self) -> None:
        await self.engine.dispose()
