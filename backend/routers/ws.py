from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..ws import manager

router = APIRouter(tags=['websocket'])


@router.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; client can send pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
