# Local test-harness image for GNU Health HIS.
#
# NOT the production artifact — see deploy/dev/README.md. This exists to
# prove the real components (Tryton 7.0, the GNU Health modules, PostgreSQL)
# work together, with versions confirmed by actually installing them
# (see commit history), not assumed from docs.

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
COPY trytond.conf /opt/gnuhealth/trytond.conf
COPY entrypoint.sh /opt/gnuhealth/entrypoint.sh
RUN chmod +x /opt/gnuhealth/entrypoint.sh \
    && mkdir -p /opt/gnuhealth/attach /opt/gnuhealth/backup

EXPOSE 8000
ENTRYPOINT ["/opt/gnuhealth/entrypoint.sh"]
