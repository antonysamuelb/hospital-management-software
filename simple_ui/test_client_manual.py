"""Manual smoke test for gnuhealth_client.py against a real running
instance. Not a pytest suite (needs a live server + credentials) — run
directly: python test_client_manual.py
"""
from gnuhealth_client import GNUHealthClient

client = GNUHealthClient("http://localhost:8000", "gnuhealth_test")
client.login("admin", "change_me_dev_only")
print("Logged in as", client.username, "user_id", client.user_id)

count_before = client.call("gnuhealth.patient", "search_count", [])
print("Patients before:", count_before)

party_id = client.create_with_defaults(
    "party.party",
    {
        "name": "Client Test Patient",
        "is_person": True,
        "is_patient": True,
        "gender": "f",
        "contact_mechanisms": [
            ["create", [{"type": "mobile", "value": "+91-9888000111"}]]
        ],
    },
    default_fields=[
        "is_person", "is_patient", "ethnic_group", "activation_date",
        "fed_country", "citizenship", "residence",
    ],
)
print("Created party id", party_id)

patient_id = client.call("gnuhealth.patient", "create", [{"party": party_id}])[0]
print("Created patient id", patient_id)

found = client.search_read(
    "gnuhealth.patient",
    ["party.contact_mechanisms.value", "ilike", "%9888000111%"],
    ["id", "puid", "party.name", "party.gender"],
)
print("Found by phone:", found)
assert len(found) == 1
assert found[0]["id"] == patient_id

# Cleanup
client.call("gnuhealth.patient", "delete", [patient_id])
client.call("party.party", "delete", [party_id])

count_after = client.call("gnuhealth.patient", "search_count", [])
print("Patients after cleanup:", count_after)
assert count_after == count_before

print("\nALL CHECKS PASSED")
