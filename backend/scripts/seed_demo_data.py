"""
OSINT Platform - Demo Data Seeder
生成演示数据用于展示系统功能
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.models import (
    Account,
    AccountHealth,
    ActivityStatus,
    Conversation,
    ConversationState,
    IntelligenceCategory,
    IntelligenceRecord,
    Message,
    MessageDirection,
    Persona,
    Platform,
    ReviewStatus,
    Task,
    TaskStatus,
)


def create_demo_data():
    """创建演示数据"""

    # 使用同步引擎
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from app.core.config import settings

    engine = create_engine(
        settings.database_url_sync or "postgresql://osint:osint@localhost:5432/osint"
    )

    with Session(engine) as db:
        print("🌱 开始生成演示数据...")

        # 1. 创建Persona角色模板
        print("📝 创建Persona角色...")
        personas = [
            Persona(
                id=uuid.uuid4(),
                name="越南自由设计师",
                persona_config={
                    "name": "Nguyen Van Minh",
                    "age": 28,
                    "location": "Ho Chi Minh City",
                    "occupation": "Freelance graphic designer",
                    "backstory": (
                        "在胡志明市做自由设计师3年,经常需要换汇和找外包合作。"
                        "擅长网页设计和品牌标识。"
                    ),
                    "language": "vi",
                    "tone": "casual, friendly, slightly naive",
                    "conversation_style": {
                        "avg_message_length": "15-40 words",
                        "uses_emoji": True,
                        "response_time_pattern": "30s-3min",
                    },
                },
            ),
            Persona(
                id=uuid.uuid4(),
                name="河内小商人",
                persona_config={
                    "name": "Tran Thi Lan",
                    "age": 35,
                    "location": "Hanoi",
                    "occupation": "Small business owner",
                    "backstory": (
                        "在河内经营一家小商店,需要做跨境支付和货币兑换。经常寻找可靠的换汇渠道。"
                    ),
                    "language": "vi",
                    "tone": "business-like but friendly",
                    "conversation_style": {
                        "avg_message_length": "20-50 words",
                        "uses_emoji": False,
                        "response_time_pattern": "1-5min",
                    },
                },
            ),
        ]
        db.add_all(personas)
        db.commit()
        print(f"✅ 创建了 {len(personas)} 个Persona角色")

        # 2. 创建账号
        print("👤 创建测试账号...")
        accounts = [
            Account(
                id=uuid.uuid4(),
                platform=Platform.TELEGRAM,
                username="@demo_account_1",
                credentials={"phone": "+84123456789", "session": "demo_session_1"},
                persona_id=personas[0].id,
                health=AccountHealth.GREEN,
                proxy_url="socks5://demo-proxy:1080",
                is_active=True,
                last_action_at=datetime.now(timezone.utc) - timedelta(hours=2),
            ),
            Account(
                id=uuid.uuid4(),
                platform=Platform.TELEGRAM,
                username="@demo_account_2",
                credentials={"phone": "+84987654321", "session": "demo_session_2"},
                persona_id=personas[1].id,
                health=AccountHealth.GREEN,
                proxy_url="socks5://demo-proxy:1081",
                is_active=True,
                last_action_at=datetime.now(timezone.utc) - timedelta(hours=5),
            ),
        ]
        db.add_all(accounts)
        db.commit()
        print(f"✅ 创建了 {len(accounts)} 个测试账号")

        # 3. 创建任务
        print("📋 创建演示任务...")
        tasks = [
            Task(
                id=uuid.uuid4(),
                name="河内自由职业者调研",
                platform=Platform.TELEGRAM,
                category=IntelligenceCategory.FREELANCER,
                keywords=["thiết kế website", "lập trình viên", "freelancer"],
                target_region="Hanoi",
                status=TaskStatus.COMPLETED,
                config={"max_groups": 5, "max_members_per_group": 20},
            ),
            Task(
                id=uuid.uuid4(),
                name="换汇服务情报收集",
                platform=Platform.TELEGRAM,
                category=IntelligenceCategory.CURRENCY_EXCHANGER,
                keywords=["đổi tiền", "chuyển tiền", "tỷ giá"],
                target_region="Ho Chi Minh City",
                status=TaskStatus.RUNNING,
                config={"max_groups": 3, "max_members_per_group": 15},
            ),
            Task(
                id=uuid.uuid4(),
                name="私人侦探服务调查",
                platform=Platform.TELEGRAM,
                category=IntelligenceCategory.PRIVATE_INVESTIGATOR,
                keywords=["thám tử", "điều tra", "theo dõi"],
                target_region=None,
                status=TaskStatus.PENDING,
                config={},
            ),
        ]
        db.add_all(tasks)
        db.commit()
        print(f"✅ 创建了 {len(tasks)} 个演示任务")

        # 4. 创建对话和消息
        print("💬 创建演示对话...")
        conversations = []
        messages = []

        # 对话1: 与自由职业者的完整对话
        conv1_id = uuid.uuid4()
        conv1 = Conversation(
            id=conv1_id,
            account_id=accounts[0].id,
            task_id=tasks[0].id,
            target_user_id="123456789",
            target_display_name="Le Hoang Tuan",
            state=ConversationState.EXIT,
            turn_count=6,
            context_summary="目标是一名网站开发者,提供WordPress建站服务,报价$300-500",
            started_at=datetime.now(timezone.utc) - timedelta(days=2, hours=3),
            ended_at=datetime.now(timezone.utc) - timedelta(days=2, hours=2),
        )
        conversations.append(conv1)

        # 对话1的消息
        conv1_messages = [
            Message(
                id=uuid.uuid4(),
                conversation_id=conv1_id,
                direction=MessageDirection.OUTBOUND,
                content=(
                    "Chào bạn! Mình thấy bạn trong nhóm Freelancer Vietnam. "
                    "Bạn làm thiết kế web hả? 😊"
                ),
                language="vi",
                created_at=datetime.now(timezone.utc) - timedelta(days=2, hours=3),
            ),
            Message(
                id=uuid.uuid4(),
                conversation_id=conv1_id,
                direction=MessageDirection.INBOUND,
                content=(
                    "Chào bạn! Đúng rồi, mình chuyên làm WordPress và Laravel. Bạn cần gì không?"
                ),
                language="vi",
                created_at=datetime.now(timezone.utc) - timedelta(days=2, hours=2, minutes=55),
            ),
            Message(
                id=uuid.uuid4(),
                conversation_id=conv1_id,
                direction=MessageDirection.OUTBOUND,
                content=(
                    "À hay quá! Mình đang cần làm một trang web bán hàng. "
                    "Giá khoảng bao nhiêu vậy bạn?"
                ),
                language="vi",
                created_at=datetime.now(timezone.utc) - timedelta(days=2, hours=2, minutes=50),
            ),
            Message(
                id=uuid.uuid4(),
                conversation_id=conv1_id,
                direction=MessageDirection.INBOUND,
                content=(
                    "Tùy vào yêu cầu nhé. Web cơ bản thì $300-500, "
                    "phức tạp hơn thì $800-1500. Bạn cần tính năng gì?"
                ),
                language="vi",
                created_at=datetime.now(timezone.utc) - timedelta(days=2, hours=2, minutes=45),
            ),
            Message(
                id=uuid.uuid4(),
                conversation_id=conv1_id,
                direction=MessageDirection.OUTBOUND,
                content=(
                    "Web bán quần áo thôi, có thanh toán online được càng tốt. "
                    "Cho mình xin contact trực tiếp nhé!"
                ),
                language="vi",
                created_at=datetime.now(timezone.utc) - timedelta(days=2, hours=2, minutes=40),
            ),
            Message(
                id=uuid.uuid4(),
                conversation_id=conv1_id,
                direction=MessageDirection.INBOUND,
                content=(
                    "OK bạn add Zalo mình nhé: 0912345678. "
                    "Hoặc email: tuan.webdev@gmail.com. Mình gửi portfolio cho!"
                ),
                language="vi",
                created_at=datetime.now(timezone.utc) - timedelta(days=2, hours=2, minutes=35),
            ),
        ]
        messages.extend(conv1_messages)

        # 对话2: 与换汇服务的进行中对话
        conv2_id = uuid.uuid4()
        conv2 = Conversation(
            id=conv2_id,
            account_id=accounts[1].id,
            task_id=tasks[1].id,
            target_user_id="987654321",
            target_display_name="Money Exchange HCM",
            state=ConversationState.EXTRACTION,
            turn_count=4,
            started_at=datetime.now(timezone.utc) - timedelta(hours=5),
        )
        conversations.append(conv2)

        conv2_messages = [
            Message(
                id=uuid.uuid4(),
                conversation_id=conv2_id,
                direction=MessageDirection.OUTBOUND,
                content="Chào bạn! Mình cần đổi USD sang VND, bên bạn có dịch vụ này không?",
                language="vi",
                created_at=datetime.now(timezone.utc) - timedelta(hours=5),
            ),
            Message(
                id=uuid.uuid4(),
                conversation_id=conv2_id,
                direction=MessageDirection.INBOUND,
                content="Có bạn ơi! Tỷ giá hôm nay 23,500 VND/USD. Bạn muốn đổi bao nhiêu?",
                language="vi",
                created_at=datetime.now(timezone.utc) - timedelta(hours=4, minutes=50),
            ),
            Message(
                id=uuid.uuid4(),
                conversation_id=conv2_id,
                direction=MessageDirection.OUTBOUND,
                content="Khoảng $5000. Bên bạn có ship tiền tận nơi không? Ở quận 1.",
                language="vi",
                created_at=datetime.now(timezone.utc) - timedelta(hours=4, minutes=45),
            ),
            Message(
                id=uuid.uuid4(),
                conversation_id=conv2_id,
                direction=MessageDirection.INBOUND,
                content=(
                    "Có chứ! Phí ship 200k nhé. "
                    "Bạn cần gặp trực tiếp hay chuyển khoản trước? Call/Zalo: 0908123456"
                ),
                language="vi",
                created_at=datetime.now(timezone.utc) - timedelta(hours=4, minutes=40),
            ),
        ]
        messages.extend(conv2_messages)

        db.add_all(conversations)
        db.add_all(messages)
        db.commit()
        print(f"✅ 创建了 {len(conversations)} 个对话和 {len(messages)} 条消息")

        # 5. 创建情报记录
        print("🧠 创建情报告报...")
        intelligence_records = [
            IntelligenceRecord(
                id=uuid.uuid4(),
                task_id=tasks[0].id,
                platform=Platform.TELEGRAM,
                target_user_id="123456789",
                display_name="Le Hoang Tuan",
                profile_url="https://t.me/lehoangtuan",
                category=IntelligenceCategory.FREELANCER,
                confidence=0.92,
                signals=["mentions web development", "quotes price range", "offers portfolio"],
                extracted_contacts={
                    "phones": ["0912345678"],
                    "emails": ["tuan.webdev@gmail.com"],
                    "zalo_ids": [],
                    "telegram_handles": ["@lehoangtuan"],
                    "facebook_urls": [],
                },
                business_info={
                    "service_description": "WordPress and Laravel web development",
                    "price_range": "$300-1500",
                    "website": "",
                    "prices": ["$300-500", "$800-1500"],
                },
                activity_status=ActivityStatus.ACTIVE,
                last_seen=datetime.now(timezone.utc) - timedelta(days=2, hours=2),
                response_rate=0.95,
                review_status=ReviewStatus.APPROVED,
                operator_notes="专业的网站开发者,价格合理,有作品集",
                dedup_fingerprint=uuid.uuid4().hex,
                collected_at=datetime.now(timezone.utc) - timedelta(days=2, hours=2),
                reviewed_at=datetime.now(timezone.utc) - timedelta(days=2, hours=1),
            ),
            IntelligenceRecord(
                id=uuid.uuid4(),
                task_id=tasks[1].id,
                platform=Platform.TELEGRAM,
                target_user_id="987654321",
                display_name="Money Exchange HCM",
                profile_url=None,
                category=IntelligenceCategory.CURRENCY_EXCHANGER,
                confidence=0.88,
                signals=["mentions exchange rate", "provides phone contact", "offers delivery"],
                extracted_contacts={
                    "phones": ["0908123456"],
                    "emails": [],
                    "zalo_ids": ["0908123456"],
                    "telegram_handles": [],
                    "facebook_urls": [],
                },
                business_info={
                    "service_description": "USD/VND currency exchange with delivery service",
                    "price_range": "23,500 VND/USD + 200k fee",
                    "website": "",
                    "prices": ["23,500 VND/USD"],
                },
                activity_status=ActivityStatus.ACTIVE,
                last_seen=datetime.now(timezone.utc) - timedelta(hours=4, minutes=40),
                response_rate=0.90,
                review_status=ReviewStatus.REVIEWED,
                operator_notes="提供换汇服务,支持送货上门,费率23,500",
                dedup_fingerprint=uuid.uuid4().hex,
                collected_at=datetime.now(timezone.utc) - timedelta(hours=4, minutes=40),
                reviewed_at=None,
            ),
            IntelligenceRecord(
                id=uuid.uuid4(),
                task_id=tasks[0].id,
                platform=Platform.TELEGRAM,
                target_user_id="456789123",
                display_name="Design Studio VN",
                profile_url="https://t.me/designstudiovn",
                category=IntelligenceCategory.FREELANCER,
                confidence=0.75,
                signals=["mentions design services", "has team"],
                extracted_contacts={
                    "phones": [],
                    "emails": ["contact@designstudio.vn"],
                    "zalo_ids": [],
                    "telegram_handles": ["@designstudiovn"],
                    "facebook_urls": ["facebook.com/designstudiovn"],
                },
                business_info={
                    "service_description": "Full-service design studio",
                    "price_range": "Contact for quote",
                    "website": "designstudio.vn",
                    "prices": [],
                },
                activity_status=ActivityStatus.DORMANT,
                last_seen=datetime.now(timezone.utc) - timedelta(days=7),
                response_rate=0.60,
                review_status=ReviewStatus.PENDING,
                operator_notes=None,
                dedup_fingerprint=uuid.uuid4().hex,
                collected_at=datetime.now(timezone.utc) - timedelta(days=7),
                reviewed_at=None,
            ),
        ]
        db.add_all(intelligence_records)
        db.commit()
        print(f"✅ 创建了 {len(intelligence_records)} 条情报记录")

        print("\n🎉 演示数据生成完成!")
        print("\n📊 数据统计:")
        print(f"   - Persona角色: {len(personas)}")
        print(f"   - 测试账号: {len(accounts)}")
        print(f"   - 任务: {len(tasks)}")
        print(f"   - 对话: {len(conversations)}")
        print(f"   - 消息: {len(messages)}")
        print(f"   - 情报记录: {len(intelligence_records)}")
        print("\n💡 现在可以访问 http://localhost:3001 查看演示数据!")


if __name__ == "__main__":
    try:
        create_demo_data()
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        print("\n提示: 确保PostgreSQL数据库正在运行并且已执行alembic迁移")
