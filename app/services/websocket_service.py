from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List
import asyncio

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.lock = asyncio.Lock()

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        async with self.lock:
            if user_id not in self.active_connections:
                self.active_connections[user_id] = []
            self.active_connections[user_id].append(websocket)

    async def disconnect(self, user_id: str, websocket: WebSocket):
        async with self.lock:
            if user_id in self.active_connections:
                self.active_connections[user_id].remove(websocket)
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]

    async def send_personal_message(self, user_id: str, message: dict):
        async with self.lock:
            for ws in self.active_connections.get(user_id, []):
                try:
                    await ws.send_json(message)
                except:
                    # Connexion fermée, on l'ignore
                    pass

    async def broadcast(self, user_id: str, message: dict):
        # Pour compatibilité, broadcast = send_personal_message
        await self.send_personal_message(user_id, message)

# Instance globale du gestionnaire de connexions
manager = ConnectionManager()

# Fonction utilitaire pour envoyer des notifications en temps réel
async def push_notification_live(user_id: str, notif: dict):
    await manager.broadcast(user_id, notif)