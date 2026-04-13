from fastapi import WebSocket

connections = []

async def connect(websocket: WebSocket):
    await websocket.accept()
    connections.append(websocket)

async def broadcast(message: str):
    for connection in connections:
        await connection.send_text(message)