# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.scheduling_slots import Busy, Window, generate_slots, week_index, windows_problem

NY = ZoneInfo("America/New_York")
DAY = date(2030, 1, 7)                      # a Monday, winter (UTC-5)
LONG_AGO = datetime(2020, 1, 1, tzinfo=timezone.utc)
NINE_TO_TWELVE = [Window(time(9), time(12))]


def local(day, hh, mm=0):
    return datetime.combine(day, time(hh, mm), tzinfo=NY)


def starts(slots):
    return [s.astimezone(NY).strftime("%H:%M") for s in slots]


def run(windows=NINE_TO_TWELVE, duration=30, buffer=0, busy=(), now=LONG_AGO, day=DAY):
    return generate_slots(day, windows, duration, buffer, list(busy), NY, now)


def test_back_to_back_slots():
    assert starts(run()) == ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30"]


def test_buffer_widens_the_step():
    assert starts(run(buffer=15)) == ["09:00", "09:45", "10:30", "11:15"]


def test_last_slot_must_fit_inside_the_window():
    assert starts(run(duration=50)) == ["09:00", "09:50", "10:40"]   # 11:30 would end at 12:20
    assert starts(run(duration=45))[-1] == "11:15"                   # ending exactly at 12:00 is fine
    assert run(windows=[Window(time(9), time(9, 20))]) == []


def test_slots_are_returned_in_utc():
    assert run()[0] == datetime(2030, 1, 7, 14, 0, tzinfo=timezone.utc)


def test_booking_blocks_its_slot_and_buffer_on_both_sides():
    busy = [Busy(local(DAY, 10), local(DAY, 10, 30))]
    assert starts(run(busy=busy, buffer=15)) == ["09:00", "11:15"]
    assert starts(run(busy=busy)) == ["09:00", "09:30", "10:30", "11:00", "11:30"]


def test_slots_already_started_are_dropped():
    assert starts(run(now=local(DAY, 10))) == ["10:30", "11:00", "11:30"]


def test_several_windows_on_one_day():
    both = [Window(time(13), time(14)), Window(time(9), time(10))]
    assert starts(run(windows=both)) == ["09:00", "09:30", "13:00", "13:30"]


def test_no_windows_means_no_slots():
    assert run(windows=[]) == []


def test_grid_survives_the_spring_forward_day():
    day = date(2030, 3, 10)                 # clocks jump 02:00 -> 03:00
    out = run(windows=[Window(time(9), time(10))], day=day)
    assert starts(out) == ["09:00", "09:30"]
    assert out[0] == datetime(2030, 3, 10, 13, 0, tzinfo=timezone.utc)   # UTC-4 by then


@pytest.mark.parametrize("duration,buffer", [(0, 0), (-5, 0), (30, -1)])
def test_bad_lengths_are_refused(duration, buffer):
    with pytest.raises(ValueError):
        run(duration=duration, buffer=buffer)


def test_windows_problem():
    ok = [(0, Window(time(9), time(12))), (0, Window(time(13), time(17)))]
    assert windows_problem(ok) is None
    assert windows_problem([(7, Window(time(9), time(12)))])
    assert windows_problem([(0, Window(time(12), time(9)))])
    assert windows_problem([(0, Window(time(9), time(12))), (0, Window(time(11), time(13)))])
    assert windows_problem([(0, Window(time(9), time(12))), (0, Window(time(12), time(13)))]) is None

START = date(2030, 1, 7)   # a Monday: the first day of Week 1

@pytest.mark.parametrize("day,expected", [
    (date(2030, 1, 7), 0), (date(2030, 1, 13), 0),     # Week 1: Monday through Sunday
    (date(2030, 1, 14), 1), (date(2030, 1, 20), 1),    # Week 2
    (date(2030, 1, 21), 0), (date(2030, 1, 28), 1),    # and back again
    (date(2029, 12, 31), 1), (date(2029, 12, 24), 0),  # before the start keeps alternating
    (date(2031, 1, 6), 0),                              # across a year boundary (52 weeks later)
])

def test_week_index_alternates(day, expected):
    assert week_index(day, START, 2) == expected

def test_week_index_counts_from_the_monday_of_the_start_date():
    thursday = date(2030, 1, 10)
    assert week_index(date(2030, 1, 7), thursday, 2) == 0
    assert week_index(date(2030, 1, 14), thursday, 2) == 1

def test_week_index_is_always_zero_for_a_weekly_schedule():
    assert week_index(date(2030, 1, 14), START, 1) == 0
    assert week_index(date(2030, 1, 14), None, 2) == 0