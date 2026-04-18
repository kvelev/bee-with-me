from fastapi import APIRouter, Depends

from ..auth import get_current_user
from ..hardware_reader import reader as hardware_reader

router = APIRouter(prefix='/api/serial', tags=['hardware_reader'])


@router.get('/status')
async def serial_status(_=Depends(get_current_user)):
    return hardware_reader.status
