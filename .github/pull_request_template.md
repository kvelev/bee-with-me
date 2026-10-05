## What & why

<!-- What does this change, and what problem does it solve? Link the issue / bug id (e.g. B61). -->

## How it was tested

<!-- Tests added/changed, manual checks (with a real gateway? simulated via /api/test/simulate?). -->

## Checklist

- [ ] `python -m pytest backend/tests/` and `npm test` (in `frontend/`) pass locally
- [ ] Schema change? Added a new numbered file in `backend/db/migrations/` (never edit a released one)
- [ ] Bee protocol change? Updated `docs/PROTOCOL.md` (the authoritative reference)
- [ ] Changed `start.sh` / `start.ps1` / `scripts/`? Changed **both** the bash and PowerShell versions
- [ ] User-visible change? Added an entry under `[Unreleased]` in `CHANGELOG.md`
- [ ] New UI strings exist in both `en` and `bg` locales
