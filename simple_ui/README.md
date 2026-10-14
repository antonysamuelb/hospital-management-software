# simple_ui — a minimal front-desk app, replacing Sao

Built in response to direct feedback: *"the current UI is too complex...
we need only patient registration. Two buttons: new registration / old
registration. Also filters based on age buckets / sex. Patients
searchable based on patient id and phone numbers."*

This is a **separate, custom-built web app** — not a GNU Health/Sao
customization. It's the option discussed earlier as "full design freedom,
but a second codebase to maintain" — that tradeoff was accepted
explicitly ("dump this UI and just build a simple UI").

**GNU Health stays the system of record.** This app has no database of
its own — it talks to the same GNU Health instance over its JSON-RPC API
(the same protocol Sao and `proteus` use), so every patient registered
here is a completely normal GNU Health record: same PUID generation,
same required-field validation, same South Asian ethnicity default, same
audit trail. You can open Sao and see exactly what this app created, and
vice versa.

## What's implemented (verified against a live instance, not just written)

- **Login**, using real GNU Health accounts/passwords — including
  restricted ones like the `reception` account from `deploy/dev/docs/
  simplified-front-desk-role.md`. No separate user system.
- **Landing page**: exactly two buttons, New Registration and Find Patient.
- **New Registration**: name, sex, date of birth (optional), phone
  (optional). Shows the generated Patient ID (PUID) on success.
- **Find Patient**: one search box (matches patient ID, phone number, or
  name — partial matches work), plus Age and Sex dropdown filters, used
  together or separately.
- **Patient detail page**: name, PUID, sex, date of birth, phone.

## What's NOT implemented yet

- Recording a visit (GNU Health calls this a "Patient Evaluation") —
  out of scope for this pivot so far; still has to be done in Sao.
- Editing an existing patient's details.
- Any administrative function (that's what the full Sao UI + `admin`
  account remain for).

## Running it

```bash
cd simple_ui
pip install -r requirements.txt

# Point at your GNU Health instance (defaults match deploy/dev/):
export GNUHEALTH_URL=http://localhost:8000      # Windows: set GNUHEALTH_URL=...
export GNUHEALTH_DATABASE=gnuhealth_test
export SIMPLE_UI_SECRET_KEY=something-random     # see Security below

python app.py
```

Open **http://localhost:5050/** and log in with any real GNU Health
account on that database (e.g. the `reception` account, or `admin`).

Needs the GNU Health instance from `deploy/dev/` (or production) actually
running first — see `deploy/dev/README.md#starting-it`.

## Architecture notes

- `gnuhealth_client.py` — a small, dependency-free JSON-RPC client (just
  the Python standard library). Deliberately not using `proteus` (used
  elsewhere in this repo for one-off scripts) — proteus fetches full
  model metadata per `Model.get()` call, more overhead than a small web
  app needs. See the module's own docstring for three real gotchas found
  and worked around while building it (session auth header format, why a
  raw `create()` doesn't auto-create the linked patient record the way
  Sao/proteus do, and why `default_get` has to be called and merged in
  by hand).
- `app.py` — plain Flask, server-rendered HTML (Jinja2 templates), no
  JavaScript framework. Session cookie stores only the GNU Health
  session token (never the password).
- Age buckets are computed from Date of Birth server-side
  (`age_bucket_to_dob_range()`), since GNU Health's displayed "Age"
  field is a read-only computed value, not something you can filter on
  directly — confirmed via `fields_get` before building this (`searchable:
  False`).

## Security — this is dev-config right now, not production-ready

- `app.py` runs Flask's own dev server (`debug=True`). **Do not** expose
  this beyond localhost/a trusted LAN as-is — switch to a real WSGI
  server (gunicorn, same idea as `deploy/systemd/gnuhealth.service`
  already does for GNU Health itself) and turn debug mode off first.
- `SIMPLE_UI_SECRET_KEY` defaults to a placeholder if not set. Set a real
  one via the environment before this touches real patient data.
- No CSRF protection or rate-limiting yet. Fine for a trusted LAN
  front-desk terminal; not fine for anything internet-facing.
- No separate authentication is implemented, which is deliberate — login
  always goes through GNU Health's own accounts, keeping one source of
  truth for who's allowed to do what.
