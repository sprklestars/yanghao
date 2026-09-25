import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.core import session_paths
from app.services.platform.base import AccountCredentials, PlatformName
from app.services.platform.telegram_adapter import TelegramAdapter


class EnsureSessionDirTests(unittest.TestCase):
    def test_absolute_session_path_creates_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sessions" / "z"
            created = session_paths.ensure_session_dir(str(target))
            self.assertEqual(created, target.parent)
            self.assertTrue(target.parent.is_dir())

    def test_relative_session_path_creates_parent_under_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                session_paths.ensure_session_dir("sessions/z")
            finally:
                os.chdir(old_cwd)
            self.assertTrue((Path(tmp) / "sessions").is_dir())

    def test_bare_session_name_is_a_noop(self):
        created = session_paths.ensure_session_dir("printer")
        self.assertEqual(created, Path("."))

    def test_default_targets_backend_sessions_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_dir = Path(tmp) / "sessions"
            with patch.object(session_paths, "SESSION_DIR", fake_dir):
                created = session_paths.ensure_session_dir()
            self.assertEqual(created, fake_dir)
            self.assertTrue(fake_dir.is_dir())


class TelegramAdapterSessionDirTests(unittest.IsolatedAsyncioTestCase):
    async def test_authenticate_creates_dir_before_constructing_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "sessions" / "z"
            adapter = TelegramAdapter(api_id=1, api_hash="hash", session_name=str(session))
            client = AsyncMock()
            client.is_user_authorized.return_value = True
            credentials = AccountCredentials(
                platform=PlatformName.TELEGRAM, username="z", credentials={}
            )
            seen: dict[str, bool] = {}

            def make_client(*args, **kwargs):
                # 关键断言：构造函数被调用的那一刻，目录必须已经存在。
                seen["dir_existed"] = session.parent.is_dir()
                return client

            with patch(
                "app.services.platform.telegram_adapter.TelegramClient",
                side_effect=make_client,
            ):
                self.assertTrue(await adapter.authenticate(credentials))

            self.assertTrue(seen.get("dir_existed"))


class RealTelethonClientTests(unittest.TestCase):
    """直接复现原始 bug：Telethon 构造客户端时就会写 SQLite 会话文件。"""

    def test_client_construction_succeeds_for_fresh_nested_path(self):
        from telethon import TelegramClient

        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "sessions" / "z"
            self.assertFalse(session.parent.exists())

            session_paths.ensure_session_dir(str(session))
            client = TelegramClient(str(session), api_id=1, api_hash="hash")
            try:
                self.assertTrue(Path(f"{session}.session").exists())
            finally:
                client.session.close()


if __name__ == "__main__":
    unittest.main()
