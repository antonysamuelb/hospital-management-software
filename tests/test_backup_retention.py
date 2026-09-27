import datetime
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

from backup_retention import Backup, select_backups_to_delete  # noqa: E402


NOW = datetime.datetime(2026, 9, 27, 12, 0, 0)


def name(db: str, dt: datetime.datetime) -> str:
    return f"gnuhealth-{db}-{dt.strftime('%Y%m%d-%H%M%S')}.tar.gz"


def test_parses_well_formed_filename():
    b = Backup.from_filename("gnuhealth-ghprod-20260115-030000.tar.gz")
    assert b.timestamp == datetime.datetime(2026, 1, 15, 3, 0, 0)


def test_rejects_malformed_filename():
    import pytest

    with pytest.raises(ValueError):
        Backup.from_filename("not-a-backup.txt")


def test_recent_backups_all_kept():
    files = [name("gh", NOW - datetime.timedelta(days=d)) for d in range(0, 30)]
    assert select_backups_to_delete(files, now=NOW) == []


def test_old_backups_beyond_daily_window_collapse_to_one_per_month():
    # Three backups in the same month, 60+ days old -> only the earliest survives.
    month_backups = [
        name("gh", datetime.datetime(2026, 6, 1, 3, 0, 0)),
        name("gh", datetime.datetime(2026, 6, 15, 3, 0, 0)),
        name("gh", datetime.datetime(2026, 6, 30, 3, 0, 0)),
    ]
    to_delete = select_backups_to_delete(month_backups, now=NOW)
    # Earliest (June 1) must be kept; the other two must go.
    assert name("gh", datetime.datetime(2026, 6, 1, 3, 0, 0)) not in to_delete
    assert name("gh", datetime.datetime(2026, 6, 15, 3, 0, 0)) in to_delete
    assert name("gh", datetime.datetime(2026, 6, 30, 3, 0, 0)) in to_delete


def test_backups_older_than_monthly_window_are_all_deleted():
    # 13 distinct months back, older than the 12-month monthly retention.
    ancient = name("gh", datetime.datetime(2020, 1, 10, 3, 0, 0))
    to_delete = select_backups_to_delete([ancient], now=NOW)
    assert ancient in to_delete


def test_recent_within_monthly_window_kept_one_per_month():
    # Build one backup per month for the last 6 months, all older than the
    # 30-day daily window, all within the 12-month monthly window.
    files = []
    for i in range(1, 7):
        dt = NOW - datetime.timedelta(days=45 * i)
        files.append(name("gh", dt))
    to_delete = select_backups_to_delete(files, now=NOW)
    # Each month has exactly one backup in this test, so nothing should be
    # deleted (each is "the earliest of its month").
    assert to_delete == []


def test_unparseable_filenames_are_never_deleted():
    files = ["readme.txt", "gnuhealth-gh-20200101-000000.tar.gz.partial"]
    assert select_backups_to_delete(files, now=NOW) == []


def test_multiple_databases_handled_independently_by_filename():
    # Retention keys on the whole filename's month, not the database name,
    # so two DBs in the same month each keep their own earliest backup.
    files = [
        name("ghprod", datetime.datetime(2026, 6, 1, 3, 0, 0)),
        name("ghprod", datetime.datetime(2026, 6, 20, 3, 0, 0)),
        name("ghdemo", datetime.datetime(2026, 6, 2, 3, 0, 0)),
        name("ghdemo", datetime.datetime(2026, 6, 21, 3, 0, 0)),
    ]
    to_delete = select_backups_to_delete(files, now=NOW)
    assert name("ghprod", datetime.datetime(2026, 6, 1, 3, 0, 0)) not in to_delete
    assert name("ghdemo", datetime.datetime(2026, 6, 2, 3, 0, 0)) not in to_delete
    assert len(to_delete) == 2
