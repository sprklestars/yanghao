"""用户拉黑列表管理。

守护进程（收消息时判断要不要回）和 API（前端点"拉黑"）是**两个进程**，
所以黑名单必须落到共享存储上，否则 API 写进内存、守护进程根本看不到
（这正是以前"点了拉黑还在自动回复"的原因）。

这里用 JSON 文件 + 按 (mtime, size) 自动重载：零依赖、离线可用，
任何进程改完，另一个进程下一次判断时就能读到。
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[3]
DEFAULT_PATH = BACKEND_DIR / "state" / "blocklist.json"


class BlockListManager:
    """拉黑列表管理器（文件持久化 + 跨进程可见）。"""

    def __init__(self, path: Path | str | None = None):
        self._path = Path(path) if path else DEFAULT_PATH
        self._lock = threading.Lock()
        self._stamp: tuple[int, int] | None = None
        self._blocked: dict[str, dict] = {}
        self._reload(force=True)

    # ── 文件读写 ──
    def _reload(self, force: bool = False) -> None:
        try:
            stat = self._path.stat()
        except OSError:
            if force or self._blocked:
                self._blocked = {}
                self._stamp = None
            return

        stamp = (stat.st_mtime_ns, stat.st_size)
        if not force and stamp == self._stamp:
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8") or "{}")
        except (OSError, ValueError) as e:
            logger.warning("读取黑名单失败（沿用内存副本）: %s", e)
            return
        self._blocked = (
            {str(key): dict(value or {}) for key, value in raw.items()}
            if isinstance(raw, dict)
            else {}
        )
        self._stamp = stamp

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(
            json.dumps(self._blocked, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, self._path)  # 原子替换，避免读到半截文件
        try:
            stat = self._path.stat()
            self._stamp = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            self._stamp = None

    # ── 对外接口 ──
    def block_user(self, user_id: str, reason: str = "") -> bool:
        """拉黑用户；已在名单里返回 False。"""
        with self._lock:
            self._reload()
            if user_id in self._blocked:
                return False
            self._blocked[user_id] = {
                "reason": reason,
                "blocked_at": datetime.now(timezone.utc).isoformat(),
            }
            self._save()
            logger.info("已拉黑用户 %s（%s）", user_id, reason or "未填原因")
            return True

    def unblock_user(self, user_id: str) -> bool:
        """取消拉黑；不在名单里返回 False。"""
        with self._lock:
            self._reload()
            if user_id not in self._blocked:
                return False
            self._blocked.pop(user_id, None)
            self._save()
            logger.info("已取消拉黑用户 %s", user_id)
            return True

    def is_blocked(self, user_id: str) -> bool:
        with self._lock:
            self._reload()
            return user_id in self._blocked

    def list_blocked(self) -> list[dict]:
        """返回 ``[{user_id, reason, blocked_at}, ...]``（按 user_id 排序）。"""
        with self._lock:
            self._reload()
            return [{"user_id": uid, **info} for uid, info in sorted(self._blocked.items())]

    def get_all_blocked(self) -> set[str]:
        with self._lock:
            self._reload()
            return set(self._blocked)

    def clear(self) -> None:
        with self._lock:
            self._blocked = {}
            self._save()
            logger.info("已清空拉黑列表")


# 全局单例
blocklist_manager = BlockListManager()


def block_user(user_id: str, reason: str = "") -> bool:
    """便捷函数：拉黑用户。"""
    return blocklist_manager.block_user(user_id, reason=reason)


def unblock_user(user_id: str) -> bool:
    """便捷函数：取消拉黑。"""
    return blocklist_manager.unblock_user(user_id)


def is_blocked(user_id: str) -> bool:
    """便捷函数：检查是否拉黑。"""
    return blocklist_manager.is_blocked(user_id)
