"""Minimal JSON-RPC client for GNU Health / Tryton.

Deliberately not using `proteus` (GNU Health's own scripting client) here:
proteus is convenient for one-off scripts (used throughout this repo's
deploy/dev/ testing) but is built around fetching full model metadata on
every `Model.get()` call — more overhead than a small web app serving
real users needs. This talks the same JSON-RPC protocol directly, using
only the standard library (no extra dependency beyond Flask itself).

Protocol details below were not assumed — each one was verified against
a live running instance before being relied on here (see the project's
git history / chat log for the verification commands):

- Login: POST {"method": "common.db.login", "params": [user, {"password":
  pw}, lang]} -> {"result": [user_id, session_token]}
- Authenticated calls: header `Authorization: Session <base64 of
  "username:user_id:session_token">`, method name "model.<model>.<method>"
- A raw `create()` call does NOT run the client-side on_change logic that
  Sao/proteus trigger automatically (e.g. GNU Health auto-creating the
  linked gnuhealth.patient record when a party is saved with
  is_patient=True happens via on_change, not a server-side create()
  hook) — so this client creates the party.party and gnuhealth.patient
  records as two explicit steps.
- A raw `create()` call also skips server-computed defaults (e.g. this
  project's own South Asian ethnicity default) unless you call
  `default_get` first and merge its result in — create_with_defaults()
  below does that merge automatically so every caller gets it for free.
- Field searchability is inconsistent between a model and its related
  display fields: gnuhealth.patient's own `gender`/`dob`-shaped fields
  are read-only proxies and aren't searchable; the real, filterable
  fields are on the linked party (`party.gender`, `party.dob`).
"""
from __future__ import annotations

import base64
import datetime
import json
import urllib.error
import urllib.request


class GNUHealthError(Exception):
    """Raised for any error response from the GNU Health server."""


class AuthenticationError(GNUHealthError):
    """Raised when login fails."""


def _json_default(obj):
    # datetime.datetime is a subclass of datetime.date -- check it FIRST,
    # or every datetime would be wire-encoded as a bare date and silently
    # lose its time-of-day.
    if isinstance(obj, datetime.datetime):
        return {
            "__class__": "datetime",
            "year": obj.year, "month": obj.month, "day": obj.day,
            "hour": obj.hour, "minute": obj.minute, "second": obj.second,
            "microsecond": obj.microsecond,
        }
    if isinstance(obj, datetime.date):
        return {
            "__class__": "date",
            "year": obj.year,
            "month": obj.month,
            "day": obj.day,
        }
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _json_object_hook(d: dict):
    cls = d.get("__class__")
    if cls == "date":
        return datetime.date(d["year"], d["month"], d["day"])
    if cls == "datetime":
        return datetime.datetime(
            d["year"], d["month"], d["day"],
            d.get("hour", 0), d.get("minute", 0), d.get("second", 0),
            d.get("microsecond", 0),
        )
    return d


class GNUHealthClient:
    """One client per logged-in user session (not a connection pool —
    this is a small app for a handful of front-desk terminals, not a
    high-throughput service)."""

    def __init__(self, base_url: str, database: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.database = database
        self.timeout = timeout
        self._request_id = 0
        # Set after a successful login(); needed for every call after that.
        self.username: str | None = None
        self.user_id: int | None = None
        self.session: str | None = None

    @property
    def is_authenticated(self) -> bool:
        return self.session is not None

    def _rpc_url(self) -> str:
        return f"{self.base_url}/{self.database}/"

    def _auth_header(self) -> str:
        token = f"{self.username}:{self.user_id}:{self.session}"
        encoded = base64.b64encode(token.encode("utf-8")).decode("ascii")
        return f"Session {encoded}"

    def _raw_call(self, method: str, params: list, authenticated: bool) -> object:
        self._request_id += 1
        payload = json.dumps(
            {"id": self._request_id, "method": method, "params": params},
            default=_json_default,
        ).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if authenticated:
            if not self.is_authenticated:
                raise GNUHealthError("Client is not logged in")
            headers["Authorization"] = self._auth_header()

        req = urllib.request.Request(
            self._rpc_url(), data=payload, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
        except urllib.error.HTTPError as e:
            body = e.read()
        except urllib.error.URLError as e:
            raise GNUHealthError(f"Could not reach GNU Health server: {e}") from e

        try:
            parsed = json.loads(body, object_hook=_json_object_hook)
        except json.JSONDecodeError as e:
            raise GNUHealthError(f"Invalid response from server: {body[:200]!r}") from e

        if "error" in parsed and parsed["error"] is not None:
            # Tryton error shape is typically [message, description].
            err = parsed["error"]
            message = err[0] if isinstance(err, list) and err else str(err)
            raise GNUHealthError(message)
        return parsed.get("result")

    def login(self, username: str, password: str) -> None:
        result = self._raw_call(
            "common.db.login", [username, {"password": password}, "en"],
            authenticated=False,
        )
        if not result or not isinstance(result, list) or len(result) < 2:
            raise AuthenticationError("Login failed")
        self.username = username
        self.user_id, self.session = result[0], result[1]

    def call(self, model: str, method: str, *args, context: dict | None = None):
        params = list(args) + [{"context": context or {}}]
        return self._raw_call(f"model.{model}.{method}", params, authenticated=True)

    def default_get(self, model: str, fields: list[str], context: dict | None = None) -> dict:
        result = self.call(model, "default_get", fields, context=context)
        # Drop related-record expansion keys like "ethnic_group." — only
        # keep plain field values suitable for feeding back into create().
        return {k: v for k, v in result.items() if not k.endswith(".")}

    def create_with_defaults(
        self, model: str, values: dict, default_fields: list[str] | None = None,
        context: dict | None = None,
    ) -> int:
        """create() a single record, after merging in server-computed
        defaults — see module docstring for why this is necessary."""
        fields = default_fields if default_fields is not None else list(values.keys())
        defaults = self.default_get(model, fields, context=context)
        merged = {**defaults, **values}
        ids = self.call(model, "create", [merged], context=context)
        return ids[0]

    def search_read(
        self, model: str, domain: list, fields: list[str],
        offset: int = 0, limit: int | None = None, order: list | None = None,
        context: dict | None = None,
    ) -> list[dict]:
        return self.call(
            model, "search_read", domain, offset, limit, order, fields,
            context=context,
        )

    def read(self, model: str, ids: list[int], fields: list[str], context: dict | None = None) -> list[dict]:
        return self.call(model, "read", ids, fields, context=context)
