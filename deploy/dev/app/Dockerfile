# Local test-harness image for GNU Health HIS.
#
# NOT the production artifact — see deploy/dev/README.md. This exists to
# prove the real components (Tryton 7.0, the GNU Health modules, PostgreSQL)
# work together, with versions confirmed by actually installing them
# (see commit history), not assumed from docs.

# Sao (Tryton's web client) build stage. Confirmed by actually installing it:
# `npm install tryton-sao@7.0.58` (pinned to match trytond 7.0.57 — npm's
# "series-7.0" dist-tag) produces a ready-to-serve index.html + dist/*.js/css
# directly, no grunt build step needed despite what older docs suggest.
FROM node:20-slim AS sao
RUN apt-get update \
    && apt-get install -y --no-install-recommends git python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /sao
RUN npm install tryton-sao@7.0.58 --production --legacy-peer-deps

FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq-dev \
        build-essential \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Confirmed by actual install: pulls trytond 7.0.57 + 67 health_* modules.
RUN pip install --no-cache-dir gnuhealth-all-modules gunicorn

WORKDIR /opt/gnuhealth
COPY --from=sao /sao/node_modules/tryton-sao /opt/gnuhealth/sao
COPY trytond.conf /opt/gnuhealth/trytond.conf
COPY entrypoint.sh /opt/gnuhealth/entrypoint.sh
RUN chmod +x /opt/gnuhealth/entrypoint.sh \
    && mkdir -p /opt/gnuhealth/attach /opt/gnuhealth/backup

EXPOSE 8000
ENTRYPOINT ["/opt/gnuhealth/entrypoint.sh"]
