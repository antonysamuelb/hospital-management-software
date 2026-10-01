# Hospital Management Software

Deployment project for a **10-bed rural hospital in India**: evaluating and standing up an
open-source Hospital Management System (HMS), hosted in the cloud on a tight budget.

## Decisions made so far

| Decision | Choice | Why |
|---|---|---|
| Software | **[GNU Health](https://www.gnuhealth.org)** (Python/Tryton + PostgreSQL) | Actively maintained, Python-native (matches team skills), lower operational complexity than multi-service alternatives (Bahmni), built-in bed/hospitalization management |
| ABDM/ABHA integration | **Not required for now** | Revisit if/when integration with India's Ayushman Bharat Digital Mission becomes necessary (Bahmni would be the better fit if/when this becomes a hard requirement) |
| Hosting | **Cloud**, India region (Mumbai) | Data residency for DPDP Act compliance; low latency from the hospital site |
| Compute | Single VM, GNU Health installed via its official `gnuhealth-control` ("vanilla") method + self-hosted PostgreSQL + Nginx | Avoids managed-service costs (RDS, split app/DB servers) that don't make sense at this scale. **Not Docker** — GNU Health doesn't officially support/ship Docker, so `deploy/` follows the documented install path instead of an unverified container setup |
| Managed DB service (Supabase etc.) | **Rejected for now** | Free tier lacks backups/SLA and adds cross-network latency + a second vendor for no cost savings once Postgres is self-hosted for free |
| Budget target | **$0–10/month** | Hospital revenue is ~$1000/month; infra cost must stay well under 1-2% of that |

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
scripts/
  backup.sh                Nightly backup: pg_dump -Fc + attach dir -> rclone -> retention
  backup_retention.py       Retention policy logic (unit tested)
  backup.env.example        Copy to backup.env and fill in (gitignored)
  healthcheck.py            Uptime check + webhook alerting (tested end-to-end)
tools/
  validate_deploy_configs.py   Structural validation for the deploy/ configs
tests/
  test_backup_retention.py  8 tests, pure logic, no external dependencies
  test_healthcheck.py       9 tests, spin up real local HTTP servers
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
| **Patient lookup by ID / phone** (the original requirement this whole project started from) | `deploy/dev/test_patient_lookup.py`, run against the live instance via `proteus` (Tryton's own scripting client) | **Passing against real data**: created a test patient, confirmed lookup by internal id, by GNU Health's auto-generated PUID (e.g. `QAN111KTI`), and by phone number (`party.contact_mechanisms`) all work |
| **Backup + restore** | `pg_dump --format=custom` on the live DB, restored into a fresh database, re-queried via a new server connection | **Passing**: the same patient (PUID, phone) was present and correct in the restored database. The exact archive filename `backup.sh` produces was also confirmed to parse correctly under `backup_retention.py`'s regex |
| `deploy/nginx/gnuhealth.conf`, `deploy/provision.sh` | Structural validation (`python tools/validate_deploy_configs.py`) + `bash -n` syntax check | Passing. Still **not** run through real `nginx -t` or `provision.sh` on an actual VM — that needs the real cloud host from phase 1, not something further local testing can close |
| `deploy/systemd/gnuhealth.service` | WSGI entry point (`trytond.application:app`) confirmed correct against the live instance | The module/callable is verified; the exact venv path still depends on how you installed (this repo's dev harness used a direct pip install, not `ghcontrol`'s own convention — noted in the file) |
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

## Next steps, in sequence

### 1. Pick and provision the VM — 🔴 blocked on you (needs account creation/payment)
- [ ] Try **Oracle Cloud "Always Free" tier** first (Mumbai region) — ARM Ampere instance, currently 2 OCPU / 12GB RAM, genuinely free forever. Note: signup approval and regional capacity aren't guaranteed.
- [ ] In parallel, set up a **$6/month DigitalOcean droplet (Bangalore region)** or **AWS Lightsail (Mumbai)** as a cold-standby fallback — don't run it live, just keep the account ready with a recent backup so you can switch within an hour if Oracle has issues.
- [ ] Check whether the hospital qualifies for **nonprofit cloud credits** (AWS via TechSoup, Google for Nonprofits, Microsoft nonprofit program) if it's run by a registered trust/Section 8 company/NGO — could offset costs entirely for 1–2 years.

### 2. Harden the VM — 🟡 script ready, needs the VM from step 1 to run against
- [x] Prepared as `deploy/provision.sh`: creates a locked-down `gnuhealth` service user, installs PostgreSQL/Nginx, configures the firewall (ufw: only SSH/80/443 open), enables unattended security upgrades and fail2ban. Structurally validated, not yet run on a real host.
- [ ] Run it: `sudo bash deploy/provision.sh` (once the VM exists).
- [ ] Restrict SSH to your known IP(s), or set up a VPN gate.
- [ ] (Optional but recommended) Set up **WireGuard VPN** so staff access the app through the VPN rather than the open internet — not scripted yet, flag if you want this done before go-live.

### 3. Deploy GNU Health — 🟡 configs ready and proven in Docker; one step is inherently manual on the real VM
- [x] `deploy/nginx/gnuhealth.conf` — reverse proxy + TLS-ready Nginx config, prepared for `certbot --nginx`.
- [x] `deploy/systemd/gnuhealth.service` — runs trytond via Gunicorn. WSGI target (`trytond.application:app`) **confirmed correct** against a live instance.
- [x] Confirmed the actual install (`pip install gnuhealth-all-modules`) resolves cleanly: trytond 7.0.57 + 67 `health_*` modules, and the real module names needed for `trytond-admin -u` (`health`, `health_inpatient` for bed management, etc.) — see `deploy/dev/`.
- [x] Confirmed GNU Health auto-creates the `gnuhealth.patient` record when a party is saved with `is_patient=True` — don't create one explicitly (GNU Health will refuse it as a duplicate).
- [ ] **Known gap found during testing, not yet addressed**: the trytond server only serves JSON-RPC — there is no HTML web UI at `/`. GNU Health's actual browser-based interface ("Sao") is a separate static web client that isn't part of the `gnuhealth-all-modules` pip install and isn't yet accounted for anywhere in `deploy/`. Staff need *something* to click around in day-to-day — this needs research before phase 8 (go-live).
- [ ] Point a domain name at the VM (~$1/month amortized) for clean HTTPS access.
- [ ] Run `ghcontrol` **by hand, once** — confirmed it's a curses TUI (full-screen terminal menu) with no CLI flags for unattended install, so it genuinely can't be scripted from here. Exact steps are printed at the end of `provision.sh`. (Alternative, also proven to work: install directly via `pip install gnuhealth-all-modules` + `trytond-admin -u health health_inpatient --activate-dependencies -p`, bypassing `ghcontrol` entirely — this is what `deploy/dev/` actually does.)
- [ ] Create the initial admin user and lock down default credentials.
- [ ] `sudo certbot --nginx -d your-domain.example`.

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
- [ ] Set up user roles/permissions for hospital staff (reception, nurses, doctors, pharmacy, admin).
- [ ] Import or set up any existing patient records (if migrating from paper/another system).
- [ ] Resolve the Sao web-client gap noted in phase 3 — staff need a UI, not just an API.

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
- **New, from testing**: GNU Health's actual web UI ("Sao") isn't part of the
  server-side install and isn't accounted for in `deploy/` yet — needs research
  before go-live (see phase 3/7 above). Worth deciding whether that's a separate
  static client to build/serve, or whether to reconsider the UI story entirely.
