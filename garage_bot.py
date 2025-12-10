# garage_bot.py
import os
import asyncio
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message, CallbackQuery,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# 🔐 Конфиг из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

if not BOT_TOKEN or not GROUP_CHAT_ID:
    raise ValueError("❌ Укажите BOT_TOKEN и GROUP_CHAT_ID в переменных окружения!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# Состояния FSM
class FSM(StatesGroup):
    choosing_service = State()
    recording_hours = State()
    recording_date = State()
    recording_time = State()
    genre = State()
    waiting_for_mp3 = State()

# Кнопки услуг
SERVICES_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔹 Запись — от 500₽/час")],
        [KeyboardButton(text="🔹 Сведение — от 1 500₽")],
        [KeyboardButton(text="🔹 Аранжировка — от 1 500₽")],
        [KeyboardButton(text="🔹 Трек «под ключ» — от 5 000₽")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

def extract_service(text: str) -> str:
    if "Запись" in text: return "Запись"
    if "Сведение" in text: return "Сведение"
    if "Аранжировка" in text: return "Аранжировка"
    if "под ключ" in text: return "Трек «под ключ»"
    return text

# === /start ===
@router.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject, state: FSMContext):
    # Сбрасываем состояние
    await state.clear()
    await message.answer(
        "👋 Привет! Это студия звукозаписи *«ГАРАЖ»*!\n\n"
        "Какая услуга вас интересует?",
        reply_markup=SERVICES_KEYBOARD,
        parse_mode="Markdown"
    )
    await state.set_state(FSM.choosing_service)

# === Выбор услуги ===
@router.message(FSM.choosing_service)
async def service_chosen(message: Message, state: FSMContext):
    service = extract_service(message.text)
    if service not in ["Запись", "Сведение", "Аранжировка", "Трек «под ключ»"]:
        # Некорректный ввод → предложим начать заново
        await fallback_handler(message, state)
        return

    await state.update_data(service=service)

    if service == "Сведение":
        await message.answer("Пожалуйста, пришлите MP3-файл трека для сведения.", reply_markup=ReplyKeyboardRemove())
        await state.set_state(FSM.waiting_for_mp3)

    elif service == "Аранжировка":
        await message.answer("Какой жанр аранжировки вам нужен?", reply_markup=ReplyKeyboardRemove())
        await state.set_state(FSM.genre)

    elif service == "Запись":
        await message.answer("Сколько часов вы хотите взять?", reply_markup=ReplyKeyboardRemove())
        await state.set_state(FSM.recording_hours)

    elif service == "Трек «под ключ»":
        await message.answer("В каком жанре вы хотите записать трек?", reply_markup=ReplyKeyboardRemove())
        await state.set_state(FSM.genre)

# === Сведение: MP3 ===
@router.message(FSM.waiting_for_mp3, F.audio | F.document)
async def mp3_received(message: Message, state: FSMContext):
    user = message.from_user
    profile_link = f"@{user.username}" if user.username else f"tg://user?id={user.id}"

    text = f"Сведение\n{profile_link}\nзапись"
    await bot.send_message(GROUP_CHAT_ID, text)

    if message.audio:
        await bot.send_audio(GROUP_CHAT_ID, message.audio.file_id)
    elif message.document and message.document.mime_type == "audio/mpeg":
        await bot.send_document(GROUP_CHAT_ID, message.document.file_id)
    else:
        await bot.send_message(GROUP_CHAT_ID, "⚠️ Получен файл, но не MP3 — проверьте.")

    await message.answer("✅ Ваша заявка отправлена звукорежиссёрам!")
    await state.clear()

@router.message(FSM.waiting_for_mp3)
async def not_mp3(message: Message):
    await message.answer("Пожалуйста, пришлите именно MP3-файл (аудиофайл или документ).")

# === Аранжировка / Под ключ: жанр ===
@router.message(FSM.genre)
async def genre_received(message: Message, state: FSMContext):
    data = await state.get_data()
    service = data["service"]
    genre = message.text

    user = message.from_user
    profile_link = f"@{user.username}" if user.username else f"tg://user?id={user.id}"

    text = f"{service}\n{profile_link}\n{genre}"
    await bot.send_message(GROUP_CHAT_ID, text)
    await message.answer("✅ Ваша заявка отправлена звукорежиссёрам!")
    await state.clear()

# === Запись: часы → дата → время ===
@router.message(FSM.recording_hours)
async def hours_received(message: Message, state: FSMContext):
    try:
        hours = int(message.text)
        if hours <= 0: raise ValueError
        await state.update_data(hours=hours)
        await message.answer("В какой день вы хотите записаться? (например: 12.12.2025)")
        await state.set_state(FSM.recording_date)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное количество часов (целое число > 0).")

@router.message(FSM.recording_date)
async def date_received(message: Message, state: FSMContext):
    await state.update_data(date=message.text)
    await message.answer("В какой промежуток времени? (например: 15:00–18:00)")
    await state.set_state(FSM.recording_time)

@router.message(FSM.recording_time)
async def time_received(message: Message, state: FSMContext):
    data = await state.get_data()
    hours = data["hours"]
    date = data["date"]
    time_range = message.text

    user = message.from_user
    profile_link = f"@{user.username}" if user.username else f"tg://user?id={user.id}"

    text = f"Запись\n{hours} ч, {date}, {time_range}\n{profile_link}"
    await bot.send_message(GROUP_CHAT_ID, text)
    await message.answer("✅ Ваша заявка отправлена звукорежиссёрам!")
    await state.clear()

# === Fallback: любое сообщение вне FSM → кнопка «Начать» ===
@router.message()
async def fallback_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Выбрать услугу", callback_data="start_bot")]
        ])
        await message.answer(
            "🎬 Добро пожаловать в студию *«ГАРАЖ»*!\n\n"
            "Нажмите кнопку ниже, чтобы начать — и мы поможем записать ваш трек!",
            reply_markup=kb,
            parse_mode="Markdown"
        )
    else:
        # Если в процессе — не мешаем (можно добавить «Отмена» позже)
        pass

# === Кнопка «Начать» → эмуляция /start ===
@router.callback_query(F.data == "start_bot")
async def start_bot(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await cmd_start(callback.message, None, state)

# === Запуск ===
async def main():
    print("✅ Бот студии «ГАРАЖ» запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
