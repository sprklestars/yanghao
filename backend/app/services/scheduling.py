"""任务定时调度的纯计算部分（不碰数据库、不依赖 Celery，方便单测）。

支持两种模式：

- ``daily``：每天固定 ``HH:MM``（按本机时区解释），例如 ``09:00``。
- ``interval``：每隔 N 分钟，例如 360（6 小时）。

存进 ``task.config["schedule"]``，附带 ``last_run_at`` / ``next_run_at``（UTC ISO）。
"""

from datetime import datetime, timedelta, timezone

MIN_INTERVAL_MINUTES = 5
MAX_INTERVAL_MINUTES = 7 * 24 * 60
DEFAULT_INTERVAL_MINUTES = 360


def normalize_schedule(raw: dict | None) -> dict | None:
    """校验并归一化调度配置；返回 ``None`` 表示未启用调度。

    非法配置抛 ``ValueError``，由调用方转成 400。
    """
    if not raw or not raw.get("enabled"):
        return None

    mode = str(raw.get("mode") or "daily").lower()

    if mode == "interval":
        try:
            minutes = int(raw.get("every_minutes") or DEFAULT_INTERVAL_MINUTES)
        except (TypeError, ValueError):
            raise ValueError("间隔必须是整数分钟")
        if not MIN_INTERVAL_MINUTES <= minutes <= MAX_INTERVAL_MINUTES:
            raise ValueError(
                f"间隔需在 {MIN_INTERVAL_MINUTES}-{MAX_INTERVAL_MINUTES} 分钟之间"
            )
        return {"enabled": True, "mode": "interval", "every_minutes": minutes}

    if mode == "daily":
        at = str(raw.get("at") or "09:00").strip()
        parts = at.split(":")
        if len(parts) != 2:
            raise ValueError("每天执行时间格式应为 HH:MM")
        try:
            hour, minute = int(parts[0]), int(parts[1])
        except ValueError:
            raise ValueError("每天执行时间格式应为 HH:MM")
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("每天执行时间需在 00:00 - 23:59 之间")
        return {"enabled": True, "mode": "daily", "at": f"{hour:02d}:{minute:02d}"}

    raise ValueError(f"不支持的调度模式: {mode}")


def compute_next_run(schedule: dict, now: datetime, tz=None) -> datetime:
    """算出下一次运行时间（返回 UTC）。

    ``daily`` 的 ``HH:MM`` 按 ``tz``（默认本机时区）解释；已过今天的点则顺延到明天。
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if schedule["mode"] == "interval":
        return now + timedelta(minutes=int(schedule["every_minutes"]))

    local_tz = tz or datetime.now().astimezone().tzinfo
    local_now = now.astimezone(local_tz)
    hour, minute = (int(part) for part in str(schedule["at"]).split(":"))
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
