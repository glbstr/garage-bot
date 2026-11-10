"""Расчёт свободного времени для записи. Чистые функции — их легко проверять тестами."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

from config import Schedule
from storage import Booking


def last_bookable_day(today: date, schedule: Schedule) -> date:
    return today + timedelta(days=schedule.booking_days_ahead)


def free_starts(
    day: date, hours: int, bookings: Iterable[Booking], schedule: Schedule, now: datetime
) -> list[int]:
    """Часы начала, с которых можно занять студию на `hours` часов подряд в день `day`."""
    today = now.date()
    if day < today or day > last_bookable_day(today, schedule):
        return []
    if day.isoweekday() in schedule.days_off:
        return []
    busy = [(b.start_hour, b.end_hour) for b in bookings if b.booking_date == day]
    earliest = schedule.open_hour
    if day == today:
        earliest = max(earliest, now.hour + 1)  # текущий час уже идёт
    result = []
    for start in range(earliest, schedule.close_hour - hours + 1):
        end = start + hours
        if all(end <= b_start or start >= b_end for b_start, b_end in busy):
            result.append(start)
    return result


def available_days(
    first: date, last: date, hours: int, bookings: list[Booking], schedule: Schedule, now: datetime
) -> set[date]:
    days = set()
    d = first
    while d <= last:
        if free_starts(d, hours, bookings, schedule, now):
            days.add(d)
        d += timedelta(days=1)
    return days
