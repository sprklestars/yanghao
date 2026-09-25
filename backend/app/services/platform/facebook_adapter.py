"""
Facebook Platform Adapter using Playwright for browser automation.
Supports: login, search groups, join groups, send friend requests, send/listen messages.
"""

import asyncio
import logging
import random
from datetime import datetime
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

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

    async def _human_delay(self, min_s: float = 0.5, max_s: float = 2.0):
        await asyncio.sleep(random.uniform(min_s, max_s))

    async def _human_type(self, selector: str, text: str):
        await self._page.click(selector)
        await self._human_delay(0.2, 0.6)
        for char in text:
            await self._page.type(selector, char, delay=random.randint(50, 180))
            if random.random() < 0.05:
                await self._human_delay(0.3, 0.8)

    async def _human_scroll(self, direction: str = "down", pixels: int = 300):
        delta = pixels if direction == "down" else -pixels
        steps = random.randint(3, 6)
        for _ in range(steps):
            await self._page.mouse.wheel(0, delta // steps)
            await self._human_delay(0.1, 0.4)

    async def _human_mouse_move(self):
        x = random.randint(100, 800)
        y = random.randint(100, 600)
        await self._page.mouse.move(x, y, steps=random.randint(5, 15))
        await self._human_delay(0.1, 0.3)

    async def authenticate(self, credentials: AccountCredentials) -> bool:
        """Authenticate by loading saved session or performing login."""
        try:
            from playwright_stealth import stealth_async

            self._playwright = await async_playwright().start()

            proxy_url = credentials.credentials.get("proxy", "http://127.0.0.1:7890")

            self._browser = await self._playwright.chromium.launch(
                headless=True,
                proxy={"server": proxy_url},
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
            )

            self._context = await self._browser.new_context(
                viewport={
                    "width": random.choice([1366, 1440, 1536, 1920]),
                    "height": random.choice([768, 900, 864, 1080]),
                },
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                locale="vi-VN",
                timezone_id="Asia/Ho_Chi_Minh",
                color_scheme="light",
                extra_http_headers={
                    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                    "sec-ch-ua": (
                        '"Chromium";v="125", "Not.A/Brand";v="24", "Google Chrome";v="125"'
                    ),
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                },
            )

            self._page = await self._context.new_page()
            await stealth_async(self._page)

            # Try to load saved session
            cookie_file = f"sessions/{self._session_name}_cookies.json"
            has_cookies = False
            try:
                import json
                import os

                if os.path.exists(cookie_file):
                    with open(cookie_file, "r") as f:
                        cookies = json.load(f)
                    await self._context.add_cookies(cookies)
                    has_cookies = True
                    logger.info("Loaded saved Facebook session (%d cookies)", len(cookies))
            except Exception as e:
                logger.warning("Failed to load saved session: %s", e)

            # Navigate to Facebook
            await self._page.goto(
                "https://www.facebook.com/", wait_until="domcontentloaded", timeout=60000
            )
            await asyncio.sleep(3)

            if has_cookies:
                # Trust saved cookies — verify by checking page content
                try:
                    is_logged = await self._page.is_visible(
                        '[data-testid="royal_profile_picture"], button[aria-label="Account"], '
                        '[aria-label="Trang cá nhân"], [aria-label="Messenger"]',
                        timeout=10000,
                    )
                except Exception:
                    is_logged = False

                if is_logged:
                    self._is_authenticated = True
                    logger.info("Facebook authenticated via saved cookies")
                    return True
                else:
                    logger.warning("Saved cookies may be expired, but proceeding anyway")
                    self._is_authenticated = True
                    return True

            # No cookies — need email/password login
            email = credentials.credentials.get("email")
            password = credentials.credentials.get("password")

            if not email or not password:
                logger.error("No saved cookies and no email/password provided")
                logger.error("Run: python quick_login_facebook.py first")
                return False

            # Fill login form
            await self._page.fill('input[type="email"]', email)
            await self._page.fill('input[type="password"]', password)

            # Human-like delay before clicking
            await asyncio.sleep(random.uniform(1, 3))

            # Click login button
            await self._page.click('button[type="submit"]')

            # Wait for navigation
            await self._page.wait_for_load_state("domcontentloaded", timeout=60000)

            # Save cookies for future sessions
            cookies = await self._context.cookies()
            import json
            import os

            os.makedirs("sessions", exist_ok=True)
            with open(f"sessions/{self._session_name}_cookies.json", "w") as f:
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
            await self._page.goto(search_url, wait_until="networkidle")

            # Human-like scrolling
            for _ in range(3):
                await self._page.evaluate("window.scrollBy(0, 500)")
                await asyncio.sleep(random.uniform(1, 2))

            # Extract group information
            groups = await self._page.query_selector_all('[data-pagelet="GroupsFeed::Group"]')

            for i, group in enumerate(groups[:limit]):
                try:
                    name_elem = await group.query_selector('span[dir="auto"]')
                    name = await name_elem.inner_text() if name_elem else f"Group {i + 1}"

                    members_elem = await group.query_selector('span:text-matches("\\d+.*members?")')
                    members_text = await members_elem.inner_text() if members_elem else "0 members"
                    member_count = int("".join(filter(str.isdigit, members_text)) or "0")

                    desc_elem = await group.query_selector("span:not([dir]):not([class])")
                    description = await desc_elem.inner_text() if desc_elem else ""

                    # Extract group ID from URL
                    link_elem = await group.query_selector('a[href*="/groups/"]')
                    href = await link_elem.get_attribute("href") if link_elem else ""
                    group_id = (
                        href.split("/groups/")[1].split("/")[0] if "/groups/" in href else str(i)
                    )

                    results.append(
                        GroupInfo(
                            group_id=group_id,
                            name=name.strip(),
                            member_count=member_count,
                            description=description.strip()[:200],
                            platform=PlatformName.FACEBOOK,
                        )
                    )
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
            await self._page.goto(group_url, wait_until="networkidle")

            # Find and click join button
            join_button = await self._page.query_selector(
                'button:has-text("Tham gia"), button:has-text("Join")'
            )

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
            await self._page.goto(profile_url, wait_until="networkidle")

            # Find and click add friend button
            add_friend_btn = await self._page.query_selector(
                'button:has-text("Thêm bạn bè"), button:has-text("Add Friend")'
            )

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
            await self._page.goto(messenger_url, wait_until="networkidle")

            # Wait for message input to be ready
            await asyncio.sleep(random.uniform(2, 4))

            # Type message with human-like delays
            message_input = await self._page.query_selector(
                '[contenteditable="true"], textarea[placeholder*="Aa"]'
            )

            if message_input:
                await message_input.focus()
                await message_input.fill(content.text)

                # Random delay before sending
                await asyncio.sleep(random.uniform(0.5, 2))

                # Click send button
                send_btn = await self._page.query_selector(
                    'button[aria-label*="Send"], svg[aria-label*="Send"]'
                )
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

    async def _ensure_messenger_loaded(self) -> None:
        """Navigate to Messenger and handle the landing/continuation page."""
        assert self._page is not None

        await self._page.goto(
            "https://www.messenger.com/", wait_until="domcontentloaded", timeout=60000
        )
        await asyncio.sleep(5)

        # Check if we landed on the promotional/landing page
        url = self._page.url
        logger.info("Facebook: current URL after navigation: %s", url)

        # Try clicking "Continue as..." button/link
        for attempt in range(3):
            continue_btn = await self._page.query_selector(
                'a[href*="/t/"], [role="button"]:has-text("Tiếp tục"), '
                '[role="button"]:has-text("Continue"), '
                'a:has-text("Tiếp tục"), a:has-text("Continue")'
            )
            if continue_btn:
                logger.info("Facebook: clicking continue button (attempt %d)", attempt + 1)
                try:
                    await continue_btn.click()
                    await asyncio.sleep(8)
                    url = self._page.url
                    logger.info("Facebook: URL after click: %s", url)
                    # Check if we're now in the app
                    if "/t/" in url or "/e2ee/" in url:
                        break
                except Exception as e:
                    logger.warning("Click failed: %s", e)
            else:
                # Already in the app or no button found
                break

        # Final check - if still on landing page, try direct inbox URL
        url = self._page.url
        if "messenger.com/t" not in url and "messenger.com/e2ee" not in url:
            logger.info("Facebook: still on landing page, trying direct inbox navigation")
            await self._page.goto(
                "https://www.messenger.com/inbox/", wait_until="domcontentloaded", timeout=60000
            )
            await asyncio.sleep(5)

        logger.info("Facebook: final Messenger URL: %s", self._page.url)

    async def listen_messages(self, callback) -> None:
        """Listen for incoming messages in Messenger by monitoring unread conversations."""
        assert self._page is not None

        seen_messages: set[str] = set()
        poll_count = 0

        try:
            await self._ensure_messenger_loaded()
            logger.info("Facebook listener: Messenger loaded successfully")

            while True:
                try:
                    poll_count += 1
                    current_url = self._page.url

                    # Every 3 polls or if we're not on inbox, navigate back to refresh
                    if poll_count % 3 == 0 or "/e2ee/" in current_url:
                        logger.debug(
                            "Facebook: refreshing inbox (poll #%d, url=%s)",
                            poll_count,
                            current_url[:60],
                        )
                        try:
                            await self._page.goto(
                                "https://www.messenger.com/",
                                wait_until="domcontentloaded",
                                timeout=30000,
                            )
                            await asyncio.sleep(3)
                            # Re-click continue if needed
                            btn = await self._page.query_selector(
                                'a[href*="/t/"], a:has-text("Tiếp tục"), a:has-text("Continue")'
                            )
                            if btn:
                                await btn.click()
                                await asyncio.sleep(5)
                        except Exception as e:
                            logger.warning("Facebook: refresh navigation failed: %s", e)

                    # Look for unread conversations using multiple strategies
                    unread_convs = []

                    # Strategy 1: aria-label Unread
                    for sel in ['[aria-label="Unread"]', '[aria-label*="unread" i]']:
                        try:
                            items = await self._page.query_selector_all(sel)
                            if items:
                                unread_convs.extend(items)
                                logger.info(
                                    "Facebook: found %d unread via selector '%s'", len(items), sel
                                )
                                break
                        except Exception:
                            continue

                    # Strategy 2: Look for conversation links in sidebar with unread badge/dot
                    if not unread_convs:
                        try:
                            links = await self._page.query_selector_all(
                                'a[href*="/t/"], a[href*="/e2ee/"]'
                            )
                            for link in links[:20]:
                                parent = await link.evaluate_handle(
                                    'el => el.closest("[role]") || el.parentElement'
                                )
                                parent_html = await parent.evaluate("el => el.innerHTML")
                                # Check for unread indicators in the conversation item
                                has_unread = any(
                                    kw in parent_html.lower()
                                    for kw in [
                                        "unread",
                                        'aria-label="unread"',
                                        "background-color: rgb(0, 132, 255)",  # blue dot
                                        "background-color:rgb(0,132,255)",
                                    ]
                                )
                                # Also check for bold text (unread conversations are bold)
                                has_bold = "<b>" in parent_html or "font-weight" in parent_html
                                if has_unread or has_bold:
                                    unread_convs.append(link)
                            if unread_convs:
                                logger.info(
                                    "Facebook: found %d unread via link scanning", len(unread_convs)
                                )
                        except Exception as e:
                            logger.debug("Facebook: link scanning error: %s", e)

                    # Strategy 3: Check if currently viewing a conversation with new messages
                    if not unread_convs and ("/t/" in current_url or "/e2ee/" in current_url):
                        try:
                            msg_elements = await self._page.query_selector_all('div[dir="auto"]')
                            if msg_elements:
                                texts = []
                                for m in msg_elements[-3:]:
                                    t = (await m.inner_text()).strip()
                                    if t and len(t) > 1:
                                        texts.append(t)
                                if texts:
                                    latest = texts[-1]
                                    sender_el = await self._page.query_selector(
                                        '[role="heading"] span, h2 span'
                                    )
                                    sender = (
                                        (await sender_el.inner_text()).strip()
                                        if sender_el
                                        else "Unknown"
                                    )
                                    msg_key = f"{sender}:{latest}"
                                    if msg_key not in seen_messages:
                                        seen_messages.add(msg_key)
                                        if len(seen_messages) > 500:
                                            seen_messages.clear()
                                        logger.info(
                                            "Facebook: message in current chat from %s: %s",
                                            sender,
                                            latest[:50],
                                        )
                                        await callback(
                                            {
                                                "sender_id": sender,
                                                "sender_name": sender,
                                                "text": latest,
                                                "timestamp": datetime.now().isoformat(),
                                            }
                                        )
                        except Exception as e:
                            logger.debug("Facebook: current chat check error: %s", e)

                    # Process found unread conversations
                    for conv_item in unread_convs[:3]:
                        try:
                            await conv_item.click()
                            await self._human_delay(2.0, 4.5)

                            sender = "Unknown"
                            for header_sel in [
                                '[role="heading"] span',
                                "h2 span",
                                'span[dir="auto"]',
                            ]:
                                try:
                                    header = await self._page.query_selector(header_sel)
                                    if header:
                                        text = (await header.inner_text()).strip()
                                        if text and len(text) < 100:
                                            sender = text
                                            break
                                except Exception:
                                    continue

                            msg_texts = []
                            for msg_sel in ['div[dir="auto"]', 'span[dir="auto"]']:
                                try:
                                    msgs = await self._page.query_selector_all(msg_sel)
                                    for m in msgs[-5:]:
                                        t = (await m.inner_text()).strip()
                                        if t and len(t) > 1:
                                            msg_texts.append(t)
                                except Exception:
                                    continue

                            if msg_texts:
                                latest = msg_texts[-1]
                                msg_key = f"{sender}:{latest}"
                                if msg_key not in seen_messages:
                                    seen_messages.add(msg_key)
                                    if len(seen_messages) > 500:
                                        seen_messages.clear()
                                    logger.info(
                                        "Facebook new message from %s: %s", sender, latest[:50]
                                    )
                                    await callback(
                                        {
                                            "sender_id": sender,
                                            "sender_name": sender,
                                            "text": latest,
                                            "timestamp": datetime.now().isoformat(),
                                        }
                                    )

                        except Exception as e:
                            logger.warning("Error processing unread conversation: %s", e)

                    if poll_count % 6 == 0:
                        logger.info(
                            "Facebook: poll #%d complete, seen=%d msgs, url=%s",
                            poll_count,
                            len(seen_messages),
                            self._page.url[:60],
                        )

                except Exception as e:
                    logger.warning("Error in Facebook message listener: %s", e)

                await self._human_delay(8, 15)
                if random.random() < 0.3:
                    try:
                        await self._human_mouse_move()
                    except Exception:
                        pass

        except Exception as e:
            logger.error("listen_messages error: %s", e)

    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """Get user profile information."""
        assert self._page is not None

        try:
            profile_url = f"https://www.facebook.com/{user_id}"
            await self._page.goto(profile_url, wait_until="networkidle")

            # Extract profile information
            name_elem = await self._page.query_selector('h1, span[dir="auto"]')
            name = await name_elem.inner_text() if name_elem else ""

            bio_elem = await self._page.query_selector('[data-testid="intro_bio"]')
            bio = await bio_elem.inner_text() if bio_elem else None

            avatar_elem = await self._page.query_selector('img[alt*="Avatar"]')
            avatar_url = await avatar_elem.get_attribute("src") if avatar_elem else None

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
            await self._page.goto(members_url, wait_until="networkidle")

            # Scroll to load members
            for _ in range(5):
                await self._page.evaluate("window.scrollBy(0, 800)")
                await asyncio.sleep(random.uniform(1, 2))

            # Extract member information
            member_elements = await self._page.query_selector_all(
                '[data-pagelet="MembersList::Member"]'
            )

            for member_elem in member_elements[:limit]:
                try:
                    link = await member_elem.query_selector("a")
                    href = await link.get_attribute("href") if link else ""
                    user_id = (
                        href.split("/profile.php?id=")[1].split("&")[0]
                        if "profile.php?id=" in href
                        else ""
                    )

                    name_elem = await member_elem.query_selector('span[dir="auto"]')
                    name = await name_elem.inner_text() if name_elem else "Unknown"

                    if user_id:
                        members.append(
                            UserProfile(
                                user_id=user_id,
                                display_name=name.strip(),
                            )
                        )
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

    async def is_session_valid(self) -> dict:
        import json
        import os
        import time

        cookie_file = f"sessions/{self._session_name}_cookies.json"
        if not os.path.exists(cookie_file):
            return {"valid": False, "message": "Cookie 文件不存在，请先登录", "details": {}}
        try:
            with open(cookie_file, "r") as f:
                cookies = json.load(f)
            now = time.time()
            total = len(cookies)
            expired_count = 0
            key_cookies = {}
            for c in cookies:
                exp = c.get("expires", -1)
                name = c.get("name", "")
                if exp > 0 and exp < now:
                    expired_count += 1
                if name in ("c_user", "xs", "fr", "datr"):
                    key_cookies[name] = {
                        "expires": exp,
                        "expired": exp > 0 and exp < now,
                        "days_left": round((exp - now) / 86400, 1) if exp > 0 else None,
                    }
            mtime = os.path.getmtime(cookie_file)
            hours_since_save = (now - mtime) / 3600
            c_user = key_cookies.get("c_user", {})
            xs = key_cookies.get("xs", {})
            if c_user.get("expired") or xs.get("expired"):
                return {
                    "valid": False,
                    "message": "核心 Cookie 已过期，请重新登录",
                    "details": {
                        "key_cookies": key_cookies,
                        "total": total,
                        "expired_count": expired_count,
                        "hours_since_save": round(hours_since_save, 1),
                    },
                }
            days_left = c_user.get("days_left")
            msg = f"Cookie 有效 (共{total}个, {expired_count}个已过期)"
            if days_left is not None:
                msg += f", 预计剩余 {days_left} 天"
            if hours_since_save > 168:
                msg += " ⚠️ 已超过7天未刷新，建议重新登录"
            return {
                "valid": True,
                "message": msg,
                "details": {
                    "key_cookies": key_cookies,
                    "total": total,
                    "expired_count": expired_count,
                    "hours_since_save": round(hours_since_save, 1),
                },
            }
        except Exception as e:
            return {"valid": False, "message": f"检测失败: {e}", "details": {"error": str(e)}}
