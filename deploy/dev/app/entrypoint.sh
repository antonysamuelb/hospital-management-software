#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${GNUHEALTH_DATABASE:-gnuhealth_test}"
ADMIN_EMAIL="${GNUHEALTH_ADMIN_EMAIL:-admin@example.test}"
ADMIN_PASSWORD="${GNUHEALTH_ADMIN_PASSWORD:-change_me_dev_only}"
PGHOST="${PGHOST:-db}"
PGUSER="${PGUSER:-gnuhealth}"
export PGPASSWORD="${PGPASSWORD:-gnuhealth_dev_only}"

echo "Waiting for PostgreSQL at ${PGHOST}..."
for i in $(seq 1 30); do
  if pg_isready -h "${PGHOST}" -U "${PGUSER}" >/dev/null 2>&1; then
    echo "PostgreSQL is ready."
    break
  fi
  sleep 2
done

DB_EXISTS=$(psql -h "${PGHOST}" -U "${PGUSER}" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'")
if [[ "${DB_EXISTS}" != "1" ]]; then
  echo "Creating database ${DB_NAME}..."
  createdb -h "${PGHOST}" -U "${PGUSER}" "${DB_NAME}"
fi

SCHEMA_INITIALIZED=$(psql -h "${PGHOST}" -U "${PGUSER}" -d "${DB_NAME}" -tAc \
  "SELECT 1 FROM information_schema.tables WHERE table_name='ir_module'" || echo "")

if [[ "${SCHEMA_INITIALIZED}" != "1" ]]; then
  echo "Initializing GNU Health schema + activating 'health' and 'health_inpatient' modules..."
  printf '%s\n%s\n' "${ADMIN_PASSWORD}" "${ADMIN_PASSWORD}" | trytond-admin \
    -c /opt/gnuhealth/trytond.conf \
    -d "${DB_NAME}" \
    -u health health_inpatient \
    --activate-dependencies \
    --email "${ADMIN_EMAIL}" \
    -p
else
  echo "Schema already initialized, skipping trytond-admin."
fi

echo "Starting trytond server on 0.0.0.0:8000..."
exec trytond -c /opt/gnuhealth/trytond.conf -d "${DB_NAME}"
