"""Tests for the cleaning schedule."""

from datetime import date

from custom_components.cambridge_street_sweeping.schedule import (
    SCHEDULE,
    get_next_cleaning_date,
    side_for_number,
)


def test_side_for_number():
    assert side_for_number(1) == "odd"
    assert side_for_number(118) == "even"


def test_next_date_is_inclusive_of_today():
    assert get_next_cleaning_date("A", "odd", after=date(2026, 6, 3)) == date(2026, 6, 3)
    assert get_next_cleaning_date("A", "odd", after=date(2026, 6, 4)) == date(2026, 7, 1)


def test_side_selects_schedule():
    after = date(2026, 4, 1)
    assert get_next_cleaning_date("A", "odd", after=after) == date(2026, 4, 1)
    assert get_next_cleaning_date("A", "even", after=after) == date(2026, 4, 2)


def test_expired_or_unknown_returns_none():
    assert get_next_cleaning_date("A", "odd", after=date(2026, 12, 3)) is None
    assert get_next_cleaning_date("Z", "odd", after=date(2026, 4, 1)) is None


def test_corrected_dates():
    assert (12, 10) in SCHEDULE[("E", "odd")]
    assert (9, 9) in SCHEDULE[("D", "even")]


def test_schedule_dates_are_valid_and_sorted():
    for key, dates in SCHEDULE.items():
        parsed = [date(2026, m, d) for m, d in dates]
        assert parsed == sorted(parsed), key
