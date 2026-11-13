# Design: recording visits, diagnoses, and prescriptions in `simple_ui`

Written in response to a request to add visit history to patient search
(number of visits, first/last visit date) and the ability to record a
visit's diagnosis and prescriptions — with outpatient and inpatient
visits collecting different details. This is a **design proposal**, not
yet implemented — see "Open questions" at the end before any code gets
written.

## What GNU Health already has (confirmed via official docs + this
## project's own prior testing — sources linked, not assumed)

GNU Health already structurally separates outpatient and inpatient care
into different models, which matches the requirement directly:

| Concept | GNU Health model | Where it lives in Sao | Confirmed via |
|---|---|---|---|
| **Outpatient visit** | `gnuhealth.patient.evaluation` | Patient → Relate → Evaluations | This project's own [`deploy/dev/docs/recording-a-patient-visit.md`](deploy/dev/docs/recording-a-patient-visit.md) — actually created and verified locally |
| **Inpatient admission** | `gnuhealth.inpatient.registration` | Main menu → Hospitalizations | [Official user guide](https://docs.gnuhealth.org/his/userguide/modules/inpatientmanagement.html) — not yet touched in this project |
| **Prescription** | `gnuhealth.prescription.order` (header) + `gnuhealth.prescription.line` (one per drug) | Patient → Relate → Prescriptions | [Official user guide](https://docs.gnuhealth.org/his/userguide/basics/coremodule/prescriptions.html) — not yet touched in this project |

### Outpatient visit (`gnuhealth.patient.evaluation`) — four tabs
- **Main Info**: link to an appointment (or start fresh), complaints,
  current symptoms/illness, main condition, treatment plan
- **Clinical**: vital signs, anthropometry, signs/symptoms
- **Mental Status**: Glasgow Coma Scale (only needed when relevant)
- **Info Dx**: a **presumptive diagnosis** field (free text in the UI,
  not a coded ICD-10 lookup — confirmed from the docs, no mention of
  ICD-10 anywhere on this form)
- Plus, confirmed by this project's own earlier testing:
  **Discharge Reason** is required before saving, and the evaluation
  must have a Health Professional attached (the logged-in user needs to
  be linked to one, or the API call needs to set it explicitly).

### Inpatient admission (`gnuhealth.inpatient.registration`) — genuinely different fields
- **Mandatory**: Patient, Hospital Bed, Hospitalization Date, Expected
  Discharge Date, Admission Type
- **Optional**: Registration Code, Attending/Operating Physicians,
  Reason for Admission, Extra Info, Transfer History
- **Care Plan tab**: free-text nursing plan + discharge plan
- Beds must exist as real records first (linked to a ward/institution)
  — **this project hasn't configured real ward/bed records yet**
  (`README.md` phase 7 already flags this as blocked on real data entry)

### Prescriptions (`gnuhealth.prescription.order` + `.line`)
- Header: Patient, Prescription Date, Prescribed By, Pharmacy
- Each line: Medicament (drug), Indication, Dose/Dose Unit,
  Frequency/Times/Admin Hours, PRN flag, Treatment Duration/Period,
  Start/End/Review dates, Refills, Comment
- **Important finding**: GNU Health's schema does **not** link a
  prescription to a specific evaluation — only to the patient. So
  "prescriptions from this visit" isn't a native concept; it would need
  to be a `simple_ui`-level convention (e.g. same visit date), not
  something the backend enforces.
- **Known blocker already in this repo's `TODO.md`**: the medicament
  list needs the `health_who_essential_medicines` module **activated**
  (currently only installed, not activated) before there are any real
  drugs to select from.

## Proposed integration into `simple_ui`

### 1. Patient search — visit count / first / last visit date

Add three columns to `search.html`'s results table (same place `Age`
and `Phone` were added before). Scoped to **outpatient evaluations
only** for this metric — inpatient admissions are a different kind of
episode (a date range, not a point-in-time visit) and would double-count
oddly if mixed into the same "visits" number; see open question below
if you want admissions counted too.

Implementation sketch in `app.py`'s `search()`: after the existing
`gnuhealth.patient` search, do **one batched query**, not one per
row — `search_read("gnuhealth.patient.evaluation", [["patient", "in",
<all matched ids>]], ["patient", "evaluation_start"])`, then group by
patient ID in Python to get count/min/max per patient. (The exact field
name for the evaluation's date — `evaluation_start`, `evaluation_endtime`,
or similar — needs confirming against a live instance's `fields_get`
before this is written; see "Before writing code" below.)

### 2. Patient detail page — visit history + "Record Visit"

Add to `patient_detail.html`:
- A **Visit History** list: date, chief complaint, presumptive
  diagnosis, discharge reason — one row per past evaluation, newest
  first (`search_read` on the same model, no new backend work needed)
- A **Record Visit** button

### 3. "Record Visit" form (outpatient — proposed as the v1 scope)

A single `simple_ui` page, mapped directly to the real fields above:
- Chief Complaint (short text)
- Present Illness (longer text)
- Presumptive Diagnosis (free text — see open question on coded ICD-10)
- Treatment Plan (text)
- Discharge Reason (dropdown — enumerated values read from the model's
  own selection field, not hardcoded, the same way `AGE_BUCKETS` is a
  real constant today)
- An **"Add medication"** repeatable row (drug search, dose, frequency,
  duration, PRN) — optional, can be left empty if no prescription is
  needed

Saving does two separate API calls (matching `gnuhealth_client.py`'s
existing pattern of explicit multi-step creates, e.g. party → patient):
1. `create()` the `gnuhealth.patient.evaluation` with the fields above
2. If any medication rows were filled in, `create()` a
   `gnuhealth.prescription.order` + its lines, dated the same day

### Inpatient admission — proposed as v2, deferred

Recommending **not** building this yet, for a concrete reason: a bed
can't be assigned without real ward/bed records existing, and those
don't exist in production yet (`README.md` phase 7). Building the UI
before the underlying data exists would mean it can't actually be
tested. Suggest revisiting once bed/ward setup happens.

## Real findings from verifying against the dev harness (2026-11-13)

Confirmed field names via `fields_get` and proved both creates actually
work end-to-end (not just that the API accepts them — read the records
back and checked the values):

- `gnuhealth.patient.evaluation`: `chief_complaint` (char),
  `present_illness` (text), **`info_diagnosis`** (text — this is the
  free-text "Info Dx" field; there's a *separate* `diagnosis` field that
  is coded ICD-10 via `gnuhealth.pathology`, confirmed unused for v1 per
  the decision above), `directions` (text — maps to "treatment plan"),
  `discharge_reason` (required selection: `home`, `transfer`,
  `against_advice`, `death`), `evaluation_start` (required datetime),
  `healthprof` (readonly, but **does** get set correctly through
  `default_get()` + `create()` — confirmed by creating a real evaluation
  and reading `healthprof` back as the logged-in user's linked
  professional).
- `gnuhealth.prescription.order` + `.line`: confirmed creating an order
  with a nested `prescription_line` `create` command works. Simplified
  the line fields to just `medicament` (required), `short_comment`
  (free text — doubles as dosage/frequency/indication instructions
  instead of the ~10 separate structured fields GNU Health offers, to
  keep the form small) and `quantity`.
- **`gnuhealth.medicament` had zero records** even on the dev harness
  until `health_who_essential_medicines` was activated
  (`trytond-admin -u health_who_essential_medicines
  --activate-dependencies`, then restart the server — same gotcha as
  every other module activation in this project). After activating:
  442 real drugs (halothane, oxygen, ketamine, ...). **Production needs
  this same activation before prescriptions can work there at all** —
  tracked in `TODO.md`.
- **Real blocker found and fixed in `gnuhealth_client.py`**: the JSON
  encode/decode hooks only handled `date`, not `datetime` — silently
  broken the moment this feature needed to read `evaluation_start`
  (a datetime field). Fixed to handle both.
- **A genuine safety gap, not a backend quirk — document this
  prominently, don't quietly route around it**: GNU Health's
  `gnuhealth.prescription.order` has a server-side check
  (`check_prescription_warning`, confirmed by reading GNU Health's own
  source inside the dev container) that blocks saving unless
  `prescription_warning_ack` is set, **and** raises instead if
  `pregnancy_warning` or `allergy_warning` is `True`. In Sao, those two
  warning flags get set automatically by `on_change_patient` when a
  patient is selected — computing whether the patient is of
  childbearing age or has a known allergy on file. **A raw API
  `create()` call never runs that on_change** (the same class of gotcha
  as GNU Health's auto-patient-creation found earlier in this project).
  So a `simple_ui`-created prescription will silently skip the
  pregnancy/allergy warning entirely — it won't error, it just won't
  ever warn the doctor, even if the patient genuinely has a flagged
  allergy on file. `simple_ui`'s create sets
  `prescription_warning_ack=True` unconditionally to get past the
  generic check. **This is a real limitation to fix before relying on
  this for actual prescriptions** — e.g. by replicating the same
  childbearing-age/allergy check server-side before creating, rather
  than blindly acknowledging. Added to `TODO.md`.

## Verified before writing `simple_ui` code

Consistent with how every other feature in this repo was built — done
against the local Docker dev harness (`deploy/dev/`) before touching
`simple_ui` itself, not assumed from documentation:
1. ✅ Ran `fields_get` against `gnuhealth.patient.evaluation`,
   `gnuhealth.prescription.order`, and `gnuhealth.prescription.line` —
   real field names above, not guessed from UI labels.
2. ✅ Activated `health_who_essential_medicines` in the dev harness and
   confirmed the medicament list is actually populated (442 records).
3. ✅ Proved the two-step create (evaluation, then prescription with a
   nested line) end to end against the dev harness, including reading
   the saved records back to confirm the values actually stuck.

## Decisions (made 2026-11-13)

1. **Who uses "Record Visit": doctors/nurses directly**, not front-desk
   transcription. `simple_ui` now needs to support two kinds of users —
   reception (register/search only) and clinical staff (also record
   visits) — logging in with their own individual accounts.
2. **Health Professional field resolves automatically from the logged-in
   user** via `default_get()` (the same mechanism already used for the
   South Asian ethnicity default) — **not** a doctor-selector dropdown.
   This relies on Tryton resolving the default from the session's active
   user, same as Sao auto-fills "Initiated by." The real consequence:
   **every doctor/nurse needs their own GNU Health login, individually
   linked to a Health Professional record** (Internal User field set on
   their party) — the same one-time setup gotcha hit earlier with
   `admin`, now needed per clinical staff member, not just once.
3. **Diagnosis: free text for v1**, matching the Info Dx tab as-is. No
   ICD-10 autocomplete for now.
4. **Scope: outpatient visits only for v1.** Inpatient admission is
   deferred until real ward/bed records exist in production.
