# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

INTERVALS = ("month", "quarter", "year")
MAX_RANGE_DAYS = 3660   # about ten years
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_YMD = re.compile(r"\d{4}-\d{2}-\d{2}")


class BadParam(ValueError):
    def __init__(self, field: str):
        super().__init__(field)
        self.field = field


def _ymd(text, field: str) -> date:
    if not isinstance(text, str) or not _YMD.fullmatch(text):
        raise BadParam(field)
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise BadParam(field) from None


def parse_range(args) -> tuple[date, date]:
    start = _ymd(args.get("from"), "from")
    end = _ymd(args.get("to"), "to")
    if start > end or (end - start).days >= MAX_RANGE_DAYS:
        raise BadParam("range")
    return start, end


def parse_interval(args) -> str:
    value = args.get("interval", "month")
    if value not in INTERVALS:
        raise BadParam("interval")
    return value


def period_start(day: date, interval: str) -> date:
    if interval == "month":
        return day.replace(day=1)
    if interval == "quarter":
        return date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)
    if interval == "year":
        return date(day.year, 1, 1)
    raise ValueError(interval)


def next_period(start: date, interval: str) -> date:
    """The start of the period after the one beginning on `start`."""
    if interval == "year":
        return date(start.year + 1, 1, 1)
    step = 1 if interval == "month" else 3
    month = start.month + step
    return date(start.year + 1, month - 12, 1) if month > 12 else date(start.year, month, 1)


def period_label(start: date, interval: str) -> str:
    if interval == "month":
        return f"{_MONTHS[start.month - 1]} {start.year}"
    if interval == "quarter":
        return f"{start.year} Q{(start.month - 1) // 3 + 1}"
    return str(start.year)


def buckets(start: date, end: date, interval: str) -> list[dict]:
    """Every period that overlaps start..end, including empty ones, so charts have no gaps."""
    out, current = [], period_start(start, interval)
    while current <= end:
        out.append({"start": current.isoformat(), "label": period_label(current, interval)})
        current = next_period(current, interval)
    return out


def calendar_periods(today: date) -> dict[str, tuple[date, date]]:
    """This month, quarter and year as (first day, last day)."""
    out = {}
    for name in INTERVALS:
        first = period_start(today, name)
        out[name] = (first, next_period(first, name) - timedelta(days=1))
    return out


def local_range(start: date, end: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Local midnight at the start, up to (not including) local midnight after the last day."""
    return (
        datetime.combine(start, time.min, tzinfo=tz),
        datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz),
    )


def bucket_index(moment: datetime, tz: ZoneInfo, interval: str, index: dict[str, int]) -> int:
    local_day = moment.astimezone(tz).date()
    return index[period_start(local_day, interval).isoformat()]


def average(total, count):
    return round(total / count, 1) if count else None


def csv_cell(value):
    """Stop a text cell from being run as a formula when the file is opened in a spreadsheet."""
    if value is None:
        return ""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value