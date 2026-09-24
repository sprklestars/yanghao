"""
持久化实时聊天守护进程 - 自动重连,永不掉线

使用方法:
1. python persistent_chat_demo.py start   # 启动守护进程
2. python persistent_chat_demo.py status  # 查看状态
3. python persistent_chat_demo.py stop    # 停止守护进程
4. python persistent_chat_demo.py logs    # 查看日志

特点:
- 自动重连机制(断线后自动恢复)
- 后台持久运行(nohup)
- PID文件管理
- 详细日志记录
- 心跳保活(每5分钟发送一次活动)
"""

import asyncio
import sys
import os
import signal
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from app.services.conversation.engine import ConversationEngine, ConvState
from app.services.conversation.verification import verification_manager
from app.services.security.account_warming import warming_manager
from app.core.config import settings


# 配置
SESSION_NAME = "sessions/printer"
PROXY = ('http', '127.0.0.1', 7890)

PERSONA_PRESETS = {
    "designer": {
        "name": "Nguyen Van A",
        "age": 28,
        "occupation": "Freelance graphic designer",
        "location": "Ho Chi Minh City",
        "backstory": "在胡志明市做自由设计师3年，经常需要换汇和找外包合作。",
        "tone": "casual, friendly, slightly naive",
    },
    "trader": {
        "name": "Tran Minh Duc",
        "age": 32,
        "occupation": "Crypto trader",
        "location": "Hanoi",
        "backstory": "做了5年加密货币交易，熟悉OTC场外交易和各种换汇渠道。",
        "tone": "confident, knowledgeable, direct",
    },
    "student": {
        "name": "Le Thi Mai",
        "age": 22,
        "occupation": "University student",
        "location": "Da Nang",
        "backstory": "大四学生，学国际贸易，想找兼职和实习机会。",
        "tone": "curious, polite, eager to learn",
    },
    "business": {
        "name": "Pham Hoang Nam",
        "age": 35,
        "occupation": "Import-export business owner",
        "location": "Ho Chi Minh City",
        "backstory": "经营进出口贸易公司8年，需要频繁跨境支付和换汇。",
        "tone": "professional, experienced, trustworthy",
    },
}

PERSONA_CONFIG = PERSONA_PRESETS["designer"]

CATEGORY = "currency_exchanger"

# 日志配置
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "chat_demo.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# PID文件
PID_FILE = Path(__file__).parent / "chat_demo.pid"

WS_URL = "ws://localhost:8000/ws"


class WSBridge:
    """Connect to FastAPI WebSocket and push Telegram messages to frontend."""

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
            logger.warning("⚠️ WebSocket bridge failed: %s (frontend will not receive live updates)", e)
            self.connected = False

    async def send(self, message: dict):
        if not self.connected or not self.ws:
            await self.connect()
        if not self.connected or not self.ws:
            return
        try:
            import json
            await self.ws.send(json.dumps(message))
        except Exception as e:
            logger.warning("⚠️ WebSocket send failed: %s", e)
            self.connected = False
            # Try reconnect once
            await self.connect()
            if self.connected and self.ws:
                try:
                    import json
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


class PersistentChatBot:
    """持久化聊天机器人,带自动重连"""

    def __init__(self):
        self.client = None
        self.engine = ConversationEngine()
        self.persona_config = PERSONA_CONFIG
        self.category = CATEGORY
        self.running = True
        self.last_activity = datetime.now()
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 100
        self.ws_bridge = WSBridge()
        self.reply_policy = {"private": True, "groups": False, "channels": False, "bots": False}
        self.paused = False
        self._load_meta_config()

    def _load_meta_config(self):
        import json
        session_name = SESSION_NAME.split("/")[-1]
        meta_file = Path(SESSION_NAME).parent / f"{session_name}_meta.json"
        if meta_file.exists():
            try:
                with open(meta_file) as f:
                    meta = json.load(f)
                self.reply_policy = meta.get("reply_policy", self.reply_policy)
                self.paused = meta.get("paused", False)
                persona_key = meta.get("persona")
                if persona_key and persona_key in PERSONA_PRESETS:
                    self.persona_config = PERSONA_PRESETS[persona_key]
            except Exception:
                pass

    async def connect(self):
        """连接到Telegram,带重试机制"""
        while self.running and self.reconnect_attempts < self.max_reconnect_attempts:
            try:
                logger.info(f"🔌 正在连接Telegram (尝试 {self.reconnect_attempts + 1})...")

                # 创建客户端(使用代理)
                self.client = TelegramClient(
                    SESSION_NAME,
                    settings.tg_api_id,
                    settings.tg_api_hash,
                    proxy=PROXY
                )

                await self.client.connect()

                if not await self.client.is_user_authorized():
                    logger.error("❌ Session未认证,请先运行: python quick_login.py")
                    return False

                me = await self.client.get_me()
                logger.info(f"✅ 已连接! User: {me.first_name} (@{me.username or 'N/A'})")

                self.reconnect_attempts = 0
                self.last_activity = datetime.now()
                return True

            except Exception as e:
                self.reconnect_attempts += 1
                wait_time = min(2 ** self.reconnect_attempts, 300)  # 指数退避,最多5分钟
                logger.error(f"❌ 连接失败 ({e}), {wait_time}秒后重试...")
                await asyncio.sleep(wait_time)

        return False

    async def setup_handlers(self):
        """设置消息处理器"""

        @self.client.on(events.NewMessage(incoming=True))
        async def handle_new_message(event):
            """处理新消息 — 根据 reply_policy 过滤"""
            try:
                self._load_meta_config()

                if self.paused:
                    logger.debug("⏸ 账号已暂停回复，忽略消息")
                    # Still push inbound message to frontend for monitoring
                    sender = await event.get_sender()
                    user_name = getattr(sender, 'first_name', None) or "Unknown"
                    message_text = event.message.text or ""
                    await self.ws_bridge.send({
                        "type": "telegram_message",
                        "direction": "inbound",
                        "account": SESSION_NAME.split("/")[-1],
                        "sender_id": str(event.sender_id),
                        "sender_name": user_name,
                        "content": message_text,
                        "timestamp": datetime.now().isoformat(),
                    })
                    return

                policy = self.reply_policy

                sender = await event.get_sender()
                is_bot = getattr(sender, 'bot', False)
                is_private = event.is_private

                is_group = False
                is_channel = False
                if not is_private:
                    try:
                        chat = await event.get_chat()
                        from telethon.tl.types import Channel, Chat as TGChat
                        if isinstance(chat, Channel):
                            is_channel = getattr(chat, 'broadcast', False)
                            is_group = not is_channel
                        elif isinstance(chat, TGChat):
                            is_group = True
                    except Exception:
                        is_group = True

                logger.info(f"📨 收到消息: private={is_private} group={is_group} channel={is_channel} bot={is_bot} policy={policy}")

                if is_bot and not policy.get("bots", False):
                    return
                if is_private and not policy.get("private", True):
                    return
                if is_group and not policy.get("groups", False):
                    return
                if is_channel and not policy.get("channels", False):
                    return

                user_id = str(event.sender_id)
                user_name = getattr(sender, 'first_name', None) or "Unknown"
                message_text = event.message.text or ""

                logger.info(f"📨 收到消息 from {user_name} ({user_id}): {message_text[:50]}")

                # Push incoming message to frontend
                await self.ws_bridge.send({
                    "type": "telegram_message",
                    "direction": "inbound",
                    "account": SESSION_NAME.split("/")[-1],
                    "sender_id": user_id,
                    "sender_name": user_name,
                    "content": message_text,
                    "timestamp": datetime.now().isoformat(),
                })

                # 检查是否被拉黑
                from app.services.security.blocklist import is_blocked
                if is_blocked(user_id):
                    logger.info(f"🚫 用户 {user_id} 已被拉黑,忽略消息")
                    return

                # 生成回复
                response, new_state = await self.generate_response(
                    message_text, user_id, CATEGORY
                )

                # 模拟打字延迟（缩短）
                typing_delay = min(len(response) * 0.02, 1.0)
                logger.info(f"⏳ 打字延迟: {typing_delay:.1f}秒")
                await asyncio.sleep(typing_delay)

                # 发送回复
                await self.client.send_message(event.chat_id, response)
                logger.info(f"💬 已回复: {response[:100]}")

                # Push outgoing message to frontend
                await self.ws_bridge.send({
                    "type": "telegram_message",
                    "direction": "outbound",
                    "account": SESSION_NAME.split("/")[-1],
                    "sender_id": user_id,
                    "sender_name": user_name,
                    "content": response,
                    "timestamp": datetime.now().isoformat(),
                })

                self.last_activity = datetime.now()

            except Exception as e:
                logger.error(f"❌ 处理消息失败: {e}", exc_info=True)

    async def generate_response(self, message: str, target_user_id: str, category: str):
        """生成AI回复"""
        try:
            # 检查验证状态
            if not verification_manager.is_verified(target_user_id):
                # Try to verify the user's answer first
                if verification_manager.check_answer(target_user_id, message):
                    logger.info(f"✅ 用户 {target_user_id} 通过验证!")
                    # Fall through to AI engine below
                else:
                    # Not verified yet — send or resend challenge
                    challenge_msg = verification_manager.get_challenge_message(target_user_id)
                    return challenge_msg or "请回答: 10 + 5 = ?", ConvState.VERIFICATION

            # Load context summary from DB
            context_summary = None
            try:
                from app.core.database import async_session_factory
                from sqlalchemy import select as sa_select
                from app.models.models import Conversation
                async with async_session_factory() as session:
                    result = await session.execute(
                        sa_select(Conversation).where(
                            Conversation.target_user_id == target_user_id,
                            Conversation.ended_at.is_(None),
                        )
                    )
                    conv = result.scalar_one_or_none()
                    if conv:
                        context_summary = conv.context_summary
            except Exception as e:
                logger.debug("Could not load context_summary: %s", e)

            # 调用对话引擎
            response, state = await self.engine.generate_response(
                incoming_message=message,
                persona_config=self.persona_config,
                state=ConvState.PROBING,
                category=self.category,
                history=[],
                target_user_id=target_user_id,
                context_summary=context_summary,
            )

            # Update context summary in background (don't block reply)
            async def _update_summary():
                try:
                    updated_summary = await self.engine.update_context_summary(
                        existing_summary=context_summary,
                        incoming_message=message,
                        reply=response,
                        state=state,
                    )
                    from app.core.database import async_session_factory
                    from sqlalchemy import select as sa_select
                    from app.models.models import Conversation
                    async with async_session_factory() as session:
                        result = await session.execute(
                            sa_select(Conversation).where(
                                Conversation.target_user_id == target_user_id,
                                Conversation.ended_at.is_(None),
                            )
                        )
                        conv = result.scalar_one_or_none()
                        if conv:
                            conv.context_summary = updated_summary
                            await session.commit()
                except Exception as e:
                    logger.debug("Could not save context_summary: %s", e)

            asyncio.create_task(_update_summary())

            return response, state

        except Exception as e:
            logger.error(f"❌ 生成回复失败: {e}")
            return "Xin lỗi, tôi đang bận. Hãy thử lại sau nhé! 😊", ConvState.IDLE

    async def heartbeat(self):
        """心跳保活 - 防止超时掉线"""
        while self.running:
            await asyncio.sleep(300)  # 每5分钟

            try:
                # 检查连接状态
                if self.client and self.client.is_connected():
                    logger.info("💓 心跳: 连接正常")
                    self.last_activity = datetime.now()
                else:
                    logger.warning("⚠️ 心跳检测: 连接断开,尝试重连...")
                    await self.reconnect()
            except Exception as e:
                logger.error(f"❌ 心跳异常: {e}")

    async def reconnect(self):
        """重新连接"""
        logger.info("🔄 开始重连...")

        if self.client:
            try:
                await self.client.disconnect()
            except:
                pass

        await asyncio.sleep(2)
        await self.connect()

        if self.client and self.client.is_connected():
            await self.setup_handlers()
            logger.info("✅ 重连成功!")
        else:
            logger.error("❌ 重连失败,将继续重试")

    async def run(self):
        """主运行循环"""
        logger.info("="*60)
        logger.info("🚀 Telegram OSINT - 持久化聊天机器人")
        logger.info("="*60)
        logger.info(f"Session: {SESSION_NAME}")
        logger.info(f"Proxy: {PROXY[1]}:{PROXY[2]}")
        logger.info(f"Persona: {PERSONA_CONFIG['name']}")
        logger.info("="*60)

        # 连接
        if not await self.connect():
            logger.error("无法连接,退出")
            return

        # Connect WebSocket bridge to FastAPI
        await self.ws_bridge.connect()

        # 设置消息处理器
        await self.setup_handlers()

        # 启动心跳保活
        heartbeat_task = asyncio.create_task(self.heartbeat())

        logger.info("\n✅ 服务已启动,等待消息...")
        logger.info("💡 提示: 用你的Telegram给 printer 账号发消息测试\n")

        try:
            # 运行客户端
            await self.client.run_until_disconnected()
        except KeyboardInterrupt:
            logger.info("\n⏹️  收到中断信号,正在关闭...")
        except Exception as e:
            logger.error(f"❌ 运行时错误: {e}", exc_info=True)
        finally:
            self.running = False
            heartbeat_task.cancel()

            await self.ws_bridge.close()

            if self.client:
                try:
                    await self.client.disconnect()
                except:
                    pass

            logger.info("👋 服务已停止")


def write_pid():
    """写入PID文件"""
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))


def read_pid():
    """读取PID文件"""
    if PID_FILE.exists():
        with open(PID_FILE, 'r') as f:
            return int(f.read().strip())
    return None


def remove_pid():
    """删除PID文件"""
    if PID_FILE.exists():
        PID_FILE.unlink()


async def main():
    """主函数"""
    bot = PersistentChatBot()
    write_pid()

    try:
        await bot.run()
    finally:
        remove_pid()


if __name__ == '__main__':
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == 'start':
            logger.info("启动持久化聊天机器人...")
            asyncio.run(main())

        elif command == 'stop':
            pid = read_pid()
            if pid:
                logger.info(f"停止进程 {pid}...")
                os.kill(pid, signal.SIGTERM)
                remove_pid()
                logger.info("已停止")
            else:
                logger.info("没有运行中的进程")

        elif command == 'status':
            pid = read_pid()
            if pid:
                try:
                    os.kill(pid, 0)
                    logger.info(f"✅ 运行中 (PID: {pid})")
                except ProcessLookupError:
                    logger.info("❌ 进程不存在 (清理PID文件)")
                    remove_pid()
            else:
                logger.info("❌ 未运行")

        elif command == 'logs':
            if LOG_FILE.exists():
                os.system(f'tail -f {LOG_FILE}')
            else:
                logger.info("日志文件不存在")

        else:
            print("用法:")
            print("  python persistent_chat_demo.py start   # 启动")
            print("  python persistent_chat_demo.py status  # 状态")
            print("  python persistent_chat_demo.py stop    # 停止")
            print("  python persistent_chat_demo.py logs    # 日志")
    else:
        asyncio.run(main())
