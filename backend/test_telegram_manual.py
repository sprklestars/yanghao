"""
Manual Telegram Adapter Test - No Database Required
Tests basic Telegram functionality: login, search groups, get members
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from telethon import TelegramClient, functions

# API credentials loaded from environment (.env). Never hardcode secrets.
API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")


async def test_login_and_search():
    """Test Telegram login and group search."""

    print("=" * 60)
    print("🔐 Telegram Adapter Manual Test")
    print("=" * 60)

    # Create client
    client = TelegramClient('test_session', API_ID, API_HASH)

    try:
        # Start client (will prompt for phone if not logged in)
        print("\n📱 Starting Telegram client...")
        await client.start()

        # Get user info
        me = await client.get_me()
        print("\n✅ Login successful!")
        print(f"   Username: @{me.username or 'N/A'}")
        print(f"   Name: {me.first_name} {me.last_name or ''}")
        print(f"   ID: {me.id}")
        print(f"   Phone: {me.phone or 'Hidden'}")

        # Test search groups
        print("\n" + "=" * 60)
        print("🔍 Testing Group Search...")
        print("=" * 60)

        search_queries = ["freelancer", "thiet ke web", "doi tien"]

        for query in search_queries:
            print(f"\nSearching for: '{query}'...")

            try:
                results = await client(functions.messages.SearchRequest(
                    q=query,
                    filter=None,
                    min_date=None,
                    max_date=None,
                    offset_id=0,
                    add_offset=0,
                    limit=5,
                    max_id=0,
                    min_id=0,
                    hash=0,
                ))

                if results.chats:
                    print(f"   Found {len(results.chats)} groups:")
                    for i, chat in enumerate(results.chats[:3], 1):
                        member_count = getattr(chat, 'participants_count', 'N/A')
                        print(f"   {i}. {chat.title}")
                        print(f"      Members: {member_count}")
                        print(f"      ID: {chat.id}")
                else:
                    print(f"   No groups found for '{query}'")

            except Exception as e:
                print(f"   ❌ Error searching '{query}': {e}")

        # Test get dialog (conversations)
        print("\n" + "=" * 60)
        print("💬 Testing Dialog List...")
        print("=" * 60)

        dialogs = await client.get_dialogs(limit=5)
        if dialogs:
            print(f"   You have {len(dialogs)} conversations:")
            for i, dialog in enumerate(dialogs[:5], 1):
                name = dialog.name or "Unknown"
                print(f"   {i}. {name}")
        else:
            print("   No conversations found")

        # Optional: Test sending a message (commented out for safety)
        # print("\n" + "=" * 60)
        # print("📤 Testing Send Message...")
        # print("=" * 60)
        # target_username = "username_here"  # Replace with actual username
        # await client.send_message(target_username, "Test message")
        # print(f"   Message sent to @{target_username}")

        print("\n" + "=" * 60)
        print("✅ All tests completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await client.disconnect()
        print("\n👋 Disconnected from Telegram")


if __name__ == "__main__":
    print("\n⚠️  Note: First time login will require phone number and SMS code\n")
    asyncio.run(test_login_and_search())
