"""
Login script for printer Telegram account.
Creates a new session file for automated chat demo.
"""

import asyncio

from telethon import TelegramClient

from app.core.config import settings
from app.core.proxy import telegram_proxy
from app.core.session_paths import ensure_session_dir

SESSION_NAME = "sessions/printer"


async def main():
    print("=" * 70)
    print("🔐 Telegram Login - Printer Account")
    print("=" * 70)
    print()

    # Create client with proxy
    # Telethon 构造时就写 .session 文件，目录不存在会抛 sqlite3 错误。
    ensure_session_dir(SESSION_NAME)
    try:
        client = TelegramClient(
            SESSION_NAME,
            settings.tg_api_id,
            settings.tg_api_hash,
            proxy=telegram_proxy(),
        )
        print("✅ Using proxy at 127.0.0.1:7890")
    except Exception as e:
        print(f"⚠️  Proxy setup failed: {e}")
        print("Trying without proxy...")
        client = TelegramClient(SESSION_NAME, settings.tg_api_id, settings.tg_api_hash)

    await client.start(
        phone=lambda: input("Enter phone number (e.g., +84xxx): "),
        password=lambda: input("Enter password (if 2FA enabled): "),
        code_callback=lambda: input("Enter verification code: "),
    )

    me = await client.get_me()
    print()
    print("=" * 70)
    print("✅ Login successful!")
    print(f"   User: {me.first_name} {me.last_name or ''}")
    print(f"   Username: @{me.username or 'N/A'}")
    print(f"   Phone: {me.phone}")
    print(f"   ID: {me.id}")
    print("=" * 70)
    print()
    print("Session saved to sessions/printer.session")
    print()
    print("Now you can run:")
    print("  python live_chat_demo.py")
    print()

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
