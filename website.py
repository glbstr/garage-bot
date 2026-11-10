"""Сайт студии «ГАРАЖ»: одна страница с пиксельной сценой и формой заявки.

Работает в том же процессе, что и бот (aiohttp слушает $PORT), пишет заявки в ту же базу
и отправляет их в ту же группу звукорежиссёров с пометкой «с сайта».

Предпросмотр без Telegram: python website.py  → http://localhost:8080
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
import tomllib
from collections import defaultdict, deque
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import quote

from aiohttp import web
from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import Settings, load_settings
from formatting import fmt_day, fmt_hours
from slots import free_starts, last_bookable_day
from storage import Repository, SlotTaken, make_engine

log = logging.getLogger("garage_site")

ROOT = Path(__file__).parent
WEB_DIR = ROOT / "web"
STATIC_DIR = WEB_DIR / "static"
CONTENT_PATH = Path(os.getenv("SITE_CONTENT_PATH", ROOT / "content" / "site.toml"))

UNKNOWN = "уточнить"
WEEKDAYS_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS_SHORT = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]

# Ограничение заявок: с одного адреса и всего, чтобы форму нельзя было превратить в спам по группе.
RATE_WINDOW = 600
RATE_PER_IP = 5
RATE_TOTAL = 40

Notify = Callable[[str], Awaitable[None]]

# Предметы сцены: куда ведёт клик, подпись и точка для метки (доли рамки предмета из scene.json).
HOTSPOTS = [
    {"id": "screen", "label": "Записаться", "target": "booking", "at": (0.5, 0.2), "pos": "up"},
    {"id": "prices", "label": "Цены", "target": "prices", "at": (0.5, 0.45), "pos": "down"},
    {"id": "mic", "label": "Микрофон", "target": "gear-mic", "at": (0.3, 0.75), "pos": "down"},
    {"id": "speakers", "label": "Мониторы", "target": "gear-speakers", "at": (0.88, 0.75), "pos": "down"},
    {"id": "keys", "label": "Клавиши", "target": "gear-keys", "at": (0.55, 0.28), "pos": "right"},
    {"id": "guitar", "label": "Гитара", "target": "gear-guitar", "at": (0.5, 0.7), "pos": "left"},
    {"id": "shelf", "label": "Техника", "target": "gear-shelf", "at": (0.5, 0.45), "pos": "down"},
    {"id": "address", "label": "Адрес", "target": "contacts", "at": (0.5, 0.5), "pos": "up"},
    {"id": "contacts", "label": "Связь", "target": "contacts", "at": (0.5, 0.5), "pos": "left"},
    # табло REC кликается на картинке, но отдельной метки у него нет
    {"id": "rec", "label": "Записаться", "target": "booking", "at": (0.5, 0.5), "pos": "up", "quiet": True},
]

TG_NICK = re.compile(r"^@?([A-Za-z][A-Za-z0-9_]{3,31})$")


class FormError(Exception):
    def __init__(self, message: str, field: str | None = None, status: int = 400):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


def load_content(path: Path = CONTENT_PATH) -> dict[str, Any]:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    raw.setdefault("studio", {})
    raw.setdefault("address", {})
    raw.setdefault("contacts", {})
    raw.setdefault("gear", [])
    return raw


def _asset_version() -> str:
    h = hashlib.sha1()
    for p in sorted(STATIC_DIR.rglob("*")):
        if p.is_file():
            h.update(p.name.encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:10]


def _text(value: Any, limit: int) -> str:
    """Строка из формы: без управляющих символов, с обрезкой по длине."""
    if value is None:
        return ""
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value)).strip()
    return s[:limit]


def contact_html(contact: str) -> str:
    m = TG_NICK.match(contact)
    if m:
        return f'<a href="https://t.me/{m.group(1)}">@{escape(m.group(1))}</a>'
    return escape(contact)


class Site:
    def __init__(
        self,
        settings: Settings,
        repo: Repository,
        notify: Notify,
        *,
        content: dict[str, Any] | None = None,
        bot_username: str | None = None,
        now: Callable[[], datetime] | None = None,
    ):
        self.settings = settings
        self.repo = repo
        self.notify = notify
        self.content = content if content is not None else load_content()
        self.bot_username = bot_username
        self._now = now or (lambda: datetime.now(settings.tz))
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._all_hits: deque[float] = deque()
        self._tasks: set[asyncio.Task] = set()
        self.version = _asset_version()
        self.scene = json.loads((STATIC_DIR / "scene.json").read_text(encoding="utf-8"))
        env = Environment(
            loader=FileSystemLoader(WEB_DIR / "templates"),
            autoescape=select_autoescape(["html"]),
            trim_blocks=True, lstrip_blocks=True,
        )
        env.filters["known"] = lambda v: v if v else UNKNOWN
        self._template = env.get_template("index.html")

    # ---------- страница ----------

    def _hotspots(self) -> list[dict[str, Any]]:
        w, h = self.scene["width"], self.scene["height"]
        gear_ids = {g["id"] for g in self.content["gear"]}
        result = []
        for spot in HOTSPOTS:
            box = self.scene["boxes"].get(spot["id"])
            target = spot["target"]
            if box is None or (target.startswith("gear-") and target[5:] not in gear_ids):
                continue
            ax, ay = spot["at"]
            result.append({
                **spot,
                "left": round((box[0] + box[2] * ax) / w * 100, 2),
                "top": round((box[1] + box[3] * ay) / h * 100, 2),
            })
        return result

    def _page_context(self) -> dict[str, Any]:
        s, sch = self.settings, self.settings.schedule
        studio, address, contacts = self.content["studio"], self.content["address"], self.content["contacts"]
        tg = str(contacts.get("telegram", "")).lstrip("@")
        phone = str(contacts.get("phone", ""))
        services = [
            {"id": x.id, "kind": x.kind, "title": x.title, "price": x.price, "price_per_hour": x.price_per_hour}
            for x in s.services
        ]
        days_off = sorted(sch.days_off)
        return {
            "v": self.version,
            "studio": studio,
            "address": address,
            "telegram": tg,
            "phone": phone,
            "phone_href": "+" + re.sub(r"\D", "", phone) if phone.strip().startswith("+") else re.sub(r"\D", "", phone),
            "bot_username": self.bot_username,
            "map_url": "https://yandex.ru/maps/?text=" + quote(str(address.get("map_query") or address.get("line", ""))),
            "gear": self.content["gear"],
            "services": services,
            "open_hour": sch.open_hour,
            "close_hour": sch.close_hour,
            "days_off": ", ".join(WEEKDAYS_SHORT[d - 1] for d in days_off),
            "scene": self.scene,
            "hotspots": [h for h in self._hotspots() if not h.get("quiet")],
            "year": self._now().year,
            "config_json": json.dumps({
                "services": services,
                "maxHours": sch.max_hours,
                "scene": self.scene,
                "targets": {h["id"]: h["target"] for h in self._hotspots()},
                "v": self.version,
            }, ensure_ascii=False).replace("<", "\\u003c"),
        }

    async def index(self, request: web.Request) -> web.Response:
        html = self._template.render(self._page_context())
        return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-cache"})

    async def health(self, request: web.Request) -> web.Response:
        return web.Response(text="ok")

    async def robots(self, request: web.Request) -> web.Response:
        return web.Response(text="User-agent: *\nAllow: /\nDisallow: /api/\n")

    # ---------- API: свободное время ----------

    def _hours(self, raw: Any) -> int:
        try:
            hours = int(raw)
        except (TypeError, ValueError):
            raise FormError("Укажите количество часов.", "hours")
        if not 1 <= hours <= self.settings.schedule.max_hours:
            raise FormError(f"Можно записаться на время от 1 до {self.settings.schedule.max_hours} ч.", "hours")
        return hours

    @staticmethod
    def _day(raw: Any) -> date:
        try:
            return date.fromisoformat(str(raw))
        except ValueError:
            raise FormError("Выберите день.", "date")

    async def api_days(self, request: web.Request) -> web.Response:
        """Дни, доступные для записи на заданное число часов: для полоски с датами в форме."""
        hours = self._hours(request.query.get("hours", "1"))
        current = self._now()
        today = current.date()
        last = last_bookable_day(today, self.settings.schedule)
        bookings = await self.repo.bookings_between(today, last)
        days, d = [], today
        while d <= last:
            days.append({
                "date": d.isoformat(),
                "day": d.day,
                "weekday": WEEKDAYS_SHORT[d.weekday()],
                "month": MONTHS_SHORT[d.month - 1],
                "free": bool(free_starts(d, hours, bookings, self.settings.schedule, current)),
            })
            d += timedelta(days=1)
        return web.json_response({"hours": hours, "days": days})

    async def api_slots(self, request: web.Request) -> web.Response:
        hours = self._hours(request.query.get("hours", "1"))
        day = self._day(request.query.get("date", ""))
        bookings = await self.repo.bookings_between(day, day)
        starts = free_starts(day, hours, bookings, self.settings.schedule, self._now())
        return web.json_response({"date": day.isoformat(), "hours": hours, "starts": starts})

    # ---------- API: заявка ----------

    def _check_rate(self, request: web.Request) -> None:
        forwarded = request.headers.get("X-Forwarded-For", "")
        ip = forwarded.split(",")[0].strip() or request.remote or "?"
        t = time.monotonic()
        mine = self._hits[ip]
        for q in (mine, self._all_hits):
            while q and t - q[0] > RATE_WINDOW:
                q.popleft()
        if len(mine) >= RATE_PER_IP or len(self._all_hits) >= RATE_TOTAL:
            raise FormError("Слишком много заявок подряд. Попробуйте через несколько минут.", status=429)
        mine.append(t)
        self._all_hits.append(t)
        if len(self._hits) > 5000:  # не копим адреса бесконечно
            for key in [k for k, v in self._hits.items() if not v]:
                del self._hits[key]

    async def api_request(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            raise FormError("Не удалось прочитать заявку. Обновите страницу и попробуйте ещё раз.")
        if not isinstance(data, dict):
            raise FormError("Не удалось прочитать заявку. Обновите страницу и попробуйте ещё раз.")
        if _text(data.get("website"), 200):  # поле-ловушка: человек его не видит, бот заполняет
            return web.json_response({"id": 0}, status=201)

        svc = self.settings.service(_text(data.get("service_id"), 64))
        if svc is None:
            raise FormError("Выберите услугу.", "service_id")
        name = _text(data.get("name"), 80)
        contact = _text(data.get("contact"), 80)
        comment = _text(data.get("comment"), 1000)
        if not name:
            raise FormError("Напишите, как к вам обращаться.", "name")
        if len(contact) < 3:
            raise FormError("Оставьте Telegram или телефон, чтобы мы могли ответить.", "contact")

        lines = []
        fields: dict[str, Any] = dict(
            service_id=svc.id, service_title=svc.title, source="site",
            contact_name=name, contact=contact, comment=comment or None, full_name=name,
        )
        booking = None
        if svc.kind == "booking":
            hours = self._hours(data.get("hours"))
            day = self._day(data.get("date"))
            try:
                start = int(data.get("start"))
            except (TypeError, ValueError):
                raise FormError("Выберите время.", "start")
            taken = FormError("Это время уже занято или недоступно. Выберите другое.", "start", status=409)
            if start not in free_starts(
                day, hours, await self.repo.bookings_between(day, day), self.settings.schedule, self._now()
            ):
                raise taken
            booking = (day, start, hours)
            lines.append(f"{fmt_day(day)}, {start:02d}:00–{start + hours:02d}:00 ({fmt_hours(hours)})")
        elif svc.kind == "genre":
            genre = _text(data.get("genre"), 200)
            if not genre:
                raise FormError("Напишите жанр.", "genre")
            fields["details"] = genre
            lines.append(f"Жанр: {escape(genre)}")
        else:  # file: на сайте файл не загружаем, просим ссылку или присылают потом в Telegram
            link = _text(data.get("link"), 300)
            if link:
                fields["details"] = link
                lines.append(f"Трек: {escape(link)}")
            else:
                lines.append("Трек: пришлёт после ответа")

        self._check_rate(request)
        try:
            req_id = await self.repo.add_request(booking=booking, **fields)
        except SlotTaken:
            raise FormError("Пока вы заполняли заявку, это время заняли. Выберите другое.", "start", status=409)

        lines.append(f"Клиент: {escape(name)}, {contact_html(contact)}")
        if comment:
            lines.append(f"Комментарий: {escape(comment)}")
        # Заявка уже в базе: отвечаем клиенту сразу, сообщение в группу уходит фоном.
        lines.insert(0, f"🌐 Заявка №{req_id} <b>с сайта</b>: {escape(svc.title)}")
        task = asyncio.create_task(self._notify("\n".join(lines)))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return web.json_response({"id": req_id}, status=201)

    async def _notify(self, text: str) -> None:
        try:
            await self.notify(text)
        except Exception:
            log.exception("Не удалось отправить заявку с сайта в группу")


@web.middleware
async def _errors_and_headers(request: web.Request, handler):
    try:
        response = await handler(request)
    except FormError as e:
        response = web.json_response({"error": e.message, "field": e.field}, status=e.status)
    except web.HTTPException as e:
        if not request.path.startswith("/api/"):
            raise
        response = web.json_response({"error": e.reason}, status=e.status)
    except Exception:
        if not request.path.startswith("/api/"):
            raise
        log.exception("Ошибка в %s", request.path)
        response = web.json_response(
            {"error": "Что-то пошло не так. Попробуйте ещё раз чуть позже."}, status=500
        )
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if response.content_type == "text/html":
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'self'",
        )
    if request.path.startswith("/static/") and "v" in request.query:
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


def create_app(site: Site) -> web.Application:
    app = web.Application(middlewares=[_errors_and_headers], client_max_size=32 * 1024)
    app.router.add_get("/", site.index)
    app.router.add_get("/healthz", site.health)
    app.router.add_get("/robots.txt", site.robots)
    app.router.add_get("/api/days", site.api_days)
    app.router.add_get("/api/slots", site.api_slots)
    app.router.add_post("/api/requests", site.api_request)
    app.router.add_static("/static/", STATIC_DIR)
    return app


async def start(
    settings: Settings, repo: Repository, notify: Notify, *, bot_username: str | None = None
) -> web.AppRunner:
    """Запускает сайт на $PORT (по умолчанию 8080) и возвращает управление: бот продолжает работать."""
    port = int(os.getenv("PORT", "8080"))
    runner = web.AppRunner(create_app(Site(settings, repo, notify, bot_username=bot_username)))
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info("Сайт слушает порт %s", port)
    return runner


async def _preview() -> None:
    """Сайт без бота: заявки пишутся в базу, а вместо группы печатаются в лог."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings(require_bot=False)
    repo = Repository(make_engine(settings.database_url))
    await repo.create_schema()

    async def to_log(text: str) -> None:
        log.info("В группу ушло бы:\n%s", text)

    await start(settings, repo, to_log, bot_username=os.getenv("PREVIEW_BOT_USERNAME"))
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(_preview())
