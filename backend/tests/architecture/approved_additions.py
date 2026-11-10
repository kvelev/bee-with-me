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
    'backend/tests/architecture/importlinter.toml': {
        # Step 1 (T402): debt that already existed and became visible when settings moved into a module.
        # Net change of the allowlist in step 1: 3 lines deleted, 4 added.
        'fire internals are private: backend.modules.settings.http -> backend.fire.repository':
            'clearing HQ ends its open alerts in the same transaction as the UPDATE: settings calls '
            'fire.repository.resolve_hq_alerts until the HQCleared event of step 4',
        'fire internals are private: backend.modules.settings.http -> backend.fire.service':
            'after the commit settings tells the browsers which alerts ended (notify_alerts_updated) '
            'until the HQCleared event of step 4',
        'fire internals are private: backend.modules.settings.infrastructure.publisher -> backend.fire.service':
            'settings asks the alarm service to re-evaluate after a save; before step 1 main.py wired it by '
            'assignment, so no import existed; replaced by the outbox of step 4',
        'module boundary: settings: backend.routers.settings -> backend.modules.settings.http':
            'the old import path backend.routers.settings is an alias of the module http, kept so '
            'the existing patches and imports work until step 5',
    },
    'backend/tests/architecture/allowlist.json': {},
}
