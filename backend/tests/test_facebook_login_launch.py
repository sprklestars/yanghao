"""回归测试：Facebook 登录要启动「当前解释器」跑登录脚本。

以前这里硬编码了 Linux 的 `venv/bin/python3`，Windows 上点「打开浏览器」直接
报 `[WinError 2] 系统找不到指定的文件`。
"""

import asyncio
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.api import routes

NOISY_LOG = """
Exception ignored while calling deallocator <function _ProactorBasePipeTransport.__del__>:
Traceback (most recent call last):
  File "C:\\Python314\\Lib\\asyncio\\proactor_events.py", line 117, in __del__
    _warn(f"unclosed transport {self!r}", ResourceWarning, source=self)
ValueError: I/O operation on closed pipe

============================================================
🔐 Facebook Login — Session: fk
============================================================
🌐 Using proxy: socks5://127.0.0.1:7890
❌ Login failed for fk: BrowserType.launch: spawn UNKNOWN
"""


class FacebookLoginLaunchTests(unittest.TestCase):
    def setUp(self):
        self.session_name = "fbqa"
        routes._fb_login_processes.pop(self.session_name, None)

    def tearDown(self):
        routes._fb_login_processes.pop(self.session_name, None)

    def test_launch_uses_current_interpreter_and_backend_cwd(self):
        fake_proc = SimpleNamespace(pid=4242, returncode=0, poll=lambda: None, stdin=None)
        with (
            patch.object(routes.subprocess, "Popen", return_value=fake_proc) as popen,
            # 别让用例真的等 3 秒
            patch.object(routes.asyncio, "sleep", new=AsyncMock()),
        ):
            result = asyncio.run(
                routes.facebook_login_start({"session_name": self.session_name})
            )

        command = popen.call_args.args[0]
        self.assertEqual(command[0], sys.executable)  # 关键：当前 venv 解释器
        self.assertTrue(command[1].endswith("quick_login_facebook.py"))
        self.assertEqual(command[2], self.session_name)
        self.assertEqual(popen.call_args.kwargs["cwd"], str(routes.BACKEND_DIR))
        self.assertEqual(result["status"], "browser_opened")

    def test_immediate_exit_returns_log_tail(self):
        """浏览器进程起不来时要回 400 + 日志尾部，而不是骗用户"已打开"。"""
        from fastapi import HTTPException

        fake_proc = SimpleNamespace(pid=4243, returncode=1, poll=lambda: 1, stdin=None)
        with (
            patch.object(routes.subprocess, "Popen", return_value=fake_proc),
            patch.object(routes.asyncio, "sleep", new=AsyncMock()),
            patch.object(routes, "_tail_lines", return_value=["boom: missing chromium"]),
        ):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(
                    routes.facebook_login_start({"session_name": self.session_name})
                )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("missing chromium", ctx.exception.detail)

    def test_meaningful_tail_hides_asyncio_noise(self):
        """用户看到的必须是真正的报错，而不是 Python 关管道的 ResourceWarning。"""
        with TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "facebook_login.log"
            log_path.write_text(NOISY_LOG, encoding="utf-8")
            tail = routes._meaningful_tail(log_path, 12)

        self.assertIn("spawn UNKNOWN", tail)
        self.assertIn("Using proxy", tail)
        self.assertNotIn("I/O operation on closed pipe", tail)
        self.assertNotIn("proactor_events.py", tail)

    def test_meaningful_tail_falls_back_when_log_is_pure_noise(self):
        with TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "facebook_login.log"
            log_path.write_text(
                "Exception ignored while calling deallocator:\n"
                "ValueError: I/O operation on closed pipe\n",
                encoding="utf-8",
            )
            tail = routes._meaningful_tail(log_path, 12)

        self.assertIn("I/O operation on closed pipe", tail)  # 宁可原样给出，也不能是空

    def test_immediate_exit_detail_uses_filtered_log(self):
        from fastapi import HTTPException

        fake_proc = SimpleNamespace(pid=4244, returncode=1, poll=lambda: 1, stdin=None)
        with (
            patch.object(routes.subprocess, "Popen", return_value=fake_proc),
            patch.object(routes.asyncio, "sleep", new=AsyncMock()),
            patch.object(routes, "_meaningful_tail", return_value="❌ spawn UNKNOWN"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(
                    routes.facebook_login_start({"session_name": self.session_name})
                )

        self.assertIn("spawn UNKNOWN", ctx.exception.detail)
        self.assertIn("exit code 1", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
