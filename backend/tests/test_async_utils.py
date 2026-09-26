import asyncio
import unittest

from app.core.async_utils import OperationTimeoutError, with_timeout


class WithTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_value_when_fast(self):
        async def quick():
            return "ok"

        self.assertEqual(await with_timeout(quick(), 1, "快速调用"), "ok")

    async def test_raises_on_timeout(self):
        async def slow():
            await asyncio.sleep(5)

        with self.assertRaises(OperationTimeoutError) as ctx:
            await with_timeout(slow(), 0.05, "慢调用")
        self.assertIn("慢调用 超时", str(ctx.exception))

    async def test_extra_exceptions_count_as_timeout(self):
        """Telethon 断连时抛的可能是 ConnectionResetError，也要按超时处理。"""

        async def reset():
            raise ConnectionResetError("[WinError 64] 指定的网络名不再可用")

        with self.assertRaises(OperationTimeoutError):
            await with_timeout(reset(), 1, "断连调用", on_timeout=(ConnectionResetError,))


if __name__ == "__main__":
    unittest.main()
