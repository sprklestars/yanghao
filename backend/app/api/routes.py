import asyncio
import logging
import os
import signal
import sys
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.models import Conversation, IntelligenceRecord, Task, TaskStatus
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
TG_PROXY = ("http", "127.0.0.1", 7890)


@router.get("/accounts")
async def list_accounts():
    """Return accounts based on session/cookie files in the sessions/ directory."""
    import json
    accounts = []
    if not SESSION_DIR.exists():
        return accounts

    def load_meta(name: str) -> dict:
        meta_file = SESSION_DIR / f"{name}_meta.json"
        if meta_file.exists():
            try:
                with open(meta_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    # Telegram sessions
    for session_file in sorted(SESSION_DIR.glob("*.session")):
        name = session_file.stem
        stat = session_file.stat()
        meta = load_meta(name)
        accounts.append({
            "id": name,
            "platform": "telegram",
            "username": f"@{name}",
            "display_name": meta.get("display_name", ""),
            "health": meta.get("health", "green"),
            "reply_policy": meta.get("reply_policy", {"private": True, "groups": False, "channels": False, "bots": False}),
            "paused": meta.get("paused", False),
            "persona": meta.get("persona", ""),
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
        meta = load_meta(name)
        accounts.append({
            "id": name,
            "platform": "facebook",
            "username": name,
            "display_name": meta.get("display_name", ""),
            "health": meta.get("health", "green"),
            "is_active": True,
            "last_action_at": stat.st_mtime,
            "created_at": stat.st_ctime,
            "session_file": str(cookie_file.name),
        })

    # Zalo sessions
    for zalo_file in sorted(SESSION_DIR.glob("*_zalo.json")):
        name = zalo_file.stem.replace("_zalo", "")
        stat = zalo_file.stat()
        meta = load_meta(name)
        accounts.append({
            "id": name,
            "platform": "zalo",
            "username": name,
            "display_name": meta.get("display_name", ""),
            "health": meta.get("health", "green"),
            "is_active": True,
            "last_action_at": stat.st_mtime,
            "created_at": stat.st_ctime,
            "session_file": str(zalo_file.name),
        })

    return accounts


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str):
    """Delete an account by removing its session/cookie file."""
    deleted = []
    for pattern in [f"{account_id}.session", f"{account_id}_cookies.json", f"{account_id}_zalo.json"]:
        fpath = SESSION_DIR / pattern
        if fpath.exists():
            fpath.unlink()
            deleted.append(pattern)
    meta_file = SESSION_DIR / f"{account_id}_meta.json"
    if meta_file.exists():
        meta_file.unlink()
    if not deleted:
        raise HTTPException(404, f"Account '{account_id}' not found")
    return {"status": "deleted", "files": deleted}


@router.patch("/accounts/{account_id}")
async def update_account(account_id: str, body: dict):
    """Update account metadata (display_name, health, etc.)."""
    import json
    meta_file = SESSION_DIR / f"{account_id}_meta.json"
    meta = {}
    if meta_file.exists():
        with open(meta_file) as f:
            meta = json.load(f)
    if "display_name" in body:
        meta["display_name"] = body["display_name"]
    if "health" in body:
        meta["health"] = body["health"]
    if "reply_policy" in body:
        meta["reply_policy"] = body["reply_policy"]
    if "paused" in body:
        meta["paused"] = body["paused"]
    if "persona" in body:
        meta["persona"] = body["persona"]
    with open(meta_file, "w") as f:
        json.dump(meta, f)
    return {"status": "updated", "account_id": account_id, "meta": meta}


@router.get("/accounts/personas")
async def list_personas():
    """List available persona presets."""
    return {
        "personas": [
            {"key": "designer", "name": "Nguyen Van A", "desc": "自由设计师，28岁，胡志明市", "tone": "随和友好"},
            {"key": "trader", "name": "Tran Minh Duc", "desc": "加密货币交易员，32岁，河内", "tone": "自信专业"},
            {"key": "student", "name": "Le Thi Mai", "desc": "大学生，22岁，岘港", "tone": "好奇礼貌"},
            {"key": "business", "name": "Pham Hoang Nam", "desc": "进出口贸易老板，35岁，胡志明市", "tone": "稳重可信"},
        ]
    }


@router.post("/accounts/{account_id}/check-session")
async def check_session(account_id: str):
    """Lightweight session/cookie validity check for any platform."""
    import json
    session_file = None
    platform = None

    if (SESSION_DIR / f"{account_id}.session").exists():
        platform = "telegram"
        session_file = str(SESSION_DIR / f"{account_id}.session")
    elif (SESSION_DIR / f"{account_id}_cookies.json").exists():
        platform = "facebook"
        session_file = str(SESSION_DIR / f"{account_id}_cookies.json")
    elif (SESSION_DIR / f"{account_id}_zalo.json").exists():
        platform = "zalo"
        session_file = str(SESSION_DIR / f"{account_id}_zalo.json")
    else:
        return {"valid": False, "message": "未找到 Session 文件", "platform": "unknown", "details": {}}

    try:
        if platform == "telegram":
            from app.core.config import settings
            from app.services.platform.telegram_adapter import TelegramAdapter
            adapter = TelegramAdapter(settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH, session_name=str(SESSION_DIR / account_id))
            result = await adapter.is_session_valid()
        elif platform == "facebook":
            from app.services.platform.facebook_adapter import FacebookAdapter
            adapter = FacebookAdapter(session_name=account_id)
            result = await adapter.is_session_valid()
        elif platform == "zalo":
            from app.services.platform.zalo_adapter import ZaloAdapter
            adapter = ZaloAdapter(session_name=account_id)
            result = await adapter.is_session_valid()
        else:
            result = {"valid": False, "message": "不支持的平台", "details": {}}

        result["platform"] = platform

        # Update meta health based on result
        meta_file = SESSION_DIR / f"{account_id}_meta.json"
        meta = {}
        if meta_file.exists():
            with open(meta_file) as f:
                meta = json.load(f)
        if not result["valid"]:
            meta["health"] = "red"
        elif meta.get("health") == "red":
            meta["health"] = "green"
        with open(meta_file, "w") as f:
            json.dump(meta, f)

        return result
    except Exception as e:
        logger.error("Session check failed for %s: %s", account_id, e)
        return {"valid": False, "message": f"检测异常: {e}", "platform": platform, "details": {"error": str(e)}}


# ── Account Login Flow ─────────────────────────────────

_pending_logins: dict[str, object] = {}


@router.post("/accounts/telegram/test-connection")
async def telegram_test_connection(body: dict):
    """Test Telegram connectivity without sending any code."""
    from telethon import TelegramClient

    from app.core.config import settings

    session_name = body.get("session_name", "").strip() or "test_connection"
    session_path = str(SESSION_DIR / session_name)
    client = TelegramClient(session_path, api_id=settings.tg_api_id, api_hash=settings.tg_api_hash, proxy=TG_PROXY)

    try:
        await client.connect()
        is_authorized = await client.is_user_authorized()
        me = None
        if is_authorized:
            me = await client.get_me()
        await client.disconnect()
        return {
            "status": "ok",
            "connected": True,
            "authorized": is_authorized,
            "username": (getattr(me, 'username', None) or None) if me else None,
            "message": "连接成功" + ("，已登录: @" + (getattr(me, 'username', '') or getattr(me, 'first_name', '') or 'Unknown') if me else ""),
        }
    except Exception as e:
        try:
            await client.disconnect()
        except Exception:
            pass
        return {
            "status": "error",
            "connected": False,
            "authorized": False,
            "message": f"连接失败: {e}",
        }


@router.post("/accounts/telegram/send-code")
async def telegram_send_code(body: dict):
    """Send verification code to a phone number for Telegram login."""
    import asyncio

    from telethon import TelegramClient
    from telethon.errors import FloodWaitError, PhoneNumberInvalidError

    from app.core.config import settings

    phone = body.get("phone", "").strip()
    session_name = body.get("session_name", "").strip()
    if not phone or not session_name:
        raise HTTPException(400, "请输入手机号和Session名称")

    if not phone.startswith("+"):
        phone = "+" + phone

    session_path = str(SESSION_DIR / session_name)
    client = TelegramClient(session_path, api_id=settings.tg_api_id, api_hash=settings.tg_api_hash, proxy=TG_PROXY)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            await client.connect()
            result = await client.send_code_request(phone)
            _pending_logins[session_name] = {
                "client": client,
                "phone": phone,
                "phone_code_hash": result.phone_code_hash,
            }
            return {"status": "code_sent", "session_name": session_name}
        except FloodWaitError as e:
            try:
                await client.disconnect()
            except Exception:
                pass
            raise HTTPException(429, f"请求过于频繁，请等待 {e.seconds} 秒后再试")
        except PhoneNumberInvalidError:
            try:
                await client.disconnect()
            except Exception:
                pass
            raise HTTPException(400, "手机号格式无效，请使用国际格式如 +84xxxxxxxxx")
        except ConnectionError as e:
            try:
                await client.disconnect()
            except Exception:
                pass
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
                client = TelegramClient(session_path, api_id=settings.tg_api_id, api_hash=settings.tg_api_hash, proxy=TG_PROXY)
                continue
            raise HTTPException(400, f"无法连接到Telegram服务器，请检查网络/代理设置: {e}")
        except Exception as e:
            try:
                await client.disconnect()
            except Exception:
                pass
            err_str = str(e)
            if "flood" in err_str.lower():
                raise HTTPException(429, "请求过于频繁，请稍后再试")
            raise HTTPException(400, f"发送验证码失败: {err_str}")


@router.post("/accounts/telegram/verify-code")
async def telegram_verify_code(body: dict):
    """Verify the code and complete Telegram login."""
    session_name = body.get("session_name", "").strip()
    code = body.get("code", "").strip()
    password = body.get("password", "").strip() or None

    pending = _pending_logins.get(session_name)
    if not pending:
        raise HTTPException(400, "没有待验证的登录会话，请先发送验证码")

    client = pending["client"]
    phone = pending["phone"]

    try:
        if password and not code:
            await client.sign_in(phone=phone, password=password)
        else:
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=pending["phone_code_hash"],
                password=password or None,
            )
        me = await client.get_me()
        username = getattr(me, 'username', None) or getattr(me, 'first_name', 'Unknown')
        await client.disconnect()
        del _pending_logins[session_name]
        return {"status": "success", "username": username, "user_id": me.id}
    except Exception as e:
        error_msg = str(e)
        if "password" in error_msg.lower() or "Two-steps" in error_msg or "SessionPasswordNeededError" in error_msg:
            return {"status": "need_password", "message": "此账号需要两步验证密码"}
        if "code" in error_msg.lower() or "PhoneCodeInvalid" in error_msg or "PhoneCodeExpired" in error_msg:
            del _pending_logins[session_name]
            raise HTTPException(400, f"验证码无效或已过期，请重新发送: {error_msg}")
        raise HTTPException(400, f"验证失败: {error_msg}")


_fb_login_processes: dict[str, object] = {}


@router.post("/accounts/facebook/login")
async def facebook_login_start(body: dict):
    """Launch a visible browser window for manual Facebook login."""
    import subprocess
    session_name = body.get("session_name", "fb_default").strip()

    if session_name in _fb_login_processes:
        proc = _fb_login_processes[session_name]
        if proc.poll() is None:
            return {"status": "in_progress", "message": "浏览器窗口已打开，请在弹出的窗口中完成登录", "session_name": session_name}

    script_path = str(Path(__file__).resolve().parent.parent.parent / "quick_login_facebook.py")
    venv_python = str(Path(__file__).resolve().parent.parent.parent / "venv" / "bin" / "python3")

    try:
        proc = subprocess.Popen(
            [venv_python, script_path, session_name],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _fb_login_processes[session_name] = proc
        logger.info("Facebook login browser launched for session: %s (PID: %d)", session_name, proc.pid)
        return {
            "status": "browser_opened",
            "message": "浏览器窗口已弹出，请在窗口中登录 Facebook。登录完成后点击下方「完成登录」按钮。",
            "session_name": session_name,
        }
    except Exception as e:
        logger.error("Failed to launch FB login browser: %s", e)
        raise HTTPException(400, f"启动浏览器失败: {e}")


@router.post("/accounts/facebook/login-complete")
async def facebook_login_complete(body: dict):
    """Signal that user has finished logging in; save cookies and close browser."""
    session_name = body.get("session_name", "fb_default").strip()

    proc = _fb_login_processes.get(session_name)
    if proc and proc.poll() is None:
        # Send Enter to the subprocess so it saves cookies and exits
        try:
            proc.stdin.write(b"\n")
            proc.stdin.flush()
            proc.wait(timeout=15)
        except Exception:
            proc.kill()
        del _fb_login_processes[session_name]

    cookie_file = SESSION_DIR / f"{session_name}_cookies.json"
    if cookie_file.exists():
        import json
        with open(cookie_file) as f:
            cookies = json.load(f)
        return {"status": "success", "message": f"登录成功，已保存 {len(cookies)} 个 cookies", "session_name": session_name}
    else:
        return {"status": "failed", "message": "未找到 cookie 文件，请确认已在浏览器中完成登录", "session_name": session_name}


@router.post("/accounts/zalo/login")
async def zalo_login(body: dict):
    """Login to Zalo with phone and password."""
    from app.services.platform.base import AccountCredentials, PlatformName
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


# ── Group Management ────────────────────────────────────

@router.post("/groups/search")
async def search_groups(body: dict):
    """Search Telegram groups by keyword or natural language query."""
    import traceback as tb
    try:
        from app.core.config import settings
        from app.services.platform.base import AccountCredentials, PlatformName
        from app.services.platform.telegram_adapter import TelegramAdapter

        query = body.get("query", "").strip()
        account = body.get("account", "printer").strip()
        use_ai = body.get("use_ai", False)

        if not query:
            raise HTTPException(400, "query is required")

        # If AI mode, use LLM to generate better search keywords
        ai_keywords = []
        if use_ai:
            try:
                logger.info("AI search: generating keywords for '%s'", query)
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
                resp = await client.chat.completions.create(
                    model=settings.deepseek_model,
                    messages=[{
                        "role": "user",
                        "content": (
                            f"User wants to find Telegram groups about: \"{query}\"\n"
                            "Generate 3-5 short search keywords (in the most likely language of the groups) "
                            "that would find relevant Telegram groups. Return ONLY the keywords, one per line."
                        ),
                    }],
                    temperature=0.3,
                    max_tokens=100,
                )
                ai_keywords = [k.strip() for k in (resp.choices[0].message.content or "").strip().split("\n") if k.strip()]
                logger.info("AI generated search keywords: %s", ai_keywords)
            except Exception as e:
                logger.warning("AI keyword generation failed: %s", e, exc_info=True)
                ai_keywords = []

        # Search with original query + AI keywords
        session_path = str(SESSION_DIR / account)
        logger.info("Group search: session=%s, terms=%s", session_path, [query] + ai_keywords)
        adapter = TelegramAdapter(api_id=settings.tg_api_id, api_hash=settings.tg_api_hash, session_name=session_path, proxy=TG_PROXY)
        creds = AccountCredentials(platform=PlatformName.TELEGRAM, username=account, credentials={})

        auth_ok = await adapter.authenticate(creds)
        logger.info("Group search: auth_ok=%s", auth_ok)
        if not auth_ok or not adapter._client or not adapter._client.is_connected():
            raise HTTPException(400, f"账号 {account} 认证失败，请检查session是否有效")
        all_results = []
        seen_ids = set()

        search_terms = [query] + ai_keywords
        for term in search_terms[:5]:
            results = await adapter.search_groups(term, limit=10)
            for g in results:
                if g.group_id not in seen_ids:
                    seen_ids.add(g.group_id)
                    all_results.append({
                        "group_id": g.group_id,
                        "name": g.name,
                        "member_count": g.member_count,
                        "description": g.description,
                    })

        await adapter.disconnect()
        return {"results": all_results[:20], "keywords_used": search_terms}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("search_groups unhandled error: %s\n%s", e, tb.format_exc())
        raise HTTPException(400, f"Group search failed: {e}")


@router.post("/groups/join")
async def join_group(body: dict):
    """Join a Telegram group by ID."""
    from app.core.config import settings
    from app.services.platform.base import AccountCredentials, PlatformName
    from app.services.platform.telegram_adapter import TelegramAdapter

    group_id = body.get("group_id", "").strip()
    account = body.get("account", "printer").strip()

    if not group_id:
        raise HTTPException(400, "group_id is required")

    session_path = str(SESSION_DIR / account)
    adapter = TelegramAdapter(api_id=settings.tg_api_id, api_hash=settings.tg_api_hash, session_name=session_path, proxy=TG_PROXY)
    creds = AccountCredentials(platform=PlatformName.TELEGRAM, username=account, credentials={})

    try:
        await adapter.authenticate(creds)
        success = await adapter.join_group(group_id)
        await adapter.disconnect()
        if success:
            return {"status": "joined", "group_id": group_id}
        else:
            return {"status": "failed", "message": "Could not join group"}
    except Exception as e:
        raise HTTPException(400, f"Join group failed: {e}")


@router.post("/groups/add-by-link")
async def add_group_by_link(body: dict):
    """Join a Telegram group by invite link or username."""
    from app.core.config import settings
    from app.services.platform.base import AccountCredentials, PlatformName
    from app.services.platform.telegram_adapter import TelegramAdapter

    link = body.get("link", "").strip()
    account = body.get("account", "printer").strip()

    if not link:
        raise HTTPException(400, "link is required")

    session_path = str(SESSION_DIR / account)
    adapter = TelegramAdapter(api_id=settings.tg_api_id, api_hash=settings.tg_api_hash, session_name=session_path, proxy=TG_PROXY)
    creds = AccountCredentials(platform=PlatformName.TELEGRAM, username=account, credentials={})

    try:
        auth_ok = await adapter.authenticate(creds)
        if not auth_ok or not adapter._client or not adapter._client.is_connected():
            raise HTTPException(400, f"账号 {account} 认证失败，请检查session是否有效")
        client = adapter._client

        # Handle t.me links or @username
        if link.startswith("http"):
            entity = await client.get_entity(link)
        elif link.startswith("@"):
            entity = await client.get_entity(link)
        else:
            entity = await client.get_entity(f"@{link}")

        group_id = str(entity.id)
        title = getattr(entity, "title", link)

        from telethon.tl.functions.channels import JoinChannelRequest
        try:
            await client(JoinChannelRequest(entity))
            await adapter.disconnect()
            return {"status": "joined", "group_id": group_id, "name": title}
        except Exception as join_err:
            err_str = str(join_err)
            if "already" in err_str.lower() or "USER_ALREADY_PARTICIPANT" in err_str:
                await adapter.disconnect()
                return {"status": "joined", "group_id": group_id, "name": title, "note": "已是成员"}
            if "successfully requested" in err_str.lower():
                await adapter.disconnect()
                return {"status": "joined", "group_id": group_id, "name": title, "note": "已发送加入申请，等待审批"}
            await adapter.disconnect()
            return {"status": "failed", "message": f"加入失败: {err_str}"}
    except Exception as e:
        raise HTTPException(400, f"Add group failed: {e}")


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
