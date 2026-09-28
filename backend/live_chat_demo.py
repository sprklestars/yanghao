"""
实时互动演示 - 你发消息,AI自动回复

使用方法:
1. 运行此脚本
2. 用你的Telegram给 printer 账号发私信
3. 系统会自动用AI回复你
4. 按 Ctrl+C 停止

功能:
- 算术题验证(首次对话)
- DeepSeek AI生成越南语回复
- 养号策略检查
- 实时消息监听
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from datetime import datetime

from telethon import TelegramClient, events

from app.core.config import settings
from app.core.proxy import telegram_proxy
from app.core.session_paths import ensure_session_dir
from app.services.conversation.engine import ConversationEngine, ConvState
from app.services.conversation.verification import verification_manager
from app.services.security.account_warming import warming_manager

# 配置
SESSION_NAME = "sessions/printer"

# 代理配置(如果需要)
# 代理来自 .env 的 TG_PROXY_URL（(类型, 主机, 端口) 由 app/core/proxy.py 解析）
PROXY = telegram_proxy()

# Persona配置
PERSONA_CONFIG = {
    "name": "Nguyen Van A",
    "age": 28,
    "occupation": "Freelance graphic designer",
    "location": "Ho Chi Minh City",
    "backstory": "在胡志明市做自由设计师3年，经常需要换汇和找外包合作。",
    "tone": "casual, friendly, slightly naive",
}

CATEGORY = "currency_exchanger"

# 对话历史存储: {user_id: [messages]}
conversation_histories = {}


async def handle_new_message(event):
    """处理新消息事件"""
    sender = await event.get_sender()
    if not sender or sender.bot:
        return

    user_id = str(sender.id)
    user_name = getattr(sender, "first_name", "Unknown")
    message_text = event.raw_text

    print(f"\n{'=' * 70}")
    print(f"📨 收到消息 from @{user_name} (ID: {user_id})")
    print(f"   内容: {message_text}")
    print(f"{'=' * 70}")

    # 检查养号限制
    allowed, reason = warming_manager.check_and_enforce_limits(
        account_id="printer",
        operation="send_message",
        is_stranger=(user_id not in conversation_histories),
    )

    if not allowed:
        print(f"⚠️ 养号限制: {reason}")
        await event.reply(f"⚠️ 系统限制: {reason}\n请稍后再试。")
        return

    # 初始化对话历史
    if user_id not in conversation_histories:
        conversation_histories[user_id] = []

    history = conversation_histories[user_id]

    # 检查是否需要验证
    if not verification_manager.is_verified(user_id):
        challenge_msg = verification_manager.get_challenge_message(user_id)

        if challenge_msg:
            # 发送验证问题
            print("\n 发送验证问题...")
            await event.reply(challenge_msg)
            print("✅ 验证问题已发送")
            return

        # 用户回答了验证题
        is_correct = verification_manager.check_answer(user_id, message_text)

        if is_correct:
            reply = (
                "✅ Xác minh thành công! Bây giờ chúng ta có thể bắt đầu trò chuyện. 😊\n\n"
                "Chào bạn! Mình là Nguyễn, rất vui được làm quen!"
            )
            print("\n✅ 验证通过!")
            print(f"🤖 回复: {reply}")
            await event.reply(reply)

            # 添加到历史
            history.append({"role": "assistant", "content": reply})
            return
        else:
            reply = "❌ Câu trả lời không đúng. Vui lòng thử lại hoặc liên hệ quản trị viên."
            print("\n❌ 验证失败")
            print(f"🤖 回复: {reply}")
            await event.reply(reply)
            return

    # 正常对话 - 使用AI生成回复
    print("\n🤖 调用DeepSeek AI生成回复...")

    engine = ConversationEngine()

    # 确定当前对话状态
    current_state = ConvState.PROBING if len(history) < 6 else ConvState.EXTRACTION

    try:
        ai_reply, new_state = await engine.generate_response(
            incoming_message=message_text,
            persona_config=PERSONA_CONFIG,
            state=current_state,
            category=CATEGORY,
            history=history,
            target_user_id=user_id,
        )

        print(f"   状态: {new_state.value}")
        print(f"   回复长度: {len(ai_reply)} 字符")

        # 模拟打字延迟(更真实)
        typing_delay = min(len(ai_reply) * 0.05, 5)
        print(f"   打字延迟: {typing_delay:.1f}秒")
        await asyncio.sleep(typing_delay)

        # 发送AI回复
        print("\n📤 发送AI回复...")
        await event.reply(ai_reply)
        print("✅ 回复已发送")

        # 更新对话历史
        history.append({"role": "user", "content": message_text})
        history.append({"role": "assistant", "content": ai_reply})

        # 只保留最近20条
        if len(history) > 20:
            conversation_histories[user_id] = history[-20:]

    except Exception as e:
        print(f"❌ AI生成失败: {e}")
        fallback_reply = "Xin lỗi, mình đang bận chút. Bạn nhắn lại sau nhé! 😊"
        await event.reply(fallback_reply)


async def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("🚀 Telegram OSINT - 实时AI互动演示")
    print("=" * 70)
    print("\n⚙️ 配置:")
    print(f"   Session: {SESSION_NAME}")
    print(f"   API ID: {settings.tg_api_id}")
    print(f"   代理: {PROXY[1]}:{PROXY[2]}")
    print(f"   Persona: {PERSONA_CONFIG['name']}")
    print(f"   类别: {CATEGORY}")
    print()
    print("📱 使用说明:")
    print("   1. 等待Telegram连接成功")
    print("   2. 用你的Telegram给 printer 账号发私信")
    print("   3. 首次对话会收到算术题验证")
    print("   4. 验证通过后,AI会自动回复你")
    print("   5. 按 Ctrl+C 停止演示")
    print()
    print("=" * 70)

    # 创建养号档案
    warming_manager.create_profile(
        account_id="printer",
        created_at=datetime.now(),
        ip_region="Vietnam-HCM",
    )

    # 创建Telegram客户端(带代理)
    ensure_session_dir(SESSION_NAME)
    client = TelegramClient(
        SESSION_NAME,
        settings.tg_api_id,
        settings.tg_api_hash,
        proxy=PROXY,
        device_model="Samsung Galaxy S24",
        system_version="Android 14",
        app_version="10.12.0",
    )

    try:
        print("\n🔌 正在连接Telegram(使用代理)...")
        await client.start()

        me = await client.get_me()
        print("\n✅ 连接成功!")
        print(f"   用户名: @{me.username or 'N/A'}")
        print(f"   姓名: {me.first_name} {me.last_name or ''}")
        print(f"   ID: {me.id}")
        print()
        print("👂 开始监听消息...")
        print("=" * 70)

        # 注册消息处理器
        @client.on(events.NewMessage(incoming=True))
        async def handler(event):
            await handle_new_message(event)

        # 保持运行
        print("\n 等待接收消息...(按Ctrl+C停止)")
        await client.run_until_disconnected()

    except KeyboardInterrupt:
        print("\n\n⚠️ 演示被用户中断")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback

        traceback.print_exc()
        print("\n💡 提示: 如果连接失败,请检查:")
        print("   1. 代理是否运行(127.0.0.1:7890)")
        print("   2. Session文件是否有效")
        print("   3. 网络连接是否正常")
    finally:
        await client.disconnect()
        print("\n👋 已断开连接")


if __name__ == "__main__":
    asyncio.run(main())
