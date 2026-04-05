"""
WebSocket connection manager with JWT authentication and room broadcasting.
Fixes defect #9: WS handshake validates JWT token from query param.
"""

import json
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.auth.jwt import decode_token

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        # room_id (facility_id) -> set of websockets
        self.rooms: Dict[int, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, facility_id: int):
        await websocket.accept()
        if facility_id not in self.rooms:
            self.rooms[facility_id] = set()
        self.rooms[facility_id].add(websocket)

    def disconnect(self, websocket: WebSocket, facility_id: int):
        if facility_id in self.rooms:
            self.rooms[facility_id].discard(websocket)
            if not self.rooms[facility_id]:
                del self.rooms[facility_id]

    async def broadcast(self, facility_id: int, message: dict):
        """Broadcast a message to all connections in a facility room."""
        if facility_id not in self.rooms:
            return
        dead = []
        for ws in self.rooms[facility_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.rooms[facility_id].discard(ws)

    async def send_to(self, websocket: WebSocket, message: dict):
        await websocket.send_json(message)


ws_manager = ConnectionManager()


@router.websocket("/ws/calendar")
async def websocket_calendar(
    websocket: WebSocket,
    facility_id: int = Query(1),
    token: str = Query(""),
):
    # JWT authentication on WebSocket handshake (defect #9 fix)
    if not token:
        await websocket.close(code=4001, reason="Token required")
        return

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    user_role = payload.get("role", "")
    user_id = payload.get("sub")

    await ws_manager.connect(websocket, facility_id)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")

            if msg_type == "DRAG_START":
                # Broadcast to others that this appointment is being moved
                await ws_manager.broadcast(facility_id, {
                    "type": "DRAG_START",
                    "appointment_id": msg.get("appointment_id"),
                    "by_user": user_id,
                })

            elif msg_type == "DRAG_END":
                await ws_manager.broadcast(facility_id, {
                    "type": "DRAG_END",
                    "appointment_id": msg.get("appointment_id"),
                })

            elif msg_type == "DRAG_COMMIT":
                # The actual commit is done via REST API
                # Client should call PUT /api/calendar/drag after this
                pass

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, facility_id)
