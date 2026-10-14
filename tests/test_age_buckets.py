import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "simple_ui"))

from app import age_bucket_to_dob_range  # noqa: E402

TODAY = datetime.date(2026, 10, 14)


def test_youngest_bucket_upper_bound_is_today():
    earliest, latest = age_bucket_to_dob_range(0, 5, TODAY)
    assert latest == TODAY


def test_bucket_boundaries_are_inclusive_of_edge_ages():
    # Someone who turns 19 today should fall in the 19-40 bucket.
    earliest, latest = age_bucket_to_dob_range(19, 40, TODAY)
    dob_turning_19_today = TODAY.replace(year=TODAY.year - 19)
    assert earliest <= dob_turning_19_today <= latest

    # Someone who is about to turn 41 tomorrow (so still 40 today)
    # should also fall in the 19-40 bucket.
    dob_turning_41_tomorrow = TODAY.replace(year=TODAY.year - 41) + datetime.timedelta(days=1)
    assert earliest <= dob_turning_41_tomorrow <= latest

    # Someone who turned 41 today should NOT fall in the 19-40 bucket.
    dob_turning_41_today = TODAY.replace(year=TODAY.year - 41)
    assert not (earliest <= dob_turning_41_today <= latest)


def test_open_ended_bucket_has_no_effective_lower_bound():
    earliest, latest = age_bucket_to_dob_range(61, None, TODAY)
    assert earliest.year <= 1900
    assert latest == TODAY.replace(year=TODAY.year - 61)


def test_leap_day_birthday_does_not_crash():
    # Feb 29 birthdays are the classic date-math landmine.
    leap_today = datetime.date(2024, 2, 29)
    earliest, latest = age_bucket_to_dob_range(0, 5, leap_today)
    assert earliest < latest


def test_adjacent_buckets_dont_overlap_or_leave_a_gap():
    # Someone who turns 6 today must fall in "6-12", not "0-5" — the
    # buckets share an edge with no overlap and no gap.
    dob_turning_6_today = TODAY.replace(year=TODAY.year - 6)

    earliest_0_5, latest_0_5 = age_bucket_to_dob_range(0, 5, TODAY)
    assert not (earliest_0_5 <= dob_turning_6_today <= latest_0_5)

    earliest_6_12, latest_6_12 = age_bucket_to_dob_range(6, 12, TODAY)
    assert earliest_6_12 <= dob_turning_6_today <= latest_6_12
