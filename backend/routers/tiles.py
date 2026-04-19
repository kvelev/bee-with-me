import asyncio
import math
import os

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from ..auth import require_role

router = APIRouter(prefix='/api/tiles', tags=['tiles'])

TILE_DIR   = 'tiles/bgmountains'
SOURCE_URL = 'https://bgmtile.kade.si/{z}/{x}/{y}.png'
DELAY_SEC  = 0.05

LON_MIN, LAT_MIN, LON_MAX, LAT_MAX = 22.3, 41.2, 28.7, 44.3
MIN_ZOOM, MAX_ZOOM = 8, 18

_status: dict = {'running': False, 'total': 0, 'done': 0, 'skipped': 0, 'errors': 0, 'error_msg': None}


def _lon_to_x(lon: float, z: int) -> int:
    return int((lon + 180.0) / 360.0 * (1 << z))


def _lat_to_y(lat: float, z: int) -> int:
    import math
    r = math.radians(lat)
    return int((1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * (1 << z))


def _count_tiles() -> int:
    total = 0
    for z in range(MIN_ZOOM, MAX_ZOOM + 1):
        x0, x1 = _lon_to_x(LON_MIN, z), _lon_to_x(LON_MAX, z)
        y0, y1 = _lat_to_y(LAT_MAX, z), _lat_to_y(LAT_MIN, z)
        total += (x1 - x0 + 1) * (y1 - y0 + 1)
    return total


async def _run_download() -> None:
    _status.update(running=True, done=0, skipped=0, errors=0, error_msg=None,
                   total=_count_tiles())
    try:
        async with httpx.AsyncClient(timeout=15, headers={'User-Agent': 'BeeWithMe-TileDownloader/1.0'}) as client:
            for z in range(MIN_ZOOM, MAX_ZOOM + 1):
                x0, x1 = _lon_to_x(LON_MIN, z), _lon_to_x(LON_MAX, z)
                y0, y1 = _lat_to_y(LAT_MAX, z), _lat_to_y(LAT_MIN, z)
                for x in range(x0, x1 + 1):
                    dir_path = os.path.join(TILE_DIR, str(z), str(x))
                    os.makedirs(dir_path, exist_ok=True)
                    for y in range(y0, y1 + 1):
                        out_path = os.path.join(dir_path, f'{y}.png')
                        _status['done'] += 1
                        if os.path.exists(out_path):
                            _status['skipped'] += 1
                            continue
                        try:
                            resp = await client.get(SOURCE_URL.format(z=z, x=x, y=y))
                            if resp.status_code == 200 and len(resp.content) > 67:
                                with open(out_path, 'wb') as f:
                                    f.write(resp.content)
                            elif resp.status_code not in (200, 404):
                                _status['errors'] += 1
                                if _status['errors'] == 1:
                                    _status['error_msg'] = f'HTTP {resp.status_code}'
                        except Exception as e:
                            _status['errors'] += 1
                            if _status['errors'] == 1:
                                _status['error_msg'] = str(e)
                        await asyncio.sleep(DELAY_SEC)
    except Exception as e:
        _status['error_msg'] = str(e)
    finally:
        _status['running'] = False


@router.post('/bgmountains/download')
async def start_download(
    background_tasks: BackgroundTasks,
    _=Depends(require_role('admin')),
):
    if _status['running']:
        raise HTTPException(status_code=409, detail='Download already in progress')
    background_tasks.add_task(_run_download)
    return {'started': True}


@router.get('/bgmountains/status')
async def download_status(_=Depends(require_role('admin'))):
    return _status
