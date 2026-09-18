#!/usr/bin/env python3
"""
Quick login script for printer Telegram account.
Run this and follow the prompts.
"""
import asyncio
import sys
from telethon import TelegramClient
from app.core.config import settings

SESSION = 'sessions/printer'

async def main():
    print("\n" + "="*60)
    print("🔐 Telegram Printer Account Login")
    print("="*60)
    print("\n📝 Instructions:")
    print("1. Enter your phone number with country code (e.g., +84123456789)")
    print("2. Check your Telegram app for verification code")
    print("3. Enter the code you received")
    print("4. If you have 2FA, enter your password\n")

    # Try with proxy first
    try:
        print("🔌 Attempting connection with proxy (127.0.0.1:7890)...")
        client = TelegramClient(
            SESSION,
            settings.tg_api_id,
            settings.tg_api_hash,
            proxy=('http', '127.0.0.1', 7890)
        )
        await client.connect()
        if not await client.is_user_authorized():
            print("✅ Proxy connected, but session not authenticated.")
            print("Starting authentication flow...\n")
            await client.start()
        else:
            print("✅ Already logged in!")
    except Exception as e:
        print(f"⚠️  Proxy failed: {e}")
        print("Trying without proxy...\n")
        client = TelegramClient(SESSION, settings.tg_api_id, settings.tg_api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            await client.start()
        else:
            print("✅ Already logged in!")

    # Get user info
    me = await client.get_me()
    print("\n" + "="*60)
    print("✅ LOGIN SUCCESSFUL!")
    print("="*60)
    print(f"Name: {me.first_name} {me.last_name or ''}")
    print(f"Username: @{me.username or 'N/A'}")
    print(f"Phone: {me.phone}")
    print(f"ID: {me.id}")
    print("="*60)
    print(f"\n💾 Session saved to: {SESSION}.session")
    print("\n🚀 Next step:")
    print("   Run: python live_chat_demo.py")
    print("="*60 + "\n")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
