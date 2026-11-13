# Cloud Deployment Checklist

A single, sequential runbook for actually putting this on a cloud VM.
Everything referenced here has already been built and tested locally
(see the main [`README.md`](README.md)'s status table for exactly what
was verified and how) — this document is about the steps that are
**still blocked on a real VM existing**, plus one gap found while
writing this: `simple_ui` itself has no production deployment story yet.

## What's being deployed

Two services on one VM, both behind Nginx with TLS:

1. **GNU Health** (Tryton backend + the Sao web client) — the system of
   record. Mostly for admin/clinical use once `simple_ui` is the
   day-to-day front door.
2. **`simple_ui`** — the custom Flask app built for front-desk
   registration/search. This is new since the deployment plan was first
   written and **is not covered below with the same level of
   proven-in-production confidence as GNU Health itself** — flagged
   throughout.

Both talk to the same PostgreSQL database; `simple_ui` has no database
of its own, it calls GNU Health's JSON-RPC API.

## Before you start

- Pick and provision the VM. Not scriptable — this needs an account and
  payment method. See the main README's phase 1 for the specific
  recommendation (Oracle Cloud Always Free in Mumbai, with a $6/month
  DigitalOcean droplet as cold-standby) and the cost reasoning.
- Point a domain (or a subdomain for each service — see Nginx step
  below) at the VM's IP once it exists.

---

## 1. Harden the VM

```bash
sudo bash deploy/provision.sh
```

Creates a locked-down `gnuhealth` service user, installs
PostgreSQL/Nginx/Node.js, configures the firewall (only SSH/80/443
open), enables unattended security upgrades and fail2ban. Structurally
validated, not yet run on a real host — this is genuinely the first time
it touches anything real.

Afterward: restrict SSH to your known IP(s), or put it behind a
WireGuard VPN (not scripted — do this manually if you want it before
go-live).

## 2. Install GNU Health

The script above prints the exact remaining commands at the end, but in
short:

```bash
su - gnuhealth
python3 -m venv tmp_ghvenv && cd tmp_ghvenv && source bin/activate
pip install gnuhealth-control
ghcontrol   # choose "0: Install GNU Health HIS", then "1: Create a new DB instance"
```

`ghcontrol` is a curses TUI (confirmed — no unattended-install flags
exist), so this one step is inherently manual, done once. The tested
alternative, if you'd rather skip `ghcontrol` entirely: `pip install
gnuhealth-all-modules` then `trytond-admin -u health health_inpatient
--activate-dependencies -p` — this is what the local dev harness
actually does, and it's what's really been proven end-to-end.

**Use a real database name**, not `gnuhealth_test` (that's dev-only). Pick
something like `ghprod` and use it consistently in every config below.

## 3. Port the custom modules

Two customizations exist locally and need copying onto the real venv's
`trytond/modules/` directory, then activating:

```bash
cp -r custom_modules/health_default_ethnicity \
    /opt/gnuhealth/his-50/venv/lib/python3.*/site-packages/trytond/modules/

/opt/gnuhealth/his-50/venv/bin/trytond-admin \
    -c /opt/gnuhealth/his-50/trytond.conf -d ghprod \
    -u health_default_ethnicity --activate-dependencies
```

Full detail, including why this is two explicit steps and a real gotcha
about restarting the server afterward (a module activated in one process
doesn't show up in an already-running server until it restarts): see
[`custom_modules/README.md`](custom_modules/README.md).

## 4. Install the Sao web client

```bash
cd /opt/gnuhealth
npm install tryton-sao@7.0.58 --production --legacy-peer-deps
```

(Pin the version to match whatever trytond version actually installed —
check with `npm view tryton-sao dist-tags`.) Then add this line to
`trytond.conf`'s `[web]` section, alongside `listen = ...`:

```
root = /opt/gnuhealth/node_modules/tryton-sao
```

Without this, GNU Health only answers JSON-RPC and there's no browser
UI at all for admin/clinical use. Proven working in the local Docker
harness; this is the first time it's done directly on a VM rather than
inside a container.

## 5. Deploy `simple_ui` — the gap found while writing this document

**This has not been run in anything resembling production before.**
Everything below is standard, well-established Flask deployment
practice, not something GNU-Health-specific that was tested — but
unlike every other step in this document, it hasn't been proven on a
real host yet, and the systemd unit it needs doesn't exist as a file in
this repo yet either.

```bash
cd /opt/gnuhealth/simple_ui   # or wherever you put this repo on the VM
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt gunicorn
```

Environment variables it needs (put these in a systemd `Environment=` block
or an env file, not hardcoded):

| Variable | Production value |
|---|---|
| `GNUHEALTH_URL` | `http://127.0.0.1:8000` — same VM, so internal/loopback, not a public URL |
| `GNUHEALTH_DATABASE` | whatever you named it in step 2 (e.g. `ghprod`) |
| `SIMPLE_UI_SECRET_KEY` | a real random value — generate with `python3 -c "import secrets; print(secrets.token_hex(32))"`, never the `dev-only-change-me` default |

Run it via a real WSGI server, not Flask's own dev server:

```bash
gunicorn -w 2 -b 127.0.0.1:5050 app:app
```

`deploy/systemd/simple-ui.service` now exists in this repo — copy it into
place and follow the comments at its top (generate a real
`SIMPLE_UI_SECRET_KEY`, don't leave the default running). Not yet proven
on a real host.

**Still needed before this is real:**
- [ ] Real GNU Health user accounts for actual staff, with real
      passwords — the `reception` / `reception123` account only exists
      in the local `gnuhealth_test` database and must never be the
      production login
- [ ] `simple_ui`'s own security posture reviewed before go-live — see
      "Security" in [`simple_ui/README.md`](simple_ui/README.md) (no
      CSRF protection yet, no rate-limiting; fine for a trusted LAN
      terminal, not fine if this is ever reachable beyond that)

## 6. Nginx + domain + TLS

**Architecture decision, not yet built or tested:** route `simple_ui`
and Sao through **separate subdomains** rather than path-prefixing one
under the other. Sao's own JavaScript assumes it's served from the
origin root for both its static assets and its JSON-RPC calls (per
`trytond.conf`'s `[web] root =`); putting it under a sub-path like
`/admin/` risks breaking that in ways not worth debugging for a 10-bed
hospital's deployment. Two DNS records, two Nginx server blocks, each a
normal reverse proxy to a different local port:

| Subdomain | Proxies to | Serves |
|---|---|---|
| `app.yourdomain.example` | `127.0.0.1:5050` | `simple_ui` — the day-to-day front desk app |
| `admin.yourdomain.example` | `127.0.0.1:8000` | GNU Health / Sao — admin & clinical use |

`deploy/nginx/gnuhealth.conf` already covers the `admin.` block (proxy +
TLS-ready, prepared for `certbot --nginx`) — copy it, point
`server_name` at your real domain, and `sudo certbot --nginx -d
admin.yourdomain.example`. The `app.` block for `simple_ui` doesn't
exist as a file yet — same shape, different `server_name`/port, same
certbot command repeated for the second subdomain.

## 7. Backups

```bash
# Create a Backblaze B2 account + application key (not your master key)
rclone config
cp scripts/backup.env.example scripts/backup.env   # fill in real values
```

Then wire into cron:
```
0 2 * * * /opt/gnuhealth/scripts/backup.sh >> /var/log/gnuhealth-backup.log 2>&1
```

Everything except the final `rclone sync` leg is proven end-to-end on
real data (`pg_dump` → restore → same patient confirmed intact — see
main README). The sync step itself just needs real B2 credentials to
exercise; `rclone` is mature enough that this is a low-risk gap
compared to everything else in this list.

**`simple_ui` doesn't need its own backup** — it has no database; all
real data lives in the PostgreSQL database the step above already
covers.

Schedule a recurring quarterly restore-test reminder once this is live —
the mechanism is proven, keeping it proven as real data accumulates is
an ongoing responsibility, not a one-time task.

## 8. Monitoring

```bash
# Point at BOTH services now, not just GNU Health
*/5 * * * * /opt/gnuhealth/scripts/healthcheck.py --url https://admin.yourdomain.example/ --webhook <your-webhook>
*/5 * * * * /opt/gnuhealth/scripts/healthcheck.py --url https://app.yourdomain.example/login --webhook <your-webhook>
```

`healthcheck.py` defaults to an `OPTIONS` request (confirmed necessary
for GNU Health's JSON-RPC endpoint, which 405s on GET even when
healthy). `simple_ui`'s `/login` page is a normal GET-able page, so
either method works there — `OPTIONS` is harmless to use for both and
keeps the cron lines consistent.

Optionally add UptimeRobot (or similar) as a second, independent
external check on both subdomains. Set up log rotation for
trytond/gunicorn/Nginx logs (not yet written — small, do this once the
VM exists and you can see real log volume).

## 9. Data setup (do this once the instance is live, not before)

- [ ] Configure the bed/ward layout for the actual 10 beds (`health_inpatient`
      is installed and activated, just not configured with real ward/bed
      records yet — Institution → Ward → Bed, in that order)
- [ ] Set up real user accounts and roles — reception staff get the
      built-in "Health Front Desk" group (see
      `deploy/dev/docs/simplified-front-desk-role.md` for exact steps
      and what it restricts), doctors/nurses get GNU Health's
      corresponding groups ("Health Doctor", "Health Nurse" — these
      exist but haven't been verified the same hands-on way front desk
      was)
- [ ] Import any existing patient records if migrating from paper or
      another system
- [ ] If prescriptions or hospitalization tracking are needed in
      `simple_ui` specifically (raised separately, not yet built): the
      WHO Essential Medicines module (`health_who_essential_medicines`)
      is installed but not activated — needed before a prescription
      screen would have any drugs to select from

## 10. Go-live

- [ ] Train staff on registration, patient lookup, and daily workflows
      — both the `simple_ui` front door and, for admin/clinical staff,
      Sao at the `admin.` subdomain
- [ ] Run in parallel with any existing paper process for a short trial
      period
- [ ] Confirm backup/restore and the dual-WAN failover (if set up — see
      main README phase 5, still blocked on physical networking at the
      hospital site) actually work end-to-end before fully cutting over

---

## Honest summary of what's proven vs. not

| | Status |
|---|---|
| GNU Health itself (install, modules, Sao, backups, patient lookup) | **Proven in Docker, and now proven for real** on the production AWS Lightsail VM (Mumbai): `ghcontrol`-driven install, `gnuhealth.service` running under systemd, Sao installed via npm and logged into through a real browser |
| `simple_ui` running under gunicorn behind Nginx on a real VM | **Proven.** `simple-ui.service` + `simple-ui.conf` both installed and running on the same production VM; logged into end-to-end through a real browser at the VM's bare IP |
| Domain name + TLS (HTTPS) | **Proven.** `thestfrancishospital.com` registered, DNS pointed at the VM, `certbot --nginx` issued a real cert covering both subdomains in one run. Both services are reachable over real HTTPS now, auto-renewal scheduled by certbot |
| The two-subdomain Nginx split | **Proven.** `app.thestfrancishospital.com` → `simple_ui`, `admin.thestfrancishospital.com` → Sao/GNU Health, same VM, same port, Nginx routing by `Host` header exactly as planned |
| Everything under "Data setup" | **Blocked on the real instance existing** — can't be done in advance. The instance itself is ready now |

This document exists so that when you're ready to actually provision the
VM, there's one place that says what to do, in order, with an honest
mark against each step for whether it's been proven or is still a
reasoned-but-untested plan.
