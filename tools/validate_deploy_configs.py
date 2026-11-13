#!/usr/bin/env python3
"""Static structural validation for the deploy/ configs.

This does NOT replace `nginx -t` or actually starting the systemd unit —
neither nginx nor systemd is available in the environment this was written
in. It catches the class of mistakes that are checkable without those
tools (unbalanced braces, missing required directives/keys, obviously
inconsistent references between files) so the configs aren't committed
completely unverified.

Run: python tools/validate_deploy_configs.py
Exits non-zero (and prints what failed) if any check fails.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)


def validate_nginx_conf() -> None:
    path = ROOT / "deploy" / "nginx" / "gnuhealth.conf"
    text = path.read_text(encoding="utf-8")

    check(text.count("{") == text.count("}"), f"{path}: unbalanced braces")
    check("listen 80;" in text, f"{path}: missing 'listen 80;'")
    check(
        "proxy_pass http://127.0.0.1:8000;" in text,
        f"{path}: proxy_pass must point at 127.0.0.1:8000 "
        "(GNU Health's documented default trytond web port)",
    )
    check(
        "location /.well-known/acme-challenge/" in text,
        f"{path}: missing ACME challenge location (certbot --nginx needs this reachable)",
    )
    check("server_name" in text, f"{path}: missing server_name directive")


def validate_systemd_unit() -> None:
    path = ROOT / "deploy" / "systemd" / "gnuhealth.service"
    text = path.read_text(encoding="utf-8")

    for section in ("[Unit]", "[Service]", "[Install]"):
        check(section in text, f"{path}: missing {section} section")

    required_keys = ["ExecStart", "User", "WorkingDirectory", "Restart", "WantedBy"]
    for key in required_keys:
        check(
            re.search(rf"^{key}=", text, re.MULTILINE) is not None,
            f"{path}: missing required key '{key}='",
        )

    # The port the service binds to must match what the nginx conf proxies to.
    nginx_text = (ROOT / "deploy" / "nginx" / "gnuhealth.conf").read_text(encoding="utf-8")
    service_port_match = re.search(r"--bind 127\.0\.0\.1:(\d+)", text)
    nginx_port_match = re.search(r"proxy_pass http://127\.0\.0\.1:(\d+);", nginx_text)
    check(
        bool(service_port_match and nginx_port_match)
        and service_port_match.group(1) == nginx_port_match.group(1),
        "deploy/systemd/gnuhealth.service and deploy/nginx/gnuhealth.conf "
        "must agree on the port trytond listens on",
    )


def validate_simple_ui_nginx() -> None:
    path = ROOT / "deploy" / "nginx" / "simple-ui.conf"
    text = path.read_text(encoding="utf-8")

    check(text.count("{") == text.count("}"), f"{path}: unbalanced braces")
    check("listen 80" in text, f"{path}: missing 'listen 80'")
    check(
        "proxy_pass http://127.0.0.1:5050;" in text,
        f"{path}: proxy_pass must point at 127.0.0.1:5050 "
        "(matches simple-ui.service's gunicorn --bind)",
    )
    check("server_name" in text, f"{path}: missing server_name directive")

    # The port the service binds to must match what the nginx conf proxies to.
    service_text = (ROOT / "deploy" / "systemd" / "simple-ui.service").read_text(encoding="utf-8")
    service_port_match = re.search(r"--bind 127\.0\.0\.1:(\d+)", service_text)
    nginx_port_match = re.search(r"proxy_pass http://127\.0\.0\.1:(\d+);", text)
    check(
        bool(service_port_match and nginx_port_match)
        and service_port_match.group(1) == nginx_port_match.group(1),
        "deploy/systemd/simple-ui.service and deploy/nginx/simple-ui.conf "
        "must agree on the port gunicorn listens on",
    )


def validate_provision_script() -> None:
    path = ROOT / "deploy" / "provision.sh"
    text = path.read_text(encoding="utf-8")
    check(text.startswith("#!/usr/bin/env bash"), f"{path}: missing shebang")
    check("set -euo pipefail" in text, f"{path}: should fail fast (set -euo pipefail)")
    # The user created here must match the one referenced by the systemd unit.
    service_text = (ROOT / "deploy" / "systemd" / "gnuhealth.service").read_text(encoding="utf-8")
    check(
        'GNUHEALTH_USER="gnuhealth"' in text and "User=gnuhealth" in service_text,
        "deploy/provision.sh and deploy/systemd/gnuhealth.service must use the same service account name",
    )


def main() -> int:
    validate_nginx_conf()
    validate_systemd_unit()
    validate_simple_ui_nginx()
    validate_provision_script()

    if FAILURES:
        print(f"FAILED — {len(FAILURES)} issue(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1

    print("All structural checks passed (nginx conf, systemd unit, provision script are internally consistent).")
    print("Reminder: this is static validation only — it does not replace running")
    print("`nginx -t` or actually starting the service on a real Linux host.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
