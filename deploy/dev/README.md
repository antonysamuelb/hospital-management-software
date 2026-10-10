# Local dev/test harness (NOT what ships to the VM)

This `deploy/dev/` stack exists for one purpose: let Claude (or you) prove the
GNU Health + PostgreSQL pieces actually work together, on a laptop, before
anything touches the real hospital VM.

## Starting it

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/)
running first (open the app, wait for it to say it's running).

```bash
cd deploy/dev
docker compose up -d
```

- **First time ever** (or after `docker compose down -v`, which wipes data):
  takes a few minutes — it's installing and activating 67 GNU Health/Tryton
  modules from scratch into a fresh PostgreSQL database. Watch progress with
  `docker compose logs -f app` and wait for `Starting trytond server...`.
- **Every time after that**: a few seconds — it reuses the existing database
  in the `gnuhealth-dev-db` Docker volume, so none of your data is lost
  between restarts.

Then open **http://localhost:8000/** in a browser and log in:

| Field | Value |
|---|---|
| Database | `gnuhealth_test` |
| User name | `admin` — **literally the word "admin", not an email address.** `docker-compose.yml` also sets a `GNUHEALTH_ADMIN_EMAIL` (`admin@example.test`) — that's just contact info stored on the account, not something you log in with. Typing the email as the username is a real mistake people have hit here; it fails login every time. |
| Password | `change_me_dev_only` (set in `docker-compose.yml`'s `app` service — change it there if you want a different one) |

### Stopping it

```bash
docker compose down      # stops the containers, KEEPS your data
docker compose down -v   # stops the containers AND wipes all data — fresh start next time
```

### If something seems broken

```bash
docker compose logs app        # see what the GNU Health server is doing/said
docker compose ps              # check both containers are actually running
docker compose restart app     # restart just the app without touching data
```

**"Login failed" / stuck after entering a password:** check
`docker compose logs app` for a line like `login failed for '<name>' ...` —
it tells you exactly what username was actually tried. The #1 cause is
typing the admin **email** (`admin@example.test`) instead of the username
(`admin`) — see the table above. If the log shows the right username
failing, double-check you're using the password currently set in
`docker-compose.yml` (it may have been changed from the default).

**This is not the production deployment.** The production path is
`deploy/provision.sh` + `deploy/nginx/` + `deploy/systemd/` running directly
on the VM, per GNU Health's own documented "vanilla" install method — GNU
Health doesn't officially support Docker. This directory is a test harness
only, built to validate that the underlying components (PostgreSQL, Tryton,
the GNU Health modules, the backup approach) behave the way the production
docs say they do.

Findings that came out of building this are reflected back into the
production scripts/docs, e.g. `scripts/backup.sh` was rewritten after this
harness revealed `ghcontrol`'s backup function is just `pg_dump` under a
curses menu, not the scriptable command the original script assumed.
