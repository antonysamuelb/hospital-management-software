# A simplified role for reception/front-desk staff

Answers feedback that the full UI is too complex for someone who only
needs to register and look up patients. Verified by actually creating the
account and logging in as it, not just reading docs.

## What this gets you (verified)

GNU Health ships a built-in group, **"Health Front Desk"**, intended for
exactly this role. Assigning a user to *only* this group (no other
groups):

| | Full admin (all groups) | Reception account (Health Front Desk only) |
|---|---|---|
| Top-level menu categories | ~9 (Party, Product, Currency, Companies, Health, Administration, ...) | **2** (Party, Health) |
| Total menu items | 157 | **13** |
| Prescriptions, Hospitalizations, Nursing, Reporting, Configuration, Administration | Visible | **Not visible at all** |

The 13 remaining items: under Party — Parties, Addresses, Contact
Mechanisms, Categories; under Health — Patients, Patient procedures,
Appointments, Health Professionals, Institutions, Demographics, Books of
Life, Help and Documentation, Online Documentation.

**Patient registration and search both work exactly as before** under
this restricted account — confirmed by searching a patient by PUID while
logged in as the reception account and getting a correctly filtered
result.

## How to create one

```python
# Run via proteus (see deploy/dev/test_patient_lookup.py for connection
# setup), or do the equivalent by hand in Administration > User
# Configuration > Users:
from proteus import Model, config
config.set_xmlrpc('http://admin:<password>@localhost:8000/<database>/')

User = Model.get('res.user')
Group = Model.get('res.group')

fd_group = Group.find([('name', '=', 'Health Front Desk')])[0]

u = User()
u.name = 'Reception Desk'
u.login = 'reception'          # whatever login you want
u.groups.append(fd_group)      # ONLY this group — no others
u.password = '<a real password, not this one>'
u.save()
```

## What this does NOT get you (corrected after testing)

I initially assumed `res.user`'s `menu` field could redirect a user
straight to the Patients list on login, skipping the sidebar entirely.
**That's wrong** — its domain (`[["usage","=","menu"]]`) only lets you
choose between separate top-level *menu trees*, and this install only
has one (`"Menu"`, the one everyone uses). So reception staff still see
a short sidebar (13 items) rather than landing directly on Patients with
zero clicks. Correcting this claim rather than leaving it implied.

A **literal two-button landing page** (New Registration / Find Patient,
nothing else) needs real building — not available out of the box:
- **Smaller next step, still no separate app**: a few of the 13 visible
  items (Patient procedures, Health Professionals, Institutions,
  Demographics, Books of Life, Contact Mechanisms, Categories) aren't
  actually gated by the Health Front Desk group at all — they have no
  group restriction in GNU Health's own menu definitions, so they show
  for every logged-in user regardless of role. Adding a restriction to
  those too would get reception down to effectively just Patients +
  Appointments + Parties. Small, scoped follow-up if wanted.
- **Real two-button screen**: a small custom Tryton module (same pattern
  as `custom_modules/health_default_ethnicity/`) adding an actual wizard
  view, set as the landing action. Moderate effort, stays in one
  codebase.
- **Separate lightweight web app**: full design freedom, calls GNU
  Health's JSON-RPC API for just registration + search, but is a second
  codebase to build and maintain long-term — a real architecture
  decision, not just a config change.

## Not done yet (by request)

Age-bucket filtering was raised in the same conversation but explicitly
deferred. Note for later: the "Age" column is a computed, non-searchable
display field (`searchable: False` in `fields_get`) — Date of Birth is
the actual searchable field underneath it, so age-bucket filters need to
be built as DOB-range logic (a small custom field), not a native checkbox.
Sex/gender filtering already works natively today (`gender` is a
standard searchable selection field).
