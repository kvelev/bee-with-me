"""T540: `sos` is a backend module (HTTP side)."""
import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.Trait("Task", "T540")


def test_manifest():
    from backend.modules import MODULES
    import backend.modules.sos.http as http
    from backend.modules.sos.module import manifest
    assert manifest.name == 'sos'
    assert manifest.owns_tables == ('sos_alerts',)
    assert set(manifest.reads_tables) == {'devices', 'users'}
    assert manifest.live_messages == ('sos_alert',)
    assert manifest.public_routes == ()
    assert manifest.router is http.router
    assert manifest in MODULES


def test_resolve_runs_the_same_statement():
    import backend.modules.sos.http as http
    conn = MagicMock()
    conn.execute = AsyncMock()
    alert, user = uuid.uuid4(), uuid.uuid4()
    out = asyncio.run(http.resolve_sos(alert, 'done', conn, {'id': user}))
    assert out == {'resolved': True}
    args = conn.execute.await_args.args
    assert 'UPDATE sos_alerts' in args[0]
    assert args[1:] == (alert, user, 'done')
