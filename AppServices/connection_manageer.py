from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int : WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        self.active_connections[user_id] = websocket
    def disconnect(self, user_id: int):
        # Assuming you have a way to identify each user, e.g., via a token or user ID
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def broadcast(self, message: dict):
        for connection in self.active_connections.values():
            await connection.send_json(message)

    async def send_to_user(self, user_id: int, message: dict):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_json(message)