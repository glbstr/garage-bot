"""Проверки сайта: страница, свободное время, приём заявок. Запуск: python -m pytest tests"""
import asyncio
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402
from sqlalchemy import text  # noqa: E402

import website  # noqa: E402
from config import Schedule, Service, Settings  # noqa: E402
from storage import Repository, make_engine  # noqa: E402

TZ = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 11, 10, 14, 30, tzinfo=TZ)  # вторник
SETTINGS = Settings(
    bot_token="", group_chat_id=0, database_url="", tz=TZ,
    schedule=Schedule(open_hour=10, close_hour=22, max_hours=8, booking_days_ahead=60, days_off=frozenset({7})),
    services=(
        Service(id="recording", kind="booking", title="Запись", price="от 1 000 ₽/час", price_per_hour=1000),
        Service(id="mixing", kind="file", title="Сведение", price="от 1 500 ₽"),
        Service(id="turnkey", kind="genre", title="Трек «под ключ»", price="от 5 000 ₽"),
    ),
)
BOOKING = {"service_id": "recording", "hours": 2, "date": "2026-11-11", "start": 14, "name": "Вася", "contact": "@vasya_mc"}


def run_site(tmp_path, scenario):
    async def run():
        repo = Repository(make_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}"))
        await repo.create_schema()
        sent = []

        async def notify(message):
            sent.append(message)

        site = website.Site(SETTINGS, repo, notify, bot_username="garage_bot", now=lambda: NOW)
        async with TestClient(TestServer(website.create_app(site))) as client:
            await scenario(client, repo, sent)
        await repo.engine.dispose()

    asyncio.run(run())


def test_page_has_content_without_js(tmp_path):
    async def scenario(client, repo, sent):
        resp = await client.get("/")
        assert resp.status == 200
        html = await resp.text()
        for needle in ("Высоцкого, 8", "от 1 000 ₽/час", "Микрофон", 'data-open="booking"', "@garage_bot", "уточнить"):
            assert needle in html
        assert (await client.get("/healthz")).status == 200
        assert (await client.get("/static/scene.png")).status == 200

    run_site(tmp_path, scenario)


def test_booking_from_site(tmp_path):
    async def scenario(client, repo, sent):
        slots = await (await client.get("/api/slots", params={"date": "2026-11-11", "hours": "2"})).json()
        assert 14 in slots["starts"]

        resp = await client.post("/api/requests", json=dict(BOOKING, comment="<b>привет</b>"))
        assert resp.status == 201
        req_id = (await resp.json())["id"]
        await asyncio.sleep(0.05)  # сообщение в группу уходит фоном
        assert len(sent) == 1
        assert f"Заявка №{req_id} <b>с сайта</b>: Запись" in sent[0]
        assert "11.11.2026 (среда), 14:00–16:00 (2 часа)" in sent[0]
        assert 'href="https://t.me/vasya_mc"' in sent[0]
        assert "&lt;b&gt;привет&lt;/b&gt;" in sent[0]

        saved = (await repo.bookings_between(date(2026, 11, 11), date(2026, 11, 11)))[0]
        assert (saved.source, saved.contact_name, saved.contact, saved.user_id) == ("site", "Вася", "@vasya_mc", None)

        # то же время второй раз занять нельзя, и в свободных оно больше не показывается
        again = await client.post("/api/requests", json=BOOKING)
        assert again.status == 409 and (await again.json())["field"] == "start"
        slots = await (await client.get("/api/slots", params={"date": "2026-11-11", "hours": "2"})).json()
        assert not {13, 14, 15} & set(slots["starts"])
        assert len(sent) == 1

    run_site(tmp_path, scenario)


def test_days_strip(tmp_path):
    async def scenario(client, repo, sent):
        days = (await (await client.get("/api/days", params={"hours": "8"})).json())["days"]
        by_date = {d["date"]: d["free"] for d in days}
        assert len(days) == 61
        assert by_date["2026-11-10"] is False  # сегодня 8 часов подряд уже не помещаются
        assert by_date["2026-11-11"] is True
        assert by_date["2026-11-15"] is False  # воскресенье — выходной

    run_site(tmp_path, scenario)


def test_validation_and_other_services(tmp_path):
    async def scenario(client, repo, sent):
        async def post(**changes):
            resp = await client.post("/api/requests", json={**BOOKING, **changes})
            return resp.status, await resp.json()

        assert (await post(contact=""))[1]["field"] == "contact"
        assert (await post(name=" "))[1]["field"] == "name"
        assert (await post(service_id="nope"))[1]["field"] == "service_id"
        assert (await post(hours=99))[1]["field"] == "hours"
        assert (await post(date="2026-11-09"))[0] == 409  # вчера
        assert (await post(date="2026-11-15"))[0] == 409  # выходной
        assert (await post(service_id="turnkey"))[1]["field"] == "genre"
        assert (await client.post("/api/requests", data="не json")).status == 400
        assert sent == []

        status, body = await post(service_id="turnkey", genre="архивкор")
        assert status == 201
        status, _ = await post(service_id="mixing")
        assert status == 201
        await asyncio.sleep(0.05)
        assert "Жанр: архивкор" in sent[0] and "Сведение" in sent[1]

        # поле-ловушку заполняют только роботы: отвечаем «принято», но ничего не сохраняем и не шлём
        status, _ = await post(website="http://spam")
        assert status == 201
        await asyncio.sleep(0.05)
        assert len(sent) == 2

    run_site(tmp_path, scenario)


def test_rate_limit(tmp_path):
    async def scenario(client, repo, sent):
        codes = []
        for _ in range(website.RATE_PER_IP + 1):
            resp = await client.post("/api/requests", json=dict(BOOKING, service_id="mixing"))
            codes.append(resp.status)
        assert codes == [201] * website.RATE_PER_IP + [429]

    run_site(tmp_path, scenario)


def test_old_requests_table_is_upgraded(tmp_path):
    """Таблица, созданная ботом до появления сайта, получает новые колонки и сохраняет строки."""
    async def run():
        engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'old.db'}")
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TABLE requests (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at DATETIME NOT NULL, "
                "user_id BIGINT NOT NULL, username VARCHAR(64), full_name VARCHAR(256), service_id VARCHAR(64) NOT NULL, "
                "service_title VARCHAR(128) NOT NULL, details TEXT, file_id VARCHAR(256), booking_date DATE, "
                "start_hour INTEGER, hours INTEGER, status VARCHAR(16) NOT NULL)"
            ))
            await conn.execute(text("CREATE INDEX ix_requests_booking_date ON requests (booking_date)"))
            await conn.execute(text(
                "INSERT INTO requests (created_at, user_id, username, service_id, service_title, booking_date, "
                "start_hour, hours, status) VALUES ('2026-11-01 10:00:00', 7, 'old', 'recording', 'Запись', "
                "'2026-11-11', 10, 2, 'new')"
            ))
        repo = Repository(engine)
        await repo.create_schema()
        await repo.create_schema()  # повторный запуск ничего не ломает
        rid = await repo.add_request(
            booking=(date(2026, 11, 11), 14, 2), service_id="recording", service_title="Запись",
            source="site", contact_name="Вася", contact="+7 900", full_name="Вася",
        )
        items = await repo.bookings_between(date(2026, 11, 11), date(2026, 11, 11))
        assert [(b.user_id, b.source, b.username) for b in items] == [(7, "bot", "old"), (None, "site", None)]
        assert items[1].id == rid
        await engine.dispose()

    asyncio.run(run())
