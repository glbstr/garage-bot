"""Инлайн-клавиатуры: услуги, часы, календарь, время, навигация."""
from __future__ import annotations

import calendar
from datetime import date

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import Service

MONTHS = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


class ServiceCb(CallbackData, prefix="svc"):
    id: str


class NavCb(CallbackData, prefix="nav"):
    action: str  # back | cancel


class HoursCb(CallbackData, prefix="hrs"):
    n: int


class CalCb(CallbackData, prefix="cal"):
    action: str  # day | month | noop
    y: int
    m: int
    d: int = 0


class SlotCb(CallbackData, prefix="slot"):
    h: int


class ConfirmCb(CallbackData, prefix="ok"):
    pass


def _btn(text: str, cb: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb.pack())


def nav_row(back: bool = True) -> list[InlineKeyboardButton]:
    row = [_btn("✖️ Отмена", NavCb(action="cancel"))]
    if back:
        row.insert(0, _btn("⬅️ Назад", NavCb(action="back")))
    return row


def nav_kb(back: bool = True) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[nav_row(back)])


def services_kb(services: tuple[Service, ...]) -> InlineKeyboardMarkup:
    rows = [[_btn(s.button, ServiceCb(id=s.id))] for s in services]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def hours_kb(max_hours: int) -> InlineKeyboardMarkup:
    buttons = [_btn(str(n), HoursCb(n=n)) for n in range(1, max_hours + 1)]
    rows = [buttons[i:i + 4] for i in range(0, len(buttons), 4)]
    rows.append(nav_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def calendar_kb(
    year: int, month: int, available: set[date], min_month: date, max_month: date
) -> InlineKeyboardMarkup:
    """Календарь месяца. Доступные дни — кнопки, недоступные — «·»."""
    noop = CalCb(action="noop", y=year, m=month)
    first = date(year, month, 1)

    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)
    has_prev = first > min_month.replace(day=1)
    has_next = date(next_y, next_m, 1) <= max_month

    rows = [[
        _btn("‹", CalCb(action="month", y=prev_y, m=prev_m)) if has_prev else _btn(" ", noop),
        _btn(f"{MONTHS[month]} {year}", noop),
        _btn("›", CalCb(action="month", y=next_y, m=next_m)) if has_next else _btn(" ", noop),
    ], [_btn(w, noop) for w in WEEKDAYS]]

    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(_btn(" ", noop))
            elif date(year, month, day) in available:
                row.append(_btn(str(day), CalCb(action="day", y=year, m=month, d=day)))
            else:
                row.append(_btn("·", noop))
        rows.append(row)
    rows.append(nav_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def slots_kb(starts: list[int], hours: int) -> InlineKeyboardMarkup:
    buttons = [_btn(f"{h:02d}:00–{h + hours:02d}:00", SlotCb(h=h)) for h in starts]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append(nav_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("✅ Отправить заявку", ConfirmCb())],
        nav_row(),
    ])
