"""Hermes tool handlers for the Proton plugin.

The autonomy boundary is structural, not advisory. Every mutating action takes
``confirm``; when it is false (the default) the underlying CLI is invoked with
``--dry-run``, so the call physically cannot send mail, move a file, or touch a
calendar. The result is a preview the user approves before anything happens.
"""

from __future__ import annotations

from typing import Any

from . import client as C
from .client import ProtonError

try:  # available inside Hermes; keep importable standalone for tests
    from tools.registry import tool_error, tool_result
except Exception:  # noqa: BLE001 - any import failure means "not inside Hermes"; the
    # fallback below must work for the standalone self-test, so this is deliberately broad.
    import json

    def tool_error(message, **extra):
        d = {"error": message}
        d.update(extra)
        return json.dumps(d, ensure_ascii=False)

    def tool_result(data=None, **kwargs):
        return json.dumps(data if data is not None else kwargs, ensure_ascii=False)


_AUTH_NOTE = (
    "A failure with 'authentication failed' means the saved Proton session "
    "expired. The user must run `proton account login` in a terminal — it needs "
    "their password and 2FA and CANNOT be automated. Never guess credentials."
)

_GATE_NOTE = (
    "Mutating actions require confirm=true. With confirm=false (default) the "
    "call runs as a dry-run preview and changes nothing — show the preview to "
    "the user and get an explicit go-ahead before re-calling with confirm=true."
)


def _fail(exc: ProtonError) -> str:
    return tool_error(
        str(exc),
        exit_code=exc.exit_code,
        meaning=exc.meaning,
        auth_required=exc.auth_required,
        fix=(
            "Run `proton account login` in a terminal."
            if exc.auth_required
            else None
        ),
    )


def _gated(result: Any, confirm: bool, what: str) -> str:
    if confirm:
        return tool_result({"success": True, "applied": True, "action": what,
                            "result": result})
    return tool_result({
        "success": True,
        "applied": False,
        "dry_run": True,
        "action": what,
        "preview": result,
        "next_step": (
            f"Nothing was changed. This is a preview of '{what}'. Show it to the "
            "user; if they explicitly approve, call again with confirm=true."
        ),
    })


# ==========================================================================
# proton_mail
# ==========================================================================

PROTON_MAIL_SCHEMA = {
    "name": "proton_mail",
    "description": (
        "Proton Mail, end-to-end encrypted (decryption happens locally via SRP + "
        "gopenpgp; no bridge needed). Read actions: status, list (a folder, "
        "default inbox), search (by keyword/sender/subject/date), get (one message, "
        "decrypted), folders. Mutating action: send — GATED, requires confirm=true; "
        "with confirm=false it returns a dry-run preview and sends nothing. "
        + _AUTH_NOTE
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "list", "search", "get", "folders", "send"],
                "description": "What to do. Default 'list'.",
            },
            "folder": {"type": "string", "description": "Folder/label. Default 'inbox' for list, 'all' for search."},
            "limit": {"type": "integer", "description": "Max messages. Default 25."},
            "unread": {"type": "boolean", "description": "For 'list': only unread."},
            "ref": {"type": "string", "description": "For 'get': message ID, short ID, or subject text."},
            "format": {
                "type": "string",
                "enum": ["text", "html", "raw"],
                "description": "For 'get': body rendering. Default 'text'.",
            },
            "keyword": {"type": "string", "description": "For 'search': match anywhere."},
            "sender": {"type": "string", "description": "For 'search': sender address."},
            "subject": {"type": "string", "description": "For 'search': subject text."},
            "after": {"type": "string", "description": "For 'search': YYYY-MM-DD lower bound."},
            "before": {"type": "string", "description": "For 'search': YYYY-MM-DD upper bound."},
            "to": {"type": "array", "items": {"type": "string"}, "description": "For 'send': recipients."},
            "cc": {"type": "array", "items": {"type": "string"}},
            "bcc": {"type": "array", "items": {"type": "string"}},
            "send_subject": {"type": "string", "description": "For 'send': the subject line."},
            "body": {"type": "string", "description": "For 'send': the message body."},
            "attach": {"type": "array", "items": {"type": "string"}, "description": "For 'send': local file paths."},
            "html": {"type": "boolean", "description": "For 'send': treat body as HTML."},
            "confirm": {
                "type": "boolean",
                "description": "REQUIRED true to actually send. False/absent = dry-run preview only.",
            },
        },
        "required": [],
    },
}


def _handle_proton_mail(**kw: Any) -> str:
    action = kw.get("action") or "list"
    try:
        if action == "status":
            return tool_result(C.session_status())
        if action == "folders":
            return tool_result({"success": True, "folders": C.mail_folders()})
        if action == "list":
            return tool_result({"success": True, "messages": C.mail_list(
                folder=kw.get("folder") or "inbox",
                limit=int(kw.get("limit") or 25),
                unread=bool(kw.get("unread")),
            )})
        if action == "search":
            if not any(kw.get(k) for k in ("keyword", "sender", "subject", "after", "before")):
                return tool_error("search needs at least one of: keyword, sender, subject, after, before")
            return tool_result({"success": True, "results": C.mail_search(
                keyword=kw.get("keyword"), sender=kw.get("sender"),
                subject=kw.get("subject"), folder=kw.get("folder") or "all",
                after=kw.get("after"), before=kw.get("before"),
                limit=int(kw.get("limit") or 25),
            )})
        if action == "get":
            ref = kw.get("ref")
            if not ref:
                return tool_error("get requires 'ref' (message ID, short ID, or subject)")
            return tool_result({"success": True, "message": C.mail_get(ref, kw.get("format") or "text")})
        if action == "send":
            to = kw.get("to") or []
            subject = kw.get("send_subject") or kw.get("subject")
            body = kw.get("body")
            missing = [n for n, v in (("to", to), ("send_subject", subject), ("body", body)) if not v]
            if missing:
                return tool_error(f"send requires: {', '.join(missing)}", gate=_GATE_NOTE)
            confirm = bool(kw.get("confirm"))
            res = C.mail_send(
                to=to, subject=subject, body=body, confirm=confirm,
                cc=kw.get("cc"), bcc=kw.get("bcc"),
                attach=kw.get("attach"), html=bool(kw.get("html")),
            )
            return _gated(res, confirm, f"send mail to {', '.join(to)}")
        return tool_error(f"unknown action: {action}",
                          valid=["status", "list", "search", "get", "folders", "send"])
    except ProtonError as exc:
        return _fail(exc)


# ==========================================================================
# proton_drive
# ==========================================================================

PROTON_DRIVE_SCHEMA = {
    "name": "proton_drive",
    "description": (
        "Proton Drive, end-to-end encrypted. Read actions: list (a folder), get "
        "(file/folder details), download (to a local directory). Mutating actions: "
        "upload, trash — GATED, require confirm=true; with confirm=false they return "
        "a dry-run preview and change nothing. Download is treated as read-only "
        "because it only writes into a local directory the user named. " + _AUTH_NOTE
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "get", "download", "upload", "trash"],
                "description": "What to do. Default 'list'.",
            },
            "path": {"type": "string", "description": "Remote Drive path, e.g. '/Documents'. Default '/'."},
            "local": {"type": "string", "description": "For 'upload': local file or directory to upload."},
            "dest_dir": {"type": "string", "description": "For 'download': local directory to write into."},
            "remote_dir": {"type": "string", "description": "For 'upload': destination Drive folder. Default '/'."},
            "confirm": {
                "type": "boolean",
                "description": "REQUIRED true for upload/trash. False/absent = dry-run preview only.",
            },
        },
        "required": [],
    },
}


def _handle_proton_drive(**kw: Any) -> str:
    action = kw.get("action") or "list"
    try:
        if action == "list":
            return tool_result({"success": True, "items": C.drive_list(kw.get("path") or "/")})
        if action == "get":
            if not kw.get("path"):
                return tool_error("get requires 'path'")
            return tool_result({"success": True, "item": C.drive_get(kw["path"])})
        if action == "download":
            path, dest = kw.get("path"), kw.get("dest_dir")
            if not path or not dest:
                return tool_error("download requires 'path' (remote) and 'dest_dir' (local)")
            return tool_result({"success": True, "downloaded": C.drive_download(path, dest)})
        if action == "upload":
            local = kw.get("local")
            if not local:
                return tool_error("upload requires 'local'", gate=_GATE_NOTE)
            confirm = bool(kw.get("confirm"))
            remote = kw.get("remote_dir") or "/"
            res = C.drive_upload(local, remote, confirm=confirm)
            return _gated(res, confirm, f"upload {local} -> {remote}")
        if action == "trash":
            path = kw.get("path")
            if not path:
                return tool_error("trash requires 'path'", gate=_GATE_NOTE)
            confirm = bool(kw.get("confirm"))
            return _gated(C.drive_trash(path, confirm=confirm), confirm, f"trash {path}")
        return tool_error(f"unknown action: {action}",
                          valid=["list", "get", "download", "upload", "trash"])
    except ProtonError as exc:
        return _fail(exc)


# ==========================================================================
# proton_calendar
# ==========================================================================

PROTON_CALENDAR_SCHEMA = {
    "name": "proton_calendar",
    "description": (
        "Proton Calendar, end-to-end encrypted — events are decrypted locally. This "
        "is real Proton Calendar access, not an .ics export. Read actions: calendars "
        "(list them), list (events in a date range), get (one event). Mutating "
        "actions: create, delete — GATED, require confirm=true; with confirm=false "
        "they return a dry-run preview and change nothing. " + _AUTH_NOTE
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["calendars", "list", "get", "create", "delete"],
                "description": "What to do. Default 'list'.",
            },
            "start": {
                "type": "string",
                "description": "For 'list': YYYY-MM-DD. For 'create': RFC3339 or YYYY-MM-DDTHH:MM.",
            },
            "end": {"type": "string", "description": "For 'list': YYYY-MM-DD last day included."},
            "calendar": {"type": "string", "description": "Calendar name or ID. Default: all (list) / first (create)."},
            "ref": {"type": "string", "description": "For 'get'/'delete': event ID, short ID, or title."},
            "title": {"type": "string", "description": "For 'create': event title."},
            "duration": {"type": "string", "description": "For 'create': e.g. '1h', '30m', '2h30m'."},
            "all_day": {"type": "boolean", "description": "For 'create': an all-day event."},
            "location": {"type": "string"},
            "description": {"type": "string"},
            "rrule": {"type": "string", "description": "For 'create': recurrence, e.g. 'FREQ=WEEKLY;COUNT=10'."},
            "remind": {
                "type": "array",
                "items": {"type": "string"},
                "description": "For 'create': reminders, e.g. ['15m'].",
            },
            "confirm": {
                "type": "boolean",
                "description": "REQUIRED true for create/delete. False/absent = dry-run preview only.",
            },
        },
        "required": [],
    },
}


def _handle_proton_calendar(**kw: Any) -> str:
    action = kw.get("action") or "list"
    try:
        if action == "calendars":
            return tool_result({"success": True, "calendars": C.calendars()})
        if action == "list":
            return tool_result({"success": True, "events": C.events_list(
                start=kw.get("start"), end=kw.get("end"), calendar=kw.get("calendar"),
            )})
        if action == "get":
            if not kw.get("ref"):
                return tool_error("get requires 'ref' (event ID, short ID, or title)")
            return tool_result({"success": True, "event": C.event_get(kw["ref"])})
        if action == "create":
            title, start = kw.get("title"), kw.get("start")
            missing = [n for n, v in (("title", title), ("start", start)) if not v]
            if missing:
                return tool_error(f"create requires: {', '.join(missing)}", gate=_GATE_NOTE)
            confirm = bool(kw.get("confirm"))
            res = C.event_create(
                title=title, start=start, confirm=confirm,
                duration=kw.get("duration"), all_day=bool(kw.get("all_day")),
                location=kw.get("location"), description=kw.get("description"),
                calendar=kw.get("calendar"), rrule=kw.get("rrule"),
                remind=kw.get("remind"),
            )
            return _gated(res, confirm, f"create event '{title}' at {start}")
        if action == "delete":
            ref = kw.get("ref")
            if not ref:
                return tool_error("delete requires 'ref'", gate=_GATE_NOTE)
            confirm = bool(kw.get("confirm"))
            return _gated(C.event_delete(ref, confirm=confirm), confirm, f"delete event {ref}")
        return tool_error(f"unknown action: {action}",
                          valid=["calendars", "list", "get", "create", "delete"])
    except ProtonError as exc:
        return _fail(exc)


def _check_proton_available() -> bool:
    """The toolset is useful only when the proton binary exists."""
    return C.available()
