import json
import logging
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.routes import router as api_router
from app.core.config import settings
from app.core.database import async_session_factory

logger = logging.getLogger(__name__)


async def persist_message(message: dict):
    """Save a telegram_message event to the conversations/messages tables."""
    try:
        from app.models.models import (
            Account,
            AccountHealth,
            Conversation,
            ConversationState,
            IntelligenceCategory,
            Message,
            MessageDirection,
            Platform,
            Task,
            TaskStatus,
        )

        account_name = message.get("account", "unknown")
        sender_id = message.get("sender_id", "unknown")
        sender_name = message.get("sender_name", "Unknown")
        content = message.get("content", "")
        direction = message.get("direction", "inbound")
        platform_str = message.get("platform", "telegram")
        timestamp_str = message.get("timestamp")

        if timestamp_str:
            try:
                created_at = datetime.fromisoformat(timestamp_str)
            except (ValueError, TypeError):
                created_at = datetime.now(timezone.utc)
        else:
            created_at = datetime.now(timezone.utc)

        # Deterministic UUIDs from names
        account_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, f"account-{account_name}")
        task_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, f"task-auto-{platform_str}")

        platform_enum = {
            "telegram": Platform.TELEGRAM,
            "facebook": Platform.FACEBOOK,
            "zalo": Platform.ZALO,
        }.get(platform_str, Platform.TELEGRAM)

        async with async_session_factory() as session:
            # Ensure Account exists
            result = await session.execute(select(Account).where(Account.id == account_uuid))
            if not result.scalar_one_or_none():
                acct = Account(
                    id=account_uuid,
                    platform=platform_enum,
                    username=account_name,
                    credentials={},
                    health=AccountHealth.GREEN,
                    is_active=True,
                )
                session.add(acct)

            # Ensure Task exists
            result = await session.execute(select(Task).where(Task.id == task_uuid))
            if not result.scalar_one_or_none():
                task = Task(
                    id=task_uuid,
                    name=f"Auto-{platform_str}",
                    platform=platform_enum,
                    category=IntelligenceCategory.CURRENCY_EXCHANGER,
                    keywords=[],
                    status=TaskStatus.RUNNING,
                )
                session.add(task)

            await session.flush()

            # Find or create conversation
            result = await session.execute(
                select(Conversation).where(
                    Conversation.target_user_id == sender_id,
                    Conversation.account_id == account_uuid,
                    Conversation.ended_at.is_(None),
                )
            )
            conv = result.scalar_one_or_none()

            if not conv:
                conv = Conversation(
                    id=uuid.uuid4(),
                    account_id=account_uuid,
                    task_id=task_uuid,
                    target_user_id=sender_id,
                    target_display_name=sender_name,
                    state=ConversationState.PROBING,
                    turn_count=0,
                )
                session.add(conv)
                await session.flush()

            msg_direction = (
                MessageDirection.INBOUND if direction == "inbound" else MessageDirection.OUTBOUND
            )
            msg = Message(
                id=uuid.uuid4(),
                conversation_id=conv.id,
                direction=msg_direction,
                content=content,
                created_at=created_at,
            )
            session.add(msg)
            conv.turn_count = (conv.turn_count or 0) + 1
            await session.commit()

    except Exception as e:
        logger.warning("Failed to persist message: %s", e)


class ConnectionManager:
    """Manage WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, websocket: WebSocket, channel: str = "global"):
        await websocket.accept()
        self.active_connections[channel].append(websocket)
        logger.info(
            "WebSocket connected on channel %s (total: %d)",
            channel,
            len(self.active_connections[channel]),
        )

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
    # 前端用 localhost:3000 或 127.0.0.1:3000 打开都要能连上；
    # 只放行其中一个时，另一个来源的请求会被浏览器拦掉，页面显示"后端不可达"
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
                    await persist_message(message)
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
