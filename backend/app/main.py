import hashlib
import json
import logging
import re
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.routes import router as api_router
from app.core.config import settings
from app.core.database import async_session_factory

logger = logging.getLogger(__name__)

# 本机前端可能落在任意端口上：3000 被占用时 Next.js 会自动退到 3001，
# 所以按"本机来源"放行，而不是把端口写死（写死过一次就踩了 3001 的坑）。
LOCAL_ORIGIN_REGEX = r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"


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

            # 收到对方的消息时顺手抽情报（情报报告页读的就是这张表）
            if msg_direction == MessageDirection.INBOUND and content:
                await _extract_intelligence(session, conv, platform_enum, content)

    except Exception as e:
        logger.warning("Failed to persist message: %s", e)


async def _extract_intelligence(session, conv, platform_enum, text: str) -> None:
    """从一条入站消息里抽取情报并落库/更新。

    以前只有 `workers.process_incoming_message()` 会写 `intelligence_records`，
    而那个 Celery 任务全仓库没有任何调用点（守护进程有自己的回复逻辑），
    所以情报报告页永远是空的。这里把它接在真实消息流上：
    守护进程 → WebSocket → persist_message → 抽取 → 情报表。
    """
    from app.models.models import IntelligenceCategory, IntelligenceRecord
    from app.services.intelligence.pipeline import (
        calculate_activity_score,
        classify_category,
        extract_entities,
    )

    entities = extract_entities(text)
    category_name, confidence, signals = classify_category(text)

    try:
        category = IntelligenceCategory(category_name)
    except ValueError:
        # 没命中四类业务信号词就不建记录（情报只针对特定业务线索）
        logger.info(
            "消息未命中业务分类（%s），不生成情报记录：%s",
            category_name,
            text[:60],
        )
        return

    fingerprint = hashlib.sha256(
        "|".join(
            [conv.target_user_id, *entities.phones, *entities.emails, *entities.zalo_ids]
        ).encode()
    ).hexdigest()[:128]

    existing = (
        await session.execute(
            select(IntelligenceRecord).where(
                IntelligenceRecord.dedup_fingerprint == fingerprint
            )
        )
    ).scalar_one_or_none()

    contacts = {
        "phones": entities.phones,
        "emails": entities.emails,
        "zalo_ids": entities.zalo_ids,
        "telegram_handles": entities.telegram_handles,
        "facebook_urls": entities.facebook_urls,
    }
    business = {
        "prices": entities.prices,
        "addresses": entities.addresses,
        "websites": entities.websites,
        "bank_accounts": entities.bank_accounts,
    }
    activity = calculate_activity_score(
        last_message_age_hours=0,
        messages_per_day=conv.turn_count or 1,
        response_rate=0.8,
        has_complete_profile=bool(conv.target_display_name),
    )

    if existing is not None:
        # 同一个目标再次出现：合并信号、抬高置信度，不重复建行
        existing.confidence = max(existing.confidence or 0.0, confidence)
        existing.signals = sorted(set((existing.signals or []) + signals))
        existing.extracted_contacts = contacts
        existing.business_info = business
        existing.activity_status = activity
        existing.last_seen = datetime.now(timezone.utc)
        logger.info("更新情报记录 %s（目标 %s）", existing.id, conv.target_user_id)
    else:
        session.add(
            IntelligenceRecord(
                id=uuid.uuid4(),
                task_id=conv.task_id,
                platform=platform_enum,
                target_user_id=conv.target_user_id,
                display_name=conv.target_display_name,
                category=category,
                confidence=confidence,
                signals=signals,
                extracted_contacts=contacts,
                business_info=business,
                activity_status=activity,
                last_seen=datetime.now(timezone.utc),
                dedup_fingerprint=fingerprint,
            )
        )
        logger.info(
            "新增情报记录：目标 %s / 分类 %s / 置信度 %.2f",
            conv.target_user_id,
            category_name,
            confidence,
        )
    await session.commit()


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
    allow_origin_regex=LOCAL_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """未处理异常也要带上跨域头，否则前端只能看到一句误导性的"无法连接后端服务"。

    Starlette 的 ServerErrorMiddleware 位于中间件栈的最外层，它生成的 500 响应
    不会经过 CORSMiddleware，因此不带 Access-Control-Allow-Origin。浏览器于是把
    这个响应当作跨域失败丢弃，前端的 fetch 抛 TypeError，只能提示"后端不可达"，
    真正的异常（例如 sqlite3.OperationalError）就被掩盖了。这里手工补上跨域头，
    并把异常信息返回给前端，便于定位问题。
    """
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    origin = request.headers.get("origin")
    headers = (
        {"Access-Control-Allow-Origin": origin}
        if origin and re.match(LOCAL_ORIGIN_REGEX, origin)
        else None
    )
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
        headers=headers,
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
