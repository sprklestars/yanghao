"""
Facebook persistent chat service with WebSocket bridge.

Usage:
    python persistent_facebook_demo.py start   # Start daemon
    python persistent_facebook_demo.py stop    # Stop daemon
    python persistent_facebook_demo.py status  # Check status
    python persistent_facebook_demo.py logs    # View logs
"""

import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.services.conversation.engine import ConversationEngine, ConvState
from app.services.conversation.verification import verification_manager
from app.services.platform.base import AccountCredentials, MessageContent, PlatformName
from app.services.platform.facebook_adapter import FacebookAdapter

SESSION_NAME = "fb_default"
CATEGORY = "currency_exchanger"

PERSONA_CONFIG = {
    "name": "Nguyen Van A",
    "age": 28,
    "occupation": "Freelance graphic designer",
    "location": "Ho Chi Minh City",
    "backstory": "在胡志明市做自由设计师3年，经常需要换汇和找外包合作。",
    "tone": "casual, friendly, slightly naive",
}

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "facebook_demo.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

PID_FILE = Path(__file__).parent / "facebook_demo.pid"
WS_URL = "ws://localhost:8000/ws"


class WSBridge:
    def __init__(self, url: str = WS_URL):
        self.url = url
        self.ws = None
        self.connected = False

    async def connect(self):
        try:
            import websockets
            self.ws = await websockets.connect(self.url)
            self.connected = True
            logger.info("🔗 WebSocket bridge connected to %s", self.url)
        except Exception as e:
            logger.warning("⚠️ WebSocket bridge failed: %s", e)
            self.connected = False

    async def send(self, message: dict):
        if not self.connected or not self.ws:
            await self.connect()
        if not self.connected or not self.ws:
            return
        try:
            await self.ws.send(json.dumps(message))
        except Exception as e:
            logger.warning("⚠️ WebSocket send failed: %s", e)
            self.connected = False
            await self.connect()
            if self.connected and self.ws:
                try:
                    await self.ws.send(json.dumps(message))
                except Exception:
                    pass

    async def close(self):
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.connected = False


class PersistentFacebookBot:
    def __init__(self):
        self.adapter = FacebookAdapter(session_name=SESSION_NAME)
        self.engine = ConversationEngine()
        self.persona_config = PERSONA_CONFIG
        self.category = CATEGORY
        self.running = True
        self.ws_bridge = WSBridge()

    async def connect(self):
        cookie_file = f"sessions/{SESSION_NAME}_cookies.json"
        if not os.path.exists(cookie_file):
            logger.error("❌ Cookie file not found: %s", cookie_file)
            logger.error("   Run: python quick_login_facebook.py")
            return False

        credentials = AccountCredentials(
            platform=PlatformName.FACEBOOK,
            username=SESSION_NAME,
            credentials={"email": "", "password": "", "proxy": "http://127.0.0.1:7890"},
        )

        result = await self.adapter.authenticate(credentials)
        if result:
            logger.info("✅ Facebook authenticated (session: %s)", SESSION_NAME)
        else:
            logger.error("❌ Facebook authentication failed")
        return result

    async def generate_response(self, message: str, target_user_id: str, category: str):
        try:
            if not verification_manager.is_verified(target_user_id):
                if verification_manager.check_answer(target_user_id, message):
                    logger.info("✅ User %s passed verification!", target_user_id)
                else:
                    challenge_msg = verification_manager.get_challenge_message(target_user_id)
                    return challenge_msg or "Please answer: 10 + 5 = ?", ConvState.VERIFICATION

            response, state = await self.engine.generate_response(
                incoming_message=message,
                persona_config=self.persona_config,
                state=ConvState.PROBING,
                category=self.category,
                history=[],
                target_user_id=target_user_id,
            )
            return response, state
        except Exception as e:
            logger.error("❌ Response generation failed: %s", e)
            return "Xin lỗi, tôi đang bận. Hãy thử lại sau nhé! 😊", ConvState.IDLE

    async def handle_message(self, msg_data: dict):
        sender_id = msg_data.get("sender_id", "unknown")
        sender_name = msg_data.get("sender_name", "Unknown")
        text = msg_data.get("text", "")

        logger.info("📨 Received from %s (%s): %s", sender_name, sender_id, text[:50])

        await self.ws_bridge.send({
            "type": "telegram_message",
            "direction": "inbound",
            "account": SESSION_NAME,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "content": text,
            "timestamp": datetime.now().isoformat(),
            "platform": "facebook",
        })

        response, _ = await self.generate_response(text, sender_id, CATEGORY)

        content = MessageContent(text=response, language="vi")
        sent = await self.adapter.send_message(sender_id, content)

        if sent:
            logger.info("💬 Replied: %s", response[:100])
            await self.ws_bridge.send({
                "type": "telegram_message",
                "direction": "outbound",
                "account": SESSION_NAME,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "content": response,
                "timestamp": datetime.now().isoformat(),
                "platform": "facebook",
            })
        else:
            logger.error("❌ Failed to send reply")

    async def run(self):
        logger.info("=" * 60)
        logger.info("🚀 Facebook OSINT - Persistent Chat Bot")
        logger.info("=" * 60)
        logger.info("Session: %s", SESSION_NAME)
        logger.info("Persona: %s", PERSONA_CONFIG["name"])
        logger.info("=" * 60)

        if not await self.connect():
            logger.error("Cannot connect, exiting")
            return

        await self.ws_bridge.connect()

        logger.info("\n✅ Service started, listening for messages...\n")

        try:
            await self.adapter.listen_messages(self.handle_message)
        except KeyboardInterrupt:
            logger.info("\n⏹ Interrupted, shutting down...")
        except Exception as e:
            logger.error("❌ Runtime error: %s", e, exc_info=True)
        finally:
            self.running = False
            await self.ws_bridge.close()
            await self.adapter.disconnect()
            logger.info("👋 Service stopped")


def write_pid():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def read_pid():
    if PID_FILE.exists():
        with open(PID_FILE, "r") as f:
            return int(f.read().strip())
    return None


def remove_pid():
    if PID_FILE.exists():
        PID_FILE.unlink()


async def main():
    bot = PersistentFacebookBot()
    write_pid()
    try:
        await bot.run()
    finally:
        remove_pid()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "start":
            logger.info("Starting Facebook persistent chat bot...")
            asyncio.run(main())

        elif command == "stop":
            pid = read_pid()
            if pid:
                logger.info("Stopping process %d...", pid)
                os.kill(pid, signal.SIGTERM)
                remove_pid()
                logger.info("Stopped")
            else:
                logger.info("No running process found")

        elif command == "status":
            pid = read_pid()
            if pid:
                try:
                    os.kill(pid, 0)
                    logger.info("✅ Running (PID: %d)", pid)
                except ProcessLookupError:
                    logger.info("❌ Process not found (cleaning PID)")
                    remove_pid()
            else:
                logger.info("❌ Not running")

        elif command == "logs":
            if LOG_FILE.exists():
                os.system(f"tail -f {LOG_FILE}")
            else:
                logger.info("Log file not found")
        else:
            print("Usage:")
            print("  python persistent_facebook_demo.py start")
            print("  python persistent_facebook_demo.py stop")
            print("  python persistent_facebook_demo.py status")
            print("  python persistent_facebook_demo.py logs")
    else:
        asyncio.run(main())
