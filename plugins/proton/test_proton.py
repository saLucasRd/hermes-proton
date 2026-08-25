"""Self-test for the Proton plugin. Run standalone:

    ~/.hermes/hermes-agent/venv/bin/python ~/.hermes/plugins/proton/test_proton.py

Covers the paths that must hold with NO Proton session and no network:
binary discovery, error mapping, argument validation, and — most importantly —
that every mutating action refuses to apply without confirm=true.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.expanduser("~/.hermes"))

from plugins.proton import client as C
from plugins.proton import tools as T

PASS, FAIL = 0, 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}" + (f"  -- {detail}" if detail else ""))


def j(raw):
    return json.loads(raw) if isinstance(raw, str) else raw


print("\n== binary discovery ==")
check("proton binary found", C.available(), "expected ~/.hermes/bin/proton")
check("check_fn agrees", T._check_proton_available() == C.available())

print("\n== exit-code mapping ==")
check("2 means auth failed", C.EXIT_MEANING[2] == "authentication failed")
err = C.ProtonError("x", exit_code=2)
check("ProtonError.auth_required on 2", err.auth_required is True)
check("ProtonError not auth on 3", C.ProtonError("x", exit_code=3).auth_required is False)

print("\n== argument validation (no network) ==")
r = j(T._handle_proton_mail(action="get"))
check("mail get without ref errors", "error" in r, r)
r = j(T._handle_proton_mail(action="search"))
check("mail search with no criteria errors", "error" in r, r)
r = j(T._handle_proton_mail(action="bogus"))
check("mail unknown action errors", "error" in r, r)
r = j(T._handle_proton_drive(action="download", path="/x"))
check("drive download without dest_dir errors", "error" in r, r)
r = j(T._handle_proton_drive(action="bogus"))
check("drive unknown action errors", "error" in r, r)
r = j(T._handle_proton_calendar(action="create", title="No start"))
check("calendar create without start errors", "error" in r, r)
r = j(T._handle_proton_calendar(action="bogus"))
check("calendar unknown action errors", "error" in r, r)

print("\n== the autonomy gate is structural ==")
# Build the same argv the wrapper would, and assert --dry-run vs --yes.

captured = {}


def fake_run(args, timeout=None, stdin=None):
    captured["args"] = args
    captured["stdin"] = stdin
    return {"stub": True}


real_run = C.run
C.run = fake_run
try:
    C.mail_send(to=["a@b.c"], subject="s", body="secret-body", confirm=False)
    check("mail send unconfirmed uses --dry-run", "--dry-run" in captured["args"], captured["args"])
    check("mail send unconfirmed has no --yes", "--yes" not in captured["args"])
    check("body goes over stdin, not argv", captured["stdin"] == "secret-body")
    check("body is NOT in the process arguments",
          "secret-body" not in " ".join(captured["args"]), captured["args"])

    C.mail_send(to=["a@b.c"], subject="s", body="b", confirm=True)
    check("mail send confirmed uses --yes", "--yes" in captured["args"])
    check("mail send confirmed has no --dry-run", "--dry-run" not in captured["args"])

    C.event_create(title="t", start="2026-01-01T10:00", confirm=False)
    check("event create unconfirmed uses --dry-run", "--dry-run" in captured["args"])
    C.event_delete("abc", confirm=False)
    check("event delete unconfirmed uses --dry-run", "--dry-run" in captured["args"])
    C.drive_trash("/x", confirm=False)
    check("drive trash unconfirmed uses --dry-run", "--dry-run" in captured["args"])

    # handler-level: applied must be False on an unconfirmed mutation
    r = j(T._handle_proton_mail(action="send", to=["a@b.c"],
                                send_subject="s", body="b"))
    check("handler reports applied=False when unconfirmed", r.get("applied") is False, r)
    check("handler flags dry_run", r.get("dry_run") is True, r)
    r = j(T._handle_proton_calendar(action="create", title="t",
                                    start="2026-01-01T10:00"))
    check("calendar handler applied=False when unconfirmed", r.get("applied") is False, r)
finally:
    C.run = real_run

print("\n== upload guards on a missing local path ==")
r = j(T._handle_proton_drive(action="upload", local="/definitely/not/here.txt"))
check("upload of missing file errors", "error" in r, r)

print("\n== status never raises without a session ==")
st = C.session_status()
check("session_status returns a dict", isinstance(st, dict), st)
check("session_status has logged_in key", "logged_in" in st, st)
if not st.get("logged_in"):
    check("offers the login fix", "login" in json.dumps(st).lower(), st)
    print(f"       (no session yet — reason: {str(st.get('reason'))[:90]})")

print(f"\n{PASS} passed, {FAIL} failed\n")
sys.exit(1 if FAIL else 0)
