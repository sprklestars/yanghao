"""Facebook cookie 导入的解析与端点测试。

为什么有这条路：自动化浏览器里手动登 Facebook 经常被风控卡住（转圈/验证），
而用户自己浏览器里已经有登录态了，直接导 cookie 更靠谱。
"""

import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from app.api import routes
from app.core import cookie_import

HEADER = (
    "Cookie: datr=abc123; sb=xyz789; c_user=100012345678900; "
    "xs=12%3Aabcdef%3A2%3A1700000000%3A-1%3A1234; fr=0abc.XYZ.AWx"
)


class ParseCookieInputTests(unittest.TestCase):
    def test_header_string(self):
        cookies = cookie_import.parse_cookie_input(HEADER)
        names = {c["name"] for c in cookies}
        self.assertEqual(names, {"datr", "sb", "c_user", "xs", "fr"})
        by_name = {c["name"]: c for c in cookies}
        self.assertEqual(by_name["c_user"]["domain"], ".facebook.com")
        self.assertTrue(by_name["xs"]["httpOnly"])  # xs 是 HttpOnly，导入时要标上
        self.assertFalse(by_name["c_user"]["httpOnly"])
        self.assertEqual(by_name["xs"]["value"], "12%3Aabcdef%3A2%3A1700000000%3A-1%3A1234")

    def test_header_without_prefix_and_multiline(self):
        cookies = cookie_import.parse_cookie_input("c_user=1; xs=2\nfr=3")
        self.assertEqual({c["name"] for c in cookies}, {"c_user", "xs", "fr"})

    def test_playwright_json(self):
        raw = json.dumps(
            [
                {
                    "name": "c_user",
                    "value": "100012345678900",
                    "domain": ".facebook.com",
                    "path": "/",
                    "expires": 1900000000.5,
                    "httpOnly": False,
                    "secure": True,
                    "sameSite": "None",
                },
                {"name": "xs", "value": "1%3A2", "domain": ".facebook.com", "path": "/"},
            ]
        )
        cookies = cookie_import.parse_cookie_input(raw)
        by_name = {c["name"]: c for c in cookies}
        self.assertEqual(by_name["c_user"]["expires"], 1900000000.5)
        self.assertEqual(by_name["c_user"]["sameSite"], "None")
        self.assertEqual(by_name["xs"]["value"], "1%3A2")

    def test_extension_json_with_expiration_date_and_host_only(self):
        raw = json.dumps(
            [
                {
                    "domain": ".facebook.com",
                    "name": "c_user",
                    "value": "1",
                    "path": "/",
                    "secure": True,
                    "httpOnly": False,
                    "expirationDate": 1800000000.25,
                    "sameSite": "no_restriction",
                },
                {
                    "domain": "www.facebook.com",
                    "name": "xs",
                    "value": "2",
                    "path": "/",
                    "hostOnly": True,
                    "sameSite": "unspecified",
                },
            ]
        )
        by_name = {c["name"]: c for c in cookie_import.parse_cookie_input(raw)}
        self.assertEqual(by_name["c_user"]["expires"], 1800000000.25)
        self.assertEqual(by_name["c_user"]["sameSite"], "None")
        self.assertTrue(by_name["c_user"]["secure"])
        self.assertEqual(by_name["xs"]["domain"], "www.facebook.com")  # hostOnly 不加前缀点
        self.assertNotIn("sameSite", by_name["xs"])

    def test_key_value_json(self):
        cookies = cookie_import.parse_cookie_input({"c_user": "1", "xs": "2"})
        self.assertEqual({c["name"] for c in cookies}, {"c_user", "xs"})

    def test_netscape_cookies_txt(self):
        raw = "\n".join(
            [
                "# Netscape HTTP Cookie File",
                ".facebook.com\tTRUE\t/\tTRUE\t1900000000\tc_user\t100012345678900",
                "#HttpOnly_.facebook.com\tTRUE\t/\tTRUE\t1900000000\txs\t12%3Aabc",
                "",
            ]
        )
        by_name = {c["name"]: c for c in cookie_import.parse_cookie_input(raw)}
        self.assertEqual(by_name["c_user"]["value"], "100012345678900")
        self.assertEqual(by_name["c_user"]["expires"], 1900000000.0)
        self.assertTrue(by_name["xs"]["httpOnly"])  # #HttpOnly_ 前缀

    def test_missing_login_cookies(self):
        cookies = cookie_import.parse_cookie_input("datr=abc; fr=def")
        self.assertEqual(cookie_import.missing_login_cookies(cookies), ["c_user", "xs"])
        cookies = cookie_import.parse_cookie_input("c_user=1; xs=2")
        self.assertEqual(cookie_import.missing_login_cookies(cookies), [])

    def test_garbage_raises_value_error(self):
        for raw in ("", "   ", "这不是 cookie", "[[["):
            with self.assertRaises(ValueError):
                cookie_import.parse_cookie_input(raw)


class ImportCookiesEndpointTests(unittest.TestCase):
    def setUp(self):
        self.session_name = "fbcookie"
        self._tmp = TemporaryDirectory()
        self._patches = [
            patch.object(routes, "SESSION_DIR", Path(self._tmp.name)),
        ]
        for item in self._patches:
            item.start()
        self.cookie_file = Path(self._tmp.name) / f"{self.session_name}_cookies.json"
        self.cookie_file.unlink(missing_ok=True)

    def tearDown(self):
        for item in reversed(self._patches):
            item.stop()
        self._tmp.cleanup()

    def _call(self, **body):
        payload = {"session_name": self.session_name, **body}
        return asyncio.run(routes.facebook_import_cookies(payload))

    def test_rejects_cookies_without_login_fields(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            self._call(cookies="datr=abc; fr=def")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("xs", ctx.exception.detail)
        self.assertFalse(self.cookie_file.exists())

    def test_import_saves_file_and_reports_verified(self):
        verified = {
            "verified": True,
            "reason": "ok",
            "url": "https://www.facebook.com/",
            "user_id": "100012345678900",
        }
        with patch.object(
            cookie_import, "verify_facebook_cookies", new=AsyncMock(return_value=verified)
        ):
            result = self._call(cookies=HEADER)

        saved = json.loads(self.cookie_file.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["count"], len(saved))
        self.assertTrue(result["verified"])
        self.assertIn("100012345678900", result["message"])

    def test_unverified_import_removes_file_and_errors(self):
        unverified = {"verified": False, "reason": "还是未登录", "url": "", "user_id": None}
        with patch.object(
            cookie_import, "verify_facebook_cookies", new=AsyncMock(return_value=unverified)
        ):
            from fastapi import HTTPException

            with self.assertRaises(HTTPException) as ctx:
                self._call(cookies=HEADER)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("c_user", ctx.exception.detail)
        # 校验说没登录：不能留一个用不了的账号在列表里
        self.assertFalse(self.cookie_file.exists())

    def test_verify_can_be_skipped(self):
        result = self._call(cookies=HEADER, verify=False)
        self.assertTrue(self.cookie_file.exists())
        self.assertIsNone(result["verified"])


if __name__ == "__main__":
    unittest.main()
