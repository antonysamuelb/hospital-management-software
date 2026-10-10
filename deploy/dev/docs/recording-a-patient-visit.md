# Recording a patient visit — walkthrough

GNU Health's term for a patient visit/encounter is **Patient Evaluation**
(`gnuhealth.patient.evaluation`) — chief complaint, present illness, exam
findings, diagnosis, treatment plan. Verified step-by-step against the
live `deploy/dev/` instance, including two real blockers hit along the way.

Not running yet? See [`deploy/dev/README.md`](../README.md#starting-it).

## One-time setup: link your login to a Health Professional

**Do this once, before anyone can record a visit.** Try to create an
evaluation without it and you'll hit:
> SM-CORE-0007: Currently logged in user is not associated to a health
> professional. See "Internal User" field of "Parties/People" form.

GNU Health requires every evaluation to have a Health Professional attached
(the `admin` superuser account isn't automatically one). Steps:

1. **Health → Health Professionals → +** (new).
2. In the "Health Prof" field, type a name and click **Create...** — same
   quick-create party dialog as registering a patient (set Gender, it'll
   default Ethnicity to South Asian per this project's customization).
3. Save the quick-create dialog, then **Save the Health Professional
   record itself** (the main toolbar save icon).
4. The quick-create dialog does **not** expose the field needed to finish
   linking it to your login — "Internal User" only exists on the full
   party record, not the condensed popup. Easiest way: open that party
   record and set **Internal User** to your login (`admin`) there, under
   the party's General info. (We did this via the API in one line during
   development — see `git log` for the exact commit if you want a script
   instead of clicking through it.)

Once linked, "Initiated by" on new evaluations auto-fills with your name —
that's the sign it worked.

## Steps to record a visit

1. Open the patient's record: **Health → Patients**, then click a
   non-link cell (e.g. the PUID column) and **double-click** the row —
   single-clicking the patient's name instead opens the simpler party
   record, not the full patient form you need here.
2. Click the **chain-link icon** (🔗, with a dropdown arrow) in the
   toolbar — this is Tryton's "Relate" button, listing: Appointments,
   Conditions, E-mail Archives, ECGs, **Evaluations**, Prescriptions,
   Vaccinations.
3. Click **Evaluations**, then the green **+** to start a new one.
4. Fill in at minimum:
   - **Patient** (may already be pre-filled from context)
   - **Chief Complaint** (short summary, e.g. "Fever and cough for 3 days")
   - **Present Illness** (fuller narrative)
   - Optionally: Physical exam, Diagnostic Judgement, Therapeutic and Dx
     Plan, and the Clinical/Mental/Info Dx/Procedures/Administrative tabs
     for more structured detail
5. **Before saving**, scroll down and set **Discharge Reason** (e.g.
   "Home / Selfcare") — see Gotcha below, it's required but not obviously
   marked as such.
6. Click **Save** (toolbar floppy-disk icon).

## Gotcha: "Discharge Reason" is required but not visually flagged

Clicking Save without setting it fails with `"Discharge Reason" is
required.` — easy to miss since nothing on the form visually marks it as
mandatory before you try to save. It's near the bottom, next to a
**DISCHARGE** button; set it to whatever fits (Home/Selfcare,
Transferred, Left against medical advice, Death) before saving.

## Verified

Created a real evaluation for patient "Mary Ann": Chief Complaint "Fever
and cough for 3 days", Present Illness narrative, Discharge Reason "Home
/ Selfcare", health professional "Dr. Admin" correctly auto-attached.
Confirmed saved via the API (not just that the form closed without
error) — `gnuhealth.patient.evaluation` id 1, all fields intact.
