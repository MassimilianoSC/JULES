from fastapi import WebSocket, WebSocketDisconnect
from bson import ObjectId

active_ws_connections = []

async def get_ws_user(websocket: WebSocket):
    # Recupera la sessione dai cookie
    session = websocket.cookies.get("session")
    if not session:
        return None
    try:
        db = websocket.app.state.db
        uid = websocket.session.get("user_id")
        if not uid:
            return None
        user = await db.users.find_one({"_id": ObjectId(uid)})
        return user
    except Exception as e:
        print(f"[WS DEBUG] Errore autenticazione: {e}")
        return None

async def broadcast_message(message: str):
    for ws in list(active_ws_connections):
        try:
            await ws.send_text(message)
        except Exception:
            try:
                active_ws_connections.remove(ws)
            except ValueError:
                pass

async def websocket_notify(websocket: WebSocket):
    user = await get_ws_user(websocket)
    if not user:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    await websocket.accept()
    active_ws_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_ws_connections.remove(websocket)