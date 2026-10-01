"""Proves the original requirement that kicked off this whole project:
'I should be able to query patient details using patient id or phone number.'

Uses proteus (Tryton's own official scripting client library — the same
one Tryton itself uses for its test suite) to talk to the running dev
server over JSON-RPC: creates a test patient with a phone number, then
looks them up both ways.

Run from deploy/dev/ with the stack up:
    python test_patient_lookup.py
"""
from __future__ import annotations

import os
import sys

from proteus import Model, config

DB_NAME = os.environ.get("GNUHEALTH_DATABASE", "gnuhealth_test")
ADMIN_PASSWORD = os.environ.get("GNUHEALTH_ADMIN_PASSWORD", "change_me_dev_only")
URL = os.environ.get("GNUHEALTH_URL", "http://localhost:8000")


def main() -> int:
    conn = config.set_xmlrpc(f"http://admin:{ADMIN_PASSWORD}@localhost:8000/{DB_NAME}")

    Party = Model.get("party.party")
    Patient = Model.get("gnuhealth.patient")

    unique_tag = os.environ.get("TEST_TAG", "smoketest")
    phone_number = "+91-9876543210"

    print(f"Creating a test party/patient (tag={unique_tag})...")
    party = Party()
    party.name = f"Test Patient {unique_tag}"
    party.is_person = True
    party.is_patient = True
    contact = party.contact_mechanisms.new()
    contact.type = "mobile"
    contact.value = phone_number
    party.save()

    patient = Patient()
    patient.name = party
    patient.save()
    print(f"Created patient with internal id={patient.id}, PUID={party.ref}")

    # --- Lookup 1: by patient ID (the internal database id / PUID) ---
    found_by_id = Patient.find([("id", "=", patient.id)])
    assert len(found_by_id) == 1, f"Expected 1 patient found by id, got {len(found_by_id)}"
    print(f"[PASS] Lookup by patient id {patient.id} -> found '{found_by_id[0].name.name}'")

    # --- Lookup 2: by phone number (via the party's contact mechanisms) ---
    PartyModel = Model.get("party.party")
    found_by_phone = PartyModel.find([("contact_mechanisms.value", "=", phone_number)])
    assert len(found_by_phone) == 1, f"Expected 1 party found by phone, got {len(found_by_phone)}"
    matching_patient = Patient.find([("name", "=", found_by_phone[0].id)])
    assert len(matching_patient) == 1, "Party found by phone has no linked patient record"
    print(f"[PASS] Lookup by phone number {phone_number} -> found '{found_by_phone[0].name}'")

    print("\nBoth lookup paths confirmed working against a live GNU Health instance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
