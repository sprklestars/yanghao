import asyncio
import json
import logging
import os
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.contacts import AddContactRequest
from telethon.tl.functions.contacts import SearchRequest as ContactsSearchRequest
from telethon.tl.types import User

from app.core.session_paths import SESSION_DIR, ensure_session_dir
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
from app.services.security.rate_limiter import health_monitor, rate_limiter

logger = logging.getLogger(__name__)

PLATFORM_NAME = "telegram"


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

    # ── 限流 / 健康监控 / 养号档案 ──
    def _account_name(self) -> str:
        """会话名（sessions/ 下的 id），元数据文件用它命名。"""
        return self._session_file().replace(os.sep, "/").split("/")[-1].removesuffix(".session")

    async def _rate_limit_ok(self, *actions: str) -> bool:
        """平台级限流（小时/天滑动窗口）。超限就跳过本次动作。"""
        allowed, blocked = await rate_limiter.allow(
            PLATFORM_NAME, list(actions), self._session_name
        )
        if not allowed:
            logger.warning(
                "[%s] 平台限流命中 %s，本次动作跳过", self._account_name(), blocked
            )
            self._record_health(False)
        return allowed

    def _record_health(self, success: bool) -> None:
        """记录一次动作结果，并把健康度结论同步到账号元数据（前端徽章据此显示）。"""
        health_monitor.record_action(self._session_name, success)
        self._sync_health_to_meta()

    def _ensure_warming_profile(self) -> None:
        """确保该账号有养号档案，否则数字限额形同虚设（没有档案 = 默认放行）。

        用会话文件 mtime 近似账号注册时间，据此判断 NEW / WARMING / STABLE / MATURE。
        """
        created_at = None
        try:
            created_at = datetime.fromtimestamp(Path(self._session_file()).stat().st_mtime)
        except OSError:
            created_at = None
        profile = warming_manager.ensure_profile(self._account_name(), created_at=created_at)
        configured = {
            "interface_localized": profile.interface_localized,
            "contacts_sync_disabled": profile.contacts_sync_disabled,
            "two_factor_enabled": profile.two_factor_enabled,
            "auto_delete_enabled": profile.auto_delete_enabled,
            "privacy_settings_complete": profile.privacy_settings_complete,
        }
        missing = [name for name, done in configured.items() if not done]
        meta = self._read_meta()
        meta.update(
            {
                "warming_stage": profile.account_age.name.lower(),
                "warming_age_days": profile.age_days,
                "warming_enforce_setup_check": profile.enforce_setup_check,
                "warming_missing": missing,
            }
        )
        self._write_meta(meta)
        if profile.enforce_setup_check and profile.account_age.name == "NEW" and missing:
            logger.warning(
                "[%s] 新号尚未完成 5 项自检（缺 %s），加群/发消息会被拒绝；"
                "可用 PATCH /accounts/%s/warming 补齐自检项",
                self._account_name(),
                ", ".join(missing),
                self._account_name(),
            )
        elif missing and profile.account_age.name == "NEW":
            logger.info(
                "[%s] 新号尚未完成 5 项自检（缺 %s）：当前只套用数字限额，"
                "需要严格模式可 PATCH /accounts/%s/warming {\"enforce_setup_check\": true}",
                self._account_name(),
                ", ".join(missing),
                self._account_name(),
            )
        logger.info(
            "[%s] 养号阶段 %s（%d 天），今天已加群 %d / 发消息 %d / 陌生人 %d",
            self._account_name(),
            profile.account_age.name,
            profile.age_days,
            profile.groups_joined_today,
            profile.messages_sent_today,
            profile.stranger_messages_today,
        )

    def _sync_health_to_meta(self) -> None:
        status = health_monitor.evaluate(self._session_name)
        meta = self._read_meta()
        if meta.get("health") == status:
            return
        meta["health"] = status
        self._write_meta(meta)
        logger.info("[%s] 健康度更新为 %s", self._account_name(), status)

    # ── 账号元数据文件（sessions/<name>_meta.json） ──
    def _meta_path(self) -> Path:
        return SESSION_DIR / f"{self._account_name()}_meta.json"

    def _read_meta(self) -> dict:
        path = self._meta_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8")) or {}
        except (OSError, ValueError):
            return {}

    def _write_meta(self, meta: dict) -> None:
        path = self._meta_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        except OSError as e:
            logger.warning("写入账号元数据失败: %s", e)

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
            self._ensure_warming_profile()
            return True
        except Exception as e:
            logger.error("Telegram auth failed: %s", e)
            return False

    async def disconnect(self) -> None:
        client = self._client
        if client is None:
            return
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception as e:
            # disconnect() 内部会 save_states 再 close，中途抛错就走不到 close。
            logger.warning("Telethon 断开时出错（继续清理会话文件）: %s", e)
        finally:
            # 关键：Telethon 只在 _disconnect_coro 的最后一步关 session，
            # 任何中途异常（例如 SQLite "database is locked"）都会让连接一直开着，
            # 于是这个进程永久占着 .session 文件，其它进程/任务全部失败。
            # 这里无论如何都显式关闭。
            try:
                result = client.session.close()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning("关闭会话文件失败: %s", e)
            self._client = None

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
            self._error_count += 1
            logger.error("search_groups error: %s", e, exc_info=True)
            # 以前这里把异常吞掉只返回空列表：任务会"成功完成"但一个群都没搜到，
            # 日志里也看不出原因。改成向上抛，调用方（接口/任务）自己决定怎么报错。
            raise
        return results

    async def join_group(self, group_id: str) -> bool:
        assert self._client is not None

        # Check account warming limits
        allowed, reason = warming_manager.check_and_enforce_limits(
            account_id=self._account_name(),
            operation="join_group",
        )

        if not allowed:
            logger.warning("Account warming limit: %s", reason)
            return False

        if not await self._rate_limit_ok("group_joins_per_day"):
            return False

        try:
            entity = await self._client.get_entity(int(group_id))
            await self._client(JoinChannelRequest(entity))

            # Record the operation
            warming_manager.record_operation(
                account_id=self._account_name(),
                operation="join_group",
            )

            self._daily_actions += 1
            self._total_actions += 1
            self._record_health(True)

            # Add random delay after joining (30-120 seconds as per anti-detection)
            delay = random.uniform(30, 120)
            await asyncio.sleep(delay)
            return True
        except FloodWaitError as e:
            logger.warning("FloodWait %ds on join_group", e.seconds)
            self._record_health(False)
            await asyncio.sleep(e.seconds)
            return False
        except Exception as e:
            logger.error("join_group error: %s", e)
            self._error_count += 1
            self._record_health(False)
            return False

    async def send_friend_request(self, user_id: str) -> bool:
        assert self._client is not None

        # Check account warming limits
        allowed, reason = warming_manager.check_and_enforce_limits(
            account_id=self._account_name(),
            operation="friend_request",
        )

        if not allowed:
            logger.warning("Account warming limit: %s", reason)
            return False

        if not await self._rate_limit_ok("friend_requests_per_day"):
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
                account_id=self._account_name(),
                operation="friend_request",
            )

            self._daily_actions += 1
            self._total_actions += 1
            self._record_health(True)

            delay = random.uniform(30, 120)
            await asyncio.sleep(delay)
            return True
        except FloodWaitError as e:
            logger.warning("FloodWait %ds on send_friend_request", e.seconds)
            self._record_health(False)
            await asyncio.sleep(e.seconds)
            return False
        except Exception as e:
            logger.error("send_friend_request error: %s", e)
            self._error_count += 1
            self._record_health(False)
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
            account_id=self._account_name(),
            operation="send_message",
            is_stranger=is_stranger,
        )

        if not allowed:
            logger.warning("Account warming limit: %s", reason)
            return False

        # 平台级限流：小时与天两个额度都要通过，才计这一次动作
        if not await self._rate_limit_ok("messages_per_hour", "messages_per_day"):
            return False

        try:
            # simulate typing delay based on message length
            chars = len(content.text)
            typing_delay = chars * 0.05 * random.uniform(0.7, 1.3)
            await asyncio.sleep(min(typing_delay, 10))

            # target_id 可能是数字 id，也可能是 "@username"（群成员列表拿不到时
            # 只能从群消息里捡带用户名的发言者来私聊）
            target = int(target_id) if str(target_id).lstrip("-").isdigit() else target_id
            await self._client.send_message(target, content.text)

            # Record the operation
            warming_manager.record_operation(
                account_id=self._account_name(),
                operation="send_message",
                is_stranger=is_stranger,
            )

            self._daily_actions += 1
            self._total_actions += 1
            self._record_health(True)

            # post-send cooldown
            delay = random.uniform(5, 45)
            await asyncio.sleep(delay)
            return True
        except FloodWaitError as e:
            logger.warning("FloodWait %ds on send_message", e.seconds)
            self._record_health(False)
            await asyncio.sleep(e.seconds)
            return False
        except Exception as e:
            logger.error("send_message error: %s", e)
            self._error_count += 1
            self._record_health(False)
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
            self._error_count += 1
            # Telegram 从 2021 起只允许**管理员**拉成员列表，
            # 普通账号调用 GetParticipantsRequest 会报
            # "Chat admin privileges are required"。这是平台限制，绕不过去，
            # 所以退回「扫描最近消息、收集发言者」——发言者里有 @username 的可以直接私聊。
            logger.warning("get_group_members 受限(%s)，改为扫描群消息收集发言者: %s", group_id, e)
            members = await self._members_from_recent_messages(group_id, limit=limit)
        return members

    async def _members_from_recent_messages(
        self, group_id: str, limit: int = 50
    ) -> list[UserProfile]:
        """兜底方案：从群最近的消息里收集发言者（不需要管理员权限）。"""
        assert self._client is not None
        found: dict[str, UserProfile] = {}
        try:
            entity = await self._client.get_entity(int(group_id))
            # 广播频道本身没人聊天，"人"都在它的关联讨论群里
            linked_chat_id = getattr(entity, "linked_chat_id", None)
            if linked_chat_id:
                try:
                    entity = await self._client.get_entity(linked_chat_id)
                    logger.info("%s 是频道，改从其关联讨论群取目标", group_id)
                except Exception as e:
                    logger.warning("取 %s 的关联讨论群失败: %s", group_id, e)
            async for msg in self._client.iter_messages(entity, limit=limit):
                sender = getattr(msg, "sender", None)
                if sender is None or getattr(sender, "bot", False):
                    continue
                # 只收真实用户：频道/群会以 Channel 形式出现在 sender 里，
                # @频道名 是没法私聊的
                if not isinstance(sender, User):
                    continue
                user_id = str(getattr(sender, "id", "") or "")
                if not user_id or user_id in found:
                    continue
                display_name = " ".join(
                    part
                    for part in (
                        getattr(sender, "first_name", "") or "",
                        getattr(sender, "last_name", "") or "",
                    )
                    if part
                ).strip() or getattr(sender, "title", "") or user_id
                found[user_id] = UserProfile(
                    user_id=user_id,
                    display_name=display_name,
                    username=getattr(sender, "username", None),
                )
            logger.info(
                "扫描 %s 最近 %d 条消息，找到 %d 个发言者（其中 %d 个有用户名可私聊）",
                group_id,
                limit,
                len(found),
                sum(1 for m in found.values() if m.username),
            )
        except Exception as e:
            logger.error("扫描群消息兜底失败: %s", e, exc_info=True)
        return list(found.values())

    def get_health_status(self) -> AccountHealthStatus:
        # 统一用健康监控的判定（它的结论也已同步到账号元数据，前端徽章一致）
        snapshot = health_monitor.snapshot(self._session_name)
        total = snapshot["total"] or 0
        error_rate = (snapshot["errors"] / total) if total else 0.0
        return AccountHealthStatus(
            status=snapshot["status"],
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
