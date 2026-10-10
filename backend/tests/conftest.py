"""
Shared test fixtures.

A lightweight FastAPI test app is constructed without the full lifespan
(no DB pool, no serial reader, no pg_notify listener) so tests run offline.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth import create_access_token, hash_password, get_current_user
from backend.database import get_conn
from backend.routers import auth, devices, export, fire, groups, locations, users
from backend.routers import test as test_router
from backend.routers import settings as settings_router
from backend.routers import weather as weather_router
from backend.routers import tiles as tiles_router

# ── Minimal app without lifespan ──────────────────────────────────────────────

_app = FastAPI()
_app.include_router(auth.router)
_app.include_router(users.router)
_app.include_router(groups.router)
_app.include_router(devices.router)
_app.include_router(locations.router)
_app.include_router(export.router)
_app.include_router(fire.router)
_app.include_router(settings_router.router)
_app.include_router(test_router.router)
_app.include_router(weather_router.router)
_app.include_router(tiles_router.router)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_user(role: str = 'admin', active: bool = True) -> dict:
    uid = str(uuid.uuid4())
    return {
        'id': uid,
        'username': 'testuser',
        'full_name': 'Test User',
        'role': role,
        'is_active': active,
        'password_hash': hash_password('secret'),
    }


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def mock_conn():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch    = AsyncMock(return_value=[])
    conn.execute  = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=0)
    # `async with conn.transaction():` works on the mock (a plain AsyncMock child returns a coroutine, not a context)
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    return conn


@pytest.fixture()
def admin_user():
    return make_user(role='admin')


@pytest.fixture()
def viewer_user():
    return make_user(role='viewer')


@pytest.fixture()
def client(mock_conn, admin_user):
    """TestClient with mocked DB and pre-authenticated admin user."""

    async def _get_conn():
        yield mock_conn

    async def _get_current_user():
        return admin_user

    _app.dependency_overrides[get_conn] = _get_conn
    _app.dependency_overrides[get_current_user] = _get_current_user

    with TestClient(_app, raise_server_exceptions=True) as c:
        yield c

    _app.dependency_overrides.clear()


@pytest.fixture()
def test_app():
    """The lifespan-free FastAPI app, for tests that manage dependency overrides themselves."""
    return _app


@pytest.fixture()
def auth_headers(admin_user):
    token = create_access_token(admin_user['id'], admin_user['role'])
    return {'Authorization': f'Bearer {token}'}


# ── Plan tooling: task filter + scratch databases ─────────────────────────────

import asyncio

import asyncpg
import pytest_asyncio

from backend.config import settings


def pytest_addoption(parser):
    parser.addoption(
        '--task', action='append', default=[],
        help='Only run tests tagged @pytest.mark.Trait("Task"|"Bug", "<id>"); repeatable',
    )
    parser.addoption(
        '--require-db', action='store_true',
        help='Fail (instead of skip) DB tests when PostgreSQL is unreachable',
    )


def pytest_configure(config):
    config.addinivalue_line('markers', 'Trait(kind, id): plan task/bug tag, e.g. Trait("Task", "T3")')
    config.addinivalue_line('markers', 'db: needs a reachable PostgreSQL (skipped when unreachable; fails instead under --require-db)')


def pytest_collection_modifyitems(config, items):
    wanted = set(config.getoption('--task'))
    if not wanted:
        return
    keep, drop = [], []
    for item in items:
        tags = {m.args[1] for m in item.iter_markers('Trait') if len(m.args) == 2}
        (keep if tags & wanted else drop).append(item)
    if drop:
        config.hook.pytest_deselected(items=drop)
    items[:] = keep


def _dsn(database: str) -> dict:
    return dict(
        host=settings.postgres_host, port=settings.postgres_port,
        user=settings.postgres_user, password=settings.postgres_password,
        database=database,
    )


def _allow_without_backup(mp):
    mp.setenv('ALLOW_MIGRATE_WITHOUT_BACKUP', 'true')
    mp.setattr(settings, 'allow_migrate_without_backup', True)


@pytest.fixture()
def allow_migrate_without_backup(monkeypatch):
    """ALLOW_MIGRATE_WITHOUT_BACKUP=true for one test (migrate() skips the backup-marker guard)."""
    _allow_without_backup(monkeypatch)


@pytest_asyncio.fixture()
async def scratch_db(request):
    """A fresh, empty database for one test, dropped afterwards.

    Scratch databases are throwaway, so the backup-marker guard is off while one exists
    (ALLOW_MIGRATE_WITHOUT_BACKUP=true); the guard's own tests switch it back on with monkeypatch.
    """
    with pytest.MonkeyPatch.context() as mp:
        _allow_without_backup(mp)
        async for dsn in _scratch_db(request):
            yield dsn


async def _scratch_db(request):
    try:
        admin = await asyncpg.connect(**_dsn(settings.postgres_db), timeout=3)
    except (OSError, asyncpg.PostgresError, asyncio.TimeoutError) as exc:
        if request.config.getoption('--require-db'):
            pytest.fail(f'PostgreSQL required but not reachable: {exc}')
        pytest.skip(f'PostgreSQL not reachable: {exc}')
    from backend.tests.script_env import scratch_db_name
    name = scratch_db_name()
    try:
        await admin.execute(f'CREATE DATABASE {name}')
        yield _dsn(name)
    finally:
        await admin.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)')
        await admin.close()


@pytest_asyncio.fixture()
async def scratch_conn(scratch_db):
    conn = await asyncpg.connect(**scratch_db)
    try:
        yield conn
    finally:
        await conn.close()


@pytest_asyncio.fixture()
async def migrated_conn(scratch_conn):
    """Scratch database with every migration in this build applied."""
    from backend.db.migrate import load_migrations, migrate
    await migrate(scratch_conn, load_migrations())
    return scratch_conn


@pytest_asyncio.fixture()
async def scratch_pool(migrated_conn, scratch_db):
    """asyncpg pool on the migrated scratch database."""
    pool = await asyncpg.create_pool(**scratch_db, min_size=1, max_size=4)
    try:
        yield pool
    finally:
        await pool.close()
