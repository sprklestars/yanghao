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
import sys
from getpass import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

SESSION_DIR = Path(__file__).parent / "sessions"
SESSION_DIR.mkdir(exist_ok=True)


async def login_facebook(session_name: str) -> bool:
    from playwright.async_api import async_playwright

    cookie_file = SESSION_DIR / f"{session_name}_cookies.json"

    print(f"\n{'='*60}")
    print(f"🔐 Facebook Login — Session: {session_name}")
    print(f"{'='*60}")
    print("\n📝 Instructions:")
    print("1. A browser window will open")
    print("2. Log in to your Facebook account manually")
    print("3. Handle any 2FA / captcha / checkpoint yourself")
    print("4. Once logged in, come back here and press Enter")
    print("5. Cookies will be saved for headless automation\n")

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False)
    context = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        locale="vi-VN",
        timezone_id="Asia/Ho_Chi_Minh",
    )

    # Load existing cookies if available
    if cookie_file.exists():
        try:
            with open(cookie_file, "r") as f:
                cookies = json.load(f)
            await context.add_cookies(cookies)
            print(f"📂 Loaded existing cookies from {cookie_file.name}")
        except Exception as e:
            print(f"⚠️ Could not load cookies: {e}")

    page = await context.new_page()
    await page.goto("https://www.facebook.com/", wait_until="domcontentloaded")

    input("\n✅ Press Enter after you have logged in successfully...")

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
    await pw.stop()

    print(f"\n🚀 Next step:")
    print(f"   python persistent_facebook_demo.py start")
    print(f"{'='*60}\n")
    return True


async def main():
    names = sys.argv[1:] if len(sys.argv) > 1 else ["fb_default"]

    for name in names:
        safe = "".join(c for c in name if c.isalnum() or c in "-_")
        if safe != name or not safe:
            print(f"⚠️ Skipping invalid session name: {name!r}")
            continue
        try:
            await login_facebook(safe)
        except KeyboardInterrupt:
            print(f"\n⏹ Cancelled login for {safe}")
            break
        except Exception as e:
            print(f"❌ Login failed for {safe}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
