#!/usr/bin/env bash
#
# backup.sh — nightly backup for GNU Health HIS.
#
# REVISED after hands-on testing in deploy/dev/: `ghcontrol` turned out to be
# a curses TUI (full-screen terminal menu), not a scriptable CLI — there is
# no `ghcontrol backup --backdir ... --database ...` command; that was a
# wrong assumption from secondary docs, caught by actually installing and
# inspecting gnuhealth-control's source. Its own "backup" menu option does
# nothing more than:
#     pg_dump --dbname <dbname> --file <path>.sql
# (confirmed by reading gnuhealth_control/ghcontrol.py directly). This
# script does the same thing directly — a plain pg_dump — rather than
# fighting a TUI that was never designed to be driven unattended, and adds
# a custom-format (-Fc) compressed dump plus the attachment directory,
# bundled into one archive.
#
# Produces: gnuhealth-<database>-<timestamp>.tar.gz containing:
#   - db.dump      (pg_dump custom format — restore with pg_restore)
#   - attach.tar   (GNU Health's file attachment directory, if configured)
#
# Steps:
#   1. pg_dump -Fc  -> compressed custom-format database dump
#   2. tar the attach directory (file attachments aren't in the DB dump)
#   3. bundle both into BACKUP_DIR/gnuhealth-<db>-<timestamp>.tar.gz
#   4. rclone sync  -> ships BACKUP_DIR to the offsite Backblaze B2 bucket
#   5. backup_retention.py -> deletes local copies outside the retention policy
#
# Run via cron as the `gnuhealth` user, e.g. nightly at 02:00:
#   0 2 * * * /opt/gnuhealth/scripts/backup.sh >> /var/log/gnuhealth-backup.log 2>&1
#
# Required environment (set in /opt/gnuhealth/scripts/backup.env, sourced below):
#   GNUHEALTH_DATABASE   - database name, e.g. ghprod
#   BACKUP_DIR           - local staging directory for finished backup archives
#   RCLONE_REMOTE        - rclone remote:bucket path, e.g. b2backup:hospital-backups
# Optional:
#   PGHOST, PGUSER        - default to localhost / current user, as with any psql tool
#   ATTACH_DIR             - GNU Health's attachment storage dir (trytond.conf [database] path=).
#                             Skipped if unset or missing.

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
ATTACH_DIR="${ATTACH_DIR:-}"

mkdir -p "${BACKUP_DIR}"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE_NAME="gnuhealth-${GNUHEALTH_DATABASE}-${TIMESTAMP}.tar.gz"
STAGING_DIR="$(mktemp -d)"
trap 'rm -rf "${STAGING_DIR}"' EXIT

echo "[$(date -Iseconds)] Starting backup of database '${GNUHEALTH_DATABASE}'"

# 1. Database dump (custom format: compressed, restorable with pg_restore,
#    supports selective/parallel restore — more flexible than the plain
#    .sql GNU Health's own backup menu produces).
echo "[$(date -Iseconds)] Running pg_dump"
pg_dump --format=custom --dbname "${GNUHEALTH_DATABASE}" --file "${STAGING_DIR}/db.dump"

# 2. File attachments (not covered by the DB dump).
if [[ -n "${ATTACH_DIR}" && -d "${ATTACH_DIR}" ]]; then
  echo "[$(date -Iseconds)] Archiving attachment directory ${ATTACH_DIR}"
  tar -cf "${STAGING_DIR}/attach.tar" -C "${ATTACH_DIR}" .
else
  echo "[$(date -Iseconds)] No ATTACH_DIR configured or not found — skipping attachments"
fi

# 3. Bundle into the final archive.
tar -czf "${BACKUP_DIR}/${ARCHIVE_NAME}" -C "${STAGING_DIR}" .
echo "[$(date -Iseconds)] Wrote ${BACKUP_DIR}/${ARCHIVE_NAME}"

# 4. Ship offsite. Verify the remote is reachable first so a misconfigured
#    remote fails loudly instead of silently skipping the real sync.
echo "[$(date -Iseconds)] Verifying rclone remote is reachable"
rclone lsd "${RCLONE_REMOTE%%:*}:" >/dev/null

echo "[$(date -Iseconds)] Syncing ${BACKUP_DIR} -> ${RCLONE_REMOTE}"
rclone sync "${BACKUP_DIR}" "${RCLONE_REMOTE}" --transfers 4 --checkers 4

# 5. Apply local retention policy (offsite copies are governed separately by
#    B2 bucket lifecycle rules — see deploy/README.md).
echo "[$(date -Iseconds)] Applying local retention policy"
python3 "${SCRIPT_DIR}/backup_retention.py" "${BACKUP_DIR}" --apply

echo "[$(date -Iseconds)] Backup complete"
