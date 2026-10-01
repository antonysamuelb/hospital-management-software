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
    conn = config.set_xmlrpc(f"http://admin:{ADMIN_PASSWORD}@localhost:8000/{DB_NAME}/")

    Party = Model.get("party.party")
    Patient = Model.get("gnuhealth.patient")

    unique_tag = os.environ.get("TEST_TAG", "smoketest")
    phone_number = "+91-9876543210"

    print(f"Creating a test party/patient (tag={unique_tag})...")
    party = Party()
    party.name = f"Test Patient {unique_tag}"
    party.is_person = True
    party.is_patient = True
    party.gender = "f"
    contact = party.contact_mechanisms.new()
    contact.type = "mobile"
    contact.value = phone_number
    party.save()

    # GNU Health auto-creates the linked gnuhealth.patient record when a
    # party is saved with is_patient=True — confirmed by testing (an
    # earlier version of this script explicitly created one too and hit
    # "The Patient already exists !"). So: just look up the one that was
    # auto-created, rather than creating a second one.
    auto_created = Patient.find([("party", "=", party.id)])
    assert len(auto_created) == 1, f"Expected GNU Health to auto-create 1 patient record, found {len(auto_created)}"
    patient = auto_created[0]
    print(f"Patient auto-created by GNU Health: internal id={patient.id}, PUID={party.ref}")

    # --- Lookup 1a: by internal database id ---
    found_by_id = Patient.find([("id", "=", patient.id)])
    assert len(found_by_id) == 1, f"Expected 1 patient found by id, got {len(found_by_id)}"
    print(f"[PASS] Lookup by internal id {patient.id} -> found '{found_by_id[0].party.name}'")

    # --- Lookup 1b: by PUID (the human-readable patient ID, auto-generated
    #     by GNU Health, e.g. 'VFP116RRB' — what staff would realistically
    #     type in, not the raw internal row id) ---
    found_by_puid = Party.find([("ref", "=", party.ref)])
    assert len(found_by_puid) == 1, f"Expected 1 party found by PUID, got {len(found_by_puid)}"
    print(f"[PASS] Lookup by PUID {party.ref} -> found '{found_by_puid[0].name}'")

    # --- Lookup 2: by phone number (via the party's contact mechanisms) ---
    found_by_phone = Party.find([("contact_mechanisms.value", "=", phone_number)])
    assert len(found_by_phone) == 1, f"Expected 1 party found by phone, got {len(found_by_phone)}"
    matching_patient = Patient.find([("party", "=", found_by_phone[0].id)])
    assert len(matching_patient) == 1, "Party found by phone has no linked patient record"
    print(f"[PASS] Lookup by phone number {phone_number} -> found '{found_by_phone[0].name}'")

    print("\nAll lookup paths (internal id, PUID, phone number) confirmed working")
    print("against a live GNU Health instance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
