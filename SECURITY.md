# Security Policy

## Reporting a vulnerability

Please report security issues **privately** via [GitHub Security Advisories](https://github.com/droolyai/hermes-proton/security/advisories/new) rather than a public issue.

Include what you did, what happened, and what you expected. We'll acknowledge within a few days.

## Scope

This repository is a wrapper. Vulnerabilities in the underlying tools belong upstream:

- Encryption, authentication, key handling, API access → [`roman-16/proton-cli`](https://github.com/roman-16/proton-cli/security)
- Plugin loading, tool dispatch → [Hermes Agent](https://github.com/NousResearch/hermes-agent/security)

In scope here: the gate being bypassable, credentials leaking through this wrapper, argument injection into the CLI, or errors that misreport a failure as success.

## Design commitments

These are the properties this repo intends to hold. A break in any of them is a security bug:

1. **Mutations cannot occur without `confirm=true`.** The wrapper passes `--dry-run` otherwise. This is structural — an agent cannot talk its way past it.
2. **No credential is handled by this code.** Login is interactive and out-of-band. Nothing is stored in `plugin.yaml`, env vars, or on disk by this plugin.
3. **Message bodies never appear in argv.** They travel over stdin, so they are invisible to `ps` and other local processes.
4. **Failures are never reported as success.** Exit codes are mapped and surfaced, never swallowed. An expired session reports `auth_required: true`, not an empty result set — a falsely-empty inbox is a lie the user would act on.
5. **Proton Pass and Contacts are not exposed.** Vault access requires its own explicit decision.

## Third-party trust

`proton-cli` is unaudited community software that authenticates to Proton with your real credentials using reverse-engineered API knowledge. Read its [SECURITY.md](https://github.com/roman-16/proton-cli/blob/main/SECURITY.md) and decide for yourself before pointing it at an account that matters.
