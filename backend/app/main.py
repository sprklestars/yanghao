import asyncio
import json
import logging
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manage WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, websocket: WebSocket, channel: str = "global"):
        await websocket.accept()
        self.active_connections[channel].append(websocket)
        logger.info("WebSocket connected on channel %s (total: %d)", channel, len(self.active_connections[channel]))

    def disconnect(self, websocket: WebSocket, channel: str = "global"):
        if websocket in self.active_connections[channel]:
            self.active_connections[channel].remove(websocket)
            logger.info("WebSocket disconnected from channel %s", channel)

    async def broadcast(self, message: dict, channel: str = "global"):
        """Send message to all connections in a channel."""
        disconnected = []
        for connection in self.active_connections[channel]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error("Failed to send WebSocket message: %s", e)
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn, channel)

    async def send_to_task(self, task_id: str, message: dict):
        """Send message to specific task channel."""
        await self.broadcast(message, channel=f"task:{task_id}")

    async def send_to_conversation(self, conv_id: str, message: dict):
        """Send message to specific conversation channel."""
        await self.broadcast(message, channel=f"conv:{conv_id}")


# Global connection manager
manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: init connections, warm up caches
    logger.info("OSINT Platform API starting up")
    yield
    # shutdown: close connections
    logger.info("OSINT Platform API shutting down")
    for channel in list(manager.active_connections.keys()):
        for conn in manager.active_connections[channel]:
            try:
                await conn.close()
            except Exception:
                pass


app = FastAPI(
    title="OSINT Platform API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.routes import router as api_router

app.include_router(api_router, prefix="/api/v1")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    channel = "global"

    # Accept query parameter for channel subscription
    await manager.connect(websocket, channel)

    try:
        while True:
            # Listen for client messages (e.g., channel subscription changes)
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                if message.get("type") == "subscribe":
                    new_channel = message.get("channel")
                    if new_channel:
                        manager.disconnect(websocket, channel)
                        channel = new_channel
                        manager.active_connections[channel].append(websocket)
                        await websocket.send_json({"type": "subscribed", "channel": channel})
                elif message.get("type") == "telegram_message":
                    await manager.broadcast(message, channel="global")
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        manager.disconnect(websocket, channel)


@app.get("/health")
async def health_check():
    return {"status": "ok", "env": settings.app_env}
