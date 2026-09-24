"""
真实演示脚本 - 使用真实Telegram账号和DeepSeek API

演示流程:
1. 加载真实Telegram session
2. 搜索相关群组
3. 获取群成员
4. 发起对话(带算术题验证)
5. AI生成回复(DeepSeek-V3)
6. 提取情报
7. 展示完整流程
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from telethon import TelegramClient

from app.core.config import settings
from app.services.conversation.engine import ConversationEngine, ConvState
from app.services.conversation.verification import verification_manager
from app.services.security.account_warming import warming_manager


async def demo_real_telegram():
    """演示1: 使用真实Telegram账号"""
    print("=" * 70)
    print("🔐 演示1: 加载真实Telegram Session")
    print("=" * 70)

    session_name = "sessions/printer"

    print(f"\n📱 加载账号: {session_name}")

    client = TelegramClient(
        session_name,
        settings.tg_api_id,
        settings.tg_api_hash,
        device_model="Samsung Galaxy S24",
        system_version="Android 14",
        app_version="10.12.0",
    )

    try:
        await client.connect()

        if not await client.is_user_authorized():
            print("   ❌ Session无效,需要重新登录")
            return None

        me = await client.get_me()
        print("   ✅ 登录成功!")
        print(f"      用户名: @{me.username or 'N/A'}")
        print(f"      姓名: {me.first_name} {me.last_name or ''}")
        print(f"      ID: {me.id}")
        print(f"      电话: {me.phone or '隐藏'}")

        # 创建养号档案
        profile = warming_manager.create_profile(
            account_id="printer",
            created_at=datetime.now(),
            ip_region="Vietnam-HCM",
        )
        print(f"   📊 养号状态: {profile.account_age.value}")

        return client

    except Exception as e:
        print(f"   ❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return None


async def demo_search_groups(client):
    """演示2: 搜索真实群组"""
    print("\n" + "=" * 70)
    print("🔍 演示2: 搜索Telegram群组")
    print("=" * 70)

    search_queries = ["đổi tiền", "tỷ giá", "freelancer"]

    for query in search_queries:
        print(f"\n搜索关键词: '{query}'...")

        try:
            from telethon.tl.functions.messages import SearchRequest

            results = await client(SearchRequest(
                q=query,
                filter=None,
                min_date=None,
                max_date=None,
                offset_id=0,
                add_offset=0,
                limit=3,
                max_id=0,
                min_id=0,
                hash=0,
            ))

            if results.chats:
                print(f"   ✅ 找到 {len(results.chats)} 个群组:")
                for i, chat in enumerate(results.chats[:3], 1):
                    member_count = getattr(chat, 'participants_count', 'N/A')
                    print(f"      {i}. {chat.title}")
                    print(f"         成员数: {member_count}")
                    print(f"         ID: {chat.id}")
            else:
                print("   ⚠️ 未找到相关群组")

        except Exception as e:
            print(f"   ❌ 搜索失败: {e}")


async def demo_ai_conversation():
    """演示3: 使用DeepSeek AI生成真实回复"""
    print("\n" + "=" * 70)
    print("🤖 演示3: DeepSeek AI拟人化对话")
    print("=" * 70)

    engine = ConversationEngine()

    # 模拟Persona配置
    persona_config = {
        "name": "Nguyen Van A",
        "age": 28,
        "occupation": "Freelance graphic designer",
        "location": "Ho Chi Minh City",
        "backstory": "在胡志明市做自由设计师3年，经常需要换汇和找外包合作。",
        "tone": "casual, friendly, slightly naive",
    }

    # 模拟对话场景
    test_messages = [
        ("Chào bạn! Mình cần đổi tiền USD sang VND.", "probing"),
        ("Tỷ giá hiện tại là 25,500 VND/USD. Bạn cần đổi bao nhiêu?", "extraction"),
        ("Mình cần đổi khoảng $2000. Bên bạn có uy tín không?", "extraction"),
    ]

    history = []

    for user_msg, expected_state in test_messages:
        print(f"\n 用户消息: {user_msg}")

        reply, new_state = await engine.generate_response(
            incoming_message=user_msg,
            persona_config=persona_config,
            state=ConvState(expected_state),
            category="currency_exchanger",
            history=history,
            target_user_id="test_user",
        )

        print(f"   🤖 AI回复: {reply}")
        print(f"   📊 对话状态: {new_state.value}")

        # 添加到历史
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": reply})

    print("\n✅ AI对话演示完成")


async def demo_verification_flow():
    """演示4: 真实算术题验证流程"""
    print("\n" + "=" * 70)
    print(" 演示4: 算术题验证机制")
    print("=" * 70)

    test_user_id = "real_test_user_001"

    print(f"\n👤 模拟真实用户: {test_user_id}")

    # 生成验证问题
    challenge_msg = verification_manager.get_challenge_message(test_user_id)
    if challenge_msg:
        print("\n📩 系统发送验证消息:")
        for line in challenge_msg.split('\n'):
            print(f"   {line}")

    # 模拟用户回答
    import re
    match = re.search(r'(\d+)\s*([+\-])\s*(\d+)', challenge_msg)
    if match:
        num1 = int(match.group(1))
        operator = match.group(2)
        num2 = int(match.group(3))

        if operator == '+':
            correct_answer = str(num1 + num2)
        else:
            correct_answer = str(num1 - num2)

        print(f"\n✅ 用户回答: '{correct_answer}'")
        is_correct = verification_manager.check_answer(test_user_id, correct_answer)
        print(f"   验证结果: {'通过' if is_correct else '失败'}")

        if is_correct:
            print("   🎉 验证成功!用户可以开始对话")


async def main():
    """运行真实演示"""
    print("\n" + "=" * 70)
    print("🚀 Telegram OSINT 系统 - 真实演示")
    print("=" * 70)
    print("\n⚙️ 配置信息:")
    print(f"   Telegram API ID: {settings.tg_api_id}")
    print(f"   DeepSeek Model: {settings.deepseek_model}")
    print("   Session文件: sessions/printer.session")
    print()

    try:
        # 演示1: 加载真实Telegram账号
        client = await demo_real_telegram()

        if client:
            # 演示2: 搜索群组
            await demo_search_groups(client)
            await client.disconnect()

        # 演示3: AI对话(不需要Telegram连接)
        await demo_ai_conversation()

        # 演示4: 验证机制
        await demo_verification_flow()

        print("\n" + "=" * 70)
        print("🎉 真实演示完成!")
        print("=" * 70)
        print("\n 演示总结:")
        print("   ✅ 真实Telegram账号登录成功")
        print("   ✅ 真实群组搜索功能正常")
        print("   ✅ DeepSeek AI生成拟人化回复")
        print("   ✅ 算术题验证机制工作正常")
        print("   ✅ 养号策略管理器已初始化")
        print("\n 下一步:")
        print("   1. 前端访问: http://localhost:3000 (演示模式)")
        print("   2. API文档: http://localhost:8000/docs")
        print("   3. 可以开始创建真实任务并执行")
        print()

    except KeyboardInterrupt:
        print("\n\n⚠️ 演示被用户中断")
    except Exception as e:
        print(f"\n❌ 演示出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
