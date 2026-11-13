import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "simple_ui"))

from app import summarize_visits  # noqa: E402


def dt(day):
    return datetime.datetime(2026, 11, day, 9, 0, 0)


def test_empty_rows_gives_empty_summary():
    assert summarize_visits([]) == {}


def test_single_visit_counts_as_one_with_matching_first_and_last():
    rows = [{"patient": 1, "evaluation_start": dt(10)}]
    summary = summarize_visits(rows)
    assert summary[1] == {"count": 1, "first": dt(10), "last": dt(10)}


def test_multiple_visits_for_one_patient_tracks_count_and_date_range():
    rows = [
        {"patient": 1, "evaluation_start": dt(10)},
        {"patient": 1, "evaluation_start": dt(1)},
        {"patient": 1, "evaluation_start": dt(20)},
    ]
    summary = summarize_visits(rows)
    assert summary[1]["count"] == 3
    assert summary[1]["first"] == dt(1)
    assert summary[1]["last"] == dt(20)


def test_rows_are_not_necessarily_in_date_order():
    # The real search_read result isn't guaranteed sorted -- summarize_visits
    # must find min/max itself, not assume the first/last row in the list
    # are the earliest/latest dates.
    rows = [
        {"patient": 1, "evaluation_start": dt(15)},
        {"patient": 1, "evaluation_start": dt(5)},
    ]
    summary = summarize_visits(rows)
    assert summary[1]["first"] == dt(5)
    assert summary[1]["last"] == dt(15)


def test_different_patients_are_kept_separate():
    rows = [
        {"patient": 1, "evaluation_start": dt(10)},
        {"patient": 2, "evaluation_start": dt(5)},
        {"patient": 2, "evaluation_start": dt(12)},
    ]
    summary = summarize_visits(rows)
    assert summary[1] == {"count": 1, "first": dt(10), "last": dt(10)}
    assert summary[2]["count"] == 2
    assert summary[2]["first"] == dt(5)
    assert summary[2]["last"] == dt(12)


def test_patient_with_no_visits_is_simply_absent_from_the_summary():
    # app.py's search() route handles this by defaulting visit_count to 0
    # when a patient id isn't a key in the returned dict at all.
    summary = summarize_visits([{"patient": 1, "evaluation_start": dt(1)}])
    assert 2 not in summary
