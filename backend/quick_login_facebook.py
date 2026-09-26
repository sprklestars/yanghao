#!/usr/bin/env python3
"""
Facebook login script using Playwright.
Opens a visible browser, lets you log in manually (handles 2FA/captcha),
then saves cookies for headless automation.

Usage:
    python quick_login_facebook.py              # default session name: fb_default
    python quick_login_facebook.py fb_account1  # custom session name
"""

import asyncio
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.core.browser_launch import channel_label, launch_browser  # noqa: E402

SESSION_DIR = Path(__file__).parent / "sessions"
SESSION_DIR.mkdir(exist_ok=True)

LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-dev-shm-usage",
]


def _browser_proxy() -> dict | None:
    """浏览器代理：复用 .env 里的 TG_PROXY_URL（本机访问 FB 通常要走代理）。

    留空表示直连。Playwright 需要形如 socks5://host:port 或 http://host:port 的地址。
    """
    try:
        from app.core.config import settings
    except Exception:  # 单独跑脚本、环境不完整时退回直连
        return None
    url = (settings.tg_proxy_url or "").strip()
    return {"server": url} if url else None


async def login_facebook(session_name: str) -> bool:
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    cookie_file = SESSION_DIR / f"{session_name}_cookies.json"

    print(f"\n{'=' * 60}")
    print(f"🔐 Facebook Login — Session: {session_name}")
    print(f"{'=' * 60}")
    print("\n📝 Instructions:")
    print("1. A browser window will open")
    print("2. Log in to your Facebook account manually")
    print("3. Handle any 2FA / captcha / checkpoint yourself")
    print("4. Once logged in, come back here and press Enter")
    print("5. Cookies will be saved for headless automation\n")

    proxy = _browser_proxy()
    if proxy:
        print(f"🌐 Using proxy: {proxy['server']}")

    # 用带窗口的浏览器（headless=False）。这里不能写死 Playwright 自带的 Chromium：
    # 本机那个包的有头模式起不来（Windows 并行配置），helper 会自动退到 Edge/Chrome。
    pw = await async_playwright().start()
    try:
        browser, channel = await launch_browser(
            pw, headless=False, proxy=proxy, args=LAUNCH_ARGS, log=print
        )
        context = await browser.new_context(
            viewport={
                "width": random.choice([1366, 1440, 1536, 1920]),
                "height": random.choice([768, 900, 864, 1080]),
            },
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            color_scheme="light",
            extra_http_headers={
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                "sec-ch-ua": '"Chromium";v="125", "Not.A/Brand";v="24", "Google Chrome";v="125"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
            },
        )

        page = await context.new_page()
        await Stealth().apply_stealth_async(page)

        # Load existing cookies if available
        if cookie_file.exists():
            try:
                with open(cookie_file, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                await context.add_cookies(cookies)
                print(f"📂 Loaded existing cookies from {cookie_file.name}")
            except Exception as e:
                print(f"⚠️ Could not load cookies: {e}")

        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=60000)
        print(f"🌍 Page loaded: {page.url}")
        print(f"   Browser window: {channel_label(channel)}")

        try:
            input("\n✅ Press Enter after you have logged in successfully...")
        except EOFError:
            print("\n⏹ Stdin closed, saving cookies as-is.")

        # Verify login by checking for profile indicator
        try:
            is_logged = await page.is_visible(
                'button[aria-label="Account"], [aria-label="Trang cá nhân"], '
                '[data-testid="royal_profile_picture"]',
                timeout=5000,
            )
        except Exception:
            is_logged = False

        if not is_logged:
            print("⚠️ Login not detected. Saving cookies anyway (you can retry later).")

        # Save cookies
        cookies = await context.cookies()
        with open(cookie_file, "w") as f:
            json.dump(cookies, f, indent=2)

        print(f"\n💾 Cookies saved to: {cookie_file}")
        print(f"   Total cookies: {len(cookies)}")

        # Try to extract user info
        try:
            name_elem = await page.query_selector('h1, span[dir="auto"]')
            if name_elem:
                name = await name_elem.inner_text()
                print(f"   Logged in as: {name}")
        except Exception:
            pass

        await browser.close()
        print("\n🚀 Next step:")
        print("   python persistent_facebook_demo.py start")
        print(f"{'=' * 60}\n")
        return is_logged
    finally:
        # 无论成功失败都收掉 Playwright：以前失败路径直接跳过 stop()，
        # Python 3.14 会在解释器退出时刷一屏 "I/O operation on closed pipe" 噪音，
        # 把真正的报错盖住了。
        await pw.stop()


async def main():
    names = sys.argv[1:] if len(sys.argv) > 1 else ["fb_default"]
    failed = False

    for name in names:
        safe = "".join(c for c in name if c.isalnum() or c in "-_")
        if safe != name or not safe:
            print(f"⚠️ Skipping invalid session name: {name!r}")
            failed = True
            continue
        try:
            if not await login_facebook(safe):
                failed = True
        except KeyboardInterrupt:
            print(f"\n⏹ Cancelled login for {safe}")
            break
        except Exception as e:
            print(f"❌ Login failed for {safe}: {e}")
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    # 退出码有意义：API 那一侧靠它判断「脚本到底跑成功没有」
    sys.exit(asyncio.run(main()))
