import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.models import (
    ActivityStatus,
    ConversationState,
    IntelligenceCategory,
    Platform,
    ReviewStatus,
    TaskStatus,
)

# ── Task Schemas ──────────────────────────────────────


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    platform: Platform
    category: IntelligenceCategory
    keywords: list[str] = Field(min_length=1)
    target_region: str | None = None
    config: dict = Field(default_factory=dict)


class TaskResponse(BaseModel):
    id: uuid.UUID
    name: str
    platform: Platform
    category: IntelligenceCategory
    keywords: list[str]
    target_region: str | None
    status: TaskStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Conversation Schemas ──────────────────────────────


class MessageResponse(BaseModel):
    id: uuid.UUID
    direction: str
    content: str
    language: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    task_id: uuid.UUID
    target_user_id: str
    target_display_name: str | None
    state: ConversationState
    turn_count: int
    started_at: datetime
    ended_at: datetime | None
    messages: list[MessageResponse] = []

    model_config = {"from_attributes": True}


# ── Intelligence Schemas ──────────────────────────────


class IntelligenceResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    platform: Platform
    target_user_id: str
    display_name: str | None
    profile_url: str | None
    category: IntelligenceCategory
    confidence: float
    signals: list[str]
    extracted_contacts: dict
    business_info: dict
    activity_status: ActivityStatus
    last_seen: datetime | None
    response_rate: float | None
    review_status: ReviewStatus
    operator_notes: str | None
    collected_at: datetime

    model_config = {"from_attributes": True}


class IntelligenceListResponse(BaseModel):
    items: list[IntelligenceResponse]
    total: int
    page: int
    page_size: int
