import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.models import Task, Conversation, Message, IntelligenceRecord, TaskStatus
from app.schemas.schemas import (
    ConversationResponse,
    IntelligenceListResponse,
    IntelligenceResponse,
    TaskCreate,
    TaskResponse,
)
from app.workers.tasks import run_task

router = APIRouter()


def _get_manager():
    from app.main import manager
    return manager


SESSION_DIR = Path(__file__).resolve().parent.parent.parent / "sessions"


@router.get("/accounts")
async def list_accounts():
    """Return accounts based on session files in the sessions/ directory."""
    accounts = []
    if not SESSION_DIR.exists():
        return accounts

    for session_file in sorted(SESSION_DIR.glob("*.session")):
        name = session_file.stem
        stat = session_file.stat()
        accounts.append({
            "id": name,
            "platform": "telegram",
            "username": f"@{name}",
            "health": "green",
            "proxy_url": "http://127.0.0.1:7890",
            "is_active": True,
            "last_action_at": stat.st_mtime,
            "created_at": stat.st_ctime,
            "session_file": str(session_file.name),
        })

    return accounts


# ── Tasks ──────────────────────────────────────────────

@router.post("/tasks", response_model=TaskResponse)
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db)):
    task = Task(
        id=uuid.uuid4(),
        name=body.name,
        platform=body.platform,
        category=body.category,
        keywords=body.keywords,
        target_region=body.target_region,
        config=body.config,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Notify via WebSocket
    await _get_manager().broadcast({
        "type": "task_created",
        "task_id": str(task.id),
        "name": task.name,
    })

    return task


@router.post("/tasks/{task_id}/start")
async def start_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """Start executing a task by dispatching to Celery worker."""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status in [TaskStatus.RUNNING, TaskStatus.PENDING]:
        raise HTTPException(status_code=400, detail="Task already running or pending")

    # Dispatch to Celery
    run_task.delay(task_id=str(task_id))

    task.status = TaskStatus.RUNNING
    await db.commit()

    # Notify via WebSocket
    await _get_manager().send_to_task(task_id, {
        "type": "task_started",
        "task_id": task_id,
    })

    return {"status": "started", "task_id": task_id}


@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).order_by(Task.created_at.desc()))
    return result.scalars().all()


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


# ── Conversations ──────────────────────────────────────

@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    task_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Conversation).options(selectinload(Conversation.messages))
    if task_id:
        query = query.where(Conversation.task_id == task_id)
    query = query.order_by(Conversation.started_at.desc())
    result = await db.execute(query)
    return result.scalars().unique().all()


@router.get("/conversations/{conv_id}", response_model=ConversationResponse)
async def get_conversation(conv_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conv_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.post("/conversations/{conv_id}/end")
async def end_conversation(conv_id: str, db: AsyncSession = Depends(get_db)):
    """End a conversation and mark the target user as blocked."""
    from datetime import datetime
    
    result = await db.execute(
        select(Conversation).where(Conversation.id == conv_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Mark conversation as ended
    conv.ended_at = datetime.now(datetime.timezone.utc)
    conv.state = "exit"  # Changed to exit state
    
    await db.commit()
    
    # Notify via WebSocket
    await _get_manager().send_to_task(str(conv.task_id), {
        "type": "conversation_ended",
        "conversation_id": conv_id,
        "target_user_id": conv.target_user_id,
        "reason": "blocked_by_operator",
    })
    
    return {"status": "ended", "conversation_id": conv_id}


# ── Intelligence ──────────────────────────────────────

@router.get("/intelligence", response_model=IntelligenceListResponse)
async def list_intelligence(
    task_id: str | None = None,
    category: str | None = None,
    platform: str | None = None,
    review_status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    query = select(IntelligenceRecord)
    count_query = select(func.count()).select_from(IntelligenceRecord)

    if task_id:
        query = query.where(IntelligenceRecord.task_id == task_id)
        count_query = count_query.where(IntelligenceRecord.task_id == task_id)
    if category:
        query = query.where(IntelligenceRecord.category == category)
        count_query = count_query.where(IntelligenceRecord.category == category)
    if platform:
        query = query.where(IntelligenceRecord.platform == platform)
        count_query = count_query.where(IntelligenceRecord.platform == platform)
    if review_status:
        query = query.where(IntelligenceRecord.review_status == review_status)
        count_query = count_query.where(IntelligenceRecord.review_status == review_status)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(IntelligenceRecord.collected_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return IntelligenceListResponse(
        items=[IntelligenceResponse.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )
