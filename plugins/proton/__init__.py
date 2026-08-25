"""Proton integration plugin — Mail, Drive and Calendar, end-to-end encrypted.

Registers three tools into the ``proton`` toolset:

- ``proton_mail``     — list/search/read mail; send is gated behind confirm=true
- ``proton_drive``    — list/get/download; upload/trash gated behind confirm=true
- ``proton_calendar`` — real Proton Calendar read; create/delete gated

Backed by roman-16/proton-cli (MIT): SRP login and the full PGP key hierarchy
run locally via Proton's own go-srp and gopenpgp. No bridge, no proxy, no
plaintext relay — the ciphertext is decrypted on this machine.

Deliberate boundaries:

- Every mutation is *structurally* gated. Without ``confirm=true`` the wrapper
  passes ``--dry-run`` to the CLI, so an over-eager call physically cannot send
  mail, delete a file, or create an event. It returns a preview instead.
- Login is interactive (password + 2FA) and is the user's job. The plugin never
  handles, stores, or guesses a credential; it only reports when the session
  has expired (exit code 2).
- Proton Pass and Contacts are supported by the underlying CLI but are left out
  here on purpose: a password vault is not something an agent should reach into
  without a separate, explicit decision.
"""

from __future__ import annotations

from .tools import (
    PROTON_CALENDAR_SCHEMA,
    PROTON_DRIVE_SCHEMA,
    PROTON_MAIL_SCHEMA,
    _check_proton_available,
    _handle_proton_calendar,
    _handle_proton_drive,
    _handle_proton_mail,
)

_TOOLS = (
    ("proton_mail",     PROTON_MAIL_SCHEMA,     _handle_proton_mail,     "✉️"),
    ("proton_drive",    PROTON_DRIVE_SCHEMA,    _handle_proton_drive,    "🗄️"),
    ("proton_calendar", PROTON_CALENDAR_SCHEMA, _handle_proton_calendar, "🗓️"),
)


def register(ctx) -> None:
    """Register Proton tools. Called once by the plugin loader."""
    for name, schema, handler, emoji in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="proton",
            schema=schema,
            handler=handler,
            check_fn=_check_proton_available,
            emoji=emoji,
        )
