import logging
import uuid
from datetime import datetime, timezone

from celery import Celery
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
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
from app.services.platform.base import AccountCredentials, MessageContent
from app.services.platform.telegram_adapter import TelegramAdapter

logger = logging.getLogger(__name__)

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


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def run_task(self, task_id: str):
    """Execute an OSINT gathering task. Called by the API when a task is started."""
    logger.info("Starting task %s", task_id)

    db = SessionLocal()
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
            if not account:
                logger.warning("No active account for platform %s", task.platform)
                task.status = TaskStatus.FAILED
                db.commit()
                return

            # 3. Initialize platform adapter (sync version for Celery)
            if task.platform == Platform.TELEGRAM:
                adapter = TelegramAdapter(
                    api_id=settings.tg_api_id,
                    api_hash=settings.tg_api_hash,
                    session_name=f"osint_{account.id}",
                )

                credentials = AccountCredentials(
                    platform=account.platform.value,
                    username=account.username,
                    credentials=account.credentials,
                )

                # Run async authenticate in sync context
                import asyncio

                loop = asyncio.new_event_loop()
                authenticated = loop.run_until_complete(adapter.authenticate(credentials))
                loop.close()

                if not authenticated:
                    logger.error("Failed to authenticate account %s", account.id)
                    task.status = TaskStatus.FAILED
                    db.commit()
                    return

                # 4. Search groups by keywords
                for keyword in task.keywords[:3]:  # Limit to first 3 keywords
                    logger.info("Searching for keyword: %s", keyword)
                    loop = asyncio.new_event_loop()
                    groups = loop.run_until_complete(adapter.search_groups(query=keyword, limit=5))
                    loop.close()

                    for group in groups:
                        logger.info("Found group: %s (%s members)", group.name, group.member_count)

                        # 5. Join group
                        loop = asyncio.new_event_loop()
                        joined = loop.run_until_complete(adapter.join_group(group.group_id))
                        loop.close()

                        if joined:
                            logger.info("Successfully joined group %s", group.group_id)

                            # Get group members
                            loop = asyncio.new_event_loop()
                            members = loop.run_until_complete(
                                adapter.get_group_members(group.group_id, limit=20)
                            )
                            loop.close()

                            logger.info(
                                "Retrieved %d members from group %s", len(members), group.group_id
                            )

                            # 6. Start conversations with selected members
                            for member in members[:5]:  # Limit to 5 members per group
                                conv_id = _start_conversation_sync(
                                    db=db,
                                    task=task,
                                    account=account,
                                    adapter=adapter,
                                    target_user_id=member.user_id,
                                    target_display_name=member.display_name,
                                )
                                if conv_id:
                                    logger.info(
                                        "Started conversation %s with %s",
                                        conv_id,
                                        member.display_name,
                                    )

                loop = asyncio.new_event_loop()
                loop.run_until_complete(adapter.disconnect())
                loop.close()

            else:
                logger.warning("Platform %s not yet implemented", task.platform)
                task.status = TaskStatus.PAUSED
                db.commit()
                return

            task.status = TaskStatus.COMPLETED
            db.commit()

        except Exception as e:
            logger.error("Task %s failed: %s", task_id, e, exc_info=True)
            task.status = TaskStatus.FAILED
            db.commit()
            raise self.retry(exc=e)
    finally:
        db.close()


def _start_conversation_sync(
    db,
    task: Task,
    account: Account,
    adapter: TelegramAdapter,
    target_user_id: str,
    target_display_name: str,
) -> str | None:
    """Start a new conversation with a target user (sync version for Celery)."""
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

        # Generate greeting message
        import asyncio

        loop = asyncio.new_event_loop()
        greeting, new_state = loop.run_until_complete(
            engine.generate_response(
                incoming_message="",  # First message, no incoming
                persona_config=persona_config,
                state=ConvState.GREETING,
                category=task.category.value,
                history=[],
            )
        )
        loop.close()

        # Send message via adapter
        loop = asyncio.new_event_loop()
        sent = loop.run_until_complete(
            adapter.send_message(
                target_id=target_user_id,
                content=MessageContent(text=greeting, language="vi"),
            )
        )
        loop.close()

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
