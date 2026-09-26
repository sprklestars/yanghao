import asyncio
import logging
import uuid
from datetime import datetime, timezone

from celery import Celery
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.proxy import telegram_proxy
from app.core.session_paths import SESSION_DIR
from app.models.models import (
    Account,
    Conversation,
    ConversationState,
    IntelligenceRecord,
    Message,
    MessageDirection,
    Platform,
    Task,
    TaskStatus,
)
from app.services.conversation.engine import ConversationEngine, ConvState
from app.services.intelligence.pipeline import (
    calculate_activity_score,
    classify_category,
    extract_entities,
)
from app.services.platform.base import AccountCredentials, MessageContent, PlatformName
from app.services.platform.telegram_adapter import TelegramAdapter

logger = logging.getLogger(__name__)


class TaskCancelledError(Exception):
    """任务被用户在运行中取消（不再重试）。"""


def _cancel_requested(db, task_id) -> bool:
    """实时读取 DB 里的取消标记（API 在另一个进程里写，本地对象看不到）。"""
    fresh = db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
    return bool(fresh and (fresh.config or {}).get("cancel_requested"))


def _set_progress(db, task, **fields) -> None:
    """把进度写进 task.config["progress"]，任务详情页实时读这里。"""
    config = dict(task.config or {})
    progress = dict(config.get("progress") or {})
    progress.update(fields)
    task.config = {**config, "progress": progress}
    db.commit()


def _get_or_create_account_for_session(db, session_file) -> Account:
    """sessions/ 目录里的账号在 DB 里没有对应行时补登记一条。

    会话记录（conversations.account_id）是外键，没有这一行就没法落库；
    账号列表本来就是扫描 sessions/ 目录得到的，两边应该互相对应。
    """
    name = session_file.stem
    account = db.execute(
        select(Account)
        .where(Account.platform == Platform.TELEGRAM)
        .where(Account.username == name)
        .limit(1)
    ).scalar_one_or_none()
    if account is None:
        account = Account(platform=Platform.TELEGRAM, username=name, credentials={}, is_active=True)
        db.add(account)
        db.commit()
        db.refresh(account)
        logger.info("已在 accounts 表登记会话账号 %s (id=%s)", name, account.id)
    return account


def _telegram_session_candidates(
    account: Account | None, preferred_name: str | None = None
) -> list:
    """挑可用的会话文件：优先账号名对应的那个，否则按文件名顺序全试一遍。

    之所以要"试一遍"，是因为 sessions/ 里可能有没登录成功的空会话文件
    （例如群组页以前用硬编码账号名点过"加入"），按名字排序时它可能排在
    真正的账号前面，直接把任务带进"认证失败"。
    """
    if preferred_name:
        # 建任务时在界面上选的账号优先（task.config["account"]）
        preferred = SESSION_DIR / f"{preferred_name}.session"
        if preferred.exists():
            return [preferred]
        logger.warning("任务指定的账号 %s 不存在，回退到自动挑选", preferred_name)
    if account is not None:
        preferred = SESSION_DIR / f"{account.username}.session"
        if preferred.exists():
            return [preferred]
    return sorted(SESSION_DIR.glob("*.session"))

celery_app = Celery(
    "osint_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Ho_Chi_Minh",
    enable_utc=True,
    task_track_started=True,
    worker_max_tasks_per_child=1000,
)


def _run_task_pipeline(task_id: str):
    """任务体的真正实现。

    单独抽出来是给「没有 Celery worker」的进程内直跑用：`apply()` 在 eager 模式下
    遇到 `self.retry()` 会把整个任务体重跑一遍（最多 4 次），对会加群/私聊的任务来说
    太危险，所以进程内路径直接调这个函数，不做重试。
    """
    logger.info("Starting task %s", task_id)

    db = SessionLocal()
    task = None
    try:
        # 1. Load task config from DB
        result = db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            logger.error("Task %s not found", task_id)
            return

        task.status = TaskStatus.RUNNING
        db.commit()

        try:
            # 2. Select available account
            result = db.execute(
                select(Account)
                .where(Account.platform == task.platform)
                .where(Account.is_active)
                .limit(1)
            )
            account = result.scalar_one_or_none()

            if account is None and task.platform != Platform.TELEGRAM:
                logger.warning("No active account for platform %s", task.platform)
                task.status = TaskStatus.FAILED
                db.commit()
                return

            # 3. Initialize platform adapter (sync version for Celery)
            if task.platform == Platform.TELEGRAM:
                # 账号名对应 sessions/<username>.session 时优先用它；DB 里没账号
                # 或者那个账号不可用时，挨个试 sessions/ 下的其它会话文件。
                session_candidates = _telegram_session_candidates(
                    account, (task.config or {}).get("account")
                )
                if not session_candidates:
                    logger.warning("sessions/ 下没有任何会话文件，任务无法执行")
                    task.status = TaskStatus.FAILED
                    db.commit()
                    return

                summary = {
                    "searched_keywords": 0,
                    "found_groups": 0,
                    "joined_groups": 0,
                    "members_found": 0,
                    "dm_failed": 0,
                    "conversations": 0,
                    "account": account.username if account else None,
                    "error": None,
                }

                async def _campaign() -> None:
                    """整个外呼流程跑在同一个事件循环里。

                    Telethon 明确要求连接期间不能更换事件循环；以前每次调用都
                    `asyncio.new_event_loop()`，于是鉴权之后的 search/join/send
                    全部报 "The asyncio event loop must not change after connection"，
                    任务还照样显示"完成"。
                    """
                    nonlocal account
                    adapter = None
                    used_session = None
                    for candidate_path in session_candidates:
                        candidate = TelegramAdapter(
                            api_id=settings.tg_api_id,
                            api_hash=settings.tg_api_hash,
                            session_name=str(candidate_path),
                            proxy=telegram_proxy(),
                        )
                        if await candidate.authenticate(
                            AccountCredentials(
                                platform=PlatformName.TELEGRAM,
                                username=candidate_path.stem,
                                credentials={},
                            )
                        ):
                            adapter = candidate
                            used_session = candidate_path
                            break
                        # 没登录成功的空会话（例如以前用演示账号名点过"加入"生成的），
                        # 跳过它换下一个，别让它把任务带进"认证失败"
                        await candidate.disconnect()

                    if adapter is None or used_session is None:
                        raise RuntimeError(
                            "sessions/ 里没有可用的已登录账号（可能都是未登录的空会话文件），"
                            "请先在「账号管理」里添加并确认账号可用"
                        )

                    if account is None or account.username != used_session.stem:
                        account = _get_or_create_account_for_session(db, used_session)
                    summary["account"] = account.username
                    logger.info("本次外呼使用账号: %s", used_session.name)
                    _set_progress(db, task, stage="已就绪", account=account.username)
                    try:
                        # 4. Search groups by keywords
                        for keyword in task.keywords[:3]:  # Limit to first 3 keywords
                            if _cancel_requested(db, task.id):
                                raise TaskCancelledError()
                            _set_progress(db, task, stage="搜索群组", keyword=keyword)
                            logger.info("Searching for keyword: %s", keyword)
                            groups = await adapter.search_groups(query=keyword, limit=5)
                            summary["searched_keywords"] += 1

                            for group in groups:
                                if _cancel_requested(db, task.id):
                                    raise TaskCancelledError()
                                summary["found_groups"] += 1
                                logger.info(
                                    "Found group: %s (%s members)", group.name, group.member_count
                                )
                                _set_progress(
                                    db, task, stage="加入群组", keyword=keyword, group=group.name
                                )

                                # 5. Join group
                                joined = await adapter.join_group(group.group_id)
                                if not joined:
                                    continue
                                summary["joined_groups"] += 1
                                logger.info("Successfully joined group %s", group.group_id)

                                # Get group members
                                members = await adapter.get_group_members(group.group_id, limit=20)
                                logger.info(
                                    "Retrieved %d members from group %s",
                                    len(members),
                                    group.group_id,
                                )
                                _set_progress(
                                    db,
                                    task,
                                    stage="采集目标",
                                    group=group.name,
                                    members=len(members),
                                )
                                summary["members_found"] += len(members)

                                # 6. Start conversations with selected members
                                for member in members[:5]:  # Limit to 5 members per group
                                    if _cancel_requested(db, task.id):
                                        raise TaskCancelledError()
                                    # 有用户名就用 @username 私聊（数字 id 需要实体缓存，
                                    # 拉不到成员列表时并不可靠）
                                    target = (
                                        f"@{member.username}"
                                        if member.username
                                        else member.user_id
                                    )
                                    _set_progress(
                                        db,
                                        task,
                                        stage="私聊目标",
                                        group=group.name,
                                        target=member.display_name,
                                    )
                                    conv_id = await _start_conversation(
                                        db=db,
                                        task=task,
                                        account=account,
                                        adapter=adapter,
                                        target_user_id=target,
                                        target_display_name=member.display_name,
                                    )
                                    if conv_id:
                                        summary["conversations"] += 1
                                        logger.info(
                                            "Started conversation %s with %s",
                                            conv_id,
                                            member.display_name,
                                        )
                                    else:
                                        summary["dm_failed"] += 1
                    finally:
                        # 一定要断开：否则 SQLite 会话文件被本进程一直占着，
                        # 之后再跑任务/常驻服务会报 "database is locked"。
                        await adapter.disconnect()

                try:
                    asyncio.run(_campaign())
                except TaskCancelledError:
                    summary["error"] = "用户取消"
                    task.status = TaskStatus.FAILED
                    task.config = {
                        **(task.config or {}),
                        "progress": None,
                        "last_run": {
                            **summary,
                            "finished_at": datetime.now(timezone.utc).isoformat(),
                        },
                    }
                    db.commit()
                    return

                # 把这次跑的结果记进 task.config，前端能看到"跑完到底做了几件事"
                task.config = {
                    **(task.config or {}),
                    "progress": None,
                    "last_run": {
                        **summary,
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                    },
                }
                db.commit()

            else:
                logger.warning("Platform %s not yet implemented", task.platform)
                task.status = TaskStatus.PAUSED
                db.commit()
                return

            task.status = TaskStatus.COMPLETED
            db.commit()

        except Exception as e:
            logger.error("Task %s failed: %s", task_id, e, exc_info=True)
            if task is not None:
                task.status = TaskStatus.FAILED
                db.commit()
            raise
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def run_task(self, task_id: str):
    """Celery 入口：失败时按 Celery 规则重试（进程内直跑请用 _run_task_pipeline）。"""
    try:
        return _run_task_pipeline(task_id)
    except Exception as e:
        raise self.retry(exc=e)


async def _start_conversation(
    db,
    task: Task,
    account: Account,
    adapter: TelegramAdapter,
    target_user_id: str,
    target_display_name: str,
) -> str | None:
    """Start a new conversation with a target user."""
    try:
        # Create conversation record
        conv_id = uuid.uuid4()
        conv = Conversation(
            id=conv_id,
            account_id=account.id,
            task_id=task.id,
            target_user_id=target_user_id,
            target_display_name=target_display_name,
            state=ConversationState.IDLE,
            turn_count=0,
        )
        db.add(conv)
        db.commit()

        # Send initial greeting
        engine = ConversationEngine()
        persona_config = (
            account.persona.persona_config
            if account.persona
            else {
                "name": "User",
                "age": 28,
                "occupation": "freelancer",
                "location": "Ho Chi Minh City",
                "backstory": "Freelance designer looking for opportunities",
                "tone": "casual, friendly",
            }
        )

        # Generate greeting message（和 send_message 共用同一个事件循环）
        greeting, new_state = await engine.generate_response(
            incoming_message="",  # First message, no incoming
            persona_config=persona_config,
            state=ConvState.GREETING,
            category=task.category.value,
            history=[],
        )

        # Send message via adapter
        sent = await adapter.send_message(
            target_id=target_user_id,
            # 主动私聊属于"找陌生人"，走养号模块的陌生人额度
            content=MessageContent(text=greeting, language="vi", metadata={"is_stranger": True}),
        )

        if sent:
            # Save outbound message
            msg_id = uuid.uuid4()
            msg = Message(
                id=msg_id,
                conversation_id=conv_id,
                direction=MessageDirection.OUTBOUND,
                content=greeting,
                language="vi",
            )
            db.add(msg)

            # Update conversation state
            conv.state = new_state
            conv.turn_count = 1
            db.commit()

            return str(conv_id)
        else:
            logger.warning("Failed to send initial message to %s", target_user_id)
            return None

    except Exception as e:
        logger.error("Failed to start conversation: %s", e, exc_info=True)
        return None


@celery_app.task
def process_incoming_message(message_data: dict):
    """Process an incoming message from a platform listener."""
    conversation_id = message_data.get("conversation_id")
    text = message_data.get("text", "")

    logger.info("Processing incoming message for conversation %s", conversation_id)

    db = SessionLocal()
    try:
        # Load conversation
        result = db.execute(select(Conversation).where(Conversation.id == conversation_id))
        conv = result.scalar_one_or_none()
        if not conv:
            logger.error("Conversation %s not found", conversation_id)
            return

        # Save inbound message
        msg_id = uuid.uuid4()
        msg = Message(
            id=msg_id,
            conversation_id=conversation_id,
            direction=MessageDirection.INBOUND,
            content=text,
            language=message_data.get("language"),
        )
        db.add(msg)

        # Get conversation history
        result = db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .limit(20)
        )
        history = [
            {
                "role": "user" if m.direction == MessageDirection.INBOUND else "assistant",
                "content": m.content,
            }
            for m in result.scalars().all()
        ]

        # Load account and persona
        result = db.execute(select(Account).where(Account.id == conv.account_id))
        account = result.scalar_one()
        persona_config = account.persona.persona_config if account.persona else {}

        # Generate response using conversation engine
        engine = ConversationEngine()
        import asyncio

        loop = asyncio.new_event_loop()
        response, new_state = loop.run_until_complete(
            engine.generate_response(
                incoming_message=text,
                persona_config=persona_config,
                state=ConvState(conv.state.value),
                category=conv.task.category.value,
                history=history,
                context_summary=conv.context_summary,
            )
        )

        # Update context summary with this exchange
        updated_summary = loop.run_until_complete(
            engine.update_context_summary(
                existing_summary=conv.context_summary,
                incoming_message=text,
                reply=response,
                state=new_state,
            )
        )
        conv.context_summary = updated_summary
        loop.close()

        # Send response via adapter
        if conv.task.platform == Platform.TELEGRAM:
            adapter = TelegramAdapter(
                api_id=settings.tg_api_id,
                api_hash=settings.tg_api_hash,
                session_name=f"osint_{account.id}",
                proxy=telegram_proxy(),
            )
            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                adapter.authenticate(
                    AccountCredentials(
                        platform=account.platform.value,
                        username=account.username,
                        credentials=account.credentials,
                    )
                )
            )

            sent = loop.run_until_complete(
                adapter.send_message(
                    target_id=conv.target_user_id,
                    content=MessageContent(text=response, language="vi"),
                )
            )
            loop.run_until_complete(adapter.disconnect())
            loop.close()

            if sent:
                # Save outbound message
                reply_msg = Message(
                    id=uuid.uuid4(),
                    conversation_id=conversation_id,
                    direction=MessageDirection.OUTBOUND,
                    content=response,
                    language="vi",
                )
                db.add(reply_msg)

                # Update conversation state
                conv.state = new_state
                conv.turn_count += 1
                if new_state == ConvState.EXIT:
                    conv.ended_at = datetime.now(timezone.utc)

                db.commit()

                # Process intelligence after extraction phase
                if new_state in [ConvState.EXTRACTION, ConvState.EXIT]:
                    _process_intelligence_sync(db, conv, text)

    except Exception as e:
        logger.error("Failed to process incoming message: %s", e, exc_info=True)
    finally:
        db.close()


def _process_intelligence_sync(db, conv: Conversation, text: str):
    """Extract and store intelligence from conversation (sync version)."""
    try:
        # Extract entities
        entities = extract_entities(text)

        # Classify category
        category, confidence, signals = classify_category(text)

        # Calculate activity score
        activity_status = calculate_activity_score(
            last_message_age_hours=0,
            messages_per_day=conv.turn_count,
            response_rate=0.8,  # Placeholder
            has_complete_profile=bool(conv.target_display_name),
        )

        # Build extracted contacts
        extracted_contacts = {
            "phones": entities.phones,
            "emails": entities.emails,
            "zalo_ids": entities.zalo_ids,
            "telegram_handles": entities.telegram_handles,
            "facebook_urls": entities.facebook_urls,
        }

        # Build business info
        business_info = {
            "prices": entities.prices,
            "addresses": entities.addresses,
            "websites": entities.websites,
            "bank_accounts": entities.bank_accounts,
        }

        # Create intelligence record
        intel_id = uuid.uuid4()
        intel = IntelligenceRecord(
            id=intel_id,
            task_id=conv.task_id,
            platform=conv.task.platform,
            target_user_id=conv.target_user_id,
            display_name=conv.target_display_name,
            category=category,
            confidence=confidence,
            signals=signals,
            extracted_contacts=extracted_contacts,
            business_info=business_info,
            activity_status=activity_status,
            last_seen=datetime.now(timezone.utc),
            dedup_fingerprint=_generate_fingerprint(conv.target_user_id, entities),
        )
        db.add(intel)
        db.commit()

        logger.info("Created intelligence record %s (confidence: %.2f)", intel_id, confidence)

    except Exception as e:
        logger.error("Failed to process intelligence: %s", e, exc_info=True)


def _generate_fingerprint(target_user_id: str, entities) -> str:
    """Generate deduplication fingerprint."""
    import hashlib

    # Combine user ID with extracted contact info
    fingerprint_parts = [target_user_id]
    fingerprint_parts.extend(entities.phones)
    fingerprint_parts.extend(entities.emails)
    fingerprint_parts.extend(entities.zalo_ids)

    raw = "|".join(fingerprint_parts)
    return hashlib.sha256(raw.encode()).hexdigest()
