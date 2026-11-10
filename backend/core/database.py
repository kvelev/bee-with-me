import asyncpg
from .config import settings

_pool: asyncpg.Pool | None = None


def connect_kwargs() -> dict:
    """Connection arguments as keywords. Never build a postgresql:// URL from them: asyncpg splits a URL on the first
    '@', so a password containing '@' and ':' ends up in the port field and the int() error repeats it (B86)."""
    return dict(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )


def redact(text: str) -> str:
    """Error text that is safe to log or broadcast: the database password is masked."""
    pw = settings.postgres_password
    return text.replace(pw, '***') if pw else text


async def init_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        **connect_kwargs(),
        min_size=2,
        max_size=10,
    )


async def close_pool() -> None:
    if _pool:
        await _pool.close()


def get_pool() -> asyncpg.Pool:
    assert _pool is not None, 'Pool not initialised'
    return _pool


async def get_conn():
    async with get_pool().acquire() as conn:
        yield conn
