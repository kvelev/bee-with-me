"""Allowlist entries that a step may add on purpose, each with the reason.

The ratchet (`test_allowlist_never_grows`, `test_sql_allowlist_never_grows`) fails on any entry the merge-base does
not have. A step that has to carry new, named debt (for example `settings` calling `fire` until the outbox of step 4)
lists the entry here, with a reason of at least 20 characters. `test_every_approval_is_still_in_its_file` fails when an
approval no longer matches a line, so delete the approval together with the line it covered.

Keys are repo-relative allowlist files; each inner key is an entry exactly as `test_ratchet.entries()` prints it
(`'<contract name>: <a> -> <b>'` for the TOML, `'<key>: <json of the row>'` for allowlist.json).
"""
from __future__ import annotations

APPROVED: dict[str, dict[str, str]] = {
    'backend/tests/architecture/importlinter.toml': {},
    'backend/tests/architecture/allowlist.json': {},
}
