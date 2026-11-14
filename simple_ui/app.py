"""simple_ui — a deliberately small front-desk app, replacing Sao for
day-to-day reception use.

Two things on the landing page (new registration, find patient), a
search with age-bucket + sex filters, lookup by patient ID or phone —
per the explicit feedback this was built for: "the current UI is too
complex."

GNU Health itself (Tryton/Sao) stays as the system of record underneath
— this talks to it over the same JSON-RPC API proteus/Sao use (see
gnuhealth_client.py), so every record created here is a completely
normal GNU Health party+patient, visible and editable in Sao too, with
full audit trail (who did what) preserved. This is NOT a separate
database or a bypass of GNU Health's validation — registrations still
go through the same business logic (required Gender, auto PUID
generation, the South Asian ethnicity default, etc.).

Run (see simple_ui/README.md for the full walkthrough):
    pip install -r requirements.txt
    python app.py
"""
from __future__ import annotations

import datetime
import os

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

from gnuhealth_client import AuthenticationError, GNUHealthClient, GNUHealthError

GNUHEALTH_URL = os.environ.get("GNUHEALTH_URL", "http://localhost:8000")
GNUHEALTH_DATABASE = os.environ.get("GNUHEALTH_DATABASE", "gnuhealth_test")

app = Flask(__name__)
app.secret_key = os.environ.get("SIMPLE_UI_SECRET_KEY", "dev-only-change-me")

# Age buckets shown in the search filter. (label, min_age_inclusive, max_age_inclusive)
# max_age=None means "no upper bound".
AGE_BUCKETS = [
    ("0-5", 0, 5),
    ("6-12", 6, 12),
    ("13-18", 13, 18),
    ("19-40", 19, 40),
    ("41-60", 41, 60),
    ("61+", 61, None),
]

SEX_OPTIONS = [("m", "Male"), ("f", "Female")]

# Fields a brand-new party needs server defaults for, so create_with_defaults
# can merge them in (see gnuhealth_client.py docstring for why this matters).
PARTY_DEFAULT_FIELDS = [
    "is_person", "is_patient", "ethnic_group", "activation_date",
    "fed_country", "citizenship", "residence",
]

# gnuhealth.patient.evaluation's discharge_reason is a required selection
# field -- confirmed against a live instance via fields_get (see
# VISIT_TRACKING_DESIGN.md), hardcoded here the same way AGE_BUCKETS is
# rather than fetched fresh on every request, since these are stable
# values baked into the GNU Health module itself, not per-hospital data.
DISCHARGE_REASONS = [
    ("home", "Home / Selfcare"),
    ("transfer", "Transferred to another institution"),
    ("against_advice", "Left against medical advice"),
    ("death", "Death"),
]

# healthprof is readonly in the form (auto-resolved from the logged-in
# user, the same mechanism as the ethnicity default) but evaluation_start
# still needs a default merged in via default_get -- see
# gnuhealth_client.py's create_with_defaults(). Confirmed both actually
# resolve correctly through create_with_defaults() against a live
# instance (see VISIT_TRACKING_DESIGN.md).
VISIT_DEFAULT_FIELDS = ["evaluation_start", "healthprof"]
PRESCRIPTION_DEFAULT_FIELDS = ["prescription_date", "healthprof"]

# Fixed number of optional medication rows on the Record Visit form --
# no JS "add another row" needed for a form this small. Each row is
# skipped entirely if no medicament was chosen.
PRESCRIPTION_LINE_SLOTS = 5


def _safe_replace_year(d: datetime.date, year: int) -> datetime.date:
    """date.replace(year=...) but doesn't crash on Feb 29 in a non-leap year."""
    try:
        return d.replace(year=year)
    except ValueError:
        return d.replace(year=year, day=28)


def age_bucket_to_dob_range(min_age: int, max_age: int | None, today: datetime.date | None = None):
    """Convert an age bucket to a (earliest_dob, latest_dob) range.

    Older people have EARLIER dates of birth, so min_age maps to the
    upper (later/more recent) DOB bound and max_age maps to the lower
    (earlier) DOB bound.
    """
    today = today or datetime.date.today()
    latest_dob = _safe_replace_year(today, today.year - min_age)
    if max_age is None:
        earliest_dob = datetime.date(1900, 1, 1)
    else:
        earliest_dob = _safe_replace_year(today, today.year - max_age - 1) + datetime.timedelta(days=1)
    return earliest_dob, latest_dob


def compute_age_years(dob: datetime.date | None, today: datetime.date | None = None) -> int | None:
    """Whole years of age as of `today`, or None if DOB is unknown.

    GNU Health's own "Age" display (seen in Sao) breaks this down into
    years/months/days; this app only needs whole years for a quick
    front-desk glance, matched against the AGE_BUCKETS definitions.
    """
    if dob is None:
        return None
    today = today or datetime.date.today()
    years = today.year - dob.year
    # Subtract one if this year's birthday hasn't happened yet.
    if (today.month, today.day) < (dob.month, dob.day):
        years -= 1
    return years


def summarize_visits(rows: list[dict]) -> dict[int, dict]:
    """Group evaluation rows (each with 'patient' and 'evaluation_start')
    into per-patient stats: count, first (earliest), last (latest).

    Takes a flat list so the caller can fetch all matched patients'
    evaluations in ONE batched search_read, instead of one query per
    search result row.
    """
    summary: dict[int, dict] = {}
    for row in rows:
        patient_id = row["patient"]
        start = row["evaluation_start"]
        stats = summary.setdefault(patient_id, {"count": 0, "first": start, "last": start})
        stats["count"] += 1
        if start < stats["first"]:
            stats["first"] = start
        if start > stats["last"]:
            stats["last"] = start
    return summary


def get_client() -> GNUHealthClient | None:
    """Reconstruct an authenticated client from the Flask session, or
    None if not logged in."""
    if "gnuhealth_session" not in session:
        return None
    client = GNUHealthClient(GNUHEALTH_URL, GNUHEALTH_DATABASE)
    client.username = session["gnuhealth_username"]
    client.user_id = session["gnuhealth_user_id"]
    client.session = session["gnuhealth_session"]
    return client


def require_login():
    client = get_client()
    if client is None:
        return None
    return client


@app.before_request
def _ensure_logged_in():
    exempt = {"login", "static"}
    if request.endpoint in exempt:
        return None
    if get_client() is None:
        return redirect(url_for("login", next=request.path))
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    client = GNUHealthClient(GNUHEALTH_URL, GNUHEALTH_DATABASE)
    try:
        client.login(username, password)
    except AuthenticationError:
        flash("Incorrect username or password.", "error")
        return render_template("login.html", username=username)
    except GNUHealthError as e:
        flash(f"Could not reach the server: {e}", "error")
        return render_template("login.html", username=username)

    session["gnuhealth_username"] = client.username
    session["gnuhealth_user_id"] = client.user_id
    session["gnuhealth_session"] = client.session
    next_url = request.args.get("next") or request.form.get("next")
    return redirect(next_url or url_for("landing"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def landing():
    return render_template("landing.html", username=session.get("gnuhealth_username"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", sex_options=SEX_OPTIONS)

    client = require_login()
    name = request.form.get("name", "").strip()
    sex = request.form.get("sex", "")
    phone = request.form.get("phone", "").strip()
    dob_raw = request.form.get("dob", "").strip()

    errors = []
    if not name:
        errors.append("Name is required.")
    if sex not in dict(SEX_OPTIONS):
        errors.append("Sex is required.")
    dob = None
    if dob_raw:
        try:
            dob = datetime.date.fromisoformat(dob_raw)
        except ValueError:
            errors.append("Date of birth must be a valid date.")

    if errors:
        for e in errors:
            flash(e, "error")
        return render_template(
            "register.html", sex_options=SEX_OPTIONS,
            name=name, sex=sex, phone=phone, dob=dob_raw,
        )

    party_values = {
        "name": name,
        "is_person": True,
        "is_patient": True,
        "gender": sex,
    }
    if dob is not None:
        party_values["dob"] = dob
    if phone:
        party_values["contact_mechanisms"] = [
            ["create", [{"type": "mobile", "value": phone}]]
        ]

    try:
        party_id = client.create_with_defaults(
            "party.party", party_values, default_fields=PARTY_DEFAULT_FIELDS,
        )
        patient_id = client.call("gnuhealth.patient", "create", [{"party": party_id}])[0]
        patient = client.read("gnuhealth.patient", [patient_id], ["id", "puid"])[0]
    except GNUHealthError as e:
        flash(f"Could not save: {e}", "error")
        return render_template(
            "register.html", sex_options=SEX_OPTIONS,
            name=name, sex=sex, phone=phone, dob=dob_raw,
        )

    return render_template(
        "register_success.html", name=name, puid=patient["puid"], patient_id=patient["id"],
    )


@app.route("/search")
def search():
    client = require_login()
    query = request.args.get("q", "").strip()
    age_bucket = request.args.get("age_bucket", "")
    sex = request.args.get("sex", "")

    results = []
    searched = bool(query or age_bucket or sex)

    if searched:
        domain_parts = []
        if query:
            domain_parts.append([
                "OR",
                ["party.name", "ilike", f"%{query}%"],
                ["party.contact_mechanisms.value", "ilike", f"%{query}%"],
                ["puid", "ilike", f"%{query}%"],
            ])
        if sex:
            domain_parts.append(["party.gender", "=", sex])
        if age_bucket:
            bucket = next((b for b in AGE_BUCKETS if b[0] == age_bucket), None)
            if bucket:
                earliest, latest = age_bucket_to_dob_range(bucket[1], bucket[2])
                domain_parts.append(["party.dob", ">=", earliest])
                domain_parts.append(["party.dob", "<=", latest])

        domain = ["AND"] + domain_parts if len(domain_parts) > 1 else domain_parts[0]

        try:
            results = client.search_read(
                "gnuhealth.patient", domain,
                ["id", "puid", "party.name", "party.gender", "party.dob",
                 "party.contact_mechanisms.value"],
                limit=50,
            )
            for row in results:
                row["age_years"] = compute_age_years(row["party."]["dob"])
                phones = row["party."]["contact_mechanisms."]
                row["phone_display"] = ", ".join(cm["value"] for cm in phones) if phones else None

            # One batched query for ALL matched patients' visit history,
            # not one query per row -- see summarize_visits()'s docstring.
            if results:
                visit_rows = client.search_read(
                    "gnuhealth.patient.evaluation",
                    # The extra wrapping list is NOT optional here --
                    # confirmed against a live instance that a bare
                    # ["field", "in", [ids]] triple at the top level gets
                    # misparsed (Tryton's domain parser tries to interpret
                    # the list value itself as a nested domain), raising
                    # "invalid literal for int() with base 10: 'AND'".
                    # Every other domain elsewhere in this file uses a
                    # scalar value, which doesn't hit this.
                    [["patient", "in", [row["id"] for row in results]]],
                    ["patient", "evaluation_start"],
                )
                visit_summary = summarize_visits(visit_rows)
                for row in results:
                    stats = visit_summary.get(row["id"])
                    row["visit_count"] = stats["count"] if stats else 0
                    row["first_visit"] = stats["first"] if stats else None
                    row["last_visit"] = stats["last"] if stats else None
        except GNUHealthError as e:
            flash(f"Search failed: {e}", "error")

    return render_template(
        "search.html", query=query, age_bucket=age_bucket, sex=sex,
        age_buckets=AGE_BUCKETS, sex_options=SEX_OPTIONS,
        results=results, searched=searched,
    )


@app.route("/patient/<int:patient_id>")
def patient_detail(patient_id: int):
    client = require_login()
    try:
        records = client.search_read(
            "gnuhealth.patient", ["id", "=", patient_id],
            ["id", "puid", "party.name", "party.gender", "party.dob",
             "party.contact_mechanisms.value", "party.contact_mechanisms.type"],
        )
    except GNUHealthError as e:
        flash(f"Could not load patient: {e}", "error")
        return redirect(url_for("search"))

    if not records:
        abort(404)

    discharge_labels = dict(DISCHARGE_REASONS)
    try:
        visits = client.search_read(
            "gnuhealth.patient.evaluation", ["patient", "=", patient_id],
            ["id", "evaluation_start", "chief_complaint", "info_diagnosis", "discharge_reason"],
            order=[("evaluation_start", "DESC")],
        )
        for visit in visits:
            visit["discharge_reason_display"] = discharge_labels.get(visit["discharge_reason"], "—")
    except GNUHealthError as e:
        flash(f"Could not load visit history: {e}", "error")
        visits = []

    return render_template("patient_detail.html", patient=records[0], visits=visits)


@app.route("/patient/<int:patient_id>/visit/new", methods=["GET", "POST"])
def record_visit(patient_id: int):
    client = require_login()
    try:
        patients = client.search_read(
            "gnuhealth.patient", ["id", "=", patient_id], ["id", "puid", "party.name"],
        )
    except GNUHealthError as e:
        flash(f"Could not load patient: {e}", "error")
        return redirect(url_for("search"))
    if not patients:
        abort(404)
    patient = patients[0]

    try:
        # rec_name is a computed (Function) field -- Tryton can't ORDER BY
        # it server-side (raises NotImplementedError), confirmed against
        # the dev harness. Sorting ~400 rows in Python instead is cheap
        # and avoids digging into gnuhealth.medicament's underlying
        # product.product relation just for a sort key.
        #
        # category is included because the WHO Essential Medicines List
        # genuinely lists the same drug multiple times under different
        # clinical-use categories (e.g. acetylsalicylic acid appears
        # under both "Non-opioids and non-steroidal anti-inflammatory
        # medicines" and "Antithrombotic medicines") -- confirmed
        # against the dev harness that strength/form/route are blank
        # for these, so category is the one field that actually
        # distinguishes them. Without it the dropdown shows the same
        # name several times with no way to tell them apart.
        medicaments = client.search_read(
            "gnuhealth.medicament", [], ["id", "rec_name", "category.name"],
        )
        for med in medicaments:
            category = med["category."]["name"] if med["category."] else None
            med["display_label"] = f"{med['rec_name']} ({category})" if category else med["rec_name"]
        medicaments.sort(key=lambda m: m["display_label"])
    except GNUHealthError as e:
        flash(f"Could not load the medication list: {e}", "error")
        medicaments = []

    form_context = dict(
        patient=patient, discharge_reasons=DISCHARGE_REASONS, medicaments=medicaments,
        line_slots=range(PRESCRIPTION_LINE_SLOTS),
    )

    if request.method == "GET":
        return render_template("record_visit.html", **form_context)

    chief_complaint = request.form.get("chief_complaint", "").strip()
    present_illness = request.form.get("present_illness", "").strip()
    info_diagnosis = request.form.get("info_diagnosis", "").strip()
    directions = request.form.get("directions", "").strip()
    discharge_reason = request.form.get("discharge_reason", "")

    errors = []
    if not chief_complaint:
        errors.append("Chief complaint is required.")
    if discharge_reason not in dict(DISCHARGE_REASONS):
        errors.append("Discharge reason is required.")

    if errors:
        for err in errors:
            flash(err, "error")
        return render_template(
            "record_visit.html", **form_context,
            chief_complaint=chief_complaint, present_illness=present_illness,
            info_diagnosis=info_diagnosis, directions=directions, discharge_reason=discharge_reason,
        )

    evaluation_values = {
        "patient": patient_id,
        "evaluation_type": "outpatient",
        "chief_complaint": chief_complaint,
        "discharge_reason": discharge_reason,
    }
    if present_illness:
        evaluation_values["present_illness"] = present_illness
    if info_diagnosis:
        evaluation_values["info_diagnosis"] = info_diagnosis
    if directions:
        evaluation_values["directions"] = directions

    try:
        client.create_with_defaults(
            "gnuhealth.patient.evaluation", evaluation_values, default_fields=VISIT_DEFAULT_FIELDS,
        )
    except GNUHealthError as e:
        flash(f"Could not save visit: {e}", "error")
        return render_template(
            "record_visit.html", **form_context,
            chief_complaint=chief_complaint, present_illness=present_illness,
            info_diagnosis=info_diagnosis, directions=directions, discharge_reason=discharge_reason,
        )

    # Optional prescription. NOTE on prescription_warning_ack: GNU
    # Health's own pregnancy/allergy warnings on a prescription are
    # normally computed by Sao's on_change_patient when a patient is
    # picked -- a raw API create() never runs that, so those warnings
    # never fire here. prescription_warning_ack is set True to get past
    # GNU Health's generic "has this been verified" check, NOT because
    # the warnings were actually checked. See VISIT_TRACKING_DESIGN.md's
    # "Real findings" section -- flagged as a real gap to close before
    # relying on this for actual prescriptions, not something to treat
    # as handled.
    lines = []
    for i in range(PRESCRIPTION_LINE_SLOTS):
        medicament_id = request.form.get(f"medicament_{i}", "").strip()
        if not medicament_id:
            continue
        line_values = {"medicament": int(medicament_id)}
        comment = request.form.get(f"comment_{i}", "").strip()
        if comment:
            line_values["short_comment"] = comment
        quantity = request.form.get(f"quantity_{i}", "").strip()
        if quantity.isdigit():
            line_values["quantity"] = int(quantity)
        lines.append(line_values)

    if lines:
        try:
            client.create_with_defaults(
                "gnuhealth.prescription.order",
                {
                    "patient": patient_id,
                    "prescription_warning_ack": True,
                    "prescription_line": [["create", lines]],
                },
                default_fields=PRESCRIPTION_DEFAULT_FIELDS,
            )
        except GNUHealthError as e:
            flash(f"Visit saved, but the prescription could not be saved: {e}", "error")

    flash("Visit recorded.", "success")
    return redirect(url_for("patient_detail", patient_id=patient_id))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
