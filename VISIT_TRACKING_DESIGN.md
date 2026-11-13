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

## Before writing any code

Consistent with how every other feature in this repo was built — verify
against a real running instance, don't assume field names from
documentation alone:
1. Start the local Docker dev harness (`deploy/dev/`) and run
   `fields_get` against `gnuhealth.patient.evaluation`,
   `gnuhealth.prescription.order`, and `gnuhealth.prescription.line` to
   get the real machine field names (the docs above describe UI labels,
   not necessarily the exact field names the JSON-RPC API expects).
2. Activate `health_who_essential_medicines` in the dev harness and
   confirm the medicament list is actually populated before building
   the drug-search UI against it.
3. Prove the two-step create (evaluation, then prescription) end to end
   against the dev harness before touching the production VM, same as
   every other feature here.

## Open questions (need your call before implementing)

1. **Who actually uses the "Record Visit" screen?** `simple_ui` was
   built for front-desk (registration/search only). Diagnosis and
   prescriptions are clinical documentation — normally a doctor or
   nurse's job, not reception's. Should this be a doctor/nurse-facing
   addition to `simple_ui` (meaning it needs some notion of "who's
   logged in matters" beyond just reception), or is front-desk meant to
   transcribe from a doctor's paper notes?
2. **Health Professional field** — tied to #1: should the logged-in
   `simple_ui` user be required to have their own linked Health
   Professional record (like the `admin` gotcha hit earlier), or should
   the visit form have a doctor-selector dropdown (useful if one
   terminal is shared by multiple staff without individual logins)?
3. **Diagnosis: free text now, or coded (ICD-10) later?** Free text is
   much faster to build and matches what the Info Dx tab actually does
   today. Coded diagnosis would need a searchable autocomplete against
   thousands of `gnuhealth.pathology` records — real extra UI work, but
   gives structured data if reporting/analytics (or a future ABDM
   revisit) ever matters.
4. **Scope confirmation**: OK to build outpatient visits first and
   defer inpatient admission until wards/beds are configured for real?
