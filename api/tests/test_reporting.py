from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app import reporting as rp
from app.config import parse_fiscal_month, parse_timezone

NY = ZoneInfo("America/New_York")


@pytest.mark.parametrize("day,interval,expected", [
    (date(2026, 11, 17), "month", date(2026, 11, 1)),
    (date(2026, 11, 17), "quarter", date(2026, 10, 1)),
    (date(2026, 2, 28), "quarter", date(2026, 1, 1)),
    (date(2026, 5, 1), "quarter", date(2026, 4, 1)),
    (date(2026, 9, 30), "quarter", date(2026, 7, 1)),
    (date(2026, 11, 17), "year", date(2026, 1, 1)),
])
def test_period_start(day, interval, expected):
    assert rp.period_start(day, interval) == expected


@pytest.mark.parametrize("start,interval,expected", [
    (date(2026, 1, 1), "month", date(2026, 2, 1)),
    (date(2026, 12, 1), "month", date(2027, 1, 1)),
    (date(2026, 1, 1), "quarter", date(2026, 4, 1)),
    (date(2026, 10, 1), "quarter", date(2027, 1, 1)),
    (date(2026, 1, 1), "year", date(2027, 1, 1)),
])
def test_next_period(start, interval, expected):
    assert rp.next_period(start, interval) == expected


def test_labels():
    assert rp.period_label(date(2026, 3, 1), "month") == "Mar 2026"
    assert rp.period_label(date(2026, 7, 1), "quarter") == "2026 Q3"
    assert rp.period_label(date(2026, 1, 1), "year") == "2026"


def test_buckets_cover_partial_edges():
    got = rp.buckets(date(2026, 2, 15), date(2026, 4, 10), "month")
    assert [(b["start"], b["label"]) for b in got] == [
        ("2026-02-01", "Feb 2026"), ("2026-03-01", "Mar 2026"), ("2026-04-01", "Apr 2026"),
    ]


def test_buckets_quarters_across_a_year_end():
    got = rp.buckets(date(2025, 11, 15), date(2026, 2, 10), "quarter")
    assert [b["label"] for b in got] == ["2025 Q4", "2026 Q1"]


def test_buckets_for_years_and_a_single_day():
    assert [b["label"] for b in rp.buckets(date(2025, 6, 1), date(2026, 6, 1), "year")] == ["2025", "2026"]
    assert len(rp.buckets(date(2026, 3, 5), date(2026, 3, 5), "month")) == 1


def test_calendar_periods():
    got = rp.calendar_periods(date(2026, 11, 2))
    assert got["month"] == (date(2026, 11, 1), date(2026, 11, 30))
    assert got["quarter"] == (date(2026, 10, 1), date(2026, 12, 31))
    assert got["year"] == (date(2026, 1, 1), date(2026, 12, 31))


def test_calendar_periods_in_a_leap_february():
    assert rp.calendar_periods(date(2028, 2, 10))["month"] == (date(2028, 2, 1), date(2028, 2, 29))


def test_parse_range_accepts_a_good_range():
    assert rp.parse_range({"from": "2026-01-01", "to": "2026-12-31"}) == (date(2026, 1, 1), date(2026, 12, 31))
    assert rp.parse_range({"from": "2016-01-01", "to": "2026-01-01"})


@pytest.mark.parametrize("args,field", [
    ({}, "from"),
    ({"from": "2026-01-01"}, "to"),
    ({"from": "2026-1-1", "to": "2026-12-31"}, "from"),
    ({"from": "20260101", "to": "2026-12-31"}, "from"),
    ({"from": "2026-02-30", "to": "2026-12-31"}, "from"),
    ({"from": "2026-01-01", "to": "garbage"}, "to"),
    ({"from": "2026-12-31", "to": "2026-01-01"}, "range"),
    ({"from": "2000-01-01", "to": "2026-12-31"}, "range"),
])
def test_parse_range_problems(args, field):
    with pytest.raises(rp.BadParam) as exc:
        rp.parse_range(args)
    assert exc.value.field == field


def test_parse_interval():
    assert rp.parse_interval({}) == "month"
    assert rp.parse_interval({"interval": "quarter"}) == "quarter"
    with pytest.raises(rp.BadParam) as exc:
        rp.parse_interval({"interval": "week"})
    assert exc.value.field == "interval"


def test_local_range_follows_daylight_saving_time():
    lo, hi = rp.local_range(date(2026, 3, 1), date(2026, 3, 30), NY)
    assert lo.astimezone(timezone.utc) == datetime(2026, 3, 1, 5, 0, tzinfo=timezone.utc)    # EST
    assert hi.astimezone(timezone.utc) == datetime(2026, 3, 31, 4, 0, tzinfo=timezone.utc)   # EDT


def test_bucket_index_uses_local_time():
    index = {"2026-02-01": 0, "2026-03-01": 1}
    before = datetime(2026, 3, 1, 4, 59, tzinfo=timezone.utc)   # Feb 28, 11:59 pm in New York
    after = datetime(2026, 3, 1, 5, 0, tzinfo=timezone.utc)     # Mar 1, midnight in New York
    assert rp.bucket_index(before, NY, "month", index) == 0
    assert rp.bucket_index(after, NY, "month", index) == 1


def test_average():
    assert rp.average(0, 0) is None
    assert rp.average(75, 2) == 37.5
    assert rp.average(230, 6) == 38.3


@pytest.mark.parametrize("value", ["=1+1", "+1", "-1", "@SUM(A1)", "\tx", "\rx"])
def test_csv_cells_cannot_start_a_formula(value):
    assert rp.csv_cell(value) == "'" + value


def test_csv_cells_otherwise_pass_through():
    assert rp.csv_cell("Lee, Pat") == "Lee, Pat"
    assert rp.csv_cell(5) == 5
    assert rp.csv_cell(37.5) == 37.5
    assert rp.csv_cell(None) == ""


def test_settings_are_checked():
    assert parse_timezone("America/New_York") == "America/New_York"
    for bad in ("Mars/Olympus", "", "../etc/passwd"):
        with pytest.raises(RuntimeError):
            parse_timezone(bad)
    assert parse_fiscal_month("7") == 7
    for bad in ("0", "13", "july", ""):
        with pytest.raises(RuntimeError):
            parse_fiscal_month(bad)