# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

"""Pure slot maths for booking. No Flask, no database.

Availability windows are local wall-clock times (LIBRARY_TIMEZONE); every datetime that
comes out is UTC. Weekdays follow Python: Monday=0 ... Sunday=6.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc


@dataclass(frozen=True)
class Window:
    start: time
    end: time


@dataclass(frozen=True)
class Busy:
    start: datetime
    end: datetime


def as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _local_to_utc(day: date, t: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, t, tzinfo=tz).astimezone(UTC)


def generate_slots(
    day: date,
    windows: list[Window],
    duration_min: int,
    buffer_min: int,
    busy: list[Busy],
    tz: ZoneInfo,
    now: datetime,
) -> list[datetime]:
    """Start (UTC) of every bookable slot on local date `day`.

    Slots sit back to back in each window, one every duration + buffer minutes. A slot is
    dropped if it doesn't fit the window, has already started, or is closer than `buffer_min`
    to an existing booking on either side.
    """
    if duration_min <= 0 or buffer_min < 0:
        raise ValueError("duration must be positive and buffer cannot be negative")
    now = as_utc(now)
    duration, buffer = timedelta(minutes=duration_min), timedelta(minutes=buffer_min)
    step = duration + buffer
    slots: list[datetime] = []
    for w in sorted(windows, key=lambda w: w.start):
        cursor = _local_to_utc(day, w.start, tz)
        window_end = _local_to_utc(day, w.end, tz)
        while cursor + duration <= window_end:   # step in UTC so DST can't skew the grid
            slot_end = cursor + duration
            clash = any(b.start < slot_end + buffer and cursor < b.end + buffer for b in busy)
            if cursor > now and not clash:
                slots.append(cursor)
            cursor += step
    return slots

def week_index(day: date, cycle_start: date | None, cycle_weeks: int) -> int:
    """Which week of the repeating cycle `day` falls in: 0 for Week 1, 1 for Week 2.

    Weeks run Monday to Sunday and are counted from the Monday of `cycle_start`. Dates before
    the start keep alternating backwards, so the pattern never has a gap.
    """
    if cycle_weeks <= 1 or cycle_start is None:
        return 0
    monday = lambda d: d - timedelta(days=d.weekday())
    return ((monday(day) - monday(cycle_start)).days // 7) % cycle_weeks


def windows_problem(windows: list[tuple[int, Window]]) -> str | None:
    """Why a (weekday, Window) list can't be used, or None."""
    by_day: dict[int, list[Window]] = {}
    for weekday, w in windows:
        if not 0 <= weekday <= 6:
            return "Weekday must be 0 to 6."
        if w.start >= w.end:
            return "Each block must end after it starts."
        by_day.setdefault(weekday, []).append(w)
    for blocks in by_day.values():
        blocks.sort(key=lambda w: w.start)
        if any(b.start < a.end for a, b in zip(blocks, blocks[1:])):
            return "Blocks on the same day can't overlap."
    return None