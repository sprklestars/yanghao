import os
import sqlite3
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


class RemoveSessionFilesTests(unittest.TestCase):
    def test_removes_session_and_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "sessions" / "t"
            base.parent.mkdir(parents=True)
            Path(f"{base}.session").write_bytes(b"x")
            Path(f"{base}.session-journal").write_bytes(b"x")

            removed = session_paths.remove_session_files(base)

            self.assertEqual(
                sorted(path.name for path in removed), ["t.session", "t.session-journal"]
            )
            self.assertFalse(Path(f"{base}.session").exists())
            self.assertFalse(Path(f"{base}.session-journal").exists())

    def test_missing_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(session_paths.remove_session_files(Path(tmp) / "nope"), [])


class SessionInUseTests(unittest.TestCase):
    def test_detects_lock_held_by_another_connection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.session"
            holder = sqlite3.connect(str(path))
            try:
                holder.execute("CREATE TABLE t (x INTEGER)")
                holder.commit()
                self.assertFalse(session_paths.session_in_use(path))

                holder.execute("BEGIN IMMEDIATE")  # 模拟"被别的客户端占着"
                self.assertTrue(session_paths.session_in_use(path))

                holder.execute("ROLLBACK")
                self.assertFalse(session_paths.session_in_use(path))
            finally:
                holder.close()

    def test_missing_file_is_not_in_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(session_paths.session_in_use(Path(tmp) / "nope"))


class SessionNameValidationTests(unittest.TestCase):
    def test_accepts_normal_names(self):
        for name in ("printer", "tg8801934061959", "user-3", "a", "a" * 48):
            with self.subTest(name=name):
                self.assertTrue(session_paths.is_valid_session_name(name))

    def test_rejects_path_traversal_and_bad_chars(self):
        for name in ("../printer", "..\\printer", "/tmp/x", "TEST", "user 1", "", "-a", "a" * 49):
            with self.subTest(name=name):
                self.assertFalse(session_paths.is_valid_session_name(name))


if __name__ == "__main__":
    unittest.main()
