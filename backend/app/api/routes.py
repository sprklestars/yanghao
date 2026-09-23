import asyncio
import os
import signal
import sys
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
    """Return accounts based on session/cookie files in the sessions/ directory."""
    accounts = []
    if not SESSION_DIR.exists():
        return accounts

    # Telegram sessions
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

    # Facebook cookies
    for cookie_file in sorted(SESSION_DIR.glob("*_cookies.json")):
        name = cookie_file.stem.replace("_cookies", "")
        stat = cookie_file.stat()
        accounts.append({
            "id": name,
            "platform": "facebook",
            "username": name,
            "health": "green",
            "is_active": True,
            "last_action_at": stat.st_mtime,
            "created_at": stat.st_ctime,
            "session_file": str(cookie_file.name),
        })

    # Zalo sessions
    for zalo_file in sorted(SESSION_DIR.glob("*_zalo.json")):
        name = zalo_file.stem.replace("_zalo", "")
        stat = zalo_file.stat()
        accounts.append({
            "id": name,
            "platform": "zalo",
            "username": name,
            "health": "green",
            "is_active": True,
            "last_action_at": stat.st_mtime,
            "created_at": stat.st_ctime,
            "session_file": str(zalo_file.name),
        })

    return accounts


# ── Account Login Flow ─────────────────────────────────

_pending_logins: dict[str, object] = {}


@router.post("/accounts/telegram/send-code")
async def telegram_send_code(body: dict):
    """Send verification code to a phone number for Telegram login."""
    from telethon import TelegramClient
    from app.core.config import settings

    phone = body.get("phone", "").strip()
    session_name = body.get("session_name", "").strip()
    if not phone or not session_name:
        raise HTTPException(400, "phone and session_name are required")

    session_path = str(SESSION_DIR / session_name)
    client = TelegramClient(session_path, api_id=settings.tg_api_id, api_hash=settings.tg_api_hash)

    try:
        await client.connect()
        result = await client.send_code_request(phone)
        _pending_logins[session_name] = {
            "client": client,
            "phone": phone,
            "phone_code_hash": result.phone_code_hash,
        }
        return {"status": "code_sent", "session_name": session_name}
    except Exception as e:
        try:
            await client.disconnect()
        except Exception:
            pass
        raise HTTPException(400, f"Failed to send code: {e}")


@router.post("/accounts/telegram/verify-code")
async def telegram_verify_code(body: dict):
    """Verify the code and complete Telegram login."""
    session_name = body.get("session_name", "").strip()
    code = body.get("code", "").strip()
    password = body.get("password", "").strip() or None

    pending = _pending_logins.get(session_name)
    if not pending:
        raise HTTPException(400, "No pending login for this session. Send code first.")

    client = pending["client"]
    phone = pending["phone"]

    try:
        await client.sign_in(
            phone=phone,
            code=code,
            phone_code_hash=pending["phone_code_hash"],
            password=password,
        )
        me = await client.get_me()
        username = getattr(me, 'username', None) or getattr(me, 'first_name', 'Unknown')
        await client.disconnect()
        del _pending_logins[session_name]
        return {"status": "success", "username": username, "user_id": me.id}
    except Exception as e:
        error_msg = str(e)
        if "password" in error_msg.lower() or "Two-steps" in error_msg:
            return {"status": "need_password", "message": "This account requires a 2FA password"}
        raise HTTPException(400, f"Verification failed: {e}")


@router.post("/accounts/facebook/login")
async def facebook_login_start(body: dict):
    """Start Facebook login by opening a visible browser for manual login."""
    session_name = body.get("session_name", "fb_default").strip()
    return {
        "status": "instructions",
        "message": f"Run: python quick_login_facebook.py {session_name}",
        "session_name": session_name,
    }


@router.post("/accounts/zalo/login")
async def zalo_login(body: dict):
    """Login to Zalo with phone and password."""
    from app.services.platform.base import PlatformName, AccountCredentials
    from app.services.platform.zalo_adapter import ZaloAdapter

    phone = body.get("phone", "").strip()
    password = body.get("password", "").strip()
    session_name = body.get("session_name", "").strip()

    if not phone or not password or not session_name:
        raise HTTPException(400, "phone, password, and session_name are required")

    try:
        adapter = ZaloAdapter()
        credentials = AccountCredentials(
            platform=PlatformName.ZALO,
            username=session_name,
            credentials={"phone": phone, "password": password},
        )
        result = await adapter.authenticate(credentials)
        if result:
            return {"status": "success", "session_name": session_name}
        else:
            return {"status": "failed", "message": "Zalo authentication failed"}
    except Exception as e:
        raise HTTPException(400, f"Zalo login error: {e}")


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


# ── Services ───────────────────────────────────────────

import subprocess

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

SERVICE_MAP = {
    "telegram": {
        "script": "persistent_chat_demo.py",
        "pid_file": "chat_demo.pid",
        "log_file": "logs/chat_demo.log",
    },
    "facebook": {
        "script": "persistent_facebook_demo.py",
        "pid_file": "facebook_demo.pid",
        "log_file": "logs/facebook_demo.log",
    },
}


def _read_pid(pid_file: Path) -> int | None:
    if pid_file.exists():
        try:
            return int(pid_file.read_text().strip())
        except (ValueError, OSError):
            return None
    return None


def _is_running(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


@router.get("/services/status")
async def get_services_status():
    """Return status of all platform services."""
    statuses = []
    for platform, info in SERVICE_MAP.items():
        pid_file = BACKEND_DIR / info["pid_file"]
        pid = _read_pid(pid_file)
        running = _is_running(pid)
        statuses.append({
            "platform": platform,
            "running": running,
            "pid": pid if running else None,
            "script": info["script"],
        })
    return statuses


@router.post("/services/{platform}/start")
async def start_service(platform: str):
    """Start a persistent chat service for the given platform."""
    if platform not in SERVICE_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

    info = SERVICE_MAP[platform]
    pid_file = BACKEND_DIR / info["pid_file"]
    script = BACKEND_DIR / info["script"]

    pid = _read_pid(pid_file)
    if _is_running(pid):
        return {"status": "already_running", "pid": pid, "platform": platform}

    if not script.exists():
        raise HTTPException(status_code=404, detail=f"Script not found: {script.name}")

    log_file = BACKEND_DIR / info["log_file"]
    log_file.parent.mkdir(exist_ok=True)

    with open(log_file, "a") as lf:
        proc = subprocess.Popen(
            [sys.executable, str(script), "start"],
            cwd=str(BACKEND_DIR),
            stdout=lf,
            stderr=lf,
            start_new_session=True,
        )

    await asyncio.sleep(2)

    new_pid = _read_pid(pid_file) or proc.pid
    return {"status": "started", "pid": new_pid, "platform": platform}


@router.post("/services/{platform}/stop")
async def stop_service(platform: str):
    """Stop a persistent chat service for the given platform."""
    if platform not in SERVICE_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

    info = SERVICE_MAP[platform]
    pid_file = BACKEND_DIR / info["pid_file"]
    pid = _read_pid(pid_file)

    if not _is_running(pid):
        if pid_file.exists():
            pid_file.unlink()
        return {"status": "not_running", "platform": platform}

    try:
        os.kill(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass

    if pid_file.exists():
        pid_file.unlink()

    return {"status": "stopped", "pid": pid, "platform": platform}


@router.get("/services/{platform}/logs")
async def get_service_logs(platform: str, lines: int = 50):
    """Return recent log lines for a service."""
    if platform not in SERVICE_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

    log_file = BACKEND_DIR / SERVICE_MAP[platform]["log_file"]
    if not log_file.exists():
        return {"platform": platform, "logs": [], "message": "No log file yet"}

    content = log_file.read_text(encoding="utf-8", errors="replace")
    all_lines = content.strip().split("\n")
    return {"platform": platform, "logs": all_lines[-lines:]}
