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
                ["id", "puid", "party.name", "party.gender", "party.dob"],
                limit=50,
            )
            for row in results:
                row["age_years"] = compute_age_years(row["party."]["dob"])
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
    return render_template("patient_detail.html", patient=records[0])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
