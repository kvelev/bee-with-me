from fastapi import APIRouter, Depends

from ..auth import get_current_user
from ..serial import reader as serial_reader

router = APIRouter(prefix='/api/serial', tags=['serial'])


@router.get('/status')
async def serial_status(_=Depends(get_current_user)):
    return serial_reader.status
