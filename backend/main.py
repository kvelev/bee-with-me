import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .auth import hash_password
from .database import close_pool, get_pool, init_pool
from .routers import auth, devices, export, groups, locations, users, ws, test, hardware_reader
from .ws import manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _ensure_default_admin() -> None:
    async with get_pool().acquire() as conn:
        count = await conn.fetchval('SELECT COUNT(*) FROM users')
        if count == 0:
            await conn.execute(
                """INSERT INTO users (username, password_hash, full_name, role)
                   VALUES ('admin', $1, 'Administrator', 'admin')""",
                hash_password('admin'),
            )
            logger.info('Default admin created — username: admin / password: admin')


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    logger.info('Database pool ready')
    await _ensure_default_admin()

    notify_task = asyncio.create_task(manager.listen_notifications())

    # Hardware reader runs only when a real port is available
    serial_task = None
    try:
        from .hardware_reader.reader import run as hardware_reader_run
        serial_task = asyncio.create_task(hardware_reader_run())
        logger.info('Hardware reader task started')
    except Exception as exc:
        logger.warning('Serial reader not started: %s', exc)

    yield

    notify_task.cancel()
    if serial_task:
        serial_task.cancel()
    await close_pool()


app = FastAPI(title='Bee With Me API', version='1.2.0', lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],  # tighten in production
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(groups.router)
app.include_router(devices.router)
app.include_router(locations.router)
app.include_router(export.router)
app.include_router(ws.router)
app.include_router(test.router)
app.include_router(hardware_reader.router)


import os
os.makedirs('backend/uploads', exist_ok=True)
app.mount('/uploads', StaticFiles(directory='backend/uploads'), name='uploads')


@app.get('/health')
async def health():
    return {'status': 'ok'}
