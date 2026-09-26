"""账号状态（health）的读写：让它反映真实情况，而不是永远"健康"。

2026-09-26 的问题：账号被 Facebook 的安全验证墙挡住，界面上却还是"🟢 健康"。
原因是 health 只有三个写入点——新建时默认 ``green``、手动 PATCH、
以及"检测"按钮里那段只看 cookie 过期时间的判断（Facebook 分支根本没连过 FB）。

现在统一走这里写，语义固定为四档：

* ``green``  正常：登录态有效，可以跑任务
* ``yellow`` 注意：能用但需要留意（cookie 快过期等）
* ``red``    失效：登录态过期/需要重新登录
* ``black``  需人工：被平台拦下（安全验证 checkpoint、封号等），必须人工处理

同时写一个可读原因 ``health_reason`` 和时间戳 ``health_updated_at``，
前端直接显示，用户一眼能看懂为什么不是绿的。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.session_paths import SESSION_DIR

logger = logging.getLogger(__name__)

HEALTH_LEVELS: tuple[str, ...] = ("green", "yellow", "red", "black")


def meta_path(account_name: str) -> Path:
    return SESSION_DIR / f"{account_name}_meta.json"


def read_account_meta(account_name: str) -> dict[str, Any]:
    path = meta_path(account_name)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("账号 meta 读不出来：%s", path, exc_info=True)
        return {}
    return data if isinstance(data, dict) else {}


def write_account_meta(account_name: str, meta: dict[str, Any]) -> None:
    path = meta_path(account_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def set_account_status(
    account_name: str,
    *,
    health: str | None = None,
    reason: str | None = None,
    clear_reason: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """写账号状态。``health`` 只接受四档之一；``clear_reason`` 表示恢复正常。"""
    if health is not None and health not in HEALTH_LEVELS:
        raise ValueError(f"未知的健康档位：{health}")
    if not account_name:
        return {}

    meta = read_account_meta(account_name)
    if health is not None:
        meta["health"] = health
    if clear_reason:
        meta.pop("health_reason", None)
        meta.pop("health_reason_kind", None)
    if reason:
        meta["health_reason"] = reason
    if health is not None or reason or clear_reason:
        meta["health_updated_at"] = datetime.now(timezone.utc).isoformat()
    if extra:
        meta.update(extra)
    write_account_meta(account_name, meta)
    return meta


def record_login_check(
    account_name: str, *, valid: bool | None, reason: str = ""
) -> dict[str, Any]:
    """把一次登录态检测的结果写进状态。

    ``valid=None`` 表示这次没测出来（网络/浏览器问题），不动 health，只记备注。
    """
    if valid is True:
        return set_account_status(
            account_name, health="green", clear_reason=True,
            extra={"last_check_at": datetime.now(timezone.utc).isoformat()},
        )
    if valid is False:
        return set_account_status(
            account_name,
            health="red",
            reason=reason or "登录态失效，需要重新登录",
            extra={"health_reason_kind": "login_invalid",
                   "last_check_at": datetime.now(timezone.utc).isoformat()},
        )
    return set_account_status(
        account_name,
        reason=reason or "本次检测没跑成（网络或浏览器问题）",
        extra={"health_reason_kind": "check_failed",
               "last_check_at": datetime.now(timezone.utc).isoformat()},
    )


def record_platform_block(account_name: str, reason: str) -> dict[str, Any]:
    """被平台拦下（安全验证/封号）：状态打到 black，必须人工处理。"""
    return set_account_status(
        account_name,
        health="black",
        reason=reason,
        extra={"health_reason_kind": "platform_block",
               "last_block_at": datetime.now(timezone.utc).isoformat()},
    )


def record_task_success(account_name: str) -> dict[str, Any]:
    """任务真正跑出结果了：把之前的拦截/失效标记清掉，恢复 green。"""
    return set_account_status(account_name, health="green", clear_reason=True)
