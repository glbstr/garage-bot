"""Загрузка настроек: секреты из переменных окружения, услуги и расписание из settings.toml."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

SETTINGS_PATH = Path(os.getenv("SETTINGS_PATH", Path(__file__).with_name("settings.toml")))

KINDS = {"booking", "file", "genre"}


@dataclass(frozen=True)
class Service:
    id: str
    kind: str
    title: str
    price: str
    price_per_hour: int | None = None

    @property
    def button(self) -> str:
        return f"{self.title} — {self.price}"


@dataclass(frozen=True)
class Schedule:
    open_hour: int
    close_hour: int
    max_hours: int
    booking_days_ahead: int
    days_off: frozenset[int]


@dataclass(frozen=True)
class Settings:
    bot_token: str
    group_chat_id: int
    database_url: str
    tz: ZoneInfo
    schedule: Schedule
    services: tuple[Service, ...]

    def service(self, service_id: str) -> Service | None:
        return next((s for s in self.services if s.id == service_id), None)


def _env_int(name: str) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        raise SystemExit(f"❌ Укажите {name} в переменных окружения!")
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"❌ {name} должен быть числом, сейчас: {raw!r}")


def load_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise SystemExit("❌ Укажите BOT_TOKEN в переменных окружения!")
    group_chat_id = _env_int("GROUP_CHAT_ID")
    database_url = os.getenv("DATABASE_URL", "").strip() or "sqlite+aiosqlite:///garage.db"

    with open(SETTINGS_PATH, "rb") as f:
        raw = tomllib.load(f)

    sch = raw.get("schedule", {})
    schedule = Schedule(
        open_hour=int(sch.get("open_hour", 10)),
        close_hour=int(sch.get("close_hour", 22)),
        max_hours=int(sch.get("max_hours", 8)),
        booking_days_ahead=int(sch.get("booking_days_ahead", 60)),
        days_off=frozenset(int(d) for d in sch.get("days_off", [])),
    )
    if not 0 <= schedule.open_hour < schedule.close_hour <= 24:
        raise SystemExit("❌ settings.toml: нужно 0 <= open_hour < close_hour <= 24")
    if schedule.max_hours < 1:
        raise SystemExit("❌ settings.toml: max_hours должен быть >= 1")

    services = []
    for item in raw.get("services", []):
        svc = Service(
            id=str(item["id"]),
            kind=str(item["kind"]),
            title=str(item["title"]),
            price=str(item.get("price", "")),
            price_per_hour=item.get("price_per_hour"),
        )
        if svc.kind not in KINDS:
            raise SystemExit(f"❌ settings.toml: у услуги {svc.id} неизвестный kind {svc.kind!r}")
        services.append(svc)
    if not services:
        raise SystemExit("❌ settings.toml: не задано ни одной услуги")

    return Settings(
        bot_token=bot_token,
        group_chat_id=group_chat_id,
        database_url=database_url,
        tz=ZoneInfo(raw.get("timezone", "Europe/Moscow")),
        schedule=schedule,
        services=tuple(services),
    )
