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
    make_dedup_fingerprint,
    merge_intelligence,
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


def _requested_account_sessions(task: Task) -> list | None:
    """任务显式指定的账号（多选 accounts，兼容单选 account）；没指定返回 None。"""
    config = task.config or {}
    requested = config.get("accounts") or ([config["account"]] if config.get("account") else [])
    if not requested:
        return None
    sessions = []
    for name in requested:
        path = SESSION_DIR / f"{name}.session"
        if path.exists():
            sessions.append(path)
        else:
            logger.warning("任务指定的账号 %s 不存在（sessions/%s.session），跳过", name, name)
    return sessions or None

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


async def _run_account_campaign(
    db, task: Task, account: Account, adapter: TelegramAdapter, sub: dict
) -> None:
    """用单个账号跑一遍「搜群 → 加群 → 取目标 → 私聊」，统计写进 ``sub``。

    不负责 disconnect（由调用方在一个账号结束后统一断开，好释放 .session）。
    """
    strategy = (task.config or {}).get("strategy") or {}
    search_limit = int(strategy.get("search_limit", 5))
    member_scan = int(strategy.get("member_scan", 20))
    dm_per_group = int(strategy.get("dm_per_group", 5))

    for keyword in task.keywords[:3]:  # Limit to first 3 keywords
        if _cancel_requested(db, task.id):
            raise TaskCancelledError()
        _set_progress(db, task, stage="搜索群组", keyword=keyword, account=account.username)
        logger.info("[%s] Searching for keyword: %s", account.username, keyword)
        groups = await adapter.search_groups(query=keyword, limit=search_limit)
        sub["searched_keywords"] += 1

        for group in groups:
            if _cancel_requested(db, task.id):
                raise TaskCancelledError()
            sub["found_groups"] += 1
            _set_progress(
                db,
                task,
                stage="加入群组",
                keyword=keyword,
                group=group.name,
                account=account.username,
            )

            joined = await adapter.join_group(group.group_id)
            if not joined:
                continue
            sub["joined_groups"] += 1

            members = await adapter.get_group_members(group.group_id, limit=member_scan)
            _set_progress(
                db,
                task,
                stage="采集目标",
                group=group.name,
                members=len(members),
                account=account.username,
            )
            sub["members_found"] += len(members)

            for member in members[:dm_per_group]:
                if _cancel_requested(db, task.id):
                    raise TaskCancelledError()
                target = f"@{member.username}" if member.username else member.user_id
                _set_progress(
                    db,
                    task,
                    stage="私聊目标",
                    group=group.name,
                    target=member.display_name,
                    account=account.username,
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
                    sub["conversations"] += 1
                else:
                    sub["dm_failed"] += 1


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
                # 账号来源优先级：task.config["accounts"]（多选）> ["account"]（单选）
                # > 自动挑一个真正登录过的。多账号会**串行**各跑一轮（Telegram 一账号一客户端）。
                session_candidates = _requested_account_sessions(task)
                if session_candidates is None:
                    session_candidates = _telegram_session_candidates(account, None)
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
                    "account": None,
                    "accounts": {},
                    "error": None,
                }

                async def _campaign() -> None:
                    """整个外呼流程跑在同一个事件循环里。

                    Telethon 明确要求连接期间不能更换事件循环；以前每次调用都
                    `asyncio.new_event_loop()`，导致鉴权之后的 search/join/send 全部报错。
                    多账号在这里**串行**跑：一个账号结束并断开后，再轮到下一个。
                    """
                    nonlocal account
                    used_names = []
                    for candidate_path in session_candidates:
                        if _cancel_requested(db, task.id):
                            raise TaskCancelledError()

                        adapter = TelegramAdapter(
                            api_id=settings.tg_api_id,
                            api_hash=settings.tg_api_hash,
                            session_name=str(candidate_path),
                            proxy=telegram_proxy(),
                        )
                        if not await adapter.authenticate(
                            AccountCredentials(
                                platform=PlatformName.TELEGRAM,
                                username=candidate_path.stem,
                                credentials={},
                            )
                        ):
                            logger.warning("账号 %s 未登录，跳过", candidate_path.stem)
                            await adapter.disconnect()
                            continue

                        acct = _get_or_create_account_for_session(db, candidate_path)
                        if account is None:
                            account = acct
                        used_names.append(candidate_path.stem)

                        sub = {
                            "searched_keywords": 0,
                            "found_groups": 0,
                            "joined_groups": 0,
                            "members_found": 0,
                            "dm_failed": 0,
                            "conversations": 0,
                        }
                        _set_progress(db, task, stage="已就绪", account=candidate_path.stem)
                        logger.info("本次外呼使用账号: %s", candidate_path.name)
                        try:
                            await _run_account_campaign(db, task, acct, adapter, sub)
                        finally:
                            # 一个账号跑完就断开，释放 .session 给下一个账号
                            await adapter.disconnect()

                        for key in (
                            "searched_keywords",
                            "found_groups",
                            "joined_groups",
                            "members_found",
                            "dm_failed",
                            "conversations",
                        ):
                            summary[key] += sub[key]
                        summary["accounts"][candidate_path.stem] = sub
                        summary["account"] = ",".join(used_names)

                    if not used_names:
                        raise RuntimeError(
                            "sessions/ 里没有可用的已登录账号（可能都是未登录的空会话文件），"
                            "请先在「账号管理」里添加并确认账号可用"
                        )

                try:
                    asyncio.run(_campaign())
                except TaskCancelledError:
                    summary["error"] = "用户取消"
                    summary["warning"] = None
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

                if summary["found_groups"] == 0:
                    summary["warning"] = "未搜到任何群"
                elif summary["members_found"] == 0:
                    summary["warning"] = "未获取到任何可私聊目标"
                else:
                    summary["warning"] = None

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

        platform_value = conv.task.platform.value
        fingerprint = make_dedup_fingerprint(platform_value, conv.target_user_id, entities)
        existing = db.execute(
            select(IntelligenceRecord).where(IntelligenceRecord.dedup_fingerprint == fingerprint)
        ).scalar_one_or_none()

        incoming = IntelligenceRecord(
            id=uuid.uuid4(),
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
            dedup_fingerprint=fingerprint,
            platforms=[platform_value],
        )

        if existing is not None:
            merge_intelligence(existing, incoming)
            logger.info("合并情报记录 %s", existing.id)
        else:
            db.add(incoming)
            logger.info(
                "Created intelligence record %s (confidence: %.2f)", incoming.id, confidence
            )
        db.commit()

    except Exception as e:
        logger.error("Failed to process intelligence: %s", e, exc_info=True)
