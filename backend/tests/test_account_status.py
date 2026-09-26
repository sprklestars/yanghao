"""账号状态（health）测试。

回归点：账号被 Facebook 安全验证墙挡住时界面仍显示"🟢 健康"。
原因是 health 只有"默认 green + 手动改 + 只看 cookie 过期时间的检测"三个写入点，
而且 detector 对 Facebook 根本不去问 FB 一次。
"""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.api import routes
from app.core import account_status
from app.services.platform import facebook_adapter


class AccountStatusWriterTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._patch = patch.object(account_status, "SESSION_DIR", Path(self._tmp.name))
        self._patch.start()
        self.meta = Path(self._tmp.name) / "acc_meta.json"

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_platform_block_marks_black_with_reason(self):
        account_status.record_platform_block("acc", "Facebook 要求安全验证（checkpoint）")
        meta = json.loads(self.meta.read_text(encoding="utf-8"))
        self.assertEqual(meta["health"], "black")  # 需要人工介入
        self.assertIn("安全验证", meta["health_reason"])
        self.assertEqual(meta["health_reason_kind"], "platform_block")
        self.assertTrue(meta["health_updated_at"])

    def test_login_check_false_marks_red(self):
        account_status.record_login_check("acc", valid=False, reason="cookie 已失效")
        meta = json.loads(self.meta.read_text(encoding="utf-8"))
        self.assertEqual(meta["health"], "red")
        self.assertEqual(meta["health_reason_kind"], "login_invalid")

    def test_login_check_true_clears_reason(self):
        account_status.record_platform_block("acc", "被拦住")
        account_status.record_login_check("acc", valid=True)
        meta = json.loads(self.meta.read_text(encoding="utf-8"))
        self.assertEqual(meta["health"], "green")
        self.assertNotIn("health_reason", meta)

    def test_unknown_check_keeps_health_but_records_reason(self):
        account_status.set_account_status("acc", health="green", clear_reason=True)
        account_status.record_login_check("acc", valid=None, reason="浏览器起不来")
        meta = json.loads(self.meta.read_text(encoding="utf-8"))
        self.assertEqual(meta["health"], "green")  # 没测出来不能乱改档位
        self.assertEqual(meta["health_reason_kind"], "check_failed")

    def test_task_success_restores_green(self):
        account_status.record_platform_block("acc", "被拦住")
        account_status.record_task_success("acc")
        meta = json.loads(self.meta.read_text(encoding="utf-8"))
        self.assertEqual(meta["health"], "green")
        self.assertNotIn("health_reason", meta)

    def test_invalid_health_level_rejected(self):
        with self.assertRaises(ValueError):
            account_status.set_account_status("acc", health="purple")


class CheckSessionWritesStatusTests(unittest.TestCase):
    """「检测」按钮要把真实结论写进状态：checkpoint → 需人工，未登录 → 失效。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.session_dir = Path(self._tmp.name)
        (self.session_dir / "fbacc_cookies.json").write_text(
            json.dumps(
                [
                    {"name": "c_user", "value": "1", "domain": ".facebook.com", "path": "/"},
                    {"name": "xs", "value": "2", "domain": ".facebook.com", "path": "/"},
                ]
            ),
            encoding="utf-8",
        )
        self._patches = [
            patch.object(routes, "SESSION_DIR", self.session_dir),
            patch.object(account_status, "SESSION_DIR", self.session_dir),
            # 适配器也用绝对路径读 cookie，测试里要把它指到临时目录
            patch.object(facebook_adapter, "SESSION_DIR", self.session_dir),
        ]
        for item in self._patches:
            item.start()

    def tearDown(self):
        for item in reversed(self._patches):
            item.stop()
        self._tmp.cleanup()

    def _check(self, live_result):
        with patch(
            "app.core.cookie_import.verify_facebook_cookies",
            new=AsyncMock(return_value=live_result),
        ):
            return asyncio.run(routes.check_session("fbacc"))

    def test_checkpoint_marks_black(self):
        result = self._check(
            {
                "verified": False,
                "reason": "Facebook 把请求重定向到了登录/验证页",
                "url": "https://www.facebook.com/checkpoint/1501092823525282/",
                "user_id": None,
            }
        )
        self.assertFalse(result["valid"])
        self.assertIn("安全验证", result["message"])
        meta = json.loads((self.session_dir / "fbacc_meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["health"], "black")
        self.assertIn("安全验证", meta["health_reason"])

    def test_not_logged_in_marks_red(self):
        result = self._check(
            {
                "verified": False,
                "reason": "页面看起来还是未登录状态",
                "url": "https://www.facebook.com/login/",
                "user_id": None,
            }
        )
        self.assertFalse(result["valid"])
        meta = json.loads((self.session_dir / "fbacc_meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["health"], "red")

    def test_valid_login_marks_green(self):
        result = self._check(
            {
                "verified": True,
                "reason": "页面上找到了登录后的元素",
                "url": "https://www.facebook.com/",
                "user_id": "100012345678900",
            }
        )
        self.assertTrue(result["valid"])
        self.assertIn("实测通过", result["message"])
        meta = json.loads((self.session_dir / "fbacc_meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["health"], "green")
        self.assertNotIn("health_reason", meta)

    def test_unreachable_check_does_not_change_health(self):
        account_status.set_account_status("fbacc", health="green")
        result = self._check(
            {
                "verified": None,
                "reason": "校验没跑成：网络不通",
                "url": "",
                "user_id": None,
            }
        )
        self.assertTrue(result["valid"])  # 本地检查仍然通过
        meta = json.loads((self.session_dir / "fbacc_meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["health"], "green")
        self.assertEqual(meta["health_reason_kind"], "check_failed")


if __name__ == "__main__":
    unittest.main()
