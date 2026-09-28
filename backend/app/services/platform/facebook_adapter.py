"""
Facebook Platform Adapter using Playwright for browser automation.
Supports: login, search groups, join groups, send friend requests, send/listen messages.
"""

import asyncio
import logging
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from playwright.async_api import Browser, BrowserContext, Locator, Page, async_playwright

from app.core.browser_launch import launch_browser
from app.core.config import settings
from app.core.session_paths import SESSION_DIR
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


def fb_cookie_path(session_name: str) -> Path:
    """Facebook 登录态文件（绝对路径）。"""
    return SESSION_DIR / f"{session_name}_cookies.json"


# ── Facebook 页面解析的纯函数 ─────────────────────────────────────────────
# 2026-09-26 实测（真实账号 cookie，无头浏览器）：
# 这一版 Facebook 页面里 **完全没有 data-pagelet 属性** 了，
# 旧代码靠 [data-pagelet="GroupsFeed::Group"] / [data-pagelet="MembersList::Member"]
# 抓数据，所以永远抓到 0 条 —— 这就是"任务里搜不到群"的根因。
# 现在改为按 role="article" 卡片 + /groups/、/user/ 链接来解析。

_GROUP_HREF_RE = re.compile(r"/groups/([^/?#]+)")
_USER_HREF_RES = (
    re.compile(r"/user/(\d+)"),
    re.compile(r"profile\.php\?id=(\d+)"),
)
# "35 K membres" / "6,2 K membres" / "1,234 members" / "4,1 K thành viên"
_MEMBER_TEXT_RE = re.compile(
    r"(\d[\d\s.,]*)\s*([KkMm])?\s*"
    r"(?:membres?|members?|thành\s*viên|người\s*tham\s*gia)",
    re.IGNORECASE,
)

# 加群按钮在 FB 上会按账号语言本地化（实测这个账号是法语 "Rejoindre le groupe"），
# 所以不能用单一句子去匹配。
JOIN_BUTTON_LABELS: tuple[str, ...] = (
    "join group",
    "join",
    "rejoindre le groupe",
    "rejoindre",
    "tham gia nhóm",
    "tham gia",
    "加入小组",
    "加入群组",
    "加入",
    "参加",
)
# 只有「群成员才会看到」的按钮，才能用来判断"已经在群里"。
# 注意：不能拿 "Partager / Share" 当依据——实测没加入的群页面上也有分享按钮。
# 也必须用完整短语：实测群页搜索框的 aria-label 是
# "Quitter la saisie semi-automatique"（退出自动补全），只写 "quitter" 会误判成已入群。
MEMBER_ONLY_LABELS: tuple[str, ...] = (
    "quitter le groupe",
    "leave group",
    "rời nhóm",
    "退出小组",
    "invite des membres",
    "inviter des membres",
    "invite members",
    "mời mọi người",
)
PENDING_LABELS: tuple[str, ...] = (
    "demande envoyée",
    "request sent",
    "annuler la demande",
    "đã gửi yêu cầu",
    "已请求",
)
# 这些词一旦命中就说明是"退群/已加入/邀请/申请中"类按钮，绝不能当成加入按钮点下去
NEVER_CLICK_WORDS: tuple[str, ...] = (
    MEMBER_ONLY_LABELS + PENDING_LABELS + ("joined", "cancel", "annuler")
)


def parse_member_count(text: str) -> int:
    """把 "6,2 K membres" 这类文案解析成数字（0 表示解析不出来）。"""
    match = _MEMBER_TEXT_RE.search(text or "")
    if not match:
        return 0
    raw, unit = match.group(1).strip(), (match.group(2) or "").lower()
    try:
        if unit:  # "6,2 K" 里的逗号是小数点
            digits = raw.replace(" ", "")
            if "," in digits and "." not in digits:
                digits = digits.replace(",", ".")
            value = float(digits)
        else:  # "1,234 members" 里的逗号是千分位
            value = float(re.sub(r"[\s.,]", "", raw) or 0)
    except ValueError:
        return 0
    return int(value * {"k": 1_000, "m": 1_000_000}.get(unit, 1))


def parse_group_search_results(items: list[dict], limit: int = 10) -> list[GroupInfo]:
    """搜索结果卡片 → GroupInfo 列表（items 来自页面里的 {href, text}）。"""
    results: list[GroupInfo] = []
    seen: set[str] = set()
    for item in items:
        href = str(item.get("href") or "")
        match = _GROUP_HREF_RE.search(href)
        if not match:
            continue
        group_id = match.group(1)
        if not group_id or group_id in seen:
            continue
        seen.add(group_id)

        lines = [line.strip() for line in str(item.get("text") or "").split("\n") if line.strip()]
        name = lines[0] if lines else group_id
        description = " ".join(lines[1:])[:200]
        results.append(
            GroupInfo(
                group_id=group_id,
                name=name[:120],
                member_count=parse_member_count(" ".join(lines)),
                description=description,
                platform=PlatformName.FACEBOOK,
            )
        )
        if len(results) >= limit:
            break
    return results


def parse_member_cards(items: list[dict], limit: int = 100) -> list[UserProfile]:
    """成员卡片 → UserProfile 列表（items 来自页面里的 {href, text}）。"""
    members: list[UserProfile] = []
    seen: set[str] = set()
    for item in items:
        href = str(item.get("href") or "")
        user_id = ""
        for pattern in _USER_HREF_RES:
            match = pattern.search(href)
            if match:
                user_id = match.group(1)
                break
        name = str(item.get("text") or "").strip()
        if not user_id or user_id in seen or not name:
            continue
        seen.add(user_id)
        members.append(UserProfile(user_id=user_id, display_name=name[:80]))
        if len(members) >= limit:
            break
    return members


def _extract_cards_script() -> str:
    """在页面里把 role="article" 卡片抠成 {href, text}，避免依赖易变的 class。"""
    return """
        (selectors) => {
            const out = [];
            for (const card of document.querySelectorAll('div[role="article"]')) {
                for (const selector of selectors) {
                    const link = card.querySelector(selector);
                    if (link) {
                        out.push({
                            href: link.getAttribute('href') || '',
                            text: card.innerText || '',
                        });
                        break;
                    }
                }
            }
            return out;
        }
    """


def _aria_label_selector(label: str, tag: str = "div") -> str:
    """`aria-label` 里包含某个词的按钮选择器（大小写不敏感）。"""
    return f'{tag}[role="button"][aria-label*="{label}" i]'


def _visible_union(labels: tuple[str, ...]) -> str:
    """把这些文案拼成"任一可见即命中"的 CSS（`:visible` 是 Playwright 的伪类）。"""
    return ", ".join(f"{_aria_label_selector(label)}:visible" for label in labels)


def _label_matches(value: str, words: tuple[str, ...]) -> bool:
    text = (value or "").lower()
    return any(word in text for word in words)


# Facebook 的安全验证/登录墙：出现这些就说明"不是没搜到，是账号被拦了"
_BLOCK_URL_MARKERS = ("/checkpoint", "/login", "/recover", "/suspended")
_BLOCK_TEXT_MARKERS = (
    "confirmez que vous êtes une personne réelle",
    "confirm you're a real person",
    "xác nhận bạn là người thật",
    "确认真人",
    "temporarily blocked",
)


def detect_block_reason(url: str, text: str = "") -> str | None:
    """页面是不是被 Facebook 拦下了？是的话给出给人看的原因。"""
    target = (url or "").lower()
    if any(marker in target for marker in _BLOCK_URL_MARKERS):
        return (
            "Facebook 要求安全验证（checkpoint）：请到「账号管理」点「打开浏览器」"
            "完成验证后重新保存登录态，再跑任务"
        )
    body = (text or "").lower()
    if any(marker in body for marker in _BLOCK_TEXT_MARKERS):
        return "Facebook 提示需要确认真人（安全验证），请先手动完成验证再跑任务"
    return None


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
        self._header_rendered = False  # 群页头（含加入按钮）是否已触发渲染
        # 被 Facebook 安全验证拦下时的原因（给任务告警用，避免误报成"没搜到群"）
        self.block_reason: str | None = None

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
            from playwright_stealth import Stealth

            self._playwright = await async_playwright().start()

            # 代理默认取 .env 的 TG_PROXY_URL：以前这里写死 http://127.0.0.1:7890，
            # 而实际配置是 socks5，走错了协议就连不上 FB。
            proxy_url = credentials.credentials.get("proxy") or settings.tg_proxy_url

            # 走统一的浏览器探测：自带 Chromium 在这台机器上有头起不来（Windows SxS），
            # 无头一般没问题，但坏掉时能自动退到 Edge/Chrome，不至于整个任务失败。
            self._browser, _channel = await launch_browser(
                self._playwright,
                headless=True,
                proxy={"server": proxy_url} if proxy_url else None,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
                log=logger.info,
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
            await Stealth().apply_stealth_async(self._page)

            # Try to load saved session
            # 用绝对路径：以前写的是相对路径 "sessions/..."，只有在 cwd=backend 时才找得到，
            # 换个工作目录就会误判成"没有 cookie / cookie 文件不存在"。
            cookie_file = fb_cookie_path(self._session_name)
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
            with open(fb_cookie_path(self._session_name), "w") as f:
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
            search_url = f"https://www.facebook.com/search/groups/?q={quote_plus(query)}"
            await self._page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
            await self._note_block_if_any()
            # 结果卡片是异步渲染的，先等一等（拿不到也继续，后面解析为空自然返回 0）
            try:
                await self._page.wait_for_selector('div[role="article"]', timeout=15000)
            except Exception:
                logger.warning("Facebook 群搜索结果加载超时（query=%s），可能被风控或网络慢", query)

            for _ in range(3):
                await self._page.evaluate("window.scrollBy(0, 600)")
                await asyncio.sleep(random.uniform(0.8, 1.6))

            items = await self._page.evaluate(
                _extract_cards_script(), ['a[href*="/groups/"]']
            )
            results = parse_group_search_results(items, limit=limit)

            logger.info("Found %d Facebook groups for query: %s", len(results), query)
            if not results:
                logger.warning(
                    "Facebook 群搜索没有解析出结果（query=%s，卡片数=%s）；"
                    "如果账号没登录或页面被风控，先重新导入 cookie",
                    query,
                    len(items),
                )

        except Exception as e:
            logger.error("search_groups error: %s", e)
            self._error_count += 1

        return results

    async def find_join_button(self, timeout_s: float = 12.0) -> Locator | None:
        """找**可见**的「加入小组」按钮，找不到返回 None。

        实测（真实账号、无头浏览器）：
        * 按钮文案按账号语言本地化，这个账号是法语 "Rejoindre le groupe"；
        * 同一个按钮在 DOM 里有两份，其中一份是 `visibility:hidden` 的响应式副本；
        * 不滚动的话它一直是 0x0（懒渲染），滚动之后才变成 180x36，
          所以要先把页头"催"出来再等可见，否则会误判成"没有加入按钮"。
        另外必须排除「退出小组 / 已申请」这类按钮，否则会误点成退群。
        """
        assert self._page is not None
        await self._render_group_header()
        deadline = time.monotonic() + timeout_s
        # 先让 Playwright 自己在页面里等"可见的加入按钮"：一次查询、
        # 由渲染进程判断，比我们在 Python 侧反复扫 DOM 快得多也准得多。
        await self._wait_visible(JOIN_BUTTON_LABELS, max(1.0, timeout_s * 0.8))
        selectors = [
            ", ".join(
                (
                    _aria_label_selector(label),
                    _aria_label_selector(label, "a"),
                    f'div[role="button"]:has-text("{label}")',
                )
            )
            for label in JOIN_BUTTON_LABELS
        ]
        while True:
            for selector in selectors:
                candidates = self._page.locator(selector)
                try:
                    count = await candidates.count()
                except Exception:
                    continue
                for index in range(count):
                    candidate = candidates.nth(index)
                    try:
                        aria = await candidate.get_attribute("aria-label") or ""
                        text = (await candidate.inner_text() or "").strip()
                    except Exception:
                        continue
                    if _label_matches(aria, NEVER_CLICK_WORDS) or _label_matches(
                        text, NEVER_CLICK_WORDS
                    ):
                        continue  # 退群/已申请按钮，跳过
                    try:
                        if await candidate.is_visible():
                            return candidate
                    except Exception:
                        continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            await asyncio.sleep(min(0.5, remaining))

    async def _wait_visible(self, labels: tuple[str, ...], timeout_s: float) -> bool:
        """等这些文案里任意一个按钮变成可见（超时返回 False，不抛异常）。"""
        assert self._page is not None
        try:
            await self._page.wait_for_selector(
                _visible_union(labels), timeout=int(timeout_s * 1000), state="visible"
            )
            return True
        except Exception:
            return False

    async def _render_group_header(self) -> None:
        """触发群页头渲染：FB 的「加入小组」按钮在滚动前一直是 0x0（懒渲染）。

        实测（真实账号、无头）：打开群页面后按钮一直 `[0,0]`、Playwright 判定为不可见；
        `window.scrollBy(0, 800)` 之后立刻变成 180x36 且可见——不滚动就永远找不到按钮，
        这也是"有时能加群、有时说找不到按钮"的真正原因。
        """
        assert self._page is not None
        if self._header_rendered:
            return
        for _ in range(2):
            await self._page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(1)
        await self._page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(0.5)
        self._header_rendered = True

    async def _note_block_if_any(self) -> str | None:
        """检查当前页面是不是被 FB 的安全验证拦下了，并记在 self.block_reason。"""
        assert self._page is not None
        try:
            url = self._page.url
            text = await self._page.evaluate("() => (document.body ? document.body.innerText : '')")
        except Exception:
            return self.block_reason
        reason = detect_block_reason(url, str(text)[:2000])
        if reason:
            self.block_reason = reason
            logger.warning("Facebook 拦下了这次访问：%s（url=%s）", reason, url)
        return reason

    async def _has_visible_label(self, label: str) -> bool:
        assert self._page is not None
        locator = self._page.locator(_aria_label_selector(label))
        try:
            count = await locator.count()
        except Exception:
            return False
        for index in range(count):
            try:
                if await locator.nth(index).is_visible():
                    return True
            except Exception:
                continue
        return False

    async def group_join_state(self, timeout_s: float = 12.0) -> str:
        """判断当前群页面状态：joined / pending / joinable / unknown。"""
        deadline = time.monotonic() + timeout_s
        await self._render_group_header()
        # 群页头是异步渲染的：先让 Playwright 等"任意一个相关按钮可见"，
        # 等不到再按下面的循环扫（真实页面上这一步约 5 秒）。
        await self._wait_visible(
            MEMBER_ONLY_LABELS + PENDING_LABELS + JOIN_BUTTON_LABELS,
            max(1.0, timeout_s * 0.8),
        )
        while True:
            # 先看"能不能加入"：这版的群页只有成员才显示「退出小组」，
            # 而"邀请/退出"类文案容易和页面其它按钮撞车，所以以加入按钮为准。
            if await self.find_join_button(timeout_s=1.0) is not None:
                return "joinable"
            for label in MEMBER_ONLY_LABELS:
                if await self._has_visible_label(label):
                    return "joined"
            for label in PENDING_LABELS:
                if await self._has_visible_label(label):
                    return "pending"
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return "unknown"
            await asyncio.sleep(min(0.5, remaining))

    async def join_group(self, group_id: str) -> bool:
        """Join a Facebook group."""
        assert self._page is not None

        try:
            group_url = f"https://www.facebook.com/groups/{group_id}"
            await self._page.goto(group_url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(random.uniform(1, 2))
            if await self._note_block_if_any():
                return False
            await self._render_group_header()

            state = await self.group_join_state()
            if state == "joined":
                logger.info("已在群里，跳过加入: %s", group_id)
                return True
            if state == "pending":
                logger.info("加群申请还在审核中，先跳过: %s", group_id)
                return False

            join_button = await self.find_join_button(timeout_s=3.0)
            if join_button is None:
                logger.warning(
                    "找不到「加入小组」按钮（group=%s，可能是需要管理员审批的私有群，"
                    "或按钮文案是别的语言）",
                    group_id,
                )
                return False

            await join_button.click()
            self._daily_actions += 1
            self._total_actions += 1
            # 保留原来的拟人化停顿（30-120s）：加群是高风险动作，
            # 这里不要为了跑得快把防封延迟去掉。
            await asyncio.sleep(random.uniform(30, 120))
            logger.info("已提交加入申请: %s", group_id)
            return True

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
            await self._page.goto(members_url, wait_until="domcontentloaded", timeout=60000)

            # Scroll to load members
            for _ in range(5):
                await self._page.evaluate("window.scrollBy(0, 800)")
                await asyncio.sleep(random.uniform(1, 2))

            # 成员卡片：优先 role="article"，退一步直接收页面里的个人主页链接
            items = await self._page.evaluate(
                _extract_cards_script(), ['a[href*="/user/"], a[href*="profile.php?id="]']
            )
            if not items:
                items = await self._page.evaluate(
                    """() => [...document.querySelectorAll(
                            'a[href*="/user/"], a[href*="profile.php?id="]')]
                        .map(a => ({
                            href: a.getAttribute('href') || '',
                            text: (a.innerText || '').trim(),
                        }))"""
                )
            members = parse_member_cards(items, limit=limit)

            logger.info("Retrieved %d members from Facebook group: %s", len(members), group_id)
            if not members:
                # 实测：Facebook 只对**群成员**开放成员列表，没加入的群打开 /members 是空白页。
                logger.warning(
                    "群 %s 没取到成员：Facebook 只对已加入的群开放成员列表，"
                    "如果加群还在审批中，这一步会一直是 0",
                    group_id,
                )

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

        cookie_file = fb_cookie_path(self._session_name)
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
