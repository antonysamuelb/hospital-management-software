#!/usr/bin/env python3
"""Health check for a GNU Health HIS server, for cron + external uptime monitoring.

Two ways to use it:

  1. As a cron job, alerting on failure via a webhook (Slack/Discord/generic):
       */5 * * * * /opt/gnuhealth/scripts/healthcheck.py \
           --url https://your-domain.example/ \
           --webhook https://hooks.slack.com/services/... \
           --state-file /var/lib/gnuhealth/healthcheck.state
     The --state-file is what stops it from alerting every 5 minutes during
     a prolonged outage — it only fires the webhook on a state *transition*
     (up->down or down->up), not on every failing check.

  2. As the endpoint an external free uptime monitor (e.g. UptimeRobot)
     polls directly — point it at the same --url this script checks; no
     need to run this script at all for that use case. Both are documented
     here since the paid/free-tier boundary on external monitors may not
     always be available (see deploy/README.md), and this script works
     with zero third-party account as a fallback.

Exit codes: 0 = healthy, 1 = unhealthy, 2 = usage/config error.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request


def check_once(url: str, timeout: float = 10.0) -> tuple[bool, str]:
    """Perform a single health check. Returns (is_healthy, detail)."""
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "gnuhealth-healthcheck/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = time.monotonic() - start
            status = resp.status
            if 200 <= status < 400:
                return True, f"HTTP {status} in {elapsed:.2f}s"
            return False, f"HTTP {status} in {elapsed:.2f}s"
    except urllib.error.HTTPError as e:
        # A 5xx from the app itself is "reachable but unhealthy"; still a failure.
        elapsed = time.monotonic() - start
        return False, f"HTTP {e.code} in {elapsed:.2f}s"
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        elapsed = time.monotonic() - start
        return False, f"unreachable after {elapsed:.2f}s: {e}"


def read_last_state(state_file: pathlib.Path) -> str | None:
    if not state_file.exists():
        return None
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        return data.get("state")
    except (json.JSONDecodeError, OSError):
        return None


def write_state(state_file: pathlib.Path, state: str, detail: str) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps({"state": state, "detail": detail, "checked_at": time.time()}),
        encoding="utf-8",
    )


def notify(webhook: str, message: str, timeout: float = 10.0) -> None:
    payload = json.dumps({"text": message}).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout):
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True, help="URL to check, e.g. https://your-domain.example/")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--webhook", default=None, help="Optional webhook URL to notify on state change")
    parser.add_argument(
        "--state-file",
        type=pathlib.Path,
        default=None,
        help="Path used to detect up/down transitions and avoid repeat alerts. "
        "Without this, every failing run alerts (fine for ad-hoc use).",
    )
    args = parser.parse_args(argv)

    is_healthy, detail = check_once(args.url, timeout=args.timeout)
    new_state = "up" if is_healthy else "down"

    print(f"[{'OK' if is_healthy else 'FAIL'}] {args.url} — {detail}")

    if args.state_file is not None:
        old_state = read_last_state(args.state_file)
        transitioned = old_state is not None and old_state != new_state
        write_state(args.state_file, new_state, detail)
        should_notify = transitioned or old_state is None and not is_healthy
    else:
        should_notify = not is_healthy

    if should_notify and args.webhook:
        emoji = "✅" if is_healthy else "\U0001F6A8"
        notify(args.webhook, f"{emoji} GNU Health at {args.url} is {new_state.upper()} ({detail})")

    return 0 if is_healthy else 1


if __name__ == "__main__":
    sys.exit(main())
