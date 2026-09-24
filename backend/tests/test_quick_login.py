import asyncio
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import quick_login


class LoginArgumentsTests(unittest.TestCase):
    def test_default_preserves_printer(self):
        self.assertEqual(quick_login.parse_args([]).sessions, ["printer"])

    def test_three_distinct_names(self):
        self.assertEqual(
            quick_login.parse_args(["test1", "test2", "test3"]).sessions,
            ["test1", "test2", "test3"],
        )

    def test_rejects_invalid_or_duplicate_names(self):
        for names in (["../printer"], ["/tmp/session"], ["TEST1"], ["a" * 49], ["a", "a"]):
            with self.subTest(names=names), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    quick_login.parse_args(names)
                self.assertEqual(error.exception.code, 2)


class LoginAccountTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = SimpleNamespace(tg_api_id=12345, tg_api_hash="test-placeholder")
        self.client = AsyncMock()
        self.client.is_user_authorized.return_value = False
        self.client.get_me.return_value = SimpleNamespace(id=1)
        self.factory = self.enterContext(patch.object(quick_login, "TelegramClient", return_value=self.client))
        self.output = self.enterContext(redirect_stdout(io.StringIO()))

    async def test_login_uses_named_session_and_hidden_prompts(self):
        self.assertTrue(await quick_login.login_account("test2", self.settings))
        self.assertEqual(self.factory.call_args.args[0], str(quick_login.SESSION_DIR / "test2"))
        callbacks = self.client.start.call_args.kwargs
        with patch("builtins.input", return_value=" +12345 "), patch.object(
            quick_login, "getpass", side_effect=[" 12345 ", " secret "]
        ):
            self.assertEqual(callbacks["phone"](), "+12345")
            self.assertEqual(callbacks["code_callback"](), "12345")
            self.assertEqual(callbacks["password"](), " secret ")
        self.client.disconnect.assert_awaited_once()
        self.assertIn("LOGIN SUCCESSFUL", self.output.getvalue())

    async def test_authorized_session_does_not_request_login(self):
        self.client.is_user_authorized.return_value = True
        self.assertTrue(await quick_login.login_account("test1", self.settings))
        self.client.start.assert_not_awaited()
        self.client.disconnect.assert_awaited_once()

    async def test_unauthenticated_result_is_not_success(self):
        self.client.get_me.return_value = None
        self.assertFalse(await quick_login.login_account("test1", self.settings))
        self.assertNotIn("LOGIN SUCCESSFUL", self.output.getvalue())
        self.client.disconnect.assert_awaited_once()

    async def test_auth_error_disconnects_without_network_fallback(self):
        self.client.start.side_effect = ValueError("invalid code")
        with self.assertRaises(ValueError):
            await quick_login.login_account("test1", self.settings)
        self.factory.assert_called_once()
        self.client.disconnect.assert_awaited_once()

    async def test_connect_error_disconnects(self):
        self.client.connect.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            await quick_login.login_account("test1", self.settings)
        self.client.start.assert_not_awaited()
        self.client.disconnect.assert_awaited_once()

    async def test_cancellation_disconnects(self):
        self.client.start.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await quick_login.login_account("test1", self.settings)
        self.client.disconnect.assert_awaited_once()


class LoginBatchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = SimpleNamespace(tg_api_id=12345, tg_api_hash="test-placeholder")
        self.settings_factory = self.enterContext(patch.object(quick_login, "Settings", return_value=self.settings))
        self.enterContext(patch.object(quick_login.sys.stdin, "isatty", return_value=True))
        self.directory = self.enterContext(patch.object(quick_login, "SESSION_DIR"))
        self.login = self.enterContext(patch.object(quick_login, "login_account", new_callable=AsyncMock))
        self.output = self.enterContext(redirect_stdout(io.StringIO()))

    async def test_sequential_batch_uses_local_env(self):
        events = []

        async def login(name, settings):
            events.append(("start", name))
            await asyncio.sleep(0)
            events.append(("end", name))
            return True

        self.login.side_effect = login
        self.assertEqual(await quick_login.main(["test1", "test2", "test3"]), 0)
        self.assertEqual(events, [
            ("start", "test1"), ("end", "test1"),
            ("start", "test2"), ("end", "test2"),
            ("start", "test3"), ("end", "test3"),
        ])
        self.settings_factory.assert_called_once_with(_env_file=quick_login.BACKEND_DIR / ".env")

    async def test_account_failure_continues_and_exits_nonzero(self):
        self.login.side_effect = [True, ValueError("private details"), True]
        self.assertEqual(await quick_login.main(["test1", "test2", "test3"]), 1)
        self.assertEqual(self.login.await_count, 3)
        self.assertIn("2/3", self.output.getvalue())
        self.assertNotIn("private details", self.output.getvalue())

    async def test_eof_stops_the_batch(self):
        self.login.side_effect = EOFError()
        self.assertEqual(await quick_login.main(["test1", "test2"]), 1)
        self.login.assert_awaited_once()

    async def test_noninteractive_run_never_connects(self):
        with patch.object(quick_login.sys.stdin, "isatty", return_value=False):
            self.assertEqual(await quick_login.main(["test1"]), 1)
        self.login.assert_not_awaited()
        self.directory.mkdir.assert_not_called()

    async def test_missing_credentials_never_connects(self):
        self.settings.tg_api_hash = ""
        self.assertEqual(await quick_login.main(["test1"]), 1)
        self.login.assert_not_awaited()
        self.directory.mkdir.assert_not_called()


if __name__ == "__main__":
    unittest.main()
