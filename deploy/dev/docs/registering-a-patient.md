# Registering a patient — walkthrough

Verified step-by-step against the live `deploy/dev/` instance (GNU Health 5.0,
trytond 7.0.57), not written from documentation. Two real UI quirks are
called out below because they'll trip you up otherwise — they're GNU
Health/Sao's own behavior, not something specific to this setup.

Not running yet? See [`deploy/dev/README.md`](../README.md#starting-it) for
how to start the stack first.

## Steps

1. Log in at `http://localhost:8000/` — Database `gnuhealth_test`, your admin
   user/password (see `deploy/dev/docker-compose.yml`'s `app` service
   environment for the dev defaults).
2. Left menu → **Health → Patients**.
3. Click the green **+** (new) icon in the toolbar.
4. In **Main Info**, click the name field (magnifying-glass icon) and type
   the patient's name. A dropdown offers **Search...** / **Create...** —
   click **Create...**.
5. A "Patient" quick-create dialog opens, pre-checked with **Person** and
   **Patient** already ticked (this matters — see Gotcha 1 below). Fill in:
   - **Gender** (required — see Gotcha 2 below for how to actually get this
     to stick)
   - Switch to the **General** tab → **Contact Mechanisms** panel → click
     the green **+** → set **Type** (e.g. "Phone" or "Mobile") → click into
     **Value** and type the phone number.
6. Click **SAVE** on the dialog. It closes and returns you to the outer
   "New Patient" form with the party now linked.
7. **Do not click Save again on the outer form — see Gotcha 1.** Just close
   the tab (the **×** next to "Patient" at the top) and choose **No** when
   asked whether to save changes. The patient already exists.
8. Health → Patients list now shows the new patient, with an auto-generated
   **PUID** (e.g. `GUX953CGG`) — that's the human-readable ID to search by,
   alongside the phone number entered in step 5.

## Gotcha 1: "The Patient already exists!"

GNU Health auto-creates the linked `gnuhealth.patient` record the moment the
party is saved with **Patient** checked — which it is, by default, in the
quick-create dialog. If you then click **Save** on the *outer* "New Patient"
form (the one you opened in step 3), it tries to create a **second** patient
record for the same party and fails with `The Patient already exists !`.

This is the UI-level version of the exact same bug we hit via the API in
`deploy/dev/test_patient_lookup.py` — same root cause, different surface.

**Fix:** after the quick-create dialog saves, just discard the outer form
(step 7). The patient is already in the database; nothing is lost by not
saving again.

## Gotcha 2: the Gender dropdown doesn't stick if you click straight to Save

Selecting Gender and immediately clicking **SAVE** can silently fail
validation ("Gender" is required, in a red banner) even though the field
visually shows a value. The fix: after selecting Gender, click or Tab into
another field first (to fire the widget's change/blur event) *before*
clicking Save. Clicking the field with the mouse and using arrow keys +
Tab to move off it is the most reliable method found during testing.

## Screenshot

`deploy/dev/screenshots/patients-list-after-registration.jpg` — the patient
list after this walkthrough, showing both the test patient from earlier
automated testing (PUID `QAN111KTI`) and "Ramesh Kumar" registered via this
walkthrough (PUID `GUX953CGG`).

## Next: finding this patient again

See [`searching-for-a-patient.md`](searching-for-a-patient.md) — confirms
you can look this patient up again by phone number, PUID, or name.
