"""Общие подписи дат и длительности для бота и сайта."""
from __future__ import annotations

from datetime import date

WEEKDAYS_FULL = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]


def fmt_day(d: date) -> str:
    return f"{d:%d.%m.%Y} ({WEEKDAYS_FULL[d.weekday()]})"


def fmt_hours(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} час"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} часа"
    return f"{n} часов"
