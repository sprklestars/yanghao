import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from celery import Celery
from sqlalchemy import select

from app.core.async_utils import OperationTimeoutError, with_timeout
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.processes import pid_alive
from app.core.proxy import telegram_proxy
from app.core.session_paths import (
    PLATFORM_SESSION_SUFFIX,
    SESSION_DIR,
    platform_session_name,
    platform_session_path,
)
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
from app.services.scheduling import compute_next_run, normalize_schedule, parse_iso
from app.services.security.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
CHAT_SERVICE_PID_FILE = BACKEND_DIR / "chat_demo.pid"


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


def _get_or_create_account_for_session(db, session_file, platform=None, name=None) -> Account:
    """sessions/ 目录里的账号在 DB 里没有对应行时补登记一条。

    会话记录（conversations.account_id）是外键，没有这一行就没法落库；
    账号列表本来就是扫描 sessions/ 目录得到的，两边应该互相对应。
    """
    platform = platform or Platform.TELEGRAM
    name = name or platform_session_name(platform, session_file)
    account = db.execute(
        select(Account)
        .where(Account.platform == platform)
        .where(Account.username == name)
        .limit(1)
    ).scalar_one_or_none()
    if account is None:
        account = Account(platform=platform, username=name, credentials={}, is_active=True)
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


def _platform_session_candidates(task: Task) -> tuple[list[Path], dict[str, str]]:
    """按平台挑候选登录态文件，并**剔除不可参与任务的账号**。

    返回 ``(可用的登录态文件, {被跳过的账号名: 原因})``。

    不可参与 = 账号状态是 🔴 失效 / ⚫ 需人工（被安全验证、封号、登录过期…）：
    这类账号跑任务必然失败，还会白白消耗配额，所以自动跳过并在结果里说明原因。
    """
    from app.core.account_status import task_eligibility

    platform = task.platform
    config = task.config or {}
    requested = config.get("accounts") or ([config["account"]] if config.get("account") else [])
    suffix = PLATFORM_SESSION_SUFFIX[platform.value]

    paths: list[Path] = []
    skipped: dict[str, str] = {}
    for name in requested:
        candidate = platform_session_path(platform, name)
        if not candidate.exists():
            logger.warning("任务指定的账号不存在，跳过：%s", candidate.name)
            skipped[name] = "登录态文件不存在"
            continue
        allowed, reason = task_eligibility(name)
        if not allowed:
            logger.warning("账号 %s 不可用，已跳过：%s", name, reason)
            skipped[name] = reason
            continue
        paths.append(candidate)

    if not requested:
        # 没指定账号时按平台自动挑：同样只挑可用的
        for candidate in sorted(SESSION_DIR.glob(f"*{suffix}")):
            name = platform_session_name(platform, candidate)
            allowed, reason = task_eligibility(name)
            if not allowed:
                logger.warning("账号 %s 不可用，已跳过：%s", name, reason)
                skipped[name] = reason
                continue
            paths.append(candidate)

    return paths, skipped


def _build_adapter(platform: Platform, session_path: Path):
    """为某个平台构造适配器 + 登录凭证（凭证来自 sessions/ 里的登录态文件）。"""
    name = platform_session_name(platform, session_path)

    if platform == Platform.TELEGRAM:
        adapter = TelegramAdapter(
            api_id=settings.tg_api_id,
            api_hash=settings.tg_api_hash,
            session_name=str(session_path),
            proxy=telegram_proxy(),
        )
        credentials = AccountCredentials(
            platform=PlatformName.TELEGRAM, username=name, credentials={}
        )
        return adapter, credentials

    if platform == Platform.FACEBOOK:
        from app.services.platform.facebook_adapter import FacebookAdapter

        adapter = FacebookAdapter(session_name=name)
        credentials = AccountCredentials(
            platform=PlatformName.FACEBOOK,
            username=name,
            # Playwright 的代理地址取自同一份 TG_PROXY_URL 配置
            credentials={"proxy": settings.tg_proxy_url},
        )
        return adapter, credentials

    if platform == Platform.ZALO:
        from app.services.platform.zalo_adapter import ZaloAdapter

        data: dict = {}
        try:
            data = json.loads(session_path.read_text(encoding="utf-8")) or {}
        except (OSError, ValueError) as e:
            logger.warning("读取 Zalo 登录态失败（%s）：%s", session_path.name, e)
        adapter = ZaloAdapter(session_name=name)
        credentials = AccountCredentials(
            platform=PlatformName.ZALO,
            username=name,
            # zlapi 即使复用 cookie 也需要 phone，imei 用来固定设备
            credentials={"phone": data.get("phone"), "imei": data.get("imei")},
        )
        return adapter, credentials

    raise ValueError(f"不支持的平台: {platform}")


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

# Celery Beat 每分钟扫一次数据库里的定时任务（见 scan_task_schedules）
celery_app.conf.beat_schedule = {
    "scan-task-schedules": {
        "task": "app.workers.tasks.scan_task_schedules",
        "schedule": 60.0,
    }
}


# 常驻在线服务的 PID 文件（它和任务抢同一份登录态）
SERVICE_PID_FILES = {
    Platform.TELEGRAM: BACKEND_DIR / "chat_demo.pid",
    Platform.FACEBOOK: BACKEND_DIR / "facebook_demo.pid",
}


def _platform_service_running(platform: Platform) -> bool:
    """该平台的常驻在线服务是否在跑。"""
    pid_file = SERVICE_PID_FILES.get(platform)
    if pid_file is None:
        return False
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    return pid_alive(pid)


async def _run_account_campaign(
    db,
    task: Task,
    account: Account,
    adapter,
    sub: dict,
    platform: Platform | None = None,
) -> None:
    """用单个账号跑一遍「搜群 → 加群 → 取目标 → 私聊」，统计写进 ``sub``。

    不负责 disconnect（由调用方在一个账号结束后统一断开，好释放 .session）。
    Telegram 适配器内部已做平台限流；其它平台在这里统一过一遍，避免重复计数。
    """
    platform = platform or task.platform
    strategy = (task.config or {}).get("strategy") or {}
    search_limit = int(strategy.get("search_limit", 5))
    member_scan = int(strategy.get("member_scan", 20))
    dm_per_group = int(strategy.get("dm_per_group", 5))

    for keyword in task.keywords[:3]:  # Limit to first 3 keywords
        if _cancel_requested(db, task.id):
            raise TaskCancelledError()
        _set_progress(db, task, stage="搜索群组", keyword=keyword, account=account.username)
        logger.info("[%s] Searching for keyword: %s", account.username, keyword)
        groups = await with_timeout(
            adapter.search_groups(query=keyword, limit=search_limit),
            settings.adapter_timeout_seconds,
            f"搜索群组({keyword})",
        )
        sub["searched_keywords"] += 1
        # 被平台安全验证拦下时别含糊成"没搜到群"：把真实原因记下来给前端看
        block_reason = getattr(adapter, "block_reason", None)
        if block_reason:
            sub["block_reason"] = block_reason
            # 同时落到账号状态上：账号卡片会变成"需人工"并显示原因
            try:
                from app.core import account_status

                account_status.record_platform_block(account.username, block_reason)
            except Exception:  # 状态写失败不能影响任务本身
                logger.warning("记录账号拦截状态失败：%s", account.username, exc_info=True)
        elif groups:
            # 这一轮真的搜到东西了：清掉之前的拦截/失效标记
            try:
                from app.core import account_status

                account_status.record_task_success(account.username)
            except Exception:
                logger.warning("恢复账号健康状态失败：%s", account.username, exc_info=True)

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

            if platform != Platform.TELEGRAM:
                allowed, blocked = await rate_limiter.allow(
                    platform.value, ["group_joins_per_day"], account.username
                )
                if not allowed:
                    logger.warning("[%s] 平台限流命中 %s，跳过加群", account.username, blocked)
                    sub["blocked_by_limit"] = sub.get("blocked_by_limit", 0) + 1
                    continue

            joined = await with_timeout(
                adapter.join_group(group.group_id),
                settings.adapter_timeout_seconds,
                f"加入群组({group.name})",
            )
            if not joined:
                continue
            sub["joined_groups"] += 1

            members = await with_timeout(
                adapter.get_group_members(group.group_id, limit=member_scan),
                settings.adapter_timeout_seconds,
                f"获取群成员({group.name})",
            )
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

                if platform != Platform.TELEGRAM:
                    allowed, blocked = await rate_limiter.allow(
                        platform.value,
                        ["messages_per_hour", "messages_per_day"],
                        account.username,
                    )
                    if not allowed:
                        logger.warning(
                            "[%s] 平台限流命中 %s，跳过私聊", account.username, blocked
                        )
                        sub["blocked_by_limit"] = sub.get("blocked_by_limit", 0) + 1
                        continue

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
            # 2. 先看看 DB 里有没有这个平台的账号行（没有也没关系：
            #    下面会按 sessions/ 里的登录态文件自动补登记）
            result = db.execute(
                select(Account)
                .where(Account.platform == task.platform)
                .where(Account.is_active)
                .limit(1)
            )
            account = result.scalar_one_or_none()

            # 3. Initialize platform adapter（三个平台统一走这里）
            # 账号来源优先级：task.config["accounts"]（界面勾选/多选）
            # > ["account"]（单选）> 自动挑第一个登录态文件。
            # 多账号**串行**各跑一轮：一个账号结束并断开后，再轮到下一个。
            session_candidates, skipped_accounts = _platform_session_candidates(task)
            if not session_candidates:
                suffix = PLATFORM_SESSION_SUFFIX[task.platform.value]
                logger.warning(
                    "sessions/ 下没有 %s 的登录态文件（*%s）", task.platform.value, suffix
                )
                if skipped_accounts:
                    # 不是没有账号，而是账号都被判定为不可用：把原因写进任务结果
                    detail = "；".join(
                        f"{name}：{reason}" for name, reason in skipped_accounts.items()
                    )
                    task.config = {
                        **(task.config or {}),
                        "progress": None,
                        "last_run": {
                            "searched_keywords": 0,
                            "found_groups": 0,
                            "joined_groups": 0,
                            "members_found": 0,
                            "dm_failed": 0,
                            "conversations": 0,
                            "blocked_by_limit": 0,
                            "platform": task.platform.value,
                            "account": None,
                            "accounts": {},
                            "skipped_accounts": skipped_accounts,
                            "error": None,
                            "warning": f"没有可用账号：{detail}",
                            "finished_at": datetime.now(timezone.utc).isoformat(),
                        },
                    }
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
                "blocked_by_limit": 0,
                "platform": task.platform.value,
                "account": None,
                "accounts": {},
                "error": None,
            }
            if skipped_accounts:
                summary["skipped_accounts"] = skipped_accounts
                for name, reason in skipped_accounts.items():
                    summary["accounts"][name] = {
                        "account": name,
                        "skipped": True,
                        "skip_reason": reason,
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

                    session_name = platform_session_name(task.platform, candidate_path)
                    try:
                        adapter, credentials = _build_adapter(task.platform, candidate_path)
                    except ValueError as e:
                        logger.error("构造适配器失败：%s", e)
                        continue

                    try:
                        authenticated = await with_timeout(
                            adapter.authenticate(credentials),
                            settings.adapter_timeout_seconds,
                            f"[{task.platform.value}] 账号鉴权({session_name})",
                        )
                    except OperationTimeoutError as e:
                        logger.warning("%s；跳过该账号", e)
                        await adapter.disconnect()
                        continue

                    if not authenticated:
                        logger.warning(
                            "[%s] 账号 %s 未登录/登录态失效，跳过",
                            task.platform.value,
                            session_name,
                        )
                        await adapter.disconnect()
                        continue

                    acct = _get_or_create_account_for_session(
                        db, candidate_path, platform=task.platform, name=session_name
                    )
                    if account is None:
                        account = acct
                    used_names.append(session_name)

                    sub = {
                        "searched_keywords": 0,
                        "found_groups": 0,
                        "joined_groups": 0,
                        "members_found": 0,
                        "dm_failed": 0,
                        "conversations": 0,
                    }
                    _set_progress(db, task, stage="已就绪", account=session_name)
                    logger.info("[%s] 本次外呼使用账号: %s", task.platform.value, session_name)
                    try:
                        await _run_account_campaign(
                            db, task, acct, adapter, sub, platform=task.platform
                        )
                    except OperationTimeoutError as e:
                        # 单个账号卡住只跳过它，别拖垮整条任务（其它账号继续）
                        logger.warning("[%s] %s；跳过该账号剩余动作", session_name, e)
                        sub["timeout"] = str(e)
                    finally:
                        # 一个账号跑完就断开，释放登录态给下一个账号
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
                    summary["accounts"][session_name] = sub
                    summary["account"] = ",".join(used_names)

                if not used_names:
                    raise RuntimeError(
                        "sessions/ 里没有可用的已登录账号（登录态文件可能已失效），"
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

            platform_block_reason = next(
                (
                    sub.get("block_reason")
                    for sub in (summary["accounts"] or {}).values()
                    if isinstance(sub, dict) and sub.get("block_reason")
                ),
                None,
            )

            if any(
                isinstance(sub, dict) and sub.get("timeout")
                for sub in (summary["accounts"] or {}).values()
            ):
                summary["warning"] = "有账号调用超时被跳过（网络/连接不稳定），本轮产出不完整"
            elif platform_block_reason:
                # 被安全验证拦下：这是账号侧的问题，跟关键词无关，必须如实说
                summary["warning"] = platform_block_reason
                summary["blocked_by_platform"] = True
            elif summary["found_groups"] == 0:
                summary["warning"] = "未搜到任何群"
            elif summary["members_found"] == 0:
                summary["warning"] = "未获取到任何可私聊目标"
            elif summary["joined_groups"] == 0:
                # 搜到群却一个都没加进去：多半被养号限额/新号自检/平台限流拦了
                summary["warning"] = "有群但未能加入（可能被养号限额、新号自检或平台限流拦截）"
            else:
                summary["warning"] = None

            # 被跳过的不可用账号必须让人看见，否则用户会以为"我勾了它怎么没跑"
            skipped_map = summary.get("skipped_accounts") or {}
            if skipped_map:
                detail = "；".join(f"{name}：{reason}" for name, reason in skipped_map.items())
                skip_note = f"已跳过 {len(skipped_map)} 个不可用账号（{detail}）"
                summary["warning"] = (
                    f"{summary['warning']}；{skip_note}" if summary.get("warning") else skip_note
                )

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


@celery_app.task
def scan_task_schedules():
    """Celery Beat 每分钟调用：把到点的定时任务派发出去。

    调度配置存在 ``task.config["schedule"]``（见 app/services/scheduling.py）。
    遇到「上一次还在跑」或「常驻在线服务占用账号」就跳过本轮并顺延，不会硬闯。
    """
    db = SessionLocal()
    try:
        tasks = (
            db.execute(select(Task).where(Task.config.op("->>")("schedule").isnot(None)))
            .scalars()
            .all()
        )
        if not tasks:
            return

        now = datetime.now(timezone.utc)
        for task in tasks:
            config = dict(task.config or {})
            raw = config.get("schedule") or {}
            try:
                schedule = normalize_schedule(raw)
            except ValueError as e:
                logger.warning("任务 %s 的定时配置非法，已跳过: %s", task.id, e)
                continue
            if schedule is None:
                continue

            next_run = parse_iso(raw.get("next_run_at"))
            if next_run is None:
                schedule["next_run_at"] = compute_next_run(schedule, now).isoformat()
                task.config = {**config, "schedule": schedule}
                db.commit()
                continue
            if now < next_run:
                continue

            skip_reason = None
            if task.status == TaskStatus.RUNNING:
                skip_reason = "上一次运行还没结束"
            elif _platform_service_running(task.platform):
                skip_reason = f"{task.platform.value} 常驻在线服务正在占用账号"

            if skip_reason:
                schedule["next_run_at"] = compute_next_run(schedule, now).isoformat()
                schedule["last_skipped_reason"] = skip_reason
                task.config = {**config, "schedule": schedule}
                db.commit()
                logger.info("任务 %s 到点但跳过：%s", task.id, skip_reason)
                continue

            schedule["last_run_at"] = now.isoformat()
            schedule["next_run_at"] = compute_next_run(schedule, now).isoformat()
            schedule["last_skipped_reason"] = None
            task.config = {**config, "cancel_requested": False, "schedule": schedule}
            task.status = TaskStatus.RUNNING
            db.commit()
            run_task.delay(task_id=str(task.id))
            logger.info("定时触发任务 %s（%s）", task.id, task.name)
    except Exception as e:
        logger.error("扫描定时任务失败: %s", e, exc_info=True)
    finally:
        db.close()


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
        # 人设来源：DB 关联优先；没有就按 sessions/<账号>_meta.json 里选的 key
        # 去人设注册表取（这样"账号管理里选的人设"才真的会生效）。
        from app.services.conversation.personas import (
            persona_key_for_account,
            resolve_persona_config,
        )

        persona_config = (
            account.persona.persona_config
            if account.persona
            else resolve_persona_config(persona_key_for_account(account.username))
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
        from app.services.conversation.personas import (
            persona_key_for_account,
            resolve_persona_config,
        )

        persona_config = (
            account.persona.persona_config
            if account.persona
            else resolve_persona_config(persona_key_for_account(account.username))
        )

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
