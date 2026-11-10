"""Проверки расчёта слотов и хранилища. Запуск: python -m pytest tests"""
import asyncio
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from aiogram.fsm.storage.base import StorageKey  # noqa: E402

from config import Schedule  # noqa: E402
from slots import free_starts  # noqa: E402
from storage import Booking, DbFSMStorage, Repository, SlotTaken, make_engine  # noqa: E402

TZ = ZoneInfo("Europe/Moscow")
SCHEDULE = Schedule(open_hour=10, close_hour=22, max_hours=8, booking_days_ahead=60, days_off=frozenset({7}))
NOW = datetime(2026, 11, 10, 14, 30, tzinfo=TZ)  # вторник


def booking(day, start, hours):
    return Booking(id=1, booking_date=day, start_hour=start, hours=hours, username=None, full_name=None, user_id=1)


def test_free_day():
    assert free_starts(date(2026, 11, 11), 2, [], SCHEDULE, NOW) == list(range(10, 21))


def test_busy_slots_excluded():
    day = date(2026, 11, 11)
    starts = free_starts(day, 2, [booking(day, 14, 3)], SCHEDULE, NOW)  # занято 14–17
    assert 13 not in starts and 14 not in starts and 16 not in starts
    assert 12 in starts and 17 in starts


def test_today_only_future_hours():
    assert free_starts(NOW.date(), 1, [], SCHEDULE, NOW)[0] == 15


def test_past_day_off_and_far_future():
    assert free_starts(date(2026, 11, 9), 1, [], SCHEDULE, NOW) == []
    assert free_starts(date(2026, 11, 15), 1, [], SCHEDULE, NOW) == []  # воскресенье — выходной
    assert free_starts(date(2027, 3, 1), 1, [], SCHEDULE, NOW) == []


def test_too_long_booking():
    assert free_starts(date(2026, 11, 11), 13, [], SCHEDULE, NOW) == []


def test_repository_and_fsm(tmp_path):
    async def run():
        engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
        repo = Repository(engine)
        await repo.create_schema()
        day = date(2026, 11, 11)
        common = dict(service_id="recording", service_title="Запись", user_id=1, username="u", full_name="U")
        rid = await repo.add_request(booking=(day, 14, 2), **common)
        with pytest.raises(SlotTaken):
            await repo.add_request(booking=(day, 15, 2), **common)
        await repo.add_request(booking=(day, 16, 2), **common)
        assert len(await repo.bookings_between(day, day)) == 2
        assert await repo.cancel_request(rid)
        assert not await repo.cancel_request(rid)
        assert len(await repo.bookings_between(day, day)) == 1

        fsm = DbFSMStorage(engine)
        key = StorageKey(bot_id=1, chat_id=2, user_id=3)
        assert await fsm.get_state(key) is None and await fsm.get_data(key) == {}
        await fsm.set_state(key, "FSM:genre")
        await fsm.set_data(key, {"service_id": "turnkey", "date": "2026-11-11"})
        fsm2 = DbFSMStorage(engine)  # как после перезапуска
        assert await fsm2.get_state(key) == "FSM:genre"
        assert await fsm2.get_data(key) == {"service_id": "turnkey", "date": "2026-11-11"}
        await fsm.close()

    asyncio.run(run())


def test_postgres_url_normalized():
    engine = make_engine("postgresql://u:p@ep-x.neon.tech/db?sslmode=require&channel_binding=require")
    assert engine.url.drivername == "postgresql+asyncpg"
    assert "sslmode" not in engine.url.query and "channel_binding" not in engine.url.query
