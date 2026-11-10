# garage_bot.py — бот студии звукозаписи «ГАРАЖ»
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from html import escape

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, User

import keyboards as kb
import website
from config import Service, Settings, load_settings
from formatting import fmt_day, fmt_hours
from slots import available_days, free_starts, last_bookable_day
from storage import DbFSMStorage, Repository, SlotTaken, make_engine

log = logging.getLogger("garage_bot")

settings: Settings
repo: Repository

private = Router()
private.message.filter(F.chat.type == ChatType.PRIVATE)
private.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)
group = Router()

DONE_TEXT = "✅ Ваша заявка №{id} отправлена звукорежиссёрам! Скоро с вами свяжутся."

MP3_MIME = {"audio/mpeg", "audio/mp3", "audio/mpeg3"}
WAV_MIME = {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"}


class FSM(StatesGroup):
    choosing_service = State()
    booking_hours = State()
    booking_date = State()
    booking_time = State()
    booking_confirm = State()
    waiting_file = State()
    genre = State()


# ---------- helpers ----------

def now() -> datetime:
    return datetime.now(settings.tz)


def client_html(user: User) -> str:
    name = escape(user.full_name or "клиент")
    link = f'<a href="tg://user?id={user.id}">{name}</a>'
    return f"{link} (@{escape(user.username)})" if user.username else link


def user_fields(user: User) -> dict:
    return {"user_id": user.id, "username": user.username, "full_name": user.full_name}


async def render(event: Message | CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    """Нажатие кнопки — правим то же сообщение; текст от клиента — отвечаем новым."""
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=markup)
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                await event.message.answer(text, reply_markup=markup)
        await event.answer()
    else:
        await event.answer(text, reply_markup=markup)


async def current_service(state: FSMContext) -> Service | None:
    return settings.service((await state.get_data()).get("service_id", ""))


async def notify_group(text: str, *, audio: str | None = None, document: str | None = None) -> None:
    try:
        if audio:
            await bot.send_audio(settings.group_chat_id, audio, caption=text)
        elif document:
            await bot.send_document(settings.group_chat_id, document, caption=text)
        else:
            await bot.send_message(settings.group_chat_id, text)
    except Exception:  # заявка уже в БД, не теряем её из-за ошибки отправки
        log.exception("Не удалось отправить заявку в группу")


# ---------- шаги диалога ----------

async def show_services(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(FSM.choosing_service)
    await state.set_data({})
    await render(
        event,
        "Привет, это студия звукозаписи «ГАРАЖ»! Какая услуга вас интересует?",
        kb.services_kb(settings.services),
    )


async def show_hours(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(FSM.booking_hours)
    await render(event, "Сколько часов вы хотите взять?", kb.hours_kb(settings.schedule.max_hours))


async def show_calendar(event: Message | CallbackQuery, state: FSMContext, month: date | None = None) -> None:
    await state.set_state(FSM.booking_date)
    hours = (await state.get_data())["hours"]
    current = now()
    today = current.date()
    last = last_bookable_day(today, settings.schedule)
    month = (month or today).replace(day=1)
    month = max(month, today.replace(day=1))
    month = min(month, last.replace(day=1))
    next_month = (month + timedelta(days=32)).replace(day=1)
    month_end = next_month - timedelta(days=1)

    bookings = await repo.bookings_between(month, month_end)
    days = available_days(max(month, today), min(month_end, last), hours, bookings, settings.schedule, current)
    text = f"Выберите день для записи на {fmt_hours(hours)}."
    if not days:
        text += "\nВ этом месяце свободных дней нет, посмотрите следующий месяц."
    await render(event, text, kb.calendar_kb(month.year, month.month, days, today, last))


async def show_slots(event: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    day = date.fromisoformat(data["date"])
    hours = data["hours"]
    starts = free_starts(day, hours, await repo.bookings_between(day, day), settings.schedule, now())
    if not starts:
        if isinstance(event, CallbackQuery):
            await event.answer("На этот день свободного времени уже нет", show_alert=True)
        await show_calendar(event, state, day)
        return
    await state.set_state(FSM.booking_time)
    await render(event, f"{fmt_day(day)}, {fmt_hours(hours)}. Выберите время:", kb.slots_kb(starts, hours))


async def show_confirm(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(FSM.booking_confirm)
    data = await state.get_data()
    svc = await current_service(state)
    day = date.fromisoformat(data["date"])
    start, hours = data["start"], data["hours"]
    lines = [
        "Проверьте заявку:",
        f"Услуга: {escape(svc.title)}",
        f"Дата: {fmt_day(day)}",
        f"Время: {start:02d}:00–{start + hours:02d}:00 ({fmt_hours(hours)})",
    ]
    if svc.price_per_hour:
        lines.append(f"Ориентировочно: {svc.price_per_hour * hours:,} ₽".replace(",", " "))
    await render(event, "\n".join(lines), kb.confirm_kb())


# ---------- команды ----------

@private.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await show_services(message, state)


@private.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Заявка отменена. Чтобы начать заново, нажмите /start")


@private.callback_query(kb.NavCb.filter(F.action == "cancel"))
async def nav_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await render(call, "Заявка отменена. Чтобы начать заново, нажмите /start")


@private.callback_query(kb.NavCb.filter(F.action == "back"))
async def nav_back(call: CallbackQuery, state: FSMContext):
    st = await state.get_state()
    if st == FSM.booking_date.state:
        await show_hours(call, state)
    elif st == FSM.booking_time.state:
        data = await state.get_data()
        await show_calendar(call, state, date.fromisoformat(data["date"]))
    elif st == FSM.booking_confirm.state:
        await show_slots(call, state)
    else:  # часы, жанр, файл — назад к выбору услуги
        await show_services(call, state)


# ---------- выбор услуги ----------

@private.callback_query(FSM.choosing_service, kb.ServiceCb.filter())
async def service_chosen(call: CallbackQuery, callback_data: kb.ServiceCb, state: FSMContext):
    svc = settings.service(callback_data.id)
    if svc is None:
        await show_services(call, state)
        return
    await state.set_data({"service_id": svc.id})
    if svc.kind == "booking":
        await show_hours(call, state)
    elif svc.kind == "file":
        await state.set_state(FSM.waiting_file)
        await render(call, f"{escape(svc.title)}: пришлите трек файлом MP3 или WAV.", kb.nav_kb())
    else:
        await state.set_state(FSM.genre)
        await render(call, f"{escape(svc.title)}: в каком жанре?", kb.nav_kb())


@private.message(FSM.choosing_service)
async def service_text(message: Message, state: FSMContext):
    await message.answer("Выберите услугу кнопкой:", reply_markup=kb.services_kb(settings.services))


# ---------- запись: часы → дата → время → подтверждение ----------

@private.callback_query(FSM.booking_hours, kb.HoursCb.filter())
async def hours_chosen(call: CallbackQuery, callback_data: kb.HoursCb, state: FSMContext):
    if not 1 <= callback_data.n <= settings.schedule.max_hours:
        await call.answer()
        return
    await state.update_data(hours=callback_data.n)
    await show_calendar(call, state)


@private.callback_query(FSM.booking_date, kb.CalCb.filter(F.action == "month"))
async def calendar_month(call: CallbackQuery, callback_data: kb.CalCb, state: FSMContext):
    await show_calendar(call, state, date(callback_data.y, callback_data.m, 1))


@private.callback_query(FSM.booking_date, kb.CalCb.filter(F.action == "day"))
async def date_chosen(call: CallbackQuery, callback_data: kb.CalCb, state: FSMContext):
    day = date(callback_data.y, callback_data.m, callback_data.d)
    await state.update_data(date=day.isoformat())
    await show_slots(call, state)


@private.callback_query(kb.CalCb.filter(F.action == "noop"))
async def calendar_noop(call: CallbackQuery):
    await call.answer()


@private.callback_query(FSM.booking_time, kb.SlotCb.filter())
async def slot_chosen(call: CallbackQuery, callback_data: kb.SlotCb, state: FSMContext):
    data = await state.get_data()
    day = date.fromisoformat(data["date"])
    starts = free_starts(day, data["hours"], await repo.bookings_between(day, day), settings.schedule, now())
    if callback_data.h not in starts:
        await call.answer("Это время уже занято, выберите другое", show_alert=True)
        await show_slots(call, state)
        return
    await state.update_data(start=callback_data.h)
    await show_confirm(call, state)


@private.callback_query(FSM.booking_confirm, kb.ConfirmCb.filter())
async def booking_confirmed(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    svc = await current_service(state)
    day = date.fromisoformat(data["date"])
    start, hours = data["start"], data["hours"]
    if start not in free_starts(day, hours, [], settings.schedule, now()):
        await call.answer("Это время уже прошло, выберите другое", show_alert=True)
        await show_slots(call, state)
        return
    try:
        req_id = await repo.add_request(
            booking=(day, start, hours),
            service_id=svc.id, service_title=svc.title, **user_fields(call.from_user),
        )
    except SlotTaken:
        await call.answer("Пока вы выбирали, это время заняли. Выберите другое.", show_alert=True)
        await show_slots(call, state)
        return
    await state.clear()
    await render(call, DONE_TEXT.format(id=req_id))
    await notify_group(
        f"🆕 Заявка №{req_id}: {escape(svc.title)}\n"
        f"{fmt_day(day)}, {start:02d}:00–{start + hours:02d}:00 ({fmt_hours(hours)})\n"
        f"{client_html(call.from_user)}"
    )


@private.message(StateFilter(FSM.booking_hours, FSM.booking_date, FSM.booking_time, FSM.booking_confirm))
async def booking_text(message: Message):
    await message.answer("Пожалуйста, выберите вариант кнопкой выше, или нажмите /cancel, чтобы отменить.")


# ---------- сведение: файл MP3/WAV ----------

def audio_format(message: Message) -> str | None:
    f = message.audio or message.document
    if f is None:
        return None
    name = (f.file_name or "").lower()
    mime = (f.mime_type or "").lower()
    if name.endswith(".mp3") or mime in MP3_MIME:
        return "MP3"
    if name.endswith(".wav") or mime in WAV_MIME:
        return "WAV"
    return None


@private.message(FSM.waiting_file, F.audio | F.document)
async def file_received(message: Message, state: FSMContext):
    fmt = audio_format(message)
    if fmt is None:
        await message.answer("Этот формат не подходит. Пришлите трек в MP3 или WAV.", reply_markup=kb.nav_kb())
        return
    svc = await current_service(state)
    f = message.audio or message.document
    req_id = await repo.add_request(
        service_id=svc.id, service_title=svc.title, details=f"{fmt}: {f.file_name or 'без имени'}",
        file_id=f.file_id, **user_fields(message.from_user),
    )
    await state.clear()
    await message.answer(DONE_TEXT.format(id=req_id))
    caption = (
        f"🆕 Заявка №{req_id}: {escape(svc.title)} ({fmt})\n"
        f"{escape(f.file_name or '')}\n{client_html(message.from_user)}"
    )
    if message.audio:
        await notify_group(caption, audio=f.file_id)
    else:
        await notify_group(caption, document=f.file_id)


@private.message(FSM.waiting_file)
async def file_missing(message: Message):
    await message.answer("Пришлите трек файлом в формате MP3 или WAV.", reply_markup=kb.nav_kb())


# ---------- аранжировка и «под ключ»: жанр ----------

@private.message(FSM.genre, F.text)
async def genre_received(message: Message, state: FSMContext):
    genre = message.text.strip()
    if not genre or genre.startswith("/"):
        await message.answer("Напишите жанр текстом, например: хип-хоп, поп, рок.", reply_markup=kb.nav_kb())
        return
    genre = genre[:500]
    svc = await current_service(state)
    req_id = await repo.add_request(
        service_id=svc.id, service_title=svc.title, details=genre, **user_fields(message.from_user),
    )
    await state.clear()
    await message.answer(DONE_TEXT.format(id=req_id))
    await notify_group(
        f"🆕 Заявка №{req_id}: {escape(svc.title)}\nЖанр: {escape(genre)}\n{client_html(message.from_user)}"
    )


@private.message(FSM.genre)
async def genre_not_text(message: Message):
    await message.answer("Напишите жанр текстом.", reply_markup=kb.nav_kb())


# ---------- прочее ----------

@private.callback_query()
async def stale_button(call: CallbackQuery):
    await call.answer("Эта кнопка уже неактуальна. Нажмите /start, чтобы начать заново.", show_alert=True)


@private.message()
async def no_state(message: Message):
    await message.answer("Чтобы оставить заявку, нажмите /start")


# ---------- команды для группы звукорежиссёров ----------

def in_studio_group(message: Message) -> bool:
    return message.chat.id == settings.group_chat_id


@group.message(Command("bookings"), in_studio_group)
async def cmd_bookings(message: Message):
    today = now().date()
    items = await repo.bookings_between(today, last_bookable_day(today, settings.schedule))
    if not items:
        await message.answer("Ближайших записей нет.")
        return
    lines = ["📅 Ближайшие записи:"]
    for b in items:
        if b.source == "site":
            who = f"{escape(b.contact_name or 'клиент')}, {escape(b.contact or 'без контакта')} (с сайта)"
        else:
            who = f"@{escape(b.username)}" if b.username else escape(b.full_name or str(b.user_id))
        lines.append(f"№{b.id} · {b.booking_date:%d.%m} {b.start_hour:02d}:00–{b.end_hour:02d}:00 · {who}")
    lines.append("\nОсвободить время: /cancel_booking номер")
    await message.answer("\n".join(lines))


@group.message(Command("cancel_booking"), in_studio_group)
async def cmd_cancel_booking(message: Message, command: CommandObject):
    arg = (command.args or "").strip().lstrip("№#")
    if not arg.isdigit():
        await message.answer("Укажите номер заявки: /cancel_booking 12")
        return
    if await repo.cancel_request(int(arg)):
        await message.answer(f"Заявка №{arg} отменена, время освобождено.")
    else:
        await message.answer(f"Заявка №{arg} не найдена или уже отменена.")


# ---------- запуск ----------

async def main() -> None:
    global settings, repo, bot
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    engine = make_engine(settings.database_url)
    repo = Repository(engine)
    await repo.create_schema()

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=DbFSMStorage(engine))
    dp.include_routers(group, private)
    # Сайт студии работает в этом же процессе: Render (type: web) ждёт, что сервис слушает $PORT.
    me = await bot.get_me()
    await website.start(settings, repo, notify_group, bot_username=me.username)
    log.info("✅ Бот студии «ГАРАЖ» запущен (БД: %s)", engine.url.get_backend_name())
    await dp.start_polling(bot)


bot: Bot

if __name__ == "__main__":
    asyncio.run(main())
