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
scripts/
  backup.sh                Nightly backup: ghcontrol backup -> rclone -> retention
  backup_retention.py       Retention policy logic (unit tested)
  backup.env.example        Copy to backup.env and fill in (gitignored)
  healthcheck.py            Uptime check + webhook alerting (tested end-to-end)
tools/
  validate_deploy_configs.py   Structural validation for the deploy/ configs
tests/
  test_backup_retention.py  8 tests, pure logic, no external dependencies
  test_healthcheck.py       8 tests, spin up real local HTTP servers
```

### Status: what's actually verified vs. what still needs the real VM

I (Claude) worked through everything in this repo that doesn't require creating
cloud accounts, a domain, or physical hardware — see the "blocked on you" note
on each phase below. Being precise about test coverage, since "tested" can mean
different things:

| Component | How it was tested | Result |
|---|---|---|
| `backup_retention.py` | Real unit tests (`pytest tests/test_backup_retention.py`) — no mocks, pure logic | 8/8 passing. Caught and fixed 2 real bugs (cross-database retention collision, and an ancient backup that would've survived forever) |
| `healthcheck.py` | Real end-to-end tests — spins up actual local HTTP servers and a webhook receiver (`pytest tests/test_healthcheck.py`) | 8/8 passing, plus manually smoke-tested via CLI |
| `deploy/nginx/gnuhealth.conf`, `deploy/systemd/gnuhealth.service`, `deploy/provision.sh` | Structural validation (`python tools/validate_deploy_configs.py`) + `bash -n` syntax check | Passing, but **not** run through real `nginx -t` or actually started by systemd — neither nginx, systemd, Docker, nor WSL is available in the environment this was built in, and installing them would mean changing system settings, which needs your go-ahead first (see below) |
| `scripts/backup.sh` | `bash -n` syntax check only | Calls `ghcontrol` and `rclone`, neither of which can run without a real GNU Health install — untested beyond syntax until the VM exists |

To re-run all of the above yourself at any point:
```bash
python -m pytest tests/ -v
python tools/validate_deploy_configs.py
bash -n deploy/provision.sh scripts/backup.sh
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

### 3. Deploy GNU Health — 🟡 configs ready, one step is inherently manual
- [x] `deploy/nginx/gnuhealth.conf` — reverse proxy + TLS-ready Nginx config, prepared for `certbot --nginx`.
- [x] `deploy/systemd/gnuhealth.service` — runs trytond via Gunicorn on boot/crash-restart. **Flagged unverified**: the exact Gunicorn WSGI entry point needs confirming against a real `ghcontrol` install (noted in the file itself).
- [ ] Point a domain name at the VM (~$1/month amortized) for clean HTTPS access.
- [ ] Run `ghcontrol` **by hand, once** — as of GNU Health 5.0 this is an interactive menu tool (choose "Install GNU Health HIS", then "Create a new DB instance"), so it can't be scripted from here. Exact steps are printed at the end of `provision.sh`.
- [ ] Create the initial admin user and lock down default credentials.
- [ ] Correct `gnuhealth.service`'s WSGI entry point against what `ghcontrol` actually generated, then `sudo certbot --nginx -d your-domain.example`.

### 4. Backups — 🟡 scripted and unit-tested, needs the VM + a B2 account to run end-to-end
- [x] `scripts/backup.sh` wraps the official `ghcontrol backup` command + `rclone sync` to Backblaze B2, then applies retention.
- [x] `scripts/backup_retention.py` — retention policy (30 daily + 12 monthly, per-database), **8 unit tests passing**, caught 2 real bugs during development (see Status table above).
- [ ] Create a Backblaze B2 account + application key (not your master key), `rclone config` it, fill in `scripts/backup.env` from the `.example`.
- [ ] Wire `backup.sh` into cron (`0 2 * * *`, example line is in the script's header comment).
- [ ] **Test a restore** — an untested backup isn't a backup. Not scriptable in advance; do this once real data exists.
- [ ] Schedule a recurring quarterly restore-test reminder.

### 5. Connectivity resilience (mitigating the "fully cloud, no local fallback" risk) — 🔴 blocked on you (physical/on-site)
- [ ] Set up **dual-WAN failover** at the hospital site (primary broadband + 4G/5G backup router).
- [ ] Put the router/networking gear on a UPS.
- [ ] Write a documented manual/paper fallback procedure for outages.

### 6. Monitoring — 🟡 self-hosted option ready now; external monitor is optional
- [x] `scripts/healthcheck.py` — polls the app URL, alerts on up/down *transitions* via webhook (not on every repeated failure), zero third-party account required. Tested end-to-end against real local servers.
- [ ] Point it at the real URL once deployed; wire into cron (e.g. every 5 min) and/or a webhook (Slack/Discord).
- [ ] Optionally also set up UptimeRobot (or similar) as a second, independent external check.
- [ ] Set up log rotation for the trytond/Nginx logs (`logrotate` config not yet written — small, can do once the VM exists).

### 7. Data & configuration — 🔴 blocked on a running GNU Health instance
- [ ] Configure patient registration to support lookup by **patient ID and phone number**.
- [ ] Set up user roles/permissions for hospital staff (reception, nurses, doctors, pharmacy, admin).
- [ ] Configure the bed/ward module for the 10-bed inpatient setup.
- [ ] Import or set up any existing patient records (if migrating from paper/another system).

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
- Want deeper local testing before this touches a real VM? I could validate the
  full stack (actually installing GNU Health, starting it, hitting it with
  `healthcheck.py`, running a real backup/restore cycle) locally first — but
  that needs Docker Desktop or WSL2 installed, which changes system settings
  on this machine, so I won't do it without you saying go ahead.
