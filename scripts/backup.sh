#!/usr/bin/env bash
#
# backup.sh — nightly backup for GNU Health HIS.
#
# Wraps the OFFICIAL `ghcontrol backup` command (rather than hand-rolling
# pg_dump) so the backup format matches what GNU Health itself expects for
# a restore — see:
#   https://docs.gnuhealth.org/his/techguide/administration/controlcenter.html
#
# Steps:
#   1. ghcontrol backup   -> writes a dated archive into BACKUP_DIR
#   2. rclone sync        -> ships BACKUP_DIR to the offsite Backblaze B2 bucket
#   3. backup_retention.py -> deletes local copies outside the retention policy
#      (the offsite copy's own lifecycle is managed by B2 bucket rules, not
#      this script — see deploy/README.md)
#
# Run via cron as the `gnuhealth` user, e.g. nightly at 02:00:
#   0 2 * * * /opt/gnuhealth/scripts/backup.sh >> /var/log/gnuhealth-backup.log 2>&1
#
# Required environment (set in /opt/gnuhealth/scripts/backup.env, sourced below):
#   GNUHEALTH_DATABASE   - database name, e.g. ghprod
#   BACKUP_DIR           - local staging directory for backup archives
#   RCLONE_REMOTE        - rclone remote:bucket path, e.g. b2backup:hospital-backups

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/backup.env"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
fi

: "${GNUHEALTH_DATABASE:?Set GNUHEALTH_DATABASE in scripts/backup.env}"
: "${BACKUP_DIR:?Set BACKUP_DIR in scripts/backup.env}"
: "${RCLONE_REMOTE:?Set RCLONE_REMOTE in scripts/backup.env}"

mkdir -p "${BACKUP_DIR}"

echo "[$(date -Iseconds)] Starting backup of database '${GNUHEALTH_DATABASE}'"

# 1. Official GNU Health backup (produces a file matching
#    gnuhealth-<database>-<timestamp>.tar.gz in BACKUP_DIR, per
#    backup_retention.py's FILENAME_RE — if ghcontrol's actual naming
#    differs, adjust FILENAME_RE to match; verify on first real run).
ghcontrol backup --backdir "${BACKUP_DIR}" --database "${GNUHEALTH_DATABASE}"

# 2. Ship offsite. --dry-run first so a misconfigured remote fails loudly
#    instead of silently skipping the real sync.
echo "[$(date -Iseconds)] Verifying rclone remote is reachable"
rclone lsd "${RCLONE_REMOTE%%:*}:" >/dev/null

echo "[$(date -Iseconds)] Syncing ${BACKUP_DIR} -> ${RCLONE_REMOTE}"
rclone sync "${BACKUP_DIR}" "${RCLONE_REMOTE}" --transfers 4 --checkers 4

# 3. Apply local retention policy (offsite copies are governed separately by
#    B2 bucket lifecycle rules — see deploy/README.md).
echo "[$(date -Iseconds)] Applying local retention policy"
python3 "${SCRIPT_DIR}/backup_retention.py" "${BACKUP_DIR}" --apply

echo "[$(date -Iseconds)] Backup complete"
