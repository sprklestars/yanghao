"""浏览器探测相关测试。

背景：Playwright 自带的 Chromium 只能起无头，headless=False 时 Windows 报
并行配置错误（SxS）→ Playwright 抛 ``BrowserType.launch: spawn UNKNOWN``。
所以「打开浏览器」不能写死自带 Chromium，要按顺序探测、谁先起来用谁。
"""

import asyncio
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.core import browser_launch


class FakeChromium:
    def __init__(self, failing: set[str]):
        self.failing = failing
        self.calls: list[dict] = []

    async def launch(self, **kwargs):
        self.calls.append(kwargs)
        name = kwargs.get("channel") or browser_launch.CHANNEL_BUNDLED
        if name in self.failing:
            raise RuntimeError(f"{name} 起不来")
        return f"browser::{name}"


class FakePlaywright:
    def __init__(self, failing: set[str] | None = None):
        self.chromium = FakeChromium(failing or set())


class CandidateOrderTests(unittest.TestCase):
    def test_headed_prefers_installed_browser(self):
        order = browser_launch.candidate_order(headless=False)
        self.assertEqual(order[:2], ["msedge", "chrome"])
        self.assertIn(browser_launch.CHANNEL_BUNDLED, order)

    def test_headless_prefers_bundled_chromium(self):
        self.assertEqual(browser_launch.candidate_order(headless=True)[0], "chromium")

    def test_env_override_wins(self):
        order = browser_launch.candidate_order(headless=False, preferred="chrome")
        self.assertEqual(order[0], "chrome")

    def test_cached_choice_goes_first_and_no_duplicates(self):
        order = browser_launch.candidate_order(headless=True, cached="msedge")
        self.assertEqual(order[0], "msedge")
        self.assertEqual(len(order), len(set(order)))

    def test_blank_preference_is_not_a_preference(self):
        """空环境变量不能变成"优先用自带 Chromium"，否则有头模式永远选到坏浏览器。"""
        self.assertEqual(
            browser_launch.candidate_order(headless=False, preferred="", cached=None),
            browser_launch.candidate_order(headless=False),
        )
        self.assertEqual(
            browser_launch.candidate_order(headless=False, preferred="  ")[0], "msedge"
        )

    def test_labels_and_channel_mapping(self):
        self.assertIsNone(browser_launch.playwright_channel("chromium"))
        self.assertEqual(browser_launch.playwright_channel("msedge"), "msedge")
        self.assertEqual(browser_launch.channel_label("msedge"), "Microsoft Edge")
        self.assertEqual(browser_launch.normalize_channel("Edge"), "msedge")


class LaunchBrowserTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._cache = Path(self._tmp.name) / ".browser_channel.json"
        self._patches = [
            patch.object(browser_launch, "CACHE_FILE", self._cache),
            patch.dict(os.environ, {}, clear=False),
        ]
        for item in self._patches:
            item.start()
        os.environ.pop(browser_launch.ENV_VAR, None)

    def tearDown(self):
        for item in reversed(self._patches):
            item.stop()
        self._tmp.cleanup()

    def _launch(self, playwright, headless=False):
        return asyncio.run(
            browser_launch.launch_browser(
                playwright, headless=headless, log=lambda _m: None
            )
        )

    def test_headless_falls_back_when_bundled_chromium_is_broken(self):
        playwright = FakePlaywright(failing={"chromium"})
        browser, channel = self._launch(playwright, headless=True)
        self.assertEqual(channel, "msedge")
        self.assertEqual(browser, "browser::msedge")
        # 选中的浏览器记下来，下次不用再先失败一次
        self.assertEqual(browser_launch.load_cached_channel("headless"), "msedge")

    def test_headed_falls_back_when_edge_is_missing(self):
        playwright = FakePlaywright(failing={"msedge"})
        _browser, channel = self._launch(playwright, headless=False)
        self.assertEqual(channel, "chrome")

    def test_cached_channel_is_tried_first(self):
        playwright = FakePlaywright()
        browser_launch.save_cached_channel("headed", "chromium")
        _browser, channel = self._launch(playwright, headless=False)
        self.assertEqual(channel, "chromium")
        self.assertEqual(playwright.chromium.calls[0].get("channel"), None)
        self.assertEqual(len(playwright.chromium.calls), 1)

    def test_broken_cached_channel_is_cleared_and_replaced(self):
        playwright = FakePlaywright(failing={"chromium"})
        browser_launch.save_cached_channel("headed", "chromium")
        _browser, channel = self._launch(playwright, headless=False)
        self.assertEqual(channel, "msedge")
        self.assertEqual(browser_launch.load_cached_channel("headed"), "msedge")

    def test_proxy_and_args_are_forwarded(self):
        playwright = FakePlaywright()
        asyncio.run(
            browser_launch.launch_browser(
                playwright,
                headless=True,
                proxy={"server": "socks5://127.0.0.1:7890"},
                args=["--no-first-run"],
                log=lambda _m: None,
            )
        )
        call = playwright.chromium.calls[0]
        self.assertEqual(call["proxy"], {"server": "socks5://127.0.0.1:7890"})
        self.assertEqual(call["args"], ["--no-first-run"])
        self.assertTrue(call["headless"])

    def test_all_browsers_broken_raises_with_reasons(self):
        playwright = FakePlaywright(failing={"chromium", "chrome", "msedge"})
        with self.assertRaises(RuntimeError) as ctx:
            self._launch(playwright)
        message = str(ctx.exception)
        self.assertIn("没有可用的浏览器", message)
        self.assertIn("Microsoft Edge", message)
        self.assertIn(browser_launch.ENV_VAR, message)

    def test_env_var_forces_channel(self):
        playwright = FakePlaywright()
        with patch.dict(os.environ, {browser_launch.ENV_VAR: "chrome"}):
            _browser, channel = self._launch(playwright, headless=True)
        self.assertEqual(channel, "chrome")


if __name__ == "__main__":
    unittest.main()
