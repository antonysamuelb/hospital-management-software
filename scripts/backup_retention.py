"""Pure retention-selection logic for GNU Health backups.

Kept separate from backup.sh (which does the actual pg_dump/upload work via
`ghcontrol backup` and rclone) specifically so this policy — "which backups
do we keep, which do we delete" — can be unit tested without a database,
a VM, or any network access. Getting this wrong either wastes storage
forever or silently deletes the hospital's only copy of a given day's
records, so it's worth testing in isolation.

Policy (matches deploy/README.md): keep every daily backup for 30 days,
plus the first backup of each of the last 12 months, for backups older
than that.
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass

# Expected filename produced by scripts/backup.sh:
#   gnuhealth-<database>-YYYYmmdd-HHMMSS.tar.gz
FILENAME_RE = re.compile(
    r"^gnuhealth-(?P<database>[A-Za-z0-9_]+)-(?P<timestamp>\d{8}-\d{6})\.tar\.gz$"
)


@dataclass(frozen=True)
class Backup:
    filename: str
    database: str
    timestamp: datetime.datetime

    @classmethod
    def from_filename(cls, filename: str) -> "Backup":
        match = FILENAME_RE.match(filename)
        if not match:
            raise ValueError(f"Filename does not match expected backup pattern: {filename!r}")
        ts = datetime.datetime.strptime(match.group("timestamp"), "%Y%m%d-%H%M%S")
        return cls(filename=filename, database=match.group("database"), timestamp=ts)


def select_backups_to_delete(
    filenames: list[str],
    now: datetime.datetime,
    daily_retention_days: int = 30,
    monthly_retention_months: int = 12,
) -> list[str]:
    """Return the filenames that are safe to delete under the retention policy.

    Rules (applied independently per database, so a demo/test DB's backups
    can never count against, or get deleted alongside, the production DB's):
      - Any backup younger than `daily_retention_days` is always kept.
      - For backups older than that: keep the earliest backup of each
        calendar month, for the last `monthly_retention_months` distinct
        months seen for that database.
      - Anything older than the monthly retention window, or any duplicate
        within a month beyond the one kept, is returned for deletion.

    Unparseable filenames are ignored (left alone, i.e. never returned for
    deletion) rather than raising — a backup script should never delete
    something it doesn't confidently recognize.
    """
    backups: list[Backup] = []
    for filename in filenames:
        try:
            backups.append(Backup.from_filename(filename))
        except ValueError:
            continue  # not a backup file we recognize — leave it alone

    daily_cutoff = now - datetime.timedelta(days=daily_retention_days)
    older = [b for b in backups if b.timestamp < daily_cutoff]
    # (backups >= daily_cutoff need no grouping — they're simply all kept)

    # Group "older" backups by (database, year, month), independently per DB.
    by_db_month: dict[tuple[str, int, int], list[Backup]] = {}
    for b in older:
        key = (b.database, b.timestamp.year, b.timestamp.month)
        by_db_month.setdefault(key, []).append(b)

    # The last `monthly_retention_months` calendar months counting back from
    # `now` (inclusive) — computed from the clock, NOT from which months
    # happen to be present in the data. A single ancient backup must not
    # survive just because it's the only (and therefore "most recent") month
    # seen for its database.
    anchor_month_index = now.year * 12 + (now.month - 1)
    kept_month_keys = {
        divmod(anchor_month_index - i, 12)  # -> (year, month0) where month0 is 0-based
        for i in range(monthly_retention_months)
    }
    kept_months = {(year, month0 + 1) for year, month0 in kept_month_keys}

    databases = {key[0] for key in by_db_month}
    months_to_keep: set[tuple[str, int, int]] = {
        (db, year, month) for db in databases for (year, month) in kept_months
    }

    to_delete: list[str] = []
    for key, group in by_db_month.items():
        group.sort(key=lambda b: b.timestamp)
        if key in months_to_keep:
            # Keep the earliest backup of the month for this database, delete the rest.
            to_delete.extend(b.filename for b in group[1:])
        else:
            # Entire month is past the retention window for this database.
            to_delete.extend(b.filename for b in group)

    return sorted(to_delete)


def _main() -> int:
    import argparse
    import pathlib
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=pathlib.Path, help="Directory containing backup files")
    parser.add_argument("--daily-days", type=int, default=30)
    parser.add_argument("--monthly-months", type=int, default=12)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete the selected files. Without this flag, only prints what would be deleted.",
    )
    args = parser.parse_args()

    if not args.directory.is_dir():
        print(f"Not a directory: {args.directory}", file=sys.stderr)
        return 2

    filenames = [p.name for p in args.directory.iterdir() if p.is_file()]
    to_delete = select_backups_to_delete(
        filenames,
        now=datetime.datetime.now(),
        daily_retention_days=args.daily_days,
        monthly_retention_months=args.monthly_months,
    )

    if not to_delete:
        print("Nothing to delete.")
        return 0

    for name in to_delete:
        if args.apply:
            (args.directory / name).unlink()
            print(f"deleted: {name}")
        else:
            print(f"would delete (pass --apply to actually delete): {name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
