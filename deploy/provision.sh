#!/usr/bin/env bash
#
# provision.sh — one-time OS-level setup for a GNU Health HIS server.
#
# Follows the steps documented at:
#   https://docs.gnuhealth.org/his/techguide/installation/vanilla.html
#
# Target: a fresh Ubuntu/Debian VM (Oracle Cloud Always Free ARM, AWS Lightsail,
# or DigitalOcean droplet — all ship Ubuntu images that this matches).
#
# What this script does NOT do (deliberately — these need a human at the console):
#   - Run `ghcontrol` itself to install GNU Health and create the database.
#     That tool is menu-driven/interactive as of GNU Health 5.0, so it is run
#     once, by hand, after this script finishes. See deploy/README.md.
#   - Issue the TLS certificate (needs a real domain pointed at the VM first).
#
# Usage (as a sudo-capable user, NOT as root directly):
#   sudo bash deploy/provision.sh
#
# Idempotent: safe to re-run.

set -euo pipefail

GNUHEALTH_USER="gnuhealth"
GNUHEALTH_HOME="/opt/gnuhealth"
POSTGRES_VERSION="15"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }

if [[ "${EUID}" -ne 0 ]]; then
  echo "This script must be run as root (use: sudo bash deploy/provision.sh)" >&2
  exit 1
fi

log "Updating package index"
apt-get update -y

log "Installing base packages: PostgreSQL ${POSTGRES_VERSION}, Nginx, Python, build deps"
apt-get install -y \
  "postgresql-${POSTGRES_VERSION}" \
  postgresql-client \
  nginx \
  python3 \
  python3-venv \
  python3-pip \
  build-essential \
  libpq-dev \
  certbot \
  python3-certbot-nginx \
  ufw \
  unattended-upgrades \
  fail2ban

log "Creating the ${GNUHEALTH_USER} system user"
if ! id -u "${GNUHEALTH_USER}" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "GNU Health service account" "${GNUHEALTH_USER}"
else
  echo "User ${GNUHEALTH_USER} already exists, skipping"
fi

log "Creating ${GNUHEALTH_HOME}"
mkdir -p "${GNUHEALTH_HOME}"
chown "${GNUHEALTH_USER}:${GNUHEALTH_USER}" "${GNUHEALTH_HOME}"

log "Configuring PostgreSQL peer authentication for the gnuhealth role"
PG_HBA="/etc/postgresql/${POSTGRES_VERSION}/main/pg_hba.conf"
if [[ -f "${PG_HBA}" ]] && ! grep -q "^local\s\+all\s\+${GNUHEALTH_USER}\s\+peer" "${PG_HBA}"; then
  # Insert a peer-auth line for the gnuhealth user ABOVE the default "local all all peer" line
  sed -i "0,/^local\s\+all\s\+all\s\+peer/s//local   all             ${GNUHEALTH_USER}                                peer\nlocal   all             all                                     peer/" "${PG_HBA}"
  systemctl restart postgresql
else
  echo "pg_hba.conf already configured or not found at expected path — verify manually"
fi

log "Creating the PostgreSQL role for gnuhealth (createdb, no superuser)"
su - postgres -c "psql -tc \"SELECT 1 FROM pg_roles WHERE rolname='${GNUHEALTH_USER}'\"" | grep -q 1 || \
  su - postgres -c "createuser --createdb --no-createrole --no-superuser ${GNUHEALTH_USER}"

log "Configuring firewall (ufw): allow SSH, HTTP, HTTPS only"
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

log "Enabling unattended security upgrades"
dpkg-reconfigure -f noninteractive unattended-upgrades || true

log "Enabling fail2ban (protects SSH from brute-force)"
systemctl enable --now fail2ban

cat <<'EOF'

==============================================================================
Provisioning complete. Manual steps remaining (see deploy/README.md):

  1. su - gnuhealth
  2. python3 -m venv tmp_ghvenv && cd tmp_ghvenv && source bin/activate
  3. pip install gnuhealth-control
  4. ghcontrol            # choose "0: Install GNU Health HIS", then
                           # "1: Create a new DB instance"
  5. Point your domain's DNS A record at this server's public IP
  6. sudo certbot --nginx -d your-domain.example   # after copying
                           # deploy/nginx/gnuhealth.conf into place
==============================================================================
EOF
