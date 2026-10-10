# 13. Secrets and settings in a local .env file

Date: 2026-10-03

## Status

Proposed (records the baseline 1.7.1)

**TOGAF Phase:** D (Technology Architecture)
**Decision Maker(s):** Project owner (kvelev)
**Stakeholders:** HQ operator, contributors
**Principles:** upholds TP-01, TP-03, DP-02; trades off DP-02 partly (secrets in plain text on disk)

## Context

The system needs a JWT signing key, the database password, the offline-maps download password, HID vendor and
product IDs and other settings. There is no secret store in the field, no internet guarantee and one operator.

## Decision

We will keep secrets and settings in **`bee-with-me/.env`**, read by pydantic-settings (`backend/config.py`) and
by the compose file. `.env` is created from `.env.example` on first start, is never committed (git ignore and a
staged-diff hook), and the backend warns at start-up when `SECRET_KEY`, the database password or the offline-maps
password still have their default values. Settings that an operator changes at run time (HQ, alarm radii) live in
the database, not in `.env`. No secret goes into the browser bundle. The OpenWeatherMap key (`OWM_API_KEY`) used to (R-05); since the
backend proxies weather (`/api/weather/*`) it stays on the server.

## Consequences

**Positive:**
- Works offline; one file to back up and restore with the machine.
- Same mechanism on Windows and Linux.

**Negative / Trade-offs:**
- Secrets are plain text on the laptop's disk; protection is the OS account and disk encryption.
- Default values must be changed by hand; start-up only warns.
- Changing `SECRET_KEY` logs everyone out.

## Considered options

| Option | Summary | Pros | Cons |
|--------|---------|------|------|
| ✅ **`.env` file** | As built | Simple, offline | Plain text on disk |
| OS keychain (Windows Credential Manager, libsecret) | Per-OS store | Encrypted at rest | Different code per OS; hard for scripts and containers |
| Secret manager (Vault, cloud) | Central store | Rotation, audit | Needs a server or internet |

> ⚠️ **Requires stakeholder input (owner):** is the field laptop's disk encrypted (BitLocker, LUKS)? It protects
> `.env`, the database files, photos and backups together.

## Related

- [technology-architecture.md](../technology/technology-architecture.md), ADR 8
