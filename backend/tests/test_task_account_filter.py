"""任务账号筛选测试：🔴 失效 / ⚫ 需人工 的账号自动不参与任务。

背景：账号被 Facebook 安全验证墙挡住（黑色）或登录态失效（红色）时，
以前任务照样会把它派出去跑 —— 必然失败、还白耗配额，用户也看不出为什么没结果。
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core import account_status, session_paths
from app.models.models import IntelligenceCategory, Platform, Task, TaskStatus
from app.workers import tasks as worker_tasks


def _task(config: dict) -> Task:
    return Task(
        name="t",
        platform=Platform.FACEBOOK,
        category=IntelligenceCategory.PRIVATE_INVESTIGATOR,
        keywords=["camera"],
        status=TaskStatus.PENDING,
        config=config,
    )


class PlatformSessionCandidatesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.session_dir = Path(self._tmp.name)
        self._patches = [
            patch.object(worker_tasks, "SESSION_DIR", self.session_dir),
            patch.object(account_status, "SESSION_DIR", self.session_dir),
            # platform_session_path() 读的是 session_paths 里的 SESSION_DIR
            patch.object(session_paths, "SESSION_DIR", self.session_dir),
        ]
        for item in self._patches:
            item.start()
        # 三个账号：可用的、失效的、需人工的
        for name in ("good", "expired", "blocked"):
            (self.session_dir / f"{name}_cookies.json").write_text("[]", encoding="utf-8")
        self._write_meta("good", {"health": "green"})
        self._write_meta("expired", {"health": "red", "health_reason": "登录态失效，需要重新登录"})
        self._write_meta(
            "blocked",
            {
                "health": "black",
                "health_reason": "Facebook 要求安全验证（checkpoint）：请先完成验证",
            },
        )

    def tearDown(self):
        for item in reversed(self._patches):
            item.stop()
        self._tmp.cleanup()

    def _write_meta(self, name: str, meta: dict) -> None:
        (self.session_dir / f"{name}_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )

    def test_requested_accounts_skip_unusable(self):
        task = _task({"accounts": ["good", "expired", "blocked"]})
        paths, skipped = worker_tasks._platform_session_candidates(task)

        self.assertEqual([p.name for p in paths], ["good_cookies.json"])
        self.assertEqual(set(skipped), {"expired", "blocked"})
        self.assertIn("失效", skipped["expired"])
        self.assertIn("需人工", skipped["blocked"])
        self.assertIn("安全验证", skipped["blocked"])

    def test_auto_pick_also_excludes_unusable(self):
        """没勾账号、按平台自动挑时，同样不能挑到红的/黑的。"""
        task = _task({})
        paths, skipped = worker_tasks._platform_session_candidates(task)

        self.assertEqual([p.name for p in paths], ["good_cookies.json"])
        self.assertEqual(set(skipped), {"expired", "blocked"})

    def test_all_accounts_unusable_yields_empty_list(self):
        task = _task({"accounts": ["expired", "blocked"]})
        paths, skipped = worker_tasks._platform_session_candidates(task)

        self.assertEqual(paths, [])
        self.assertEqual(set(skipped), {"expired", "blocked"})

    def test_missing_session_file_is_reported(self):
        task = _task({"accounts": ["ghost"]})
        paths, skipped = worker_tasks._platform_session_candidates(task)

        self.assertEqual(paths, [])
        self.assertIn("ghost", skipped)
        self.assertIn("不存在", skipped["ghost"])

    def test_yellow_account_still_runs(self):
        """黄色只是提醒（例如 cookie 快过期），不能拦任务。"""
        self._write_meta("good", {"health": "yellow", "health_reason": "cookie 还有 2 天过期"})
        task = _task({"accounts": ["good"]})
        paths, skipped = worker_tasks._platform_session_candidates(task)

        self.assertEqual([p.name for p in paths], ["good_cookies.json"])
        self.assertEqual(skipped, {})

    def test_single_account_config_is_supported(self):
        task = _task({"account": "blocked"})
        paths, skipped = worker_tasks._platform_session_candidates(task)

        self.assertEqual(paths, [])
        self.assertEqual(set(skipped), {"blocked"})


class EligibilityHelperTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._patch = patch.object(account_status, "SESSION_DIR", Path(self._tmp.name))
        self._patch.start()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def _write(self, meta: dict) -> None:
        (self.dir / "acc_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )

    def test_green_and_yellow_are_eligible(self):
        for health in ("green", "yellow"):
            self._write({"health": health})
            allowed, reason = account_status.task_eligibility("acc")
            self.assertTrue(allowed, health)
            self.assertEqual(reason, "")

    def test_red_and_black_are_not_eligible(self):
        self._write({"health": "red", "health_reason": "登录态失效"})
        allowed, reason = account_status.task_eligibility("acc")
        self.assertFalse(allowed)
        self.assertIn("失效", reason)

        self._write({"health": "black", "health_reason": "Facebook 要求安全验证"})
        allowed, reason = account_status.task_eligibility("acc")
        self.assertFalse(allowed)
        self.assertIn("需人工", reason)
        self.assertIn("安全验证", reason)

    def test_account_without_meta_is_eligible(self):
        allowed, _reason = account_status.task_eligibility("never-seen")
        self.assertTrue(allowed)  # 没检测过的账号按可用处理


if __name__ == "__main__":
    unittest.main()
