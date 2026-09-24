"""
Zalo Platform Adapter using zlapi (unofficial Python SDK).
Supports: authenticate with cookie refresh, search groups, add friends, send/listen messages.
Note: Zalo has strict limitations on unofficial API usage.
"""

import asyncio
import logging
import random
from typing import Optional

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


class ZaloAdapter(PlatformAdapter):
    """Zalo adapter using zlapi library for personal account operations."""

    def __init__(self, session_name: str = "osint_zalo"):
        self._session_name = session_name
        self._client = None
        self._imei = None
        self._cookie_file = f"sessions/{session_name}_zalo.json"
        self._daily_actions = 0
        self._error_count = 0
        self._total_actions = 0
        self._is_authenticated = False
        self._cookie_expiry = None

    async def authenticate(self, credentials: AccountCredentials) -> bool:
        """Authenticate with Zalo using cookie or phone/password."""
        try:
            # Try to load zlapi
            try:
                from zlapi import ZaloAPI
            except ImportError:
                logger.error("zlapi not installed. Install with: pip install zlapi")
                return False

            phone = credentials.credentials.get('phone')
            password = credentials.credentials.get('password')
            imei = credentials.credentials.get('imei')

            if not phone:
                logger.error("Zalo phone number required")
                return False

            # Generate or load IMEI (Zalo requires device ID)
            self._imei = imei or self._generate_imei()

            # Try to load saved session
            try:
                import json
                import os
                if os.path.exists(self._cookie_file):
                    with open(self._cookie_file, 'r', encoding='utf-8') as f:
                        session_data = json.load(f)

                    self._client = ZaloAPI(
                        phone=phone,
                        imei=self._imei,
                        cookie=session_data.get('cookie'),
                    )
                    logger.info("Loaded saved Zalo session")
                    self._is_authenticated = True
                    return True
            except Exception as e:
                logger.warning("Failed to load saved Zalo session: %s", e)

            # Perform fresh login
            if not password:
                logger.error("Password required for fresh Zalo login")
                return False

            self._client = ZaloAPI(phone=phone, imei=self._imei)

            # Login (this may require manual verification)
            login_result = await asyncio.to_thread(
                self._client.login,
                password=password
            )

            if login_result:
                # Save session data
                import json
                import os
                os.makedirs('sessions', exist_ok=True)

                session_data = {
                    'cookie': self._client.get_cookie(),
                    'imei': self._imei,
                    'phone': phone,
                }

                with open(self._cookie_file, 'w', encoding='utf-8') as f:
                    json.dump(session_data, f)

                self._is_authenticated = True
                logger.info("Zalo authenticated as %s", phone)
                return True
            else:
                logger.error("Zalo login failed - may require manual verification")
                return False

        except Exception as e:
            logger.error("Zalo authentication failed: %s", e)
            return False

    async def disconnect(self) -> None:
        """Close connection and cleanup."""
        try:
            if self._client:
                # Logout if needed
                pass
            logger.info("Zalo disconnected")
        except Exception as e:
            logger.error("Error during disconnect: %s", e)

    async def search_groups(self, query: str, limit: int = 10) -> list[GroupInfo]:
        """Search for Zalo groups (limited support in unofficial API)."""
        logger.warning("Zalo group search not fully supported by unofficial API")

        # Zalo doesn't have public group search like Facebook/Telegram
        # Can only list joined groups
        results: list[GroupInfo] = []

        try:
            if not self._client:
                return results

            # Get joined groups
            groups = await asyncio.to_thread(self._client.get_groups)

            for i, group in enumerate(groups[:limit]):
                results.append(GroupInfo(
                    group_id=str(group.get('id', '')),
                    name=group.get('name', f'Group {i+1}'),
                    member_count=group.get('member_count', 0),
                    description=group.get('description', ''),
                    platform=PlatformName.ZALO,
                ))

            logger.info("Found %d Zalo groups", len(results))

        except Exception as e:
            logger.error("search_groups error: %s", e)
            self._error_count += 1

        return results

    async def join_group(self, group_id: str) -> bool:
        """Join a Zalo group (requires invite link in most cases)."""
        logger.warning("Zalo group join requires invite link, not directly supported")

        try:
            if not self._client:
                return False

            # Zalo groups typically require admin approval
            result = await asyncio.to_thread(
                self._client.join_group,
                group_id
            )

            if result:
                self._daily_actions += 1
                self._total_actions += 1
                await asyncio.sleep(random.uniform(30, 120))
                return True

            return False

        except Exception as e:
            logger.error("join_group error: %s", e)
            self._error_count += 1
            return False

    async def send_friend_request(self, user_id: str) -> bool:
        """Send friend request on Zalo."""
        try:
            if not self._client:
                return False

            result = await asyncio.to_thread(
                self._client.add_friend,
                user_id
            )

            if result:
                self._daily_actions += 1
                self._total_actions += 1
                await asyncio.sleep(random.uniform(30, 120))
                logger.info("Sent friend request to: %s", user_id)
                return True

            return False

        except Exception as e:
            logger.error("send_friend_request error: %s", e)
            self._error_count += 1
            return False

    async def send_message(self, target_id: str, content: MessageContent) -> bool:
        """Send a message to a user or group on Zalo."""
        try:
            if not self._client:
                return False

            # Simulate typing delay
            chars = len(content.text)
            typing_delay = chars * 0.05 * random.uniform(0.7, 1.3)
            await asyncio.sleep(min(typing_delay, 10))

            # Send message
            result = await asyncio.to_thread(
                self._client.send_message,
                target_id,
                content.text
            )

            if result:
                self._daily_actions += 1
                self._total_actions += 1

                # Post-send cooldown
                await asyncio.sleep(random.uniform(5, 45))
                logger.info("Message sent to: %s", target_id)
                return True

            return False

        except Exception as e:
            logger.error("send_message error: %s", e)
            self._error_count += 1
            return False

    async def listen_messages(self, callback) -> None:
        """Listen for incoming messages on Zalo."""
        try:
            if not self._client:
                return

            # Use polling to check for new messages
            while True:
                try:
                    # Get recent conversations
                    conversations = await asyncio.to_thread(
                        self._client.get_recent_conversations
                    )

                    for conv in conversations:
                        # Check for new messages
                        messages = await asyncio.to_thread(
                            self._client.get_messages,
                            conv.get('id'),
                            limit=1
                        )

                        if messages:
                            latest_msg = messages[0]
                            await callback({
                                "sender_id": str(latest_msg.get('from_id', '')),
                                "sender_name": latest_msg.get('from_name', ''),
                                "text": latest_msg.get('text', ''),
                                "chat_id": str(conv.get('id', '')),
                                "timestamp": latest_msg.get('timestamp', ''),
                            })

                except Exception as e:
                    logger.warning("Error in message listener: %s", e)

                await asyncio.sleep(10)  # Poll every 10 seconds

        except Exception as e:
            logger.error("listen_messages error: %s", e)

    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """Get user profile information."""
        try:
            if not self._client:
                return None

            profile = await asyncio.to_thread(
                self._client.get_user_info,
                user_id
            )

            if profile:
                return UserProfile(
                    user_id=user_id,
                    display_name=profile.get('display_name', ''),
                    username=profile.get('username'),
                    avatar_url=profile.get('avatar_url'),
                )

            return None

        except Exception as e:
            logger.error("get_user_profile error: %s", e)
            return None

    async def get_group_members(self, group_id: str, limit: int = 100) -> list[UserProfile]:
        """Get members of a Zalo group."""
        members: list[UserProfile] = []

        try:
            if not self._client:
                return members

            group_members = await asyncio.to_thread(
                self._client.get_group_members,
                group_id
            )

            for member in group_members[:limit]:
                members.append(UserProfile(
                    user_id=str(member.get('id', '')),
                    display_name=member.get('display_name', ''),
                    username=member.get('username'),
                ))

            logger.info("Retrieved %d members from Zalo group: %s", len(members), group_id)

        except Exception as e:
            logger.error("get_group_members error: %s", e)
            self._error_count += 1

        return members

    def get_health_status(self) -> AccountHealthStatus:
        """Evaluate account health."""
        error_rate = self._error_count / max(self._total_actions, 1)

        # Check cookie expiry
        is_cookie_expired = self._check_cookie_expiry()

        if is_cookie_expired or error_rate > 0.2:
            status = "red"
        elif error_rate > 0.1 or self._daily_actions > 50:
            status = "yellow"
        else:
            status = "green"

        return AccountHealthStatus(
            status=status,
            daily_actions=self._daily_actions,
            error_rate=error_rate,
            last_error="Cookie expired" if is_cookie_expired else None,
        )

    async def is_session_valid(self) -> dict:
        import os
        import time
        if not os.path.exists(self._cookie_file):
            return {"valid": False, "message": "Session 文件不存在，请先登录", "details": {}}
        try:
            mtime = os.path.getmtime(self._cookie_file)
            hours_since_login = (time.time() - mtime) / 3600
            days_left = max(0, (48 - hours_since_login) / 24)
            if hours_since_login > 48:
                return {
                    "valid": False,
                    "message": f"Cookie 已过期 ({round(hours_since_login, 1)}小时前保存，Zalo Cookie 有效期约48小时)",
                    "details": {"hours_since_login": round(hours_since_login, 1)},
                }
            msg = f"Cookie 有效 ({round(hours_since_login, 1)}小时前保存)"
            if days_left < 1:
                msg += " ⚠️ 即将过期，建议尽快重新登录"
            else:
                msg += f", 预计剩余 {round(days_left, 1)} 天"
            return {
                "valid": True,
                "message": msg,
                "details": {"hours_since_login": round(hours_since_login, 1), "days_left": round(days_left, 1)},
            }
        except Exception as e:
            return {"valid": False, "message": f"检测失败: {e}", "details": {"error": str(e)}}

    def _generate_imei(self) -> str:
        """Generate a realistic IMEI for Zalo device identification."""
        import hashlib
        import time

        # Generate pseudo-unique IMEI based on session name and timestamp
        raw = f"{self._session_name}_{time.time()}"
        hash_hex = hashlib.md5(raw.encode()).hexdigest()

        # Format as IMEI (15 digits)
        imei = ''.join(filter(str.isdigit, hash_hex))[:14]
        imei += str(sum(int(d) for d in imei) % 10)  # Luhn check digit

        return imei

    def _check_cookie_expiry(self) -> bool:
        """Check if Zalo cookie has expired (typically 24-72 hours)."""
        try:
            import os
            import time

            if not os.path.exists(self._cookie_file):
                return True

            file_mtime = os.path.getmtime(self._cookie_file)
            hours_since_login = (time.time() - file_mtime) / 3600

            # Zalo cookies typically expire after 24-72 hours
            return hours_since_login > 48

        except Exception:
            return True

    async def refresh_cookie(self, credentials: AccountCredentials) -> bool:
        """Refresh Zalo cookie before it expires."""
        logger.info("Refreshing Zalo cookie...")
        return await self.authenticate(credentials)
