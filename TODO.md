# TODO

Working list of known gaps and follow-ups. Unlike `README.md`'s phase
checklist (the original rollout plan) and `CLOUD_DEPLOYMENT.md` (the
step-by-step runbook), this file is for things found *after* go-live
prep started — issues, risks, and loose ends to come back to.

## Security review (2026-11-13)

Done against the live production VM (`thestfrancishospital.com`, AWS
Lightsail, Mumbai) after HTTPS went live for both `app.` and `admin.`
subdomains. Ranked by what to fix first — #1 and #2 are the two with
genuine "lose everything" or "get broken into" consequences and should
be closed **before any real patient data goes in**.

- [ ] **1. No real backups running yet.** `scripts/backup.sh` is proven
      correct (pg_dump + restore cycle tested on real data), but it's
      not wired into cron on the production VM, and there's no
      Backblaze B2 account/credentials behind it yet. Right now, disk
      failure or an accidental delete has no recovery path. See
      `CLOUD_DEPLOYMENT.md` step 7.
- [ ] **2. SSH (port 22) is open to the entire internet**, not
      restricted to known IP(s). `fail2ban` mitigates brute-forcing but
      doesn't eliminate the exposure. Either restrict the Lightsail
      firewall's SSH rule to known IP(s), or put SSH behind a VPN.
- [ ] **3. No login brute-force protection on the web apps themselves.**
      `fail2ban`'s only configured jail watches SSH — the Sao and
      `simple_ui` login forms can be hammered with no lockout. Needs
      either an HTTP-auth fail2ban jail or basic rate-limiting in
      Nginx.
- [ ] **4. No monitoring/alerting wired up.** `healthcheck.py` is
      tested and ready (see `README.md`'s status table) but not pointed
      at the real `https://app...`/`https://admin...` URLs or scheduled
      via cron/webhook yet. If the server goes down, nobody finds out
      until someone notices by hand.
- [ ] **5. `simple_ui` has no CSRF protection or rate-limiting** —
      flagged in `simple_ui/README.md`'s own "Security" section when it
      was built. Acceptable for a trusted LAN terminal, less so now
      that it's reachable from anywhere over the open internet.
- [ ] **6. Python dependencies don't get patched automatically.**
      `unattended-upgrades` (enabled via `provision.sh`) only covers OS
      packages — nothing tracks CVEs in `pip`-installed packages
      (trytond, Flask, gunicorn, etc.). No process exists yet for this.
- [ ] **7. Sao (the full admin interface) is reachable from the open
      internet**, protected only by a password, no MFA, with raw
      read/write access to all patient data. Given this will hold real
      health data (a sensitive category under India's DPDP Act),
      consider putting it behind a VPN or IP-allowlist for the staff
      who actually need it, now that front-desk staff use `simple_ui`
      instead and don't need Sao access at all.

## Repo visibility

- [ ] **The GitHub repo (`antonysamuelb/hospital-management-software`)
      is public.** Confirmed no secrets, passwords, or IP addresses are
      committed (grepped the full history before writing this). What
      *is* exposed: the real domain name and subdomains, and the exact
      tech stack / firewall / systemd / Nginx / backup configuration —
      effectively a working blueprint of this specific server, which
      lowers an attacker's reconnaissance effort even though nothing
      exploitable is directly leaked.
      Note: the subdomains themselves (`app.`/`admin.thestfrancishospital.com`)
      are *already* permanently public via Certificate Transparency
      logs (e.g. crt.sh) regardless of repo visibility — that happened
      the moment real TLS certs were issued and can't be undone. Making
      the repo private would not hide that, only the configuration
      detail above.
      Recommendation: make the repo private — free, no real downside
      unless public visibility is wanted for other reasons (portfolio,
      open-source intent). Not done yet — needs the user's go-ahead
      since it's a repo setting change.

## Other known loose ends (carried over, not newly found)

- [ ] `custom_modules/health_default_ethnicity` (the "South Asian"
      ethnicity default) is proven locally but not yet ported to the
      production database (`ghprod`) — see `custom_modules/README.md`.
- [ ] Log rotation for trytond/gunicorn/Nginx logs not yet set up on
      the production VM (small, flagged in `README.md` phase 6).
- [ ] `health_inpatient` (bed/ward management) is installed and
      activated but not configured with the actual 10-bed layout yet —
      real data entry, not scriptable in advance.

## Visit/prescription recording (added 2026-11-13, see VISIT_TRACKING_DESIGN.md)

- [ ] **`health_who_essential_medicines` needs activating in
      production** (`trytond-admin -u health_who_essential_medicines
      --activate-dependencies`, then restart `gnuhealth.service`) —
      without it, `gnuhealth.medicament` has zero records and
      `simple_ui`'s "Record Visit" medication rows have nothing to
      select. Confirmed on the dev harness: 442 real drugs load after
      activating.
- [ ] **Real gap, not yet fixed**: `simple_ui`'s prescription creation
      sets `prescription_warning_ack=True` unconditionally to get past
      GNU Health's generic "has this been verified" check. The actual
      pregnancy/allergy safety checks are normally computed by Sao's
      `on_change_patient` (checking childbearing age / known allergies
      on file) — a raw API `create()` never runs that, so a prescription
      created through `simple_ui` silently skips those warnings rather
      than ever surfacing them. Fix: replicate the same check
      server-side (read `patient.childbearing_age` /
      `patient.crit_allergic` before creating) rather than blindly
      acknowledging. Don't rely on this for real prescriptions until
      fixed.
- [ ] Each doctor/nurse who will use "Record Visit" needs their own
      GNU Health login individually linked to a Health Professional
      record (Internal User field set on their party) — the
      `healthprof` field resolves automatically via `default_get()`,
      but only if this one-time per-person setup is done first. Same
      gotcha as the `admin` account hit in
      `deploy/dev/docs/recording-a-patient-visit.md`, now needed per
      clinical staff member.
