import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── Enums ──────────────────────────────────────────────


class Platform(str, enum.Enum):
    TELEGRAM = "telegram"
    FACEBOOK = "facebook"
    ZALO = "zalo"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class AccountHealth(str, enum.Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    BLACK = "black"


class ConversationState(str, enum.Enum):
    IDLE = "idle"
    GREETING = "greeting"
    PROBING = "probing"
    EXTRACTION = "extraction"
    PIVOT = "pivot"
    EXIT = "exit"
    COOLDOWN = "cooldown"


class IntelligenceCategory(str, enum.Enum):
    PRIVATE_INVESTIGATOR = "private_investigator"
    CURRENCY_EXCHANGER = "currency_exchanger"
    FREELANCER = "freelancer"
    DATA_SELLER = "data_seller"


class ActivityStatus(str, enum.Enum):
    ACTIVE = "active"
    DORMANT = "dormant"
    INACTIVE = "inactive"


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"


class MessageDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


# ── Models ─────────────────────────────────────────────


class Persona(Base):
    __tablename__ = "personas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    persona_config: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    platform: Mapped[Platform] = mapped_column(Enum(Platform))
    username: Mapped[str] = mapped_column(String(200))
    credentials: Mapped[dict] = mapped_column(JSON)
    persona_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("personas.id")
    )
    health: Mapped[AccountHealth] = mapped_column(Enum(AccountHealth), default=AccountHealth.GREEN)
    proxy_url: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    persona: Mapped[Persona | None] = relationship(backref="accounts")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="account")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(300))
    platform: Mapped[Platform] = mapped_column(Enum(Platform))
    category: Mapped[IntelligenceCategory] = mapped_column(Enum(IntelligenceCategory))
    keywords: Mapped[list[str]] = mapped_column(JSON)
    target_region: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.PENDING)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="task")
    intelligence_records: Mapped[list["IntelligenceRecord"]] = relationship(back_populates="task")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"))
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tasks.id"))
    target_user_id: Mapped[str] = mapped_column(String(200))
    target_display_name: Mapped[str | None] = mapped_column(String(300))
    state: Mapped[ConversationState] = mapped_column(
        Enum(ConversationState), default=ConversationState.IDLE
    )
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    context_summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    account: Mapped[Account] = relationship(back_populates="conversations")
    task: Mapped[Task] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id")
    )
    direction: Mapped[MessageDirection] = mapped_column(Enum(MessageDirection))
    content: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(10))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class IntelligenceRecord(Base):
    __tablename__ = "intelligence_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tasks.id"))
    platform: Mapped[Platform] = mapped_column(Enum(Platform))
    target_user_id: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str | None] = mapped_column(String(300))
    profile_url: Mapped[str | None] = mapped_column(String(1000))
    avatar_hash: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[IntelligenceCategory] = mapped_column(Enum(IntelligenceCategory))
    confidence: Mapped[float] = mapped_column(Float)
    signals: Mapped[list[str]] = mapped_column(JSON, default=list)
    extracted_contacts: Mapped[dict] = mapped_column(JSON, default=dict)
    business_info: Mapped[dict] = mapped_column(JSON, default=dict)
    activity_status: Mapped[ActivityStatus] = mapped_column(Enum(ActivityStatus))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_rate: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus), default=ReviewStatus.PENDING
    )
    operator_notes: Mapped[str | None] = mapped_column(Text)
    dedup_fingerprint: Mapped[str | None] = mapped_column(String(128), index=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    task: Mapped[Task] = relationship(back_populates="intelligence_records")


class ScriptTemplate(Base):
    __tablename__ = "script_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category: Mapped[IntelligenceCategory] = mapped_column(Enum(IntelligenceCategory))
    stage: Mapped[str] = mapped_column(String(50))
    language: Mapped[str] = mapped_column(String(10))
    templates: Mapped[list[str]] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(200))
    details: Mapped[dict | None] = mapped_column(JSON)
    operator_id: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
