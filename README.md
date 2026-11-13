# Hospital Management Software

Deployment project for a **10-bed rural hospital in India**: evaluating and standing up an
open-source Hospital Management System (HMS), hosted in the cloud on a tight budget.

**Ready to actually deploy this?** See
[`CLOUD_DEPLOYMENT.md`](CLOUD_DEPLOYMENT.md) for a single sequential
checklist — what's proven vs. still a reasoned-but-untested plan, for
every step from provisioning the VM through go-live. See
[`VISIT_TRACKING_DESIGN.md`](VISIT_TRACKING_DESIGN.md) for how visit
recording, diagnosis, and prescriptions were added to `simple_ui`, and
[`TODO.md`](TODO.md) for known gaps (security review findings, a real
prescription-safety-check limitation, etc.) still open.

## Decisions made so far

| Decision | Choice | Why |
|---|---|---|
| Software | **[GNU Health](https://www.gnuhealth.org)** (Python/Tryton + PostgreSQL) | Actively maintained, Python-native (matches team skills), lower operational complexity than multi-service alternatives (Bahmni), built-in bed/hospitalization management |
| ABDM/ABHA integration | **Not required for now** | Revisit if/when integration with India's Ayushman Bharat Digital Mission becomes necessary (Bahmni would be the better fit if/when this becomes a hard requirement) |
| Hosting | **Cloud**, India region (Mumbai) | Data residency for DPDP Act compliance; low latency from the hospital site |
| Compute | Single VM, GNU Health installed via its official `gnuhealth-control` ("vanilla") method + self-hosted PostgreSQL + Nginx | Avoids managed-service costs (RDS, split app/DB servers) that don't make sense at this scale. **Not Docker** — GNU Health doesn't officially support/ship Docker, so `deploy/` follows the documented install path instead of an unverified container setup |
| Managed DB service (Supabase etc.) | **Rejected for now** | Free tier lacks backups/SLA and adds cross-network latency + a second vendor for no cost savings once Postgres is self-hosted for free |
| Budget target | **$0–10/month** | Hospital revenue is ~$1000/month; infra cost must stay well under 1-2% of that |
| Front-end UI | **Custom app (`simple_ui/`), not Sao** | Direct feedback: Sao (GNU Health's own web client) was too complex for day-to-day front-desk use even after trimming its menu via built-in role groups (see `deploy/dev/docs/simplified-front-desk-role.md`). `simple_ui/` is a small Flask app — two buttons, age/sex-filtered search — talking to GNU Health over its existing JSON-RPC API. GNU Health remains the system of record; this doesn't touch the database directly or duplicate its business logic |

## Repo layout

```
deploy/
  provision.sh            OS-level VM setup: PostgreSQL, Nginx, firewall, users
  nginx/gnuhealth.conf     Reverse proxy + TLS config template
  systemd/gnuhealth.service   Runs trytond via Gunicorn
  dev/                     Local Docker test harness (NOT the production path —
                            see deploy/dev/README.md). Used to actually run
                            GNU Health end-to-end and prove the scripts below
                            against a real instance instead of assumptions.
  dev/introspect_fields.py Reusable tool: dumps fields_get()+selection values
                            for any GNU Health model against the dev harness,
                            so new features use real field names, not guesses.
scripts/
  backup.sh                Nightly backup: pg_dump -Fc + attach dir -> rclone -> retention
  backup_retention.py       Retention policy logic (unit tested)
  backup.env.example        Copy to backup.env and fill in (gitignored)
  healthcheck.py            Uptime check + webhook alerting (tested end-to-end)
custom_modules/
  health_default_ethnicity  Site customization: adds "South Asian" to GNU
                             Health's US-census-derived ethnicity list and
                             defaults new patients to it. See custom_modules/README.md
simple_ui/
  app.py                    Flask app: login, landing (2 buttons), register,
                             search (age bucket + sex filters + visit stats),
                             patient detail + visit history, record visit
                             (diagnosis + prescriptions)
  gnuhealth_client.py        Dependency-free JSON-RPC client talking to GNU
                             Health's API directly. See simple_ui/README.md
tools/
  validate_deploy_configs.py   Structural validation for the deploy/ configs
tests/
  test_backup_retention.py  8 tests, pure logic, no external dependencies
  test_healthcheck.py       9 tests, spin up real local HTTP servers
  test_age_buckets.py       5 tests, simple_ui's age-bucket date math
  test_visit_summary.py     6 tests, grouping evaluations into per-patient
                             visit count/first/last date stats
```

### Status: what's actually verified vs. what still needs the real VM

I (Claude) worked through everything in this repo that doesn't require creating
cloud accounts, a domain, or physical hardware — see the "blocked on you" note
on each phase below. Being precise about test coverage, since "tested" can mean
different things:

| Component | How it was tested | Result |
|---|---|---|
| `backup_retention.py` | Real unit tests (`pytest tests/test_backup_retention.py`) — no mocks, pure logic | 9/9 passing. Caught and fixed 2 real bugs (cross-database retention collision, and an ancient backup that would've survived forever) |
| `healthcheck.py` | Real end-to-end tests (local HTTP servers) **+ run against an actual live GNU Health instance** | 9/9 passing. Caught a real bug: defaulted to GET, but trytond returns 405 on GET at "/" even when healthy (it's JSON-RPC only) — fixed to default to OPTIONS, confirmed against the live server (HTTP 204) |
| GNU Health itself (`deploy/dev/`) | **Actually installed and run in Docker**: trytond 7.0.57 + 67 health_* modules, PostgreSQL 15, server started and reachable | Confirmed working. Also surfaced that GNU Health has no official Docker support and `ghcontrol` is a curses TUI with no unattended-install flags — findings fed back into `scripts/backup.sh` and this README |
| **Patient lookup by ID / phone** (the original requirement this whole project started from) | `deploy/dev/test_patient_lookup.py` (API, via `proteus`) **+ manually verified in the actual browser UI** | **Passing both ways.** API: created a test patient, confirmed lookup by internal id, PUID, and phone number. UI: the Patients list's search box correctly filters by full phone number, **partial** phone number (last 4 digits), PUID, and name — see `deploy/dev/docs/searching-for-a-patient.md` |
| **Backup + restore** | `pg_dump --format=custom` on the live DB, restored into a fresh database, re-queried via a new server connection | **Passing**: the same patient (PUID, phone) was present and correct in the restored database. The exact archive filename `backup.sh` produces was also confirmed to parse correctly under `backup_retention.py`'s regex |
| `custom_modules/health_default_ethnicity` (adds "South Asian" ethnicity, defaults new patients to it) | Activated on a **completely fresh** database (`docker compose down -v && up -d`), confirmed via API (`default_ethnic_group()` returns the right record) **and visually in the Sao UI** (new-patient dialog shows "Ethnicity: South Asian" pre-filled) | **Passing.** Wired into `deploy/dev/`'s Dockerfile/entrypoint automatically; **not yet ported to the production (non-Docker) install** — manual steps documented in `custom_modules/README.md` |
| `simple_ui`'s Record Visit (diagnosis + prescriptions) | Verified end-to-end against the dev harness **and through a real browser**: created an evaluation (chief complaint, diagnosis, discharge reason) and a prescription (real WHO Essential Medicines drug, dosage) for an existing patient, confirmed both saved correctly via a fresh API read, confirmed the new Visit History section and search columns (visit count/first/last date) render the real data | **Passing**, with one real limitation found and documented, not silently papered over: GNU Health's pregnancy/allergy prescription warnings depend on client-side `on_change` logic that a raw API `create()` never runs — see `TODO.md`. Also fixed a real bug this surfaced in `gnuhealth_client.py` (datetime fields were never being decoded, only plain dates) |
| `deploy/nginx/gnuhealth.conf`, `deploy/provision.sh` | Structural validation (`python tools/validate_deploy_configs.py`) + `bash -n` syntax check | Passing. Still **not** run through real `nginx -t` or `provision.sh` on an actual VM — that needs the real cloud host from phase 1, not something further local testing can close |
| `deploy/systemd/gnuhealth.service` | **Running for real** on the production AWS Lightsail VM (Mumbai) — `systemctl status` shows `active (running)`, `curl` to `127.0.0.1:8000/` returns `200` | **Passing.** Confirmed `ghcontrol`'s own venv (`/opt/gnuhealth/his-50/venv`) doesn't include `gunicorn` by default — had to `pip install gunicorn` into it by hand before this unit would start; WSGI target (`trytond.application:app`) also independently re-confirmed on this real install, not just the dev harness |
| `deploy/nginx/simple-ui.conf`, `deploy/systemd/simple-ui.service` | **Running for real** on the same production VM — Nginx (plain HTTP via the VM's IP, no domain yet) → Gunicorn → `simple_ui` → GNU Health's JSON-RPC API, logged into end-to-end through an actual browser (New Registration / Find Patient landing page) | **Passing.** First time `simple_ui` has run anywhere but a local dev server. `tools/validate_deploy_configs.py` extended to check this pair the same way as the GNU Health/Sao one |
| Sao (GNU Health's web client) on the production VM | Installed via `npm install tryton-sao` directly on the VM (not Docker this time) — logged in through a real browser as Administrator against the `ghprod` database | **Passing.** First non-Docker install of Sao, done live |
| `scripts/backup.sh` | `bash -n` syntax check + its `pg_dump`/tar logic proven directly (see Backup+restore row) | The `rclone sync` step itself is untested (needs a real Backblaze B2 account) — `rclone` is a mature, widely-used tool, so this is a much smaller risk than the custom logic, which is now proven |

To re-run all of the above yourself at any point:
```bash
python -m pytest tests/ -v
python tools/validate_deploy_configs.py
bash -n deploy/provision.sh scripts/backup.sh

# Full local GNU Health instance (needs Docker):
cd deploy/dev && docker compose up -d
# then see deploy/dev/test_patient_lookup.py for a working example
```

**Want to click around in the actual app yourself?** See
[`deploy/dev/README.md`](deploy/dev/README.md#starting-it) for exact startup
steps and login credentials,
[`deploy/dev/docs/registering-a-patient.md`](deploy/dev/docs/registering-a-patient.md)
for a verified walkthrough of registering a patient through the UI, and
[`deploy/dev/docs/searching-for-a-patient.md`](deploy/dev/docs/searching-for-a-patient.md)
confirming the original requirement — searching by patient ID or phone
number — works in the real UI, not just via the API, and
[`deploy/dev/docs/recording-a-patient-visit.md`](deploy/dev/docs/recording-a-patient-visit.md)
for recording a visit (a "Patient Evaluation" in GNU Health's terms),
including a one-time Health Professional setup step that trips up a fresh
install, and
[`deploy/dev/docs/simplified-front-desk-role.md`](deploy/dev/docs/simplified-front-desk-role.md)
for a reduced-menu reception role (157 menu items down to 13) in response
to "the UI is too complex" feedback, plus what a real custom landing page
would actually take.

## Next steps, in sequence

### 1. Pick and provision the VM — 🟢 done
- [x] **Live**: AWS Lightsail, Mumbai region, $7/month plan. Oracle Cloud Always Free was tried first but blocked on requiring a credit card the hospital doesn't have; a fresh "advanced" AWS signup (needed for full region access — the default "simplified" signup is locked to one region) was used instead.
- [ ] Check whether the hospital qualifies for **nonprofit cloud credits** (AWS via TechSoup, Google for Nonprofits, Microsoft nonprofit program) if it's run by a registered trust/Section 8 company/NGO — could offset costs; not pursued yet.

### 2. Harden the VM — 🟢 done
- [x] `deploy/provision.sh` **run successfully on the real VM.** Found and fixed live: Ubuntu 24.04 has no `postgresql-15` package (now auto-detects the installed version instead of hardcoding), and the script's own printed instructions had two bugs (`su - gnuhealth` needs `sudo` since the account has no password; `trytond.conf` is under `etc/`, not the venv root).
- [x] Firewall (ufw: SSH/80/443 only), fail2ban, unattended upgrades all active on the live VM.
- [ ] Restrict SSH to your known IP(s), or set up a VPN gate — not done yet.
- [ ] (Optional) Set up **WireGuard VPN** so staff access the app through the VPN rather than the open internet — not scripted yet, flag if you want this done before go-live.

### 3. Deploy GNU Health — 🟢 done (domain/TLS still pending)
- [x] `deploy/nginx/gnuhealth.conf` — reverse proxy + TLS-ready Nginx config, prepared for `certbot --nginx`. Not yet installed on the VM (no domain pointed at it yet — Sao is reachable directly for now; see note below).
- [x] `deploy/systemd/gnuhealth.service` — **installed and running on the real VM.** `systemctl status gnuhealth` shows `active (running)`; `curl 127.0.0.1:8000/` returns `200`. Found live: `ghcontrol`'s own venv doesn't include `gunicorn` — had to `pip install gunicorn` into `/opt/gnuhealth/his-50/venv` by hand first.
- [x] Installed via `ghcontrol` (the real curses TUI, run by hand as documented) against a real PostgreSQL database named `ghprod`.
- [x] Confirmed GNU Health auto-creates the `gnuhealth.patient` record when a party is saved with `is_patient=True` — don't create one explicitly (GNU Health will refuse it as a duplicate).
- [x] **Sao (the web UI) installed directly on the VM** (not Docker this time) — `npm install tryton-sao`, `trytond.conf`'s `[web] root = ...` pointed at it, matching version to the installed trytond (`7.0.61`) looked up fresh rather than hardcoded. **Logged in through a real browser** as Administrator against `ghprod`.
- [x] **Domain purchased and live**: `thestfrancishospital.com` (Namecheap), `admin.thestfrancishospital.com` A-recorded at the VM's IP.
- [x] **HTTPS live via certbot**: `sudo certbot --nginx -d app.thestfrancishospital.com -d admin.thestfrancishospital.com` issued a real Let's Encrypt cert covering both subdomains in one run, auto-renewal scheduled by certbot itself. `https://admin.thestfrancishospital.com` serves Sao with a valid cert.
- [ ] Create non-admin GNU Health user accounts for actual staff.

### 3b. Deploy `simple_ui` — 🟢 done
- [x] `deploy/systemd/simple-ui.service` — **installed and running on the real VM**, `gunicorn` bound to `127.0.0.1:5050`, `systemctl status` shows `active (running)`.
- [x] `deploy/nginx/simple-ui.conf` — **installed on the real VM**, now serving `app.thestfrancishospital.com` specifically (not a bare-IP catch-all anymore — see phase 3's domain/TLS notes, same certbot run covered this subdomain too).
- [x] **Logged into end-to-end through a real browser** over HTTPS at `https://app.thestfrancishospital.com` — the New Registration / Find Patient landing page, valid cert, no port number needed.
- [x] A real random `SIMPLE_UI_SECRET_KEY` was generated and installed (not the dev default) — see the systemd unit's `Environment=` line.

### 4. Backups — 🟢 proven end-to-end against real data, needs the VM + a B2 account for the offsite leg
- [x] `scripts/backup.sh` — **rewritten** after testing revealed `ghcontrol backup` isn't a real CLI command (ghcontrol is curses-only; its own backup menu option is just `pg_dump` under the hood, confirmed by reading its source). Now does `pg_dump --format=custom` + tars the attachment directory + `rclone sync` to Backblaze B2 + retention.
- [x] `scripts/backup_retention.py` — retention policy (30 daily + 12 monthly, per-database), **9 unit tests passing**.
- [x] **Full backup+restore cycle proven on real data**: created a test patient, backed up with `pg_dump -Fc`, restored into a fresh database, reconnected and confirmed the exact same patient (PUID, phone number) was intact. The real archive filename was also confirmed to parse correctly under the retention regex.
- [ ] Create a Backblaze B2 account + application key (not your master key), `rclone config` it, fill in `scripts/backup.env` from the `.example`. (The `rclone sync` leg itself is the only untested part — needs real B2 credentials.)
- [ ] Wire `backup.sh` into cron (`0 2 * * *`, example line is in the script's header comment).
- [ ] Schedule a recurring quarterly restore-test reminder (the mechanism is proven; this is about *keeping* it proven as real data accumulates).

### 5. Connectivity resilience (mitigating the "fully cloud, no local fallback" risk) — 🔴 blocked on you (physical/on-site)
- [ ] Set up **dual-WAN failover** at the hospital site (primary broadband + 4G/5G backup router).
- [ ] Put the router/networking gear on a UPS.
- [ ] Write a documented manual/paper fallback procedure for outages.

### 6. Monitoring — 🟡 self-hosted option ready now; external monitor is optional
- [x] `scripts/healthcheck.py` — polls the app URL, alerts on up/down *transitions* via webhook (not on every repeated failure), zero third-party account required. Tested end-to-end against real local servers.
- [ ] Point it at the real URL once deployed; wire into cron (e.g. every 5 min) and/or a webhook (Slack/Discord).
- [ ] Optionally also set up UptimeRobot (or similar) as a second, independent external check.
- [ ] Set up log rotation for the trytond/Nginx logs (`logrotate` config not yet written — small, can do once the VM exists).

### 7. Data & configuration — 🟢 core requirement proven; rest blocked on the real instance
- [x] **Patient lookup by ID and phone number — the original requirement — confirmed working** against a live instance (`deploy/dev/test_patient_lookup.py`): by internal id, by GNU Health's auto-generated PUID, and by phone number via `party.contact_mechanisms`.
- [ ] `health_inpatient` module (bed/ward management) is installed and activated in the test harness, but not yet configured for an actual 10-bed layout — that's real data entry, not scriptable in advance.
- [x] **Reception role started** — GNU Health's built-in "Health Front Desk" group verified to cut the menu from 157 items to 13, with no Prescriptions/Hospitalizations/Nursing/Reporting/Administration visible, while patient registration and search both keep working. See `deploy/dev/docs/simplified-front-desk-role.md`. Doctor/nurse/pharmacy roles not yet configured — GNU Health ships groups for those too ("Health Doctor", "Health Nurse", etc.) but haven't been verified the same way.
- [ ] Import or set up any existing patient records (if migrating from paper/another system).
- [x] Web UI (Sao) now proven working in-browser — see phase 3. Not yet ported to the production (non-Docker) install path.
- [x] **Ethnicity list localized** — added "South Asian" (GNU Health's stock list is US-census-derived and had nothing appropriate) and set it as the default for new patients. Proven on a fresh database, both via the API and visually in the UI. See `custom_modules/health_default_ethnicity/` and `custom_modules/README.md`. Not yet ported to the production (non-Docker) install path — manual steps documented there.

### 8. Go-live — 🔴 blocked on you (organizational/on-site)
- [ ] Train staff on registration, patient lookup, and daily workflows.
- [ ] Run in parallel with any existing paper process for a short trial period.
- [ ] Confirm backup/restore and failover procedures work end-to-end before fully cutting over.

### 9. Revisit later (not needed now)
- [ ] Reassess ABDM/ABHA integration if it becomes a requirement (Bahmni is the stronger candidate for that).
- [ ] Reassess managed database hosting (e.g. Supabase Pro, RDS) if self-hosting becomes an operational burden.
- [ ] Reassess hardware/hosting tier if patient volume grows beyond a single small VM.

## Open questions
- Is the hospital a registered nonprofit/trust (relevant for cloud credit eligibility)?
- Who will own day-to-day operations/maintenance of the server long-term?
- `deploy/dev/`'s Dockerfile now builds the Sao web client correctly, but the
  production path (`provision.sh` + `nginx` + `systemd`, not Docker) doesn't
  install it yet — needs porting: `npm install tryton-sao@7.0.58` into a
  directory on the VM, then `trytond.conf`'s `[web] root = ...` pointed at it,
  same as the dev harness does.
