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
        # Step 1 (T402): the alias path of the settings router.
        'module boundary: settings: backend.routers.settings -> backend.modules.settings.http':
            'the old import path backend.routers.settings is an alias of the module http, kept so '
            'the existing patches and imports work until step 5',
        # Step 2 (T520): the weather proxy becomes a module. Net change of the allowlist: 1 line deleted, 1 added.
        'module boundary: weather: backend.routers.weather -> backend.modules.weather.http':
            'the old import path backend.routers.weather is an alias of the module http, kept so '
            'the existing patches and imports work until step 5',
        # Step 2 (T502): the fire package becomes a module. Net change of the allowlist: 8 lines deleted, 9 added.
        'module boundary: fire: backend.fire.models -> backend.modules.fire.domain.models':
            'old import path kept as an alias until step 5; 24 test files import it',
        'module boundary: fire: backend.fire.parse -> backend.modules.fire.domain.parse':
            'old import path kept as an alias until step 5; 24 test files import it',
        'module boundary: fire: backend.fire.proximity -> backend.modules.fire.domain.proximity':
            'old import path kept as an alias until step 5; 24 test files import it',
        'module boundary: fire: backend.fire.h3index -> backend.modules.fire.domain.h3index':
            'old import path kept as an alias until step 5; 24 test files import it',
        'module boundary: fire: backend.fire.repository -> backend.modules.fire.infrastructure.repository':
            'old import path kept as an alias until step 5; 24 test files import it',
        'module boundary: fire: backend.fire.sources -> backend.modules.fire.infrastructure.sources':
            'old import path kept as an alias until step 5; 24 test files import it',
        'module boundary: fire: backend.fire.poller -> backend.modules.fire.infrastructure.poller':
            'old import path kept as an alias until step 5; 24 test files import it',
        'module boundary: fire: backend.fire.service -> backend.modules.fire.infrastructure.service':
            'old import path kept as an alias until step 5; 24 test files import it',
        'module boundary: fire: backend.routers.fire -> backend.modules.fire.http':
            'old import path kept as an alias until step 5; 24 test files import it',
        # Step 2 (T540): tracking and sos become modules; the old locations router is a named shim of both.
        # Net change of the allowlist: 3 lines deleted (shims), 2 added.
        'module boundary: tracking: backend.routers.locations -> backend.modules.tracking.http':
            'the old import path backend.routers.locations passes on the tracking functions and the router, kept '
            'so the existing tests and imports work until step 5',
        'module boundary: sos: backend.routers.locations -> backend.modules.sos.http':
            'the old import path backend.routers.locations passes on the sos functions and the router, kept '
            'so the existing tests and imports work until step 5',
    },
    'backend/tests/architecture/allowlist.json': {
        # Step 2 (T503): fire gets a public face (fire.api); these callers use it until the events and the outbox of step 4.
        'module_edges: {"from": "backend.modules.settings.http", "to": "backend.modules.fire.api", "until": 4}':
            'clearing HQ ends its open alerts in the same transaction as the UPDATE, and after the commit settings tells the browsers which alerts ended: it calls fire.api until the HQCleared event of step 4',
        'module_edges: {"from": "backend.modules.settings.infrastructure.publisher", "to": "backend.modules.fire.api", "until": 4}':
            'settings asks the alarm service to re-evaluate after a save through fire.api.request_evaluation, until the outbox of step 4 delivers SettingsChanged',
        'module_edges: {"from": "backend.routers.users", "to": "backend.modules.fire.api", "until": 4}':
            'deactivating a user ends the open alerts of that user and broadcasts them through fire.api until the events of step 4',
        'module_edges: {"from": "backend.routers.devices", "to": "backend.modules.fire.api", "until": 4}':
            'disabling or deleting a device ends its open alerts, takes the alarm lock and broadcasts through fire.api until the events of step 4',
    },
}
