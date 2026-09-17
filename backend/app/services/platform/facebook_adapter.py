"""
Facebook Platform Adapter using Playwright for browser automation.
Supports: login, search groups, join groups, send friend requests, send/listen messages.
"""

import asyncio
import logging
import random
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

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


class FacebookAdapter(PlatformAdapter):
    """Facebook adapter using Playwright for realistic browser automation."""

    def __init__(self, session_name: str = "osint_fb"):
        self._session_name = session_name
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._daily_actions = 0
        self._error_count = 0
        self._total_actions = 0
        self._is_authenticated = False

    async def authenticate(self, credentials: AccountCredentials) -> bool:
        """Authenticate by loading saved session or performing login."""
        try:
            self._playwright = await async_playwright().start()

            # Launch browser with realistic settings
            self._browser = await self._playwright.chromium.launch(
                headless=False,  # Visible for anti-detection
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                ],
            )

            # Create context with realistic user agent and viewport
            self._context = await self._browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='vi-VN',
                timezone_id='Asia/Ho_Chi_Minh',
            )

            # Enable stealth mode
            await self._context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """)

            self._page = await self._context.new_page()

            # Try to load saved session
            cookie_file = f"sessions/{self._session_name}_cookies.json"
            try:
                import json
                import os
                if os.path.exists(cookie_file):
                    with open(cookie_file, 'r') as f:
                        cookies = json.load(f)
                    await self._context.add_cookies(cookies)
                    logger.info("Loaded saved Facebook session")
            except Exception as e:
                logger.warning("Failed to load saved session: %s", e)

            # Navigate to Facebook
            await self._page.goto('https://www.facebook.com/', wait_until='networkidle')

            # Check if already logged in
            is_logged = await self._page.is_visible('button[aria-label="Account"]', timeout=5000)

            if not is_logged:
                # Perform login
                email = credentials.credentials.get('email')
                password = credentials.credentials.get('password')

                if not email or not password:
                    logger.error("Facebook credentials missing email or password")
                    return False

                # Fill login form
                await self._page.fill('input[type="email"]', email)
                await self._page.fill('input[type="password"]', password)

                # Human-like delay before clicking
                await asyncio.sleep(random.uniform(1, 3))

                # Click login button
                await self._page.click('button[type="submit"]')

                # Wait for navigation
                await self._page.wait_for_load_state('networkidle', timeout=30000)

                # Save cookies for future sessions
                cookies = await self._context.cookies()
                import json
                import os
                os.makedirs('sessions', exist_ok=True)
                with open(f"sessions/{self._session_name}_cookies.json", 'w') as f:
                    json.dump(cookies, f)

            self._is_authenticated = True
            logger.info("Facebook authenticated as %s", credentials.username)
            return True

        except Exception as e:
            logger.error("Facebook authentication failed: %s", e)
            return False

    async def disconnect(self) -> None:
        """Close browser and cleanup."""
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            logger.info("Facebook disconnected")
        except Exception as e:
            logger.error("Error during disconnect: %s", e)

    async def search_groups(self, query: str, limit: int = 10) -> list[GroupInfo]:
        """Search for Facebook groups by keyword."""
        assert self._page is not None
        results: list[GroupInfo] = []

        try:
            # Navigate to groups search
            search_url = f"https://www.facebook.com/search/groups/?q={query}"
            await self._page.goto(search_url, wait_until='networkidle')

            # Human-like scrolling
            for _ in range(3):
                await self._page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(random.uniform(1, 2))

            # Extract group information
            groups = await self._page.query_selector_all('[data-pagelet="GroupsFeed::Group"]')

            for i, group in enumerate(groups[:limit]):
                try:
                    name_elem = await group.query_selector('span[dir="auto"]')
                    name = await name_elem.inner_text() if name_elem else f"Group {i+1}"

                    members_elem = await group.query_selector('span:text-matches("\\d+.*members?")')
                    members_text = await members_elem.inner_text() if members_elem else "0 members"
                    member_count = int(''.join(filter(str.isdigit, members_text)) or "0")

                    desc_elem = await group.query_selector('span:not([dir]):not([class])')
                    description = await desc_elem.inner_text() if desc_elem else ""

                    # Extract group ID from URL
                    link_elem = await group.query_selector('a[href*="/groups/"]')
                    href = await link_elem.get_attribute('href') if link_elem else ""
                    group_id = href.split('/groups/')[1].split('/')[0] if '/groups/' in href else str(i)

                    results.append(GroupInfo(
                        group_id=group_id,
                        name=name.strip(),
                        member_count=member_count,
                        description=description.strip()[:200],
                        platform=PlatformName.FACEBOOK,
                    ))
                except Exception as e:
                    logger.warning("Failed to extract group %d: %s", i, e)
                    continue

            logger.info("Found %d Facebook groups for query: %s", len(results), query)

        except Exception as e:
            logger.error("search_groups error: %s", e)
            self._error_count += 1

        return results

    async def join_group(self, group_id: str) -> bool:
        """Join a Facebook group."""
        assert self._page is not None

        try:
            group_url = f"https://www.facebook.com/groups/{group_id}"
            await self._page.goto(group_url, wait_until='networkidle')

            # Find and click join button
            join_button = await self._page.query_selector('button:has-text("Tham gia"), button:has-text("Join")')

            if join_button:
                await join_button.click()
                self._daily_actions += 1
                self._total_actions += 1

                # Human-like delay after action
                await asyncio.sleep(random.uniform(30, 120))
                logger.info("Successfully joined Facebook group: %s", group_id)
                return True
            else:
                logger.warning("Join button not found for group: %s", group_id)
                return False

        except Exception as e:
            logger.error("join_group error: %s", e)
            self._error_count += 1
            return False

    async def send_friend_request(self, user_id: str) -> bool:
        """Send friend request to a user."""
        assert self._page is not None

        try:
            profile_url = f"https://www.facebook.com/{user_id}"
            await self._page.goto(profile_url, wait_until='networkidle')

            # Find and click add friend button
            add_friend_btn = await self._page.query_selector('button:has-text("Thêm bạn bè"), button:has-text("Add Friend")')

            if add_friend_btn:
                await add_friend_btn.click()
                self._daily_actions += 1
                self._total_actions += 1

                # Human-like delay
                await asyncio.sleep(random.uniform(30, 120))
                logger.info("Sent friend request to: %s", user_id)
                return True
            else:
                logger.warning("Add friend button not found for user: %s", user_id)
                return False

        except Exception as e:
            logger.error("send_friend_request error: %s", e)
            self._error_count += 1
            return False

    async def send_message(self, target_id: str, content: MessageContent) -> bool:
        """Send a message to a user via Messenger."""
        assert self._page is not None

        try:
            # Simulate typing delay based on message length
            chars = len(content.text)
            typing_delay = chars * 0.05 * random.uniform(0.7, 1.3)
            await asyncio.sleep(min(typing_delay, 10))

            # Navigate to Messenger
            messenger_url = f"https://www.messenger.com/t/{target_id}"
            await self._page.goto(messenger_url, wait_until='networkidle')

            # Wait for message input to be ready
            await asyncio.sleep(random.uniform(2, 4))

            # Type message with human-like delays
            message_input = await self._page.query_selector('[contenteditable="true"], textarea[placeholder*="Aa"]')

            if message_input:
                await message_input.focus()
                await message_input.fill(content.text)

                # Random delay before sending
                await asyncio.sleep(random.uniform(0.5, 2))

                # Click send button
                send_btn = await self._page.query_selector('button[aria-label*="Send"], svg[aria-label*="Send"]')
                if send_btn:
                    await send_btn.click()

                    self._daily_actions += 1
                    self._total_actions += 1

                    # Post-send cooldown
                    await asyncio.sleep(random.uniform(5, 45))
                    logger.info("Message sent to: %s", target_id)
                    return True

            logger.warning("Failed to send message to: %s", target_id)
            return False

        except Exception as e:
            logger.error("send_message error: %s", e)
            self._error_count += 1
            return False

    async def listen_messages(self, callback) -> None:
        """Listen for incoming messages in Messenger."""
        assert self._page is not None

        try:
            # Navigate to Messenger
            await self._page.goto('https://www.messenger.com/', wait_until='networkidle')

            # Monitor for new messages
            while True:
                try:
                    # Check for new message notifications
                    new_msg = await self._page.query_selector('[aria-label*="Tin nhắn mới"], [aria-label*="New message"]')

                    if new_msg:
                        # Extract sender and message
                        sender_elem = await self._page.query_selector('[aria-label*="From"] span')
                        message_elem = await self._page.query_selector('div[role="log"] div:last-child')

                        sender = await sender_elem.inner_text() if sender_elem else "Unknown"
                        text = await message_elem.inner_text() if message_elem else ""

                        await callback({
                            "sender_name": sender,
                            "text": text,
                            "timestamp": datetime.now().isoformat(),
                        })

                except Exception as e:
                    logger.warning("Error in message listener: %s", e)

                await asyncio.sleep(5)  # Poll every 5 seconds

        except Exception as e:
            logger.error("listen_messages error: %s", e)

    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """Get user profile information."""
        assert self._page is not None

        try:
            profile_url = f"https://www.facebook.com/{user_id}"
            await self._page.goto(profile_url, wait_until='networkidle')

            # Extract profile information
            name_elem = await self._page.query_selector('h1, span[dir="auto"]')
            name = await name_elem.inner_text() if name_elem else ""

            bio_elem = await self._page.query_selector('[data-testid="intro_bio"]')
            bio = await bio_elem.inner_text() if bio_elem else None

            avatar_elem = await self._page.query_selector('img[alt*="Avatar"]')
            avatar_url = await avatar_elem.get_attribute('src') if avatar_elem else None

            return UserProfile(
                user_id=user_id,
                display_name=name.strip(),
                bio=bio,
                avatar_url=avatar_url,
            )

        except Exception as e:
            logger.error("get_user_profile error: %s", e)
            return None

    async def get_group_members(self, group_id: str, limit: int = 100) -> list[UserProfile]:
        """Get members of a Facebook group."""
        assert self._page is not None
        members: list[UserProfile] = []

        try:
            members_url = f"https://www.facebook.com/groups/{group_id}/members"
            await self._page.goto(members_url, wait_until='networkidle')

            # Scroll to load members
            for _ in range(5):
                await self._page.evaluate('window.scrollBy(0, 800)')
                await asyncio.sleep(random.uniform(1, 2))

            # Extract member information
            member_elements = await self._page.query_selector_all('[data-pagelet="MembersList::Member"]')

            for member_elem in member_elements[:limit]:
                try:
                    link = await member_elem.query_selector('a')
                    href = await link.get_attribute('href') if link else ""
                    user_id = href.split('/profile.php?id=')[1].split('&')[0] if 'profile.php?id=' in href else ""

                    name_elem = await member_elem.query_selector('span[dir="auto"]')
                    name = await name_elem.inner_text() if name_elem else "Unknown"

                    if user_id:
                        members.append(UserProfile(
                            user_id=user_id,
                            display_name=name.strip(),
                        ))
                except Exception as e:
                    logger.warning("Failed to extract member: %s", e)
                    continue

            logger.info("Retrieved %d members from Facebook group: %s", len(members), group_id)

        except Exception as e:
            logger.error("get_group_members error: %s", e)
            self._error_count += 1

        return members

    def get_health_status(self) -> AccountHealthStatus:
        """Evaluate account health based on recent activity."""
        error_rate = self._error_count / max(self._total_actions, 1)

        if error_rate > 0.2:
            status = "red"
        elif error_rate > 0.1 or self._daily_actions > 30:
            status = "yellow"
        else:
            status = "green"

        return AccountHealthStatus(
            status=status,
            daily_actions=self._daily_actions,
            error_rate=error_rate,
        )
