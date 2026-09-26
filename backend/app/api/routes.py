import asyncio
import logging
import os
import signal
import subprocess
import sys
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.processes import pid_alive
from app.core.proxy import telegram_proxy
from app.core.session_paths import (
    SESSION_DIR,
    ensure_session_dir,
    is_valid_session_name,
    remove_session_files,
    session_in_use,
)
from app.models.models import (
    Conversation,
    ConversationState,
    IntelligenceRecord,
    Message,
    MessageDirection,
    Platform,
    Task,
    TaskStatus,
)
from app.schemas.schemas import (
    ConversationResponse,
    IntelligenceListResponse,
    IntelligenceResponse,
    TaskCreate,
    TaskResponse,
)
from app.workers.tasks import _run_task_pipeline, run_task

logger = logging.getLogger(__name__)

router = APIRouter()


def _require_valid_session_name(name: str) -> str:
    """统一校验会话名（它会被拼成 sessions/<name>.session 文件名）。"""
    name = (name or "").strip()
    if not is_valid_session_name(name):
        raise HTTPException(
            status_code=400,
            detail=(
                "Session 名称只能用 1-48 位小写字母、数字、下划线或短横线，且必须以字母/数字开头"
                f"（当前：{name!r}）"
            ),
        )
    return name


def _get_manager():
    from app.main import manager

    return manager


# 来自 .env 的 TG_PROXY_URL；协议/端口写错时这里会拿到错误配置。
TG_PROXY = telegram_proxy()


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
        accounts.append(
            {
                "id": name,
                "platform": "telegram",
                "username": f"@{name}",
                "display_name": meta.get("display_name", ""),
                "health": meta.get("health", "green"),
                "reply_policy": meta.get(
                    "reply_policy",
                    {"private": True, "groups": False, "channels": False, "bots": False},
                ),
                "paused": meta.get("paused", False),
                "persona": meta.get("persona", ""),
                "proxy_url": "http://127.0.0.1:7890",
                "is_active": True,
                "last_action_at": stat.st_mtime,
                "created_at": stat.st_ctime,
                "session_file": str(session_file.name),
            }
        )

    # Facebook cookies
    for cookie_file in sorted(SESSION_DIR.glob("*_cookies.json")):
        name = cookie_file.stem.replace("_cookies", "")
        stat = cookie_file.stat()
        meta = load_meta(name)
        accounts.append(
            {
                "id": name,
                "platform": "facebook",
                "username": name,
                "display_name": meta.get("display_name", ""),
                "health": meta.get("health", "green"),
                "is_active": True,
                "last_action_at": stat.st_mtime,
                "created_at": stat.st_ctime,
                "session_file": str(cookie_file.name),
            }
        )

    # Zalo sessions
    for zalo_file in sorted(SESSION_DIR.glob("*_zalo.json")):
        name = zalo_file.stem.replace("_zalo", "")
        stat = zalo_file.stat()
        meta = load_meta(name)
        accounts.append(
            {
                "id": name,
                "platform": "zalo",
                "username": name,
                "display_name": meta.get("display_name", ""),
                "health": meta.get("health", "green"),
                "is_active": True,
                "last_action_at": stat.st_mtime,
                "created_at": stat.st_ctime,
                "session_file": str(zalo_file.name),
            }
        )

    return accounts


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str):
    """Delete an account by removing its session/cookie file."""
    deleted = []
    locked = []
    for pattern in [
        f"{account_id}.session",
        f"{account_id}_cookies.json",
        f"{account_id}_zalo.json",
    ]:
        fpath = SESSION_DIR / pattern
        if not fpath.exists():
            continue
        try:
            fpath.unlink()
        except OSError as e:
            # Windows 上文件被别的进程占着时删不掉（例如有残留的 Telethon 连接）
            locked.append(f"{pattern}: {e}")
            continue
        deleted.append(pattern)
    if locked:
        raise HTTPException(
            status_code=409,
            detail=(
                "会话文件被其它进程占用，删不掉："
                + "；".join(locked)
                + "。请先停止该账号的常驻服务/等待正在跑的任务结束，必要时重启后端再删。"
            ),
        )
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
            {
                "key": "designer",
                "name": "Nguyen Van A",
                "desc": "自由设计师，28岁，胡志明市",
                "tone": "随和友好",
            },
            {
                "key": "trader",
                "name": "Tran Minh Duc",
                "desc": "加密货币交易员，32岁，河内",
                "tone": "自信专业",
            },
            {
                "key": "student",
                "name": "Le Thi Mai",
                "desc": "大学生，22岁，岘港",
                "tone": "好奇礼貌",
            },
            {
                "key": "business",
                "name": "Pham Hoang Nam",
                "desc": "进出口贸易老板，35岁，胡志明市",
                "tone": "稳重可信",
            },
        ]
    }


@router.post("/accounts/{account_id}/check-session")
async def check_session(account_id: str):
    """Lightweight session/cookie validity check for any platform."""
    import json

    platform = None

    if (SESSION_DIR / f"{account_id}.session").exists():
        platform = "telegram"
    elif (SESSION_DIR / f"{account_id}_cookies.json").exists():
        platform = "facebook"
    elif (SESSION_DIR / f"{account_id}_zalo.json").exists():
        platform = "zalo"
    else:
        return {
            "valid": False,
            "message": "未找到 Session 文件",
            "platform": "unknown",
            "details": {},
        }

    try:
        if platform == "telegram":
            from app.core.config import settings
            from app.services.platform.telegram_adapter import TelegramAdapter

            # 之前这里写的是 settings.TELEGRAM_API_ID（该属性不存在），一调用就 AttributeError；
            # 而且没传代理，在需要代理的网络里检测也会超时。
            adapter = TelegramAdapter(
                settings.tg_api_id,
                settings.tg_api_hash,
                session_name=str(SESSION_DIR / account_id),
                proxy=TG_PROXY,
            )
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
        return {
            "valid": False,
            "message": f"检测异常: {e}",
            "platform": platform,
            "details": {"error": str(e)},
        }


def _warming_snapshot(profile) -> dict:
    """养号档案的可读快照（前端/排障用）。"""
    return {
        "account_id": profile.account_id,
        "stage": profile.account_age.name.lower(),
        "age_days": profile.age_days,
        "is_fully_configured": profile.is_fully_configured,
        "enforce_setup_check": profile.enforce_setup_check,
        "settings": {
            "interface_localized": profile.interface_localized,
            "contacts_sync_disabled": profile.contacts_sync_disabled,
            "two_factor_enabled": profile.two_factor_enabled,
            "auto_delete_enabled": profile.auto_delete_enabled,
            "privacy_settings_complete": profile.privacy_settings_complete,
        },
        "today": {
            "groups_joined": profile.groups_joined_today,
            "messages_sent": profile.messages_sent_today,
            "stranger_messages": profile.stranger_messages_today,
            "friend_requests": profile.friend_requests_today,
        },
        "limits": {
            "groups_per_day": profile.config.max_groups_per_day,
            "messages_per_hour": profile.config.max_messages_per_hour,
            "messages_per_day": profile.config.max_messages_per_day,
            "stranger_messages_per_day": profile.config.max_stranger_messages_per_day,
            "friend_requests_per_day": profile.config.max_friend_requests_per_day,
        },
    }


@router.get("/accounts/{account_id}/warming")
async def get_account_warming(account_id: str):
    """查看账号养号档案（阶段 / 今日用量 / 5 项自检）。"""
    from app.services.security.account_warming import warming_manager

    profile = warming_manager.get_profile(account_id)
    if profile is None:
        raise HTTPException(
            status_code=404, detail="该账号还没有养号档案（账号完成一次认证后会自动创建）"
        )
    return _warming_snapshot(profile)


@router.patch("/accounts/{account_id}/warming")
async def update_account_warming(account_id: str, body: dict):
    """更新 5 项自检开关，或用 enforce_setup_check 关闭"新号必须完成自检"的强制要求。"""
    from app.services.security.account_warming import warming_manager

    profile = warming_manager.get_profile(account_id)
    if profile is None:
        raise HTTPException(
            status_code=404, detail="该账号还没有养号档案（账号完成一次认证后会自动创建）"
        )

    allowed = {
        "interface_localized",
        "contacts_sync_disabled",
        "two_factor_enabled",
        "auto_delete_enabled",
        "privacy_settings_complete",
        "enforce_setup_check",
    }
    updates = {key: bool(value) for key, value in body.items() if key in allowed}
    created_at_raw = body.get("created_at")
    parsed_created_at = None
    if created_at_raw:
        from datetime import datetime as _dt

        try:
            parsed_created_at = _dt.fromisoformat(str(created_at_raw).replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="created_at 需为 ISO 时间，如 2026-08-01")
    if not updates:
        if parsed_created_at is None:
            options = ", ".join(sorted(allowed))
            raise HTTPException(
                status_code=400,
                detail=f"没有可更新的字段（可选：{options}、created_at）",
            )
    warming_manager.update_settings(account_id, **updates, created_at=parsed_created_at)
    updated = warming_manager.get_profile(account_id)
    return _warming_snapshot(updated)


# ── Account Login Flow ─────────────────────────────────

_pending_logins: dict[str, dict] = {}


async def _safe_disconnect(client) -> None:
    try:
        await client.disconnect()
    except Exception:
        pass


def _discard_failed_session(session_name: str, existed_before: bool) -> None:
    """登录没成功时删掉本次新建的空会话文件，别让它出现在账号列表里。"""
    if existed_before:
        return
    removed = remove_session_files(SESSION_DIR / session_name)
    if removed:
        logger.info("已清理未完成的会话文件: %s", ", ".join(p.name for p in removed))


@router.post("/accounts/telegram/test-connection")
async def telegram_test_connection(body: dict):
    """Test Telegram connectivity without sending any code."""
    from telethon import TelegramClient
    from telethon.sessions import MemorySession

    from app.core.config import settings

    session_name = _require_valid_session_name(
        body.get("session_name", "").strip() or "test_connection"
    )

    problem = settings.telegram_credentials_error()
    if problem:
        return {"status": "error", "connected": False, "authorized": False, "message": problem}

    session_path = str(SESSION_DIR / session_name)
    if (SESSION_DIR / f"{session_name}.session").exists():
        # Telethon 在构造时就要写 .session 文件，目录不存在会抛 sqlite3 错误。
        ensure_session_dir(session_path)
        client = TelegramClient(
            session_path, api_id=settings.tg_api_id, api_hash=settings.tg_api_hash, proxy=TG_PROXY
        )
    else:
        # 用内存会话：否则每点一次「测试连接」都会在 sessions/ 留一个空会话文件，
        # 而账号列表是扫描该目录的，会凭空多出一个「账号」。
        client = TelegramClient(
            MemorySession(),
            api_id=settings.tg_api_id,
            api_hash=settings.tg_api_hash,
            proxy=TG_PROXY,
        )

    try:
        await client.connect()
        is_authorized = await client.is_user_authorized()
        me = None
        if is_authorized:
            me = await client.get_me()
        await client.disconnect()
        if me:
            who = getattr(me, "username", "") or getattr(me, "first_name", "") or "Unknown"
            message = f"连接成功，已登录: @{who}"
        else:
            # 这一步只证明网络/代理通了：Telegram 直到发验证码时才校验 api_id/api_hash，
            # 别让用户以为「测试连接通过 = 凭证也没问题」。
            message = (
                "网络与代理连接成功（该会话尚未登录；"
                "api_id/api_hash 要到发验证码时才会被校验）"
            )
        return {
            "status": "ok",
            "connected": True,
            "authorized": is_authorized,
            "username": (getattr(me, "username", None) or None) if me else None,
            "message": message,
        }
    except Exception as e:
        await _safe_disconnect(client)
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

    problem = settings.telegram_credentials_error()
    if problem:
        raise HTTPException(400, problem)

    phone = body.get("phone", "").strip()
    session_name = body.get("session_name", "").strip()
    if not phone or not session_name:
        raise HTTPException(400, "请输入手机号和Session名称")
    session_name = _require_valid_session_name(session_name)

    if not phone.startswith("+"):
        phone = "+" + phone

    session_path = str(SESSION_DIR / session_name)
    session_existed = (SESSION_DIR / f"{session_name}.session").exists()
    ensure_session_dir(session_path)
    client = TelegramClient(
        session_path, api_id=settings.tg_api_id, api_hash=settings.tg_api_hash, proxy=TG_PROXY
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            await client.connect()
            result = await client.send_code_request(phone)
            _pending_logins[session_name] = {
                "client": client,
                "phone": phone,
                "phone_code_hash": result.phone_code_hash,
                "session_existed": session_existed,
            }
            return {"status": "code_sent", "session_name": session_name}
        except FloodWaitError as e:
            await _safe_disconnect(client)
            _discard_failed_session(session_name, session_existed)
            raise HTTPException(429, f"请求过于频繁，请等待 {e.seconds} 秒后再试")
        except PhoneNumberInvalidError:
            await _safe_disconnect(client)
            _discard_failed_session(session_name, session_existed)
            raise HTTPException(400, "手机号格式无效，请使用国际格式如 +84xxxxxxxxx")
        except ConnectionError as e:
            await _safe_disconnect(client)
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
                client = TelegramClient(
                    session_path,
                    api_id=settings.tg_api_id,
                    api_hash=settings.tg_api_hash,
                    proxy=TG_PROXY,
                )
                continue
            _discard_failed_session(session_name, session_existed)
            raise HTTPException(400, f"无法连接到Telegram服务器，请检查网络/代理设置: {e}")
        except Exception as e:
            await _safe_disconnect(client)
            err_str = str(e)
            if "flood" in err_str.lower():
                _discard_failed_session(session_name, session_existed)
                raise HTTPException(429, "请求过于频繁，请稍后再试")
            _discard_failed_session(session_name, session_existed)
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
        username = getattr(me, "username", None) or getattr(me, "first_name", "Unknown")
        await client.disconnect()
        del _pending_logins[session_name]
        return {"status": "success", "username": username, "user_id": me.id}
    except Exception as e:
        error_msg = str(e)
        if (
            "password" in error_msg.lower()
            or "Two-steps" in error_msg
            or "SessionPasswordNeededError" in error_msg
        ):
            return {"status": "need_password", "message": "此账号需要两步验证密码"}
        if (
            "code" in error_msg.lower()
            or "PhoneCodeInvalid" in error_msg
            or "PhoneCodeExpired" in error_msg
        ):
            del _pending_logins[session_name]
            await _safe_disconnect(client)
            _discard_failed_session(session_name, bool(pending.get("session_existed", True)))
            raise HTTPException(400, f"验证码无效或已过期，请重新发送: {error_msg}")
        await _safe_disconnect(client)
        _discard_failed_session(session_name, bool(pending.get("session_existed", True)))
        raise HTTPException(400, f"验证失败: {error_msg}")


_fb_login_processes: dict[str, object] = {}


@router.post("/accounts/facebook/login")
async def facebook_login_start(body: dict):
    """Launch a visible browser window for manual Facebook login."""
    import subprocess

    session_name = _require_valid_session_name(
        body.get("session_name", "fb_default").strip() or "fb_default"
    )

    if session_name in _fb_login_processes:
        proc = _fb_login_processes[session_name]
        if proc.poll() is None:
            return {
                "status": "in_progress",
                "message": "浏览器窗口已打开，请在弹出的窗口中完成登录",
                "session_name": session_name,
            }

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
        logger.info(
            "Facebook login browser launched for session: %s (PID: %d)", session_name, proc.pid
        )
        return {
            "status": "browser_opened",
            "message": (
                "浏览器窗口已弹出，请在窗口中登录 Facebook。登录完成后点击下方「完成登录」按钮。"
            ),
            "session_name": session_name,
        }
    except Exception as e:
        logger.error("Failed to launch FB login browser: %s", e)
        raise HTTPException(400, f"启动浏览器失败: {e}")


@router.post("/accounts/facebook/login-complete")
async def facebook_login_complete(body: dict):
    """Signal that user has finished logging in; save cookies and close browser."""
    session_name = _require_valid_session_name(
        body.get("session_name", "fb_default").strip() or "fb_default"
    )

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
        return {
            "status": "success",
            "message": f"登录成功，已保存 {len(cookies)} 个 cookies",
            "session_name": session_name,
        }
    else:
        return {
            "status": "failed",
            "message": "未找到 cookie 文件，请确认已在浏览器中完成登录",
            "session_name": session_name,
        }


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
    session_name = _require_valid_session_name(session_name)

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


async def _open_telegram_adapter(account: str):
    """构造并鉴权一个 Telegram 适配器。

    账号不存在时直接报错：以前这里会无脑构造 TelegramClient，Telethon 立刻
    建出 `sessions/<account>.session` 空文件，于是账号管理里凭空多出一个
    删不掉的"幽灵账号"。
    """
    from app.core.config import settings
    from app.services.platform.base import AccountCredentials, PlatformName
    from app.services.platform.telegram_adapter import TelegramAdapter

    session_file = SESSION_DIR / f"{account}.session"
    if not session_file.exists():
        raise HTTPException(
            status_code=400,
            detail=(
                f"账号 {account} 不存在（找不到 sessions/{account}.session），"
                "请先在「账号管理」里添加"
            ),
        )
    adapter = TelegramAdapter(
        api_id=settings.tg_api_id,
        api_hash=settings.tg_api_hash,
        session_name=str(session_file),
        proxy=TG_PROXY,
    )
    ok = await adapter.authenticate(
        AccountCredentials(platform=PlatformName.TELEGRAM, username=account, credentials={})
    )
    if not ok:
        await adapter.disconnect()
        raise HTTPException(
            status_code=400,
            detail=f"账号 {account} 认证失败：会话可能失效，或被常驻服务/其它进程占用",
        )
    return adapter


@router.post("/groups/search")
async def search_groups(body: dict):
    """Search Telegram groups by keyword or natural language query."""
    import traceback as tb

    try:
        from app.core.config import settings

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

                client = AsyncOpenAI(
                    api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url
                )
                resp = await client.chat.completions.create(
                    model=settings.deepseek_model,
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                f'User wants to find Telegram groups about: "{query}"\n'
                                "Generate 3-5 short search keywords (in the most likely "
                                "language of the groups) that would find relevant "
                                "Telegram groups. Return ONLY the keywords, one per line."
                            ),
                        }
                    ],
                    temperature=0.3,
                    max_tokens=100,
                )
                ai_keywords = [
                    k.strip()
                    for k in (resp.choices[0].message.content or "").strip().split("\n")
                    if k.strip()
                ]
                logger.info("AI generated search keywords: %s", ai_keywords)
            except Exception as e:
                logger.warning("AI keyword generation failed: %s", e, exc_info=True)
                ai_keywords = []

        # Search with original query + AI keywords
        logger.info("Group search: account=%s, terms=%s", account, [query] + ai_keywords)
        adapter = await _open_telegram_adapter(account)
        all_results = []
        seen_ids = set()

        search_terms = [query] + ai_keywords
        try:
            for term in search_terms[:5]:
                results = await adapter.search_groups(term, limit=10)
                for g in results:
                    if g.group_id not in seen_ids:
                        seen_ids.add(g.group_id)
                        all_results.append(
                            {
                                "group_id": g.group_id,
                                "name": g.name,
                                "member_count": g.member_count,
                                "description": g.description,
                            }
                        )
        finally:
            # 无论成功失败都断开，否则会话文件被这个进程占着，后面全报 database is locked
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
    group_id = body.get("group_id", "").strip()
    account = body.get("account", "printer").strip()

    if not group_id:
        raise HTTPException(400, "group_id is required")

    adapter = await _open_telegram_adapter(account)
    try:
        success = await adapter.join_group(group_id)
        if success:
            return {"status": "joined", "group_id": group_id}
        return {"status": "failed", "message": "Could not join group"}
    except Exception as e:
        raise HTTPException(400, f"Join group failed: {e}")
    finally:
        await adapter.disconnect()


@router.post("/groups/add-by-link")
async def add_group_by_link(body: dict):
    """Join a Telegram group by invite link or username."""
    link = body.get("link", "").strip()
    account = body.get("account", "printer").strip()

    if not link:
        raise HTTPException(400, "link is required")

    adapter = await _open_telegram_adapter(account)
    try:
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
            return {"status": "joined", "group_id": group_id, "name": title}
        except Exception as join_err:
            err_str = str(join_err)
            if "already" in err_str.lower() or "USER_ALREADY_PARTICIPANT" in err_str:
                return {"status": "joined", "group_id": group_id, "name": title, "note": "已是成员"}
            if "successfully requested" in err_str.lower():
                return {
                    "status": "joined",
                    "group_id": group_id,
                    "name": title,
                    "note": "已发送加入申请，等待审批",
                }
            return {"status": "failed", "message": f"加入失败: {err_str}"}
    except Exception as e:
        raise HTTPException(400, f"Add group failed: {e}")
    finally:
        await adapter.disconnect()


# ── Tasks ──────────────────────────────────────────────


def _has_celery_worker(timeout: float = 0.5) -> bool:
    """探测是否有在线的 Celery worker（探测不到就走进程内执行）。"""
    try:
        from app.workers.tasks import celery_app

        return bool(celery_app.control.ping(timeout=timeout))
    except Exception as e:
        logger.warning("Celery worker 探测失败: %s", e)
        return False


async def _ensure_celery_worker() -> bool:
    """没有 worker 就自动拉起一个（和常驻服务用同一套启动逻辑）。"""
    if _has_celery_worker(timeout=1.0):
        return True
    try:
        await start_service("worker")
    except HTTPException as e:
        logger.warning("自动启动 Celery worker 失败: %s", e.detail)
        return False
    # worker 起来后要几秒才会应答 ping
    for _ in range(4):
        if _has_celery_worker(timeout=1.5):
            return True
        await asyncio.sleep(1.0)
    return False


async def _ensure_celery_beat() -> bool:
    """没有 Beat 就自动拉起一个——定时任务需要它每分钟触发扫描。"""
    if _service_running("beat"):
        return True
    try:
        await start_service("beat")
    except HTTPException as e:
        logger.warning("自动启动 Celery Beat 失败: %s", e.detail)
        return False
    return _service_running("beat")


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
    await _get_manager().broadcast(
        {
            "type": "task_created",
            "task_id": str(task.id),
            "name": task.name,
        }
    )

    return task


@router.post("/tasks/{task_id}/start")
async def start_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """Start executing a task.

    优先派发给 Celery worker；本机没起 worker（很常见）时退化为在当前进程里直接跑，
    否则任务只会挂在"运行中"永远不动。
    """
    try:
        task_uuid = uuid.UUID(str(task_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="任务 ID 格式不正确")

    result = await db.execute(select(Task).where(Task.id == task_uuid))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 只有"正在运行"才拦。PENDING 是新建任务的初始状态（界面上叫"等待中"），
    # 之前把它一并当成"已在运行"拒绝，导致新建的任务永远点不动启动。
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="任务已在运行中")

    # 三平台一致：只有 Telegram 的外呼流水线真的实现了，别让 Facebook/Zalo 的任务
    # 点下去静默变成"暂停"（那是以前最难排查的一种"没反应"）
    if task.platform != Platform.TELEGRAM:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{task.platform.value} 的外呼任务流水线尚未接入（当前只有 Telegram 支持），"
                "该任务无法启动"
            ),
        )

    # 常驻服务（persistent_chat_demo.py）和任务流水线用的是同一个 .session 文件，
    # Telegram 同一账号不能同时开两个客户端：抢同一份 SQLite 会 "database is locked"。
    if task.platform.value == "telegram":
        info = SERVICE_MAP["telegram"]
        if _is_running(_read_pid(BACKEND_DIR / info["pid_file"])):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Telegram 常驻服务正在运行，它占用了同一个账号的会话文件。"
                    "请先到「账号管理」页点「停止」，再启动任务。"
                ),
            )
        busy = next(
            (p.stem for p in sorted(SESSION_DIR.glob("*.session")) if session_in_use(p)), None
        )
        if busy:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"账号 {busy} 的会话文件正被另一个进程占用（SQLite 锁）。"
                    "常见原因是之前有过没正常结束的客户端：请关掉多余的后端进程、"
                    "重启当前后端后再启动任务。"
                ),
            )

    # 优先走 Celery；本机没起 worker 时自动拉起一个，仍然不行就在进程内直跑，
    # 这样用户不必自己再开第三个终端（有 worker 才是"正规军"模式）。
    mode = "celery"
    if await _ensure_celery_worker():
        try:
            run_task.delay(task_id=str(task_uuid))
        except Exception as e:
            logger.warning("Celery 派发失败，改为进程内执行: %s", e)
            mode = "inline"
    else:
        logger.warning("Celery worker 不可用，任务 %s 改为进程内执行", task_uuid)
        mode = "inline"

    if mode == "inline":
        # 直接跑任务体（不是 run_task.apply）：eager 模式下 Celery 的 self.retry()
        # 会把整个任务体重跑最多 4 次，对会加群/私聊的任务太危险。
        asyncio.get_running_loop().run_in_executor(None, _run_task_pipeline, str(task_uuid))

    task.status = TaskStatus.RUNNING
    await db.commit()

    # Notify via WebSocket
    await _get_manager().send_to_task(
        str(task_uuid),
        {
            "type": "task_started",
            "task_id": task_id,
        },
    )

    return {"status": "started", "task_id": str(task_uuid), "mode": mode}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """删除任务及其从属会话、消息、情报记录。"""
    try:
        task_uuid = uuid.UUID(str(task_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="任务 ID 格式不正确")

    result = await db.execute(select(Task).where(Task.id == task_uuid))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # 表间外键没有 ondelete cascade，得按依赖顺序手工删干净，否则会报外键冲突。
    conv_ids = (
        (await db.execute(select(Conversation.id).where(Conversation.task_id == task_uuid)))
        .scalars()
        .all()
    )
    if conv_ids:
        await db.execute(delete(Message).where(Message.conversation_id.in_(conv_ids)))
        await db.execute(delete(Conversation).where(Conversation.id.in_(conv_ids)))
    await db.execute(delete(IntelligenceRecord).where(IntelligenceRecord.task_id == task_uuid))
    await db.execute(delete(Task).where(Task.id == task_uuid))
    await db.commit()

    return {"status": "deleted", "task_id": str(task_uuid)}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """取消任务：运行中则立取消标记，流水线会在下个检查点停下。"""
    from datetime import datetime, timezone

    try:
        task_uuid = uuid.UUID(str(task_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="任务 ID 格式不正确")

    task = (await db.execute(select(Task).where(Task.id == task_uuid))).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    running = task.status == TaskStatus.RUNNING
    config = dict(task.config or {})
    config["cancel_requested"] = True
    if not running:
        task.status = TaskStatus.FAILED
        config["progress"] = None
        config["last_run"] = {
            **(config.get("last_run") or {}),
            "error": "用户取消",
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
    task.config = config
    await db.commit()
    return {
        "status": "cancelling" if running else "cancelled",
        "task_id": str(task_uuid),
    }


@router.post("/tasks/{task_id}/pause")
async def pause_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """暂停任务（仅对未运行的任务有效；运行中的任务请用「取消」）。"""
    try:
        task_uuid = uuid.UUID(str(task_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="任务 ID 格式不正确")

    task = (await db.execute(select(Task).where(Task.id == task_uuid))).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(
            status_code=400, detail="运行中的任务不能暂停，请用「取消」停止后再操作"
        )

    task.status = TaskStatus.PAUSED
    await db.commit()
    return {"status": "paused", "task_id": str(task_uuid)}


@router.put("/tasks/{task_id}/schedule")
async def set_task_schedule(task_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    """开启/关闭任务的定时执行。

    body 形如 ``{"enabled": true, "mode": "daily", "at": "09:00"}``
    或 ``{"enabled": true, "mode": "interval", "every_minutes": 360}``；
    ``{"enabled": false}`` 表示关闭。
    """
    from datetime import datetime, timezone

    from app.services.scheduling import compute_next_run, normalize_schedule

    try:
        task_uuid = uuid.UUID(str(task_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="任务 ID 格式不正确")

    task = (await db.execute(select(Task).where(Task.id == task_uuid))).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if not body.get("enabled"):
        config = dict(task.config or {})
        config.pop("schedule", None)
        task.config = config
        await db.commit()
        return {"status": "disabled", "task_id": str(task_uuid)}

    if task.platform != Platform.TELEGRAM:
        raise HTTPException(
            status_code=400,
            detail=f"{task.platform.value} 的外呼流水线尚未接入，无法设置定时执行",
        )

    try:
        schedule = normalize_schedule({**body, "enabled": True})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if schedule is None:  # pragma: no cover - enabled=True 时不会是 None
        raise HTTPException(status_code=400, detail="调度配置无效")

    schedule["next_run_at"] = compute_next_run(schedule, datetime.now(timezone.utc)).isoformat()
    schedule["last_skipped_reason"] = None
    task.config = {**(task.config or {}), "schedule": schedule}
    await db.commit()

    # 定时执行要靠 worker 干活、Beat 触发，两个都确保在跑
    worker_ok = await _ensure_celery_worker()
    beat_ok = await _ensure_celery_beat()
    return {
        "status": "enabled",
        "task_id": str(task_uuid),
        "schedule": schedule,
        "worker_running": worker_ok,
        "beat_running": beat_ok,
    }


@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(db: AsyncSession = Depends(get_db)):
    # 排除 persist_message() 自动建的容器任务（Auto-<平台>）：它们不是用户创建的任务，
    # 只是为了让守护进程收发的消息有地方挂 conversation 而已。
    result = await db.execute(
        select(Task).where(~Task.name.like("Auto-%")).order_by(Task.created_at.desc())
    )
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
    query = select(Conversation).options(
        selectinload(Conversation.messages), selectinload(Conversation.account)
    )
    if task_id:
        query = query.where(Conversation.task_id == task_id)
    query = query.order_by(Conversation.started_at.desc())
    result = await db.execute(query)
    return result.scalars().unique().all()


@router.get("/conversations/{conv_id}", response_model=ConversationResponse)
async def get_conversation(conv_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages), selectinload(Conversation.account))
        .where(Conversation.id == conv_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.post("/conversations/{conv_id}/reply")
async def reply_conversation(conv_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    """人工回复：用会话所属账号给目标发一条消息，并落库（供 live-chat 页使用）。"""
    from app.services.platform.base import MessageContent

    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="回复内容不能为空")
    try:
        conv_uuid = uuid.UUID(str(conv_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="会话 ID 格式不正确")

    conv = (
        await db.execute(
            select(Conversation)
            .options(selectinload(Conversation.account))
            .where(Conversation.id == conv_uuid)
        )
    ).scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    account_name = conv.account_name
    if not account_name:
        raise HTTPException(status_code=400, detail="会话没有关联账号，无法发送")
    session_file = SESSION_DIR / f"{account_name}.session"
    if not session_file.exists():
        raise HTTPException(
            status_code=400, detail=f"账号 {account_name} 的会话文件不存在，请先添加账号"
        )
    if session_in_use(session_file):
        raise HTTPException(
            status_code=409,
            detail=f"账号 {account_name} 正被常驻服务/任务占用，请先停止它们再手动回复",
        )

    adapter = await _open_telegram_adapter(account_name)
    try:
        sent = await adapter.send_message(
            target_id=conv.target_user_id,
            content=MessageContent(text=text, language="vi"),
        )
    finally:
        await adapter.disconnect()

    if not sent:
        raise HTTPException(status_code=400, detail="发送失败（可能被养号限额拦截）")

    db.add(
        Message(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            direction=MessageDirection.OUTBOUND,
            content=text,
        )
    )
    conv.turn_count = (conv.turn_count or 0) + 1
    await db.commit()
    return {"status": "sent", "conversation_id": str(conv.id)}


@router.post("/conversations/{conv_id}/end")
async def end_conversation(conv_id: str, db: AsyncSession = Depends(get_db)):
    """End a conversation and mark the target user as blocked."""
    from datetime import datetime, timezone

    from app.services.security.blocklist import block_user

    result = await db.execute(select(Conversation).where(Conversation.id == conv_id))
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Mark conversation as ended
    # 注意两点：datetime 这里导入的是类而不是模块，取时区要用 timezone；
    # 状态必须用枚举成员，PG 里存的是成员名（EXIT），传小写字符串会报枚举值非法。
    conv.ended_at = datetime.now(timezone.utc)
    conv.state = ConversationState.EXIT

    await db.commit()

    # 真正写入黑名单（跨进程文件存储）：守护进程下次收到该用户消息就不会再回
    blocked = block_user(conv.target_user_id, reason="operator_end_conversation")

    # Notify via WebSocket
    await _get_manager().send_to_task(
        str(conv.task_id),
        {
            "type": "conversation_ended",
            "conversation_id": conv_id,
            "target_user_id": conv.target_user_id,
            "reason": "blocked_by_operator",
        },
    )

    return {
        "status": "ended",
        "conversation_id": conv_id,
        "target_user_id": conv.target_user_id,
        "blocked": blocked,
    }


@router.get("/blocklist")
async def list_blocklist():
    """拉黑列表（守护进程和 API 共用同一个文件，所以这里看到的就是生效中的名单）。"""
    from app.services.security.blocklist import blocklist_manager

    return {"items": blocklist_manager.list_blocked()}


@router.delete("/blocklist/{user_id}")
async def remove_from_blocklist(user_id: str):
    """取消拉黑。"""
    from app.services.security.blocklist import unblock_user

    if not unblock_user(user_id):
        raise HTTPException(status_code=404, detail="该用户不在拉黑列表中")
    return {"status": "unblocked", "user_id": user_id}


# ── Intelligence ──────────────────────────────────────


@router.patch("/intelligence/{intel_id}", response_model=IntelligenceResponse)
async def review_intelligence(intel_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    """审核一条情报：改审核状态（pending/reviewed/approved/rejected）与备注。"""
    from datetime import datetime, timezone

    from app.services.intelligence.review import apply_review, parse_review_status

    try:
        intel_uuid = uuid.UUID(str(intel_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="情报 ID 格式不正确")

    record = (
        await db.execute(select(IntelligenceRecord).where(IntelligenceRecord.id == intel_uuid))
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="Intelligence record not found")

    status = record.review_status
    if "review_status" in body:
        try:
            status = parse_review_status(body["review_status"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # operator_notes 缺省表示不改动；显式传空串表示清空
    notes = body.get("operator_notes") if "operator_notes" in body else None
    apply_review(record, status, notes, datetime.now(timezone.utc))
    await db.commit()
    await db.refresh(record)
    return record


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

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

SERVICE_MAP = {
    "telegram": {
        "script": "persistent_chat_demo.py",
        "pid_file": "chat_demo.pid",
        "log_file": "logs/chat_demo.log",
        "label": "Telegram 常驻在线服务",
    },
    "facebook": {
        "script": "persistent_facebook_demo.py",
        "pid_file": "facebook_demo.pid",
        "log_file": "logs/facebook_demo.log",
        "label": "Facebook 常驻在线服务",
    },
    # 任务队列的消费者。以前要用户自己另开一个终端跑 celery，没跑就成了
    # 「未检测到 Celery worker」——现在和常驻服务一样由 API 管理。
    "worker": {
        "script": "",
        "pid_file": "celery_worker.pid",
        "log_file": "logs/celery_worker.log",
        "label": "任务调度器（Celery Worker）",
        "command": [
            "-m",
            "celery",
            "-A",
            "app.workers.tasks",
            "worker",
            "--loglevel=info",
            "--pool=solo" if os.name == "nt" else "--pool=prefork",
        ],
    },
    # 定时触发器：每分钟扫一次任务表，把到点的任务交给 worker
    "beat": {
        "script": "",
        "pid_file": "celery_beat.pid",
        "log_file": "logs/celery_beat.log",
        "label": "定时触发器（Celery Beat）",
        "command": [
            "-m",
            "celery",
            "-A",
            "app.workers.tasks",
            "beat",
            "--loglevel=info",
            # beat 的状态文件默认落在仓库根目录，指到 logs/ 里去（已 gitignore）
            "--schedule",
            "logs/celerybeat-schedule",
        ],
    },
}

# 常驻服务当前挂的账号（sessions/ 下的会话名），供状态展示和冲突提示用
SERVICE_SESSION_FILE = BACKEND_DIR / "chat_demo.session"


def _read_pid(pid_file: Path) -> int | None:
    if pid_file.exists():
        try:
            return int(pid_file.read_text().strip())
        except (ValueError, OSError):
            return None
    return None


def _is_running(pid: int | None) -> bool:
    # 注意：Windows 上 os.kill(pid, 0) 会 TerminateProcess，等于把服务杀掉，
    # 所以存活检测统一走 app/core/processes.pid_alive（跨平台）。
    return pid_alive(pid)


def _tail_lines(path: Path, count: int) -> list[str]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").strip().split("\n")
    except OSError:
        return []
    return lines[-count:]


def _first_session_name() -> str | None:
    """sessions/ 目录里的第一个会话名（账号列表的 id）。"""
    files = sorted(SESSION_DIR.glob("*.session"))
    return files[0].stem if files else None


async def _first_authorized_session() -> str | None:
    """挑一个**真正登录过**的会话。

    sessions/ 里可能残留没登录成功的空会话文件（例如以前群组页用演示账号名
    点过"加入"），它们的认证必然是失败的，常驻服务挂上去只会一直重连。
    """
    for path in sorted(SESSION_DIR.glob("*.session")):
        adapter = None
        try:
            adapter = await _open_telegram_adapter(path.stem)
            return path.stem
        except HTTPException:
            continue
        finally:
            if adapter is not None:
                await adapter.disconnect()
    return None


def _service_running(platform: str) -> bool:
    info = SERVICE_MAP.get(platform)
    if not info:
        return False
    return _is_running(_read_pid(BACKEND_DIR / info["pid_file"]))


@router.get("/services/status")
async def get_services_status():
    """Return status of all platform services."""
    statuses = []
    for platform, info in SERVICE_MAP.items():
        pid_file = BACKEND_DIR / info["pid_file"]
        pid = _read_pid(pid_file)
        running = _is_running(pid)
        entry = {
            "platform": platform,
            "label": info.get("label", platform),
            "running": running,
            "pid": pid if running else None,
            "script": info["script"] or "celery worker",
        }
        if platform == "telegram":
            entry["session"] = (
                SERVICE_SESSION_FILE.read_text(encoding="utf-8").strip()
                if SERVICE_SESSION_FILE.exists()
                else None
            )
        statuses.append(entry)
    return statuses


@router.post("/services/{platform}/start")
async def start_service(
    platform: str, session: str | None = None, db: AsyncSession = Depends(get_db)
):
    """Start a persistent chat service for the given platform.

    ``session`` 是要挂载的账号（sessions/ 下的会话名）；Telegram 常驻进程一次只跑
    一个账号，不传时用目录里的第一个，避免它默默去用并不存在的旧会话。
    """
    if platform not in SERVICE_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

    info = SERVICE_MAP[platform]
    pid_file = BACKEND_DIR / info["pid_file"]
    script = BACKEND_DIR / info["script"]

    pid = _read_pid(pid_file)
    if _is_running(pid):
        return {"status": "already_running", "pid": pid, "platform": platform}

    command = info.get("command")
    if command is None and not script.exists():
        raise HTTPException(status_code=404, detail=f"Script not found: {script.name}")

    log_file = BACKEND_DIR / info["log_file"]
    log_file.parent.mkdir(exist_ok=True)

    env = os.environ.copy()
    # 子进程的 stdout/stderr 也按 UTF-8 写日志：Windows 默认是 cp936，
    # 中文/emoji 落盘后前端按 UTF-8 读会变成乱码。
    env["PYTHONUTF8"] = "1"
    if platform == "telegram":
        # 任务外呼和常驻服务都要独占账号的 .session 文件，必须互斥
        running_task = (
            await db.execute(
                select(Task)
                .where(Task.platform == Platform.TELEGRAM)
                .where(Task.status == TaskStatus.RUNNING)
                .limit(1)
            )
        ).scalar_one_or_none()
        if running_task is not None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"有 Telegram 任务正在运行（{running_task.name}）。"
                    "任务外呼和常驻在线服务不能同时占用同一个账号，"
                    "请等任务结束或先在任务页删除它。"
                ),
            )
        chosen = session or await _first_authorized_session()
        if not chosen:
            raise HTTPException(
                status_code=400,
                detail=(
                    '没有可用的 Telegram 账号：sessions/ 里没有会话，或现存会话都没登录成功。'
                    '请先点"+ 添加账号"完成一次登录'
                ),
            )
        if not (SESSION_DIR / f"{chosen}.session").exists():
            raise HTTPException(status_code=400, detail=f"会话 {chosen} 不存在，请先完成登录")
        env["TG_SESSION_NAME"] = chosen

    # Windows 没有 setsid；用 DETACHED_PROCESS 让守护进程不随 API 进程退出。
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        )

    with open(log_file, "a", encoding="utf-8") as lf:
        proc = subprocess.Popen(
            [sys.executable, *(command or [str(script), "start"])],
            cwd=str(BACKEND_DIR),
            stdout=lf,
            stderr=lf,
            start_new_session=True,
            creationflags=creationflags,
            env=env,
        )

    if command is not None:
        # celery 自己不写 pid 文件，由我们记录，status/stop 才认得出它
        pid_file.write_text(str(proc.pid), encoding="utf-8")
    if platform == "telegram":
        SERVICE_SESSION_FILE.write_text(env.get("TG_SESSION_NAME", ""), encoding="utf-8")

    await asyncio.sleep(2)

    if proc.poll() is not None:
        # 子进程启动即退出（依赖缺失、凭证/代理没配好等）。以前这里照样回
        # "started"，前端看不出问题，只表现为「按钮没反应」。
        tail = "\n".join(_tail_lines(log_file, 15))
        raise HTTPException(
            status_code=500,
            detail=(
                f"{info.get('label', info['script'])} 启动后立即退出"
                f"（exit code {proc.returncode}）。"
                f"最近日志：\n{tail}"
            ),
        )

    new_pid = _read_pid(pid_file) or proc.pid
    return {
        "status": "started",
        "pid": new_pid,
        "platform": platform,
        "session": env.get("TG_SESSION_NAME"),
    }


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
        if platform == "telegram" and SERVICE_SESSION_FILE.exists():
            SERVICE_SESSION_FILE.unlink()
        return {"status": "not_running", "platform": platform}

    try:
        os.kill(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass

    if pid_file.exists():
        pid_file.unlink()
    if platform == "telegram" and SERVICE_SESSION_FILE.exists():
        SERVICE_SESSION_FILE.unlink()

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
