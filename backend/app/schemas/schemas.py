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
    id: str
    name: str
    platform: Platform
    category: IntelligenceCategory
    keywords: list[str]
    target_region: str | None
    status: TaskStatus
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


# ── Conversation Schemas ──────────────────────────────

class MessageResponse(BaseModel):
    id: str
    direction: str
    content: str
    language: str | None
    created_at: str

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: str
    account_id: str
    task_id: str
    target_user_id: str
    target_display_name: str | None
    state: ConversationState
    turn_count: int
    started_at: str
    ended_at: str | None
    messages: list[MessageResponse] = []

    model_config = {"from_attributes": True}


# ── Intelligence Schemas ──────────────────────────────

class IntelligenceResponse(BaseModel):
    id: str
    task_id: str
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
    last_seen: str | None
    response_rate: float | None
    review_status: ReviewStatus
    operator_notes: str | None
    collected_at: str

    model_config = {"from_attributes": True}


class IntelligenceListResponse(BaseModel):
    items: list[IntelligenceResponse]
    total: int
    page: int
    page_size: int
