"""统一的回复链路。

历史上有三处"生成回复"的实现：`ConversationEngine`（真正的状态机）、
守护进程 `persistent_chat_demo.py` 里的一层包装（把 state 写死成 PROBING、
history 传空，等于状态机没跑）、以及 `workers.process_incoming_message()`（死代码）。

这里把它们收敛成一个入口：加载会话状态 + 最近消息历史 → 用引擎走完状态机 →
把新状态/轮次/上下文摘要写回数据库。守护进程只负责收消息和发消息。
"""

import logging
import uuid

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.models import (
    Account,
    AccountHealth,
    Conversation,
    ConversationState,
    IntelligenceCategory,
    Message,
    MessageDirection,
    Platform,
    Task,
    TaskStatus,
)
from app.services.conversation.engine import (
    ConversationEngine,
    db_state_for,
    engine_state_from,
)

logger = logging.getLogger(__name__)

async def generate_reply(
    account_id: uuid.UUID,
    account_name: str,
    target_user_id: str,
    target_display_name: str,
    incoming_message: str,
    category: str,
    persona_config: dict,
) -> tuple[str, str]:
    """生成一条回复并落库，返回 ``(reply_text, new_state_value)``。

    ``account_id`` / ``target_user_id`` 用来定位会话；找不到就按
    ``persist_message()`` 同款确定性规则新建（挂在 Auto-<平台> 容器任务下）。
    """
    engine = ConversationEngine()
    task_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, "task-auto-telegram")

    async with async_session_factory() as session:
        # 会话依赖 account / task 两行；守护进程可能先于 persist_message 到这里，
        # 所以按 persist_message 的确定性规则自己补齐，避免外键冲突。
        if await session.get(Account, account_id) is None:
            session.add(
                Account(
                    id=account_id,
                    platform=Platform.TELEGRAM,
                    username=account_name,
                    credentials={},
                    health=AccountHealth.GREEN,
                    is_active=True,
                )
            )
        if await session.get(Task, task_uuid) is None:
            session.add(
                Task(
                    id=task_uuid,
                    name="Auto-telegram",
                    platform=Platform.TELEGRAM,
                    category=IntelligenceCategory.CURRENCY_EXCHANGER,
                    keywords=[],
                    status=TaskStatus.RUNNING,
                )
            )
        await session.flush()

        result = await session.execute(
            select(Conversation).where(
                Conversation.account_id == account_id,
                Conversation.target_user_id == target_user_id,
                Conversation.ended_at.is_(None),
            )
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            conv = Conversation(
                id=uuid.uuid4(),
                account_id=account_id,
                task_id=task_uuid,
                target_user_id=target_user_id,
                target_display_name=target_display_name or None,
                state=ConversationState.IDLE,
                turn_count=0,
            )
            session.add(conv)
            await session.flush()

        # 最近 20 条消息作为历史（按时间升序喂给引擎）
        history_rows = (
            (
                await session.execute(
                    select(Message)
                    .where(Message.conversation_id == conv.id)
                    .order_by(Message.created_at.desc())
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )
        history = [
            {
                "role": (
                    "user" if m.direction == MessageDirection.INBOUND else "assistant"
                ),
                "content": m.content or "",
            }
            for m in reversed(history_rows)
        ]

        current_state = engine_state_from(conv.state)
        reply, new_state = await engine.generate_response(
            incoming_message=incoming_message,
            persona_config=persona_config,
            state=current_state,
            category=category,
            history=history,
            target_user_id=target_user_id,
            context_summary=conv.context_summary,
        )

        conv.state = db_state_for(new_state)
        conv.turn_count = (conv.turn_count or 0) + 1
        try:
            conv.context_summary = await engine.update_context_summary(
                existing_summary=conv.context_summary,
                incoming_message=incoming_message,
                reply=reply,
                state=new_state,
            )
        except Exception as e:  # 摘要失败不阻塞回复
            logger.warning("更新上下文摘要失败: %s", e)

        await session.commit()
        return reply, new_state.value
