from fastapi import WebSocket, WebSocketDisconnect

active_ws_connections = []

async def broadcast_message(message: str):
    print(f"[WS DEBUG] Invio messaggio: {message} a {len(active_ws_connections)} client connessi")
    for ws in list(active_ws_connections):
        try:
            print(f"[WS DEBUG] Invio a client: {ws.client}")
            await ws.send_text(message)
        except Exception:
            try:
                active_ws_connections.remove(ws)
            except ValueError:
                pass

async def websocket_notify(websocket: WebSocket):
    await websocket.accept()
    active_ws_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()  # opzionale, puoi ignorare il messaggio
    except WebSocketDisconnect:
        active_ws_connections.remove(websocket) 