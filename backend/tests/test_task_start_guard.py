"""任务启动拦截（同平台互斥）测试。

回归点：`persist_message()` / `reply_service` 为了挂 conversation 会自动建
"Auto-<平台>" 容器任务，它们的状态永远是 RUNNING 且没人会去结束它。
以前的互斥检查没排除它们，于是 Telegram/Zalo 任务全都点不动，报
"已有 telegram 任务在运行（Auto-telegram）"。
"""

import unittest
import uuid
from datetime import datetime, timedelta, timezone

from app.api import routes
from app.models.models import (
    IntelligenceCategory,
    Platform,
    Task,
    TaskStatus,
)


def _task(
    name: str,
    *,
    platform: Platform = Platform.TELEGRAM,
    status: TaskStatus = TaskStatus.RUNNING,
    updated_minutes_ago: float = 0,
    task_id: uuid.UUID | None = None,
) -> Task:
    task = Task(
        name=name,
        platform=platform,
        category=IntelligenceCategory.PRIVATE_INVESTIGATOR,
        keywords=["x"],
        status=status,
        config={},
    )
    task.id = task_id or uuid.uuid4()
    task.updated_at = datetime.now(timezone.utc) - timedelta(minutes=updated_minutes_ago)
    return task


class AutoContainerTaskTests(unittest.TestCase):
    def test_name_prefix_is_detected(self):
        self.assertTrue(routes.is_auto_container_task(_task("Auto-telegram")))
        facebook_auto = _task("Auto-facebook", platform=Platform.FACEBOOK)
        self.assertTrue(routes.is_auto_container_task(facebook_auto))
        self.assertFalse(routes.is_auto_container_task(_task("tg_test_2")))

    def test_deterministic_id_is_detected(self):
        """即使名字被人改过，只要 id 是那个确定性 UUID 也认出来。"""
        container_id = routes.auto_container_task_id("telegram")
        self.assertEqual(
            container_id, uuid.uuid5(uuid.NAMESPACE_DNS, "task-auto-telegram")
        )
        task = _task("改过名字的任务", task_id=container_id)
        self.assertTrue(routes.is_auto_container_task(task))


class BlockingRunningPeerTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.target_id = uuid.uuid4()

    def _blocking(self, peers):
        return routes.blocking_running_peer(
            peers,
            task_uuid=self.target_id,
            stale_before=self.now - timedelta(minutes=routes.STALE_RUNNING_MINUTES),
        )

    def test_auto_container_does_not_block(self):
        """核心回归：Auto-telegram 不该拦住用户的任务。"""
        auto = _task("Auto-telegram", updated_minutes_ago=600)
        blocking, stale = self._blocking([auto])
        self.assertIsNone(blocking)
        self.assertEqual(stale, [])

    def test_real_running_task_blocks(self):
        peer = _task("tg_test_1", updated_minutes_ago=1)
        blocking, stale = self._blocking([peer])
        self.assertIs(blocking, peer)
        self.assertEqual(stale, [])

    def test_stale_task_is_reported_not_blocking(self):
        dead = _task("tg_old", updated_minutes_ago=routes.STALE_RUNNING_MINUTES + 5)
        blocking, stale = self._blocking([dead])
        self.assertIsNone(blocking)
        self.assertEqual(stale, [dead])

    def test_self_is_ignored(self):
        me = _task("tg_test_2", task_id=self.target_id, updated_minutes_ago=1)
        blocking, stale = self._blocking([me])
        self.assertIsNone(blocking)
        self.assertEqual(stale, [])

    def test_mixed_peers_pick_the_real_blocker(self):
        auto = _task("Auto-telegram", updated_minutes_ago=600)
        dead = _task("tg_old", updated_minutes_ago=120)
        alive = _task("tg_now", updated_minutes_ago=2)
        blocking, stale = self._blocking([auto, dead, alive])
        self.assertIs(blocking, alive)
        self.assertEqual(stale, [dead])


if __name__ == "__main__":
    unittest.main()
