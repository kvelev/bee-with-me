"""Shared fakes for the gateway tests: a connection that answers by SQL text, not by call order.

The reader issues its queries in an order the next refactor step is free to change (one transaction,
a different read sequence). The tests therefore route every `fetchrow` / `fetchval` / `fetch` call by a
fragment of its SQL and keep a little state (an alert inserted by the handler is then "open"), so a
test only breaks when the behaviour changes, not when the statements are reordered.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from backend.hardware_reader.parser import crc16


class UnroutedSql(Exception):
    """A query the fake does not know. Deliberately not an AssertionError, so a strict
    `xfail(raises=AssertionError)` cannot be satisfied by a new, unexpected query."""


# Valid Cmd=30 frame body (same as test_parser.BEE_BODY): msg_id 2, dev_sn 1235, flags (field 18) 0, event_id 884
BEE_BODY = (
    '30,2,1235,1,4,20,50,5,8,12,2024,A,42.14384090,24.74956150,'
    '5,137,12,200,0,3.7,-97,7,-101,5,884'
)
# Valid Cmd=20 repeater body (same as test_parser.REPEATER_BODY): msg_id 100, dev_sn 1256, event_id 412
REPEATER_BODY = '20,100,1256,1,4,3.4,-88,9,-92,8,412'


def body_with(body: str, overrides: dict[int, object]) -> str:
    """`body` with individual fields replaced, keyed by protocol field index."""
    fields = body.split(',')
    for index, value in overrides.items():
        fields[index] = str(value)
    return ','.join(fields)


def make_frame(body: str) -> str:
    payload = f'##{body}'
    return f'{payload}@{crc16(payload.encode("ascii", errors="replace"))}\r\n'


class GatewaySql:
    """State behind the routed answers.

    device         row for `... FROM devices ...` (None = unknown device)
    last_fix       row for the last valid fix (`gnss_valid = TRUE`)
    prev_sos       value for `SELECT sos_active ...` (previous frame's raw flag)
    existing_alert row for `SELECT id FROM sos_alerts ...` (an open alert), None = no open alert
    alert          row returned by `INSERT INTO sos_alerts ... RETURNING`
    user           row for `... FROM users ...`
    groups         rows for `... FROM user_groups ...`
    sos_open       value for `SELECT EXISTS(...)`; None = derived (an alert is open before the frame
                   or was inserted by it)
    """

    def __init__(
        self,
        *,
        device: Any = None,
        last_fix: Any = None,
        prev_sos: Any = None,
        existing_alert: Any = None,
        alert: Any = None,
        user: Any = None,
        groups: list | None = None,
        sos_open: bool | None = None,
    ) -> None:
        self.device = device
        self.last_fix = last_fix
        self.prev_sos = prev_sos
        self.existing_alert = existing_alert
        self.alert = alert
        self.user = user
        self.groups = list(groups or [])
        self.sos_open = sos_open
        self.alerts_inserted = 0
        # One ordered log of every statement (and of transaction markers, see `record_transactions`)
        self.log: list[tuple[str, str]] = []

    # ── routing ────────────────────────────────────────────────────────────────
    def fetchrow(self, sql: str, *args: Any) -> Any:
        self.log.append(('fetchrow', sql))
        if 'INSERT INTO sos_alerts' in sql:
            self.alerts_inserted += 1
            return self.alert
        if 'SELECT id FROM sos_alerts' in sql:
            return self.existing_alert
        if 'FROM devices' in sql:
            return self.device
        if 'gnss_valid = TRUE' in sql:
            return self.last_fix
        if 'FROM users' in sql:
            return self.user
        raise UnroutedSql(f'fetchrow: {sql!r}')

    def fetchval(self, sql: str, *args: Any) -> Any:
        self.log.append(('fetchval', sql))
        if 'SELECT sos_active' in sql:
            return self.prev_sos
        if 'EXISTS' in sql:
            if self.sos_open is not None:
                return self.sos_open
            return self.existing_alert is not None or self.alerts_inserted > 0
        raise UnroutedSql(f'fetchval: {sql!r}')

    def fetch(self, sql: str, *args: Any) -> Any:
        self.log.append(('fetch', sql))
        if 'FROM user_groups' in sql:
            return self.groups
        raise UnroutedSql(f'fetch: {sql!r}')

    def execute(self, sql: str, *args: Any) -> Any:
        self.log.append(('execute', sql))
        return None

    def record_transactions(self, conn) -> None:
        """Make `conn.transaction()` write `begin` / `commit` (or `rollback`) into the same log."""
        log = self.log

        def _transaction(*a, **kw):
            tx = MagicMock()

            async def _enter(*_):
                log.append(('tx', 'begin'))
                return tx

            async def _exit(exc_type, exc, tb):
                log.append(('tx', 'rollback' if exc_type else 'commit'))
                return False

            tx.__aenter__ = AsyncMock(side_effect=_enter)
            tx.__aexit__ = AsyncMock(side_effect=_exit)
            tx.start = AsyncMock(side_effect=lambda: log.append(('tx', 'begin')))
            tx.commit = AsyncMock(side_effect=lambda: log.append(('tx', 'commit')))
            tx.rollback = AsyncMock(side_effect=lambda: log.append(('tx', 'rollback')))
            return tx

        conn.transaction = MagicMock(side_effect=_transaction)


def install(conn, **state: Any) -> GatewaySql:
    """Route `conn`'s fetchrow / fetchval / fetch / execute through a fresh `GatewaySql`.

    The AsyncMocks stay in place, so `call_args_list` still records every call."""
    sql = GatewaySql(**state)
    conn.fetchrow = AsyncMock(side_effect=sql.fetchrow)
    conn.fetchval = AsyncMock(side_effect=sql.fetchval)
    conn.fetch = AsyncMock(side_effect=sql.fetch)
    conn.execute = AsyncMock(side_effect=sql.execute)
    return sql
