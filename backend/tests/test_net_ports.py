"""端口探测与自动避让测试。

背景：Windows 上 Hyper-V / WSL2 / Docker Desktop 会动态预留一大片端口
（实测本机 7681-8580 全被预留），落在里面的端口任何程序都绑不上，
报的是 WinError 10013 —— 不是"被别的进程占用"，也不是代码问题。
后端启动脚本据此自动换端口，这里验证挑选逻辑。
"""

import socket
import unittest

from app.core.net import FALLBACK_PORTS, is_port_bindable, pick_available_port


def _free_port() -> int:
    """让系统分配一个当前可用的端口，用来做真实绑定测试。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class IsPortBindableTests(unittest.TestCase):
    def test_free_port_is_bindable(self):
        port = _free_port()
        self.assertTrue(is_port_bindable("127.0.0.1", port))

    def test_occupied_port_is_not_bindable(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
            holder.bind(("127.0.0.1", 0))
            holder.listen(1)
            busy = holder.getsockname()[1]
            self.assertFalse(is_port_bindable("127.0.0.1", busy))

    def test_invalid_port(self):
        self.assertFalse(is_port_bindable("127.0.0.1", 0))
        self.assertFalse(is_port_bindable("127.0.0.1", -1))


class PickAvailablePortTests(unittest.TestCase):
    def test_preferred_port_wins_when_free(self):
        port = _free_port()
        self.assertEqual(pick_available_port("127.0.0.1", port, fallbacks=()), port)

    def test_falls_back_when_preferred_is_blocked(self):
        """模拟"首选端口被系统预留"（WinError 10013）：应该自动换到候选端口。"""
        blocked = 8000
        tried: list[int] = []

        def fake_bindable(_host: str, port: int) -> bool:
            tried.append(port)
            return port != blocked  # 只有 8000 绑不上

        picked = pick_available_port(
            "127.0.0.1", blocked, fallbacks=(8600, 9000), is_bindable=fake_bindable
        )
        self.assertEqual(picked, 8600)
        self.assertEqual(tried, [8000, 8600])

    def test_keeps_looking_until_one_works(self):
        def fake_bindable(_host: str, port: int) -> bool:
            return port not in (8000, 8600)

        picked = pick_available_port(
            "127.0.0.1", 8000, fallbacks=(8600, 9000), is_bindable=fake_bindable
        )
        self.assertEqual(picked, 9000)

    def test_raises_when_nothing_is_available(self):
        with self.assertRaises(RuntimeError) as ctx:
            pick_available_port(
                "127.0.0.1", 8000, fallbacks=(8600,), is_bindable=lambda *_: False
            )
        self.assertIn("netsh", str(ctx.exception))  # 报错里要给排错命令

    def test_fallbacks_avoid_windows_reserved_ranges(self):
        """候选端口要避开 Windows 动态预留段，否则自动避让也没用。"""
        reserved = ((7681, 8580), (50000, 50059))
        for port in FALLBACK_PORTS:
            for start, end in reserved:
                self.assertFalse(
                    start <= port <= end, f"候选端口 {port} 落在系统预留段 {start}-{end}"
                )


class SettingsPortTests(unittest.TestCase):
    def test_urls_follow_app_port(self):
        from app.core.config import Settings

        settings = Settings(app_port=8610, api_token="secret")
        self.assertEqual(settings.api_base_url, "http://localhost:8610/api/v1")
        self.assertEqual(settings.ws_url, "ws://localhost:8610/ws?token=secret")

    def test_ws_url_without_token(self):
        from app.core.config import Settings

        self.assertEqual(Settings(app_port=8000).ws_url, "ws://localhost:8000/ws")


if __name__ == "__main__":
    unittest.main()
