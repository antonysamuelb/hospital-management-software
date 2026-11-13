"""Reusable introspection tool -- dumps fields_get() (and selection
options) for one or more GNU Health models, against the local dev
harness. Used to get real machine field names and selection values
before writing any simple_ui code against a model, instead of guessing
from GNU Health's user-facing documentation (which describes UI labels,
not the JSON-RPC API's actual field names). See VISIT_TRACKING_DESIGN.md
for an example of findings this surfaced.

Run from deploy/dev/ with the harness up:
    python introspect_fields.py gnuhealth.patient.evaluation gnuhealth.prescription.order
"""
import base64
import json
import sys
import urllib.request

BASE_URL = "http://localhost:8000"
DATABASE = "gnuhealth_test"
USERNAME = "admin"
PASSWORD = "change_me_dev_only"

_request_id = 0


def rpc(method, params, session=None):
    global _request_id
    _request_id += 1
    payload = json.dumps({"id": _request_id, "method": method, "params": params}).encode()
    headers = {"Content-Type": "application/json"}
    if session:
        username, user_id, token = session
        auth = base64.b64encode(f"{username}:{user_id}:{token}".encode()).decode()
        headers["Authorization"] = f"Session {auth}"
    req = urllib.request.Request(f"{BASE_URL}/{DATABASE}/", data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read())
    if body.get("error"):
        raise RuntimeError(body["error"])
    return body["result"]


def login():
    user_id, token = rpc("common.db.login", [USERNAME, {"password": PASSWORD}, "en"])
    return (USERNAME, user_id, token)


def dump_fields(model, session):
    print(f"=== {model} ===")
    fields = rpc(f"model.{model}.fields_get", [None, {"context": {}}], session=session)
    for name, meta in sorted(fields.items()):
        required = meta.get("required", False)
        readonly = meta.get("readonly", False)
        selection = meta.get("selection")
        print(f"  {name:30s} type={meta.get('type'):12s} required={required!s:5s} readonly={readonly!s:5s} "
              f"relation={meta.get('relation')!s:30s}")
        if selection:
            print(f"      selection: {selection}")
    print()


def main():
    models = sys.argv[1:]
    if not models:
        print(__doc__)
        return 1
    session = login()
    print(f"Logged in as user_id={session[1]}\n")
    for model in models:
        dump_fields(model, session)
    return 0


if __name__ == "__main__":
    sys.exit(main())
