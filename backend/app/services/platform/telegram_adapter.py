import asyncio
import logging
import os
import random
from dataclasses import dataclass, field
from datetime import datetime

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.contacts import AddContactRequest
from telethon.tl.functions.contacts import SearchRequest as ContactsSearchRequest

from app.core.session_paths import ensure_session_dir
from app.services.platform.base import (
    AccountCredentials,
    AccountHealthStatus,
    GroupInfo,
    MessageContent,
    PlatformAdapter,
    PlatformName,
    UserProfile,
)
from app.services.security.account_warming import warming_manager

logger = logging.getLogger(__name__)


@dataclass
class MediaGroupBuffer:
    """Buffer for aggregating media group messages."""

    items: list[dict] = field(default_factory=list)
    last_update: datetime = field(default_factory=datetime.now)
    target_id: str = ""
    message_thread_id: int | None = None


class TelegramAdapter(PlatformAdapter):
    def __init__(
        self, api_id: int, api_hash: str, session_name: str = "osint_tg", proxy: tuple | None = None
    ):
        self._api_id = api_id
        self._api_hash = api_hash
        self._session_name = session_name
        self._proxy = proxy
        self._client: TelegramClient | None = None
        self._daily_actions = 0
        self._error_count = 0
        self._total_actions = 0
        # Media group buffering: {media_group_id: MediaGroupBuffer}
        self._media_groups: dict[str, MediaGroupBuffer] = {}
        self._flush_task: asyncio.Task | None = None

    async def authenticate(self, credentials: AccountCredentials) -> bool:
        # Telethon 构造时就创建 SQLite session 文件，目录不存在会直接抛
        # sqlite3.OperationalError: unable to open database file。
        ensure_session_dir(self._session_name)
        self._client = TelegramClient(
            self._session_name,
            self._api_id,
            self._api_hash,
            device_model="Samsung Galaxy S24",
            system_version="Android 14",
            app_version="10.12.0",
            proxy=self._proxy,
        )
        phone = credentials.credentials.get("phone")
        password = credentials.credentials.get("password")
        try:
            if phone:
                await self._client.start(phone=phone, password=password)
            else:
                await self._client.connect()
                if not await self._client.is_user_authorized():
                    logger.error("Session %s is not authorized", self._session_name)
                    return False
            logger.info("Telegram authenticated as %s", credentials.username)
            return True
        except Exception as e:
            logger.error("Telegram auth failed: %s", e)
            return False

    async def disconnect(self) -> None:
        if self._client and self._client.is_connected():
            await self._client.disconnect()

    async def search_groups(self, query: str, limit: int = 10) -> list[GroupInfo]:
        assert self._client is not None
        results: list[GroupInfo] = []
        try:
            response = await self._client(
                ContactsSearchRequest(
                    q=query,
                    limit=limit,
                )
            )
            for chat in response.chats or []:
                # Only include groups/channels, skip private chats
                if hasattr(chat, "title"):
                    results.append(
                        GroupInfo(
                            group_id=str(chat.id),
                            name=getattr(chat, "title", ""),
                            member_count=getattr(chat, "participants_count", 0) or 0,
                            description=getattr(chat, "about", "") or "",
                            platform=PlatformName.TELEGRAM,
                        )
                    )
            logger.info("search_groups '%s': found %d results", query, len(results))
        except FloodWaitError as e:
            logger.warning("FloodWait %ds on search_groups", e.seconds)
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error("search_groups error: %s", e)
            self._error_count += 1
        return results

    async def join_group(self, group_id: str) -> bool:
        assert self._client is not None

        # Check account warming limits
        allowed, reason = warming_manager.check_and_enforce_limits(
            account_id=self._session_name,
            operation="join_group",
        )

        if not allowed:
            logger.warning("Account warming limit: %s", reason)
            return False

        try:
            entity = await self._client.get_entity(int(group_id))
            await self._client(JoinChannelRequest(entity))

            # Record the operation
            warming_manager.record_operation(
                account_id=self._session_name,
                operation="join_group",
            )

            self._daily_actions += 1
            self._total_actions += 1

            # Add random delay after joining (30-120 seconds as per anti-detection)
            delay = random.uniform(30, 120)
            await asyncio.sleep(delay)
            return True
        except FloodWaitError as e:
            logger.warning("FloodWait %ds on join_group", e.seconds)
            await asyncio.sleep(e.seconds)
            return False
        except Exception as e:
            logger.error("join_group error: %s", e)
            self._error_count += 1
            return False

    async def send_friend_request(self, user_id: str) -> bool:
        assert self._client is not None

        # Check account warming limits
        allowed, reason = warming_manager.check_and_enforce_limits(
            account_id=self._session_name,
            operation="friend_request",
        )

        if not allowed:
            logger.warning("Account warming limit: %s", reason)
            return False

        try:
            entity = await self._client.get_entity(int(user_id))
            await self._client(
                AddContactRequest(
                    id=entity.id,
                    first_name=getattr(entity, "first_name", ""),
                    last_name=getattr(entity, "last_name", "") or "",
                    phone=getattr(entity, "phone", "") or "",
                )
            )

            # Record the operation
            warming_manager.record_operation(
                account_id=self._session_name,
                operation="friend_request",
            )

            self._daily_actions += 1
            self._total_actions += 1

            delay = random.uniform(30, 120)
            await asyncio.sleep(delay)
            return True
        except FloodWaitError as e:
            logger.warning("FloodWait %ds on send_friend_request", e.seconds)
            await asyncio.sleep(e.seconds)
            return False
        except Exception as e:
            logger.error("send_friend_request error: %s", e)
            self._error_count += 1
            return False

    async def send_message(self, target_id: str, content: MessageContent) -> bool:
        assert self._client is not None

        # Check if this is part of a media group
        media_group_id = content.metadata.get("media_group_id") if content.metadata else None

        if media_group_id:
            return await self._handle_media_group(
                target_id=target_id,
                content=content,
                media_group_id=media_group_id,
            )

        # Check account warming limits
        is_stranger = content.metadata.get("is_stranger", False) if content.metadata else False
        allowed, reason = warming_manager.check_and_enforce_limits(
            account_id=self._session_name,
            operation="send_message",
            is_stranger=is_stranger,
        )

        if not allowed:
            logger.warning("Account warming limit: %s", reason)
            return False

        try:
            # simulate typing delay based on message length
            chars = len(content.text)
            typing_delay = chars * 0.05 * random.uniform(0.7, 1.3)
            await asyncio.sleep(min(typing_delay, 10))

            await self._client.send_message(int(target_id), content.text)

            # Record the operation
            warming_manager.record_operation(
                account_id=self._session_name,
                operation="send_message",
                is_stranger=is_stranger,
            )

            self._daily_actions += 1
            self._total_actions += 1

            # post-send cooldown
            delay = random.uniform(5, 45)
            await asyncio.sleep(delay)
            return True
        except FloodWaitError as e:
            logger.warning("FloodWait %ds on send_message", e.seconds)
            await asyncio.sleep(e.seconds)
            return False
        except Exception as e:
            logger.error("send_message error: %s", e)
            self._error_count += 1
            return False

    async def _handle_media_group(
        self,
        target_id: str,
        content: MessageContent,
        media_group_id: str,
    ) -> bool:
        """Handle media group messages by buffering and batch sending."""
        assert self._client is not None

        # Get or create buffer for this media group
        if media_group_id not in self._media_groups:
            self._media_groups[media_group_id] = MediaGroupBuffer(
                target_id=target_id,
                message_thread_id=content.metadata.get("message_thread_id"),
            )

        buffer = self._media_groups[media_group_id]
        buffer.items.append(content)
        buffer.last_update = datetime.now()

        logger.info(
            "Buffered media group %s: %d items",
            media_group_id,
            len(buffer.items),
        )

        # Schedule flush if not already scheduled
        if not self._flush_task or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._flush_expired_media_groups())

        # If we have 10 items, flush immediately
        if len(buffer.items) >= 10:
            await self._flush_media_group(media_group_id)
            return True

        return True  # Buffered, will be sent later

    async def _flush_media_group(self, media_group_id: str) -> bool:
        """Flush a buffered media group to Telegram."""
        assert self._client is not None

        if media_group_id not in self._media_groups:
            return False

        buffer = self._media_groups.pop(media_group_id)

        if not buffer.items:
            return False

        try:
            # If only one item, send normally
            if len(buffer.items) == 1:
                content = buffer.items[0]
                await self._client.send_message(
                    int(buffer.target_id),
                    content.text,
                )
                logger.info("Sent single media item from group %s", media_group_id)
            else:
                # Send multiple items as a group
                # Note: Telethon doesn't have direct send_media_group,
                # so we send them sequentially with small delays
                for i, content in enumerate(buffer.items):
                    await self._client.send_message(
                        int(buffer.target_id),
                        content.text,
                    )
                    if i < len(buffer.items) - 1:
                        await asyncio.sleep(0.5)  # Small delay between items
                logger.info(
                    "Sent media group %s with %d items",
                    media_group_id,
                    len(buffer.items),
                )

            self._daily_actions += 1
            self._total_actions += 1
            return True

        except FloodWaitError as e:
            logger.warning("FloodWait %ds on flush_media_group", e.seconds)
            await asyncio.sleep(e.seconds)
            return False
        except Exception as e:
            logger.error("flush_media_group error: %s", e)
            self._error_count += 1
            return False

    async def _flush_expired_media_groups(self):
        """Flush media groups that haven't received new items for 2 seconds."""
        while True:
            now = datetime.now()
            expired_ids = []

            for media_group_id, buffer in self._media_groups.items():
                elapsed = (now - buffer.last_update).total_seconds()
                if elapsed > 2.0:  # 2 second timeout
                    expired_ids.append(media_group_id)

            for media_group_id in expired_ids:
                await self._flush_media_group(media_group_id)

            # Check every 500ms
            await asyncio.sleep(0.5)

            # Exit if no more buffers
            if not self._media_groups:
                break

    async def listen_messages(self, callback) -> None:
        assert self._client is not None

        @self._client.on(events.NewMessage(incoming=True))
        async def handler(event):
            try:
                sender = await event.get_sender()
                await callback(
                    {
                        "sender_id": str(sender.id) if sender else None,
                        "sender_name": getattr(sender, "first_name", "") if sender else None,
                        "text": event.raw_text,
                        "chat_id": str(event.chat_id),
                        "message_id": event.id,
                        "timestamp": event.date.isoformat(),
                    }
                )
            except Exception as e:
                logger.error("listen_messages callback error: %s", e)

        await self._client.run_until_disconnected()

    async def get_user_profile(self, user_id: str) -> UserProfile | None:
        assert self._client is not None
        try:
            entity = await self._client.get_entity(int(user_id))
            return UserProfile(
                user_id=str(entity.id),
                display_name=(
                    f"{getattr(entity, 'first_name', '')} {getattr(entity, 'last_name', '') or ''}"
                ).strip(),
                username=getattr(entity, "username", None),
                bio=getattr(entity, "about", None),
                is_online=getattr(entity, "status", None) is not None,
            )
        except Exception as e:
            logger.error("get_user_profile error: %s", e)
            return None

    async def get_group_members(self, group_id: str, limit: int = 100) -> list[UserProfile]:
        assert self._client is not None
        members: list[UserProfile] = []
        try:
            entity = await self._client.get_entity(int(group_id))
            participants = await self._client.get_participants(entity, limit=limit)
            for p in participants:
                members.append(
                    UserProfile(
                        user_id=str(p.id),
                        display_name=(
                            f"{getattr(p, 'first_name', '')} {getattr(p, 'last_name', '') or ''}"
                        ).strip(),
                        username=getattr(p, "username", None),
                        bio=getattr(p, "about", None),
                    )
                )
        except FloodWaitError as e:
            logger.warning("FloodWait %ds on get_group_members", e.seconds)
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error("get_group_members error: %s", e)
            self._error_count += 1
        return members

    def get_health_status(self) -> AccountHealthStatus:
        error_rate = self._error_count / max(self._total_actions, 1)
        if error_rate > 0.2:
            status = "red"
        elif error_rate > 0.1 or self._daily_actions > 50:
            status = "yellow"
        else:
            status = "green"
        return AccountHealthStatus(
            status=status,
            daily_actions=self._daily_actions,
            error_rate=error_rate,
        )

    def _session_file(self) -> str:
        """返回 Telethon 实际使用的 .session 文件路径。

        Telethon 会在 session_name 之后追加 ".session"，而调用方有两种传法：
        routes.py 传的是绝对路径（backend/sessions/xxx），脚本里传的是纯会话名。
        这里分别处理，避免拼出 "sessions/C:\\...\\printer.session" 这种无效路径，
        让会话检测永远误报"Session 文件不存在"。
        """
        name = self._session_name
        if not name.endswith(".session"):
            name = f"{name}.session"
        return name if os.path.isabs(name) else os.path.join("sessions", name)

    async def is_session_valid(self) -> dict:
        session_file = self._session_file()
        if not os.path.exists(session_file):
            return {"valid": False, "message": "Session 文件不存在", "details": {}}
        try:
            ensure_session_dir(self._session_name)
            client = TelegramClient(
                self._session_name,
                self._api_id,
                self._api_hash,
                device_model="Samsung Galaxy S24",
                system_version="Android 14",
                app_version="10.12.0",
                proxy=self._proxy,
            )
            await client.connect()
            authorized = await client.is_user_authorized()
            username = None
            if authorized:
                me = await client.get_me()
                username = getattr(me, "username", None) or getattr(me, "first_name", "")
            await client.disconnect()
            if authorized:
                return {
                    "valid": True,
                    "message": f"Session 有效 (用户: {username})",
                    "details": {"username": username},
                }
            else:
                return {"valid": False, "message": "Session 已过期，请重新登录", "details": {}}
        except Exception as e:
            return {"valid": False, "message": f"检测失败: {e}", "details": {"error": str(e)}}
