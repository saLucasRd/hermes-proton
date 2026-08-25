# hermes-proton

**Proton Mail, Drive and Calendar for [Hermes Agent](https://github.com/NousResearch/hermes-agent) — end-to-end encrypted, no bridge required.**

[![License: MIT](https://img.shields.io/badge/License-MIT-6D4AFF.svg?style=flat-square)](LICENSE)
[![Hermes Agent](https://img.shields.io/badge/Hermes-plugin-blue?style=flat-square)](https://github.com/NousResearch/hermes-agent)
[![Platforms](https://img.shields.io/badge/platforms-macOS%20%7C%20Linux%20%7C%20Windows-6D4AFF?style=flat-square)](#requirements)

Three first-class tools — `proton_mail`, `proton_drive`, `proton_calendar` — that let your agent read your encrypted mail, move files in and out of Drive, and work with real Proton Calendar events. Decryption happens on your machine. Nothing is relayed in plaintext.

> **Proton Calendar is automatable.** It's widely repeated that Proton Calendar "has no API and can't be scripted" because it's E2EE. That's out of date. `proton-cli` implements the same key hierarchy the official web clients use, so calendar events decrypt locally just like mail does. This plugin exposes that as real calendar access — not an `.ics` export.

---

## Why this exists

Every other Proton-for-agents approach routes your mail through a bridge: `hydroxide`/`protoxide` speaking IMAP on loopback, or the official Proton Bridge, plus `rclone` for Drive, plus something else again for Calendar. Three moving parts, cleartext on a local socket, a decrypted cache on disk, and still no calendar.

This plugin wraps [`roman-16/proton-cli`](https://github.com/roman-16/proton-cli) — one Go binary that does SRP login and the full PGP key hierarchy locally with Proton's own [`go-srp`](https://github.com/ProtonMail/go-srp) and [`gopenpgp`](https://github.com/ProtonMail/gopenpgp). No bridge, no proxy, no IMAP, and Mail + Drive + Calendar all covered.

## The safety model

**Every mutation is structurally gated, not gated by good intentions.**

Each mutating action takes a `confirm` parameter. When it is absent or false — the default — the wrapper passes `--dry-run` to the CLI. The call *physically cannot* send mail, delete a file, or create an event. It returns a preview instead:

```json
{
  "success": true,
  "applied": false,
  "dry_run": true,
  "action": "send mail to alice@example.com",
  "preview": { "...": "what would have happened" },
  "next_step": "Nothing was changed. Show it to the user; if they explicitly approve, call again with confirm=true."
}
```

This matters because an LLM that is trying to be helpful will otherwise happily send the email. Here, eagerness alone cannot do it — the agent has to come back to you, and the second call is the one you authorized.

| Tool | Free (read) | Gated (`confirm=true`) |
|---|---|---|
| `proton_mail` | `status` `list` `search` `get` `folders` | **`send`** |
| `proton_drive` | `list` `get` `download` | **`upload` `trash`** |
| `proton_calendar` | `calendars` `list` `get` | **`create` `delete`** |

`download` counts as read-only: it writes only into a local directory you named.

### Deliberately not included

`proton-cli` also supports **Pass** and **Contacts**. They are left out on purpose. Handing an agent read access to your password vault deserves its own explicit decision, not a ride-along on a mail plugin. Fork it if you want them; the pattern is three lines.

### Credentials

The plugin never handles, stores, or guesses a credential. Login is interactive (password + 2FA) and is yours to run. The plugin only *reports* when a session has expired — it maps exit code `2` to `auth_required: true` and tells you the fix. There is no token in `plugin.yaml`, no env var, nothing on disk. Message bodies are piped over stdin rather than passed as arguments, so they never appear in the system process list.

---

## Requirements

- [Hermes Agent](https://github.com/NousResearch/hermes-agent)
- [Go 1.24+](https://go.dev/dl/) to build the CLI (or grab a [prebuilt release](https://github.com/roman-16/proton-cli/releases))
- A Proton account

## Install

**1. Get the `proton` binary**

```bash
git clone --depth 1 https://github.com/roman-16/proton-cli.git ~/proton-cli
cd ~/proton-cli && go build -o ~/.hermes/bin/proton ./cmd/proton
```

Build `./cmd/proton` — not `./cmd/proton-cli` (the alternate install name) and not `./cmd/proton-hv` (a CGO webview helper).

Prefer a signed release? `curl -fsSL https://raw.githubusercontent.com/roman-16/proton-cli/main/scripts/install.sh | sh`, then point the plugin at it — it checks `~/.hermes/bin/proton` first, then falls back to `$PATH`.

**2. Install the plugin**

```bash
git clone https://github.com/droolyai/hermes-proton.git
cp -r hermes-proton/plugins/proton ~/.hermes/plugins/
hermes plugins doctor ~/.hermes/plugins/proton   # must report: 3 tool(s)
hermes plugins enable proton
```

`hermes plugins enable` will ask whether the plugin may override built-in tools. **Decline.** This plugin needs no such privilege; the refusal message is expected, not an error.

**3. Sign in** — interactive, and only you can do this:

```bash
proton account login
```

Your password is needed once on this machine. The session persists per-profile afterwards.

**4. Verify**

```bash
python3 ~/.hermes/plugins/proton/test_proton.py   # 28 checks, no network, no account needed
```

Then ask your agent: *"what's in my Proton inbox?"*

## Usage

Reads just work:

> *"Any unread Proton mail from my landlord this month?"*
> *"What's on my Proton calendar next week?"*
> *"Download the tax folder from Drive to ~/Documents."*

Mutations come back for approval first:

> **You:** *"Email alice@example.com the meeting notes."*
> **Agent:** *drafts it, calls `proton_mail` with `confirm` unset, gets a dry-run preview, shows you the exact message* — "Ready to send. Say the word."
> **You:** *"Send it."*
> **Agent:** *calls again with `confirm=true`.* Sent.

## Exit codes

`proton-cli` exit codes are meaningful, and the wrapper surfaces them rather than swallowing them:

| Code | Meaning | Surfaced as |
|---|---|---|
| `0` | Success | — |
| `1` | Bad argument | `meaning: "bad argument"` |
| `2` | **Authentication failed** | `auth_required: true` + the login fix |
| `3` | Not found | `meaning: "not found"` |
| `4` | Ambiguous or conflicting | `meaning: "ambiguous or conflicting"` |
| `5` | Network or server problem | `meaning: "network or server problem"` |
| `130` | Cancelled | `meaning: "cancelled"` |

A `2` almost always means the saved session expired — not a bad password. Run `proton account login` again.

## Multiple accounts

`proton-cli` supports profiles (`proton account login --profile work`). This plugin currently uses the default profile. Per-tool profile selection is a natural next feature — PRs welcome.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `plugins doctor` says OK but `registrations: 0` | That's a failure. Read the count, not the OK line. |
| `ModuleNotFoundError: No module named 'plugins.proton'` | User plugins need **relative** imports (`from . import client`). Absolute `plugins.*` only resolves for bundled plugins. |
| `command not found: proton` in your shell | `~/.hermes/bin` isn't on `PATH`. Add `export PATH="$HOME/.hermes/bin:$PATH"` to your shell rc. |
| Every call returns `auth_required: true` | The session expired. `proton account login`. |
| A call hangs | Ensure you're on this version — the wrapper always passes `--no-input`, without which a missing session blocks on an invisible password prompt. |

## Security

- No credential is ever written to disk, config, or env by this plugin.
- Message bodies travel over stdin, never argv (invisible to `ps`).
- Mutations are gated by construction (`--dry-run`), not by prompt instructions.
- `proton-cli` is unaudited third-party software; read its [SECURITY.md](https://github.com/roman-16/proton-cli/blob/main/SECURITY.md) before trusting it with an account that matters.

Found a vulnerability? Open a private security advisory rather than a public issue.

## Credits

Standing entirely on [`roman-16/proton-cli`](https://github.com/roman-16/proton-cli) (MIT), which does the genuinely hard part: SRP, the PGP key hierarchy, and Proton's undocumented API. This repo is a wrapper and a safety model.

Built for [Hermes Agent](https://github.com/NousResearch/hermes-agent) by [Nous Research](https://nousresearch.com).

## Disclaimer

Unofficial and not affiliated with, endorsed by, or supported by Proton AG. Proton is a trademark of Proton AG. Mind [Proton's terms of service](https://proton.me/legal/terms). Use at your own risk.

## License

[MIT](LICENSE) © Drooly AI, Inc.
