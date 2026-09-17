import asyncio
import logging
import random

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.contacts import AddContactRequest
from telethon.tl.functions.messages import SearchRequest
from telethon.tl.types import (
    InputPeerChannel,
    InputUser,
)

from app.services.platform.base import (
    AccountCredentials,
    AccountHealthStatus,
    GroupInfo,
    MessageContent,
    PlatformAdapter,
    PlatformName,
    UserProfile,
)

logger = logging.getLogger(__name__)


class TelegramAdapter(PlatformAdapter):
    def __init__(self, api_id: int, api_hash: str, session_name: str = "osint_tg"):
        self._api_id = api_id
        self._api_hash = api_hash
        self._session_name = session_name
        self._client: TelegramClient | None = None
        self._daily_actions = 0
        self._error_count = 0
        self._total_actions = 0

    async def authenticate(self, credentials: AccountCredentials) -> bool:
        self._client = TelegramClient(
            self._session_name,
            self._api_id,
            self._api_hash,
            device_model="Samsung Galaxy S24",
            system_version="Android 14",
            app_version="10.12.0",
        )
        phone = credentials.credentials.get("phone")
        password = credentials.credentials.get("password")
        try:
            await self._client.start(phone=phone, password=password)
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
            response = await self._client(SearchRequest(
                q=query,
                filter=None,
                min_date=None,
                max_date=None,
                offset_id=0,
                add_offset=0,
                limit=limit,
                max_id=0,
                min_id=0,
                hash=0,
            ))
            for chat in (response.chats or []):
                results.append(GroupInfo(
                    group_id=str(chat.id),
                    name=getattr(chat, "title", ""),
                    member_count=getattr(chat, "participants_count", 0),
                    description=getattr(chat, "about", ""),
                    platform=PlatformName.TELEGRAM,
                ))
        except FloodWaitError as e:
            logger.warning("FloodWait %ds on search_groups", e.seconds)
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error("search_groups error: %s", e)
            self._error_count += 1
        return results

    async def join_group(self, group_id: str) -> bool:
        assert self._client is not None
        try:
            entity = await self._client.get_entity(int(group_id))
            await self._client(JoinChannelRequest(entity))
            self._daily_actions += 1
            self._total_actions += 1
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
        try:
            entity = await self._client.get_entity(int(user_id))
            await self._client(AddContactRequest(
                id=entity.id,
                first_name=getattr(entity, "first_name", ""),
                last_name=getattr(entity, "last_name", "") or "",
                phone=getattr(entity, "phone", "") or "",
            ))
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
        try:
            # simulate typing delay based on message length
            chars = len(content.text)
            typing_delay = chars * 0.05 * random.uniform(0.7, 1.3)
            await asyncio.sleep(min(typing_delay, 10))

            await self._client.send_message(int(target_id), content.text)
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

    async def listen_messages(self, callback) -> None:
        assert self._client is not None

        @self._client.on(events.NewMessage(incoming=True))
        async def handler(event):
            try:
                sender = await event.get_sender()
                await callback({
                    "sender_id": str(sender.id) if sender else None,
                    "sender_name": getattr(sender, "first_name", "") if sender else None,
                    "text": event.raw_text,
                    "chat_id": str(event.chat_id),
                    "message_id": event.id,
                    "timestamp": event.date.isoformat(),
                })
            except Exception as e:
                logger.error("listen_messages callback error: %s", e)

        await self._client.run_until_disconnected()

    async def get_user_profile(self, user_id: str) -> UserProfile | None:
        assert self._client is not None
        try:
            entity = await self._client.get_entity(int(user_id))
            return UserProfile(
                user_id=str(entity.id),
                display_name=f"{getattr(entity, 'first_name', '')} {getattr(entity, 'last_name', '') or ''}".strip(),
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
                members.append(UserProfile(
                    user_id=str(p.id),
                    display_name=f"{getattr(p, 'first_name', '')} {getattr(p, 'last_name', '') or ''}".strip(),
                    username=getattr(p, "username", None),
                    bio=getattr(p, "about", None),
                ))
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
