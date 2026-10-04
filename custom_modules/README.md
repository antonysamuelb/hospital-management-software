# Custom modules

Small, site-specific Tryton modules that extend GNU Health without
modifying its own code. Standard Tryton customization pattern: a module
with `metaclass=PoolMeta` extends an existing model (here, `party.party`)
rather than forking GNU Health itself.

## `health_default_ethnicity`

**Why:** GNU Health's stock `gnuhealth.ethnicity` list (Black / Asian /
White / Middle-East / Hispanic / African American / "Indian American" /
Native American — confirmed by reading `health/data/ethnic_groups.xml`) is
US-census-derived and has no category that fits most patients at this
hospital. This module adds **South Asian** and defaults new patients to it.

**What it does:**
- `data/ethnic_groups.xml` — adds a `South Asian` / `SOUTHASIAN` record to
  `gnuhealth.ethnicity`, in the exact same format as GNU Health's own seed
  data (deliberately — reads as "one more entry", not a parallel system).
- `party.py` — overrides `default_ethnic_group()` on `party.party` to
  return that record's id for new patients. Follows the exact same pattern
  GNU Health's own `health.py` already uses for `default_citizenship`/
  `default_residence` (a `@staticmethod` looking up a related record) —
  not a new convention.

**Verified, not assumed:**
- Activated cleanly on a fresh database (`docker compose down -v && up -d`
  from scratch): module state `activated`, ethnicity record present, and
  a brand-new `party.party()` correctly defaults `ethnic_group` to it —
  confirmed via the API.
- Confirmed visually in the actual Sao UI: the "New Patient" quick-create
  dialog shows **Ethnicity: South Asian** pre-filled, not blank. Screenshot:
  `health_default_ethnicity/verified-in-ui.jpg`.
- One real gotcha hit during development: a module activated via
  `trytond-admin` doesn't take effect in an *already-running* `trytond`
  server process — that process has the old Pool loaded in memory and
  needs a restart to pick up a newly-registered module. `entrypoint.sh`
  doesn't hit this itself (it runs trytond-admin before starting the
  server in the same process lifecycle), but it's why a manual
  `trytond-admin -u` against a live container needs a restart afterward
  to actually take effect — noted here since it's easy to lose time to.

## How this ships

**Local dev (`deploy/dev/`):** wired in automatically —
`docker-compose.yml`'s build context is the repo root specifically so the
Dockerfile can `COPY custom_modules/health_default_ethnicity` into
trytond's modules path, and `entrypoint.sh` activates it alongside
`health`/`health_inpatient` on first run (or on next restart, for a
database that predates this module).

**Production (the real VM, not Docker — see `deploy/provision.sh`):**
not yet ported. To do it by hand once GNU Health is installed there:

```bash
# Find where ghcontrol's venv put trytond's modules directory, e.g.:
#   /opt/gnuhealth/his-50/venv/lib/python3.*/site-packages/trytond/modules/
cp -r custom_modules/health_default_ethnicity \
    /opt/gnuhealth/his-50/venv/lib/python3.*/site-packages/trytond/modules/

# Activate it (adjust -d to your actual database name):
/opt/gnuhealth/his-50/venv/bin/trytond-admin \
    -c /opt/gnuhealth/his-50/trytond.conf \
    -d <your-database> \
    -u health_default_ethnicity \
    --activate-dependencies

# Then restart the service so the running server picks it up:
sudo systemctl restart gnuhealth
```

## Adding another custom module

Same pattern: a new directory here with `tryton.cfg` (`depends: health`),
`__init__.py` registering whatever models it touches, and the actual
Python/XML. Wire it into `deploy/dev/app/Dockerfile`'s `COPY` line and
`entrypoint.sh`'s `-u` module list the same way.
