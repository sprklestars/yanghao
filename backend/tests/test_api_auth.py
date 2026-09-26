"""路由层集成测试：API 令牌鉴权 + 跨域头 + 一个不依赖数据库的真实端点。

注意：导入 app.main 会连带创建数据库引擎，所以先塞一个假 DSN，避免没有
.env 的环境在收集阶段就报错（这些用例都不碰数据库）。
"""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://test:test@localhost:5432/test")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402

LOCAL_ORIGIN = {"Origin": "http://localhost:3000"}


class ApiAuthTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_is_public(self):
        with patch.object(settings, "api_token", ""):
            self.assertEqual(self.client.get("/health").status_code, 200)

    def test_api_open_when_token_not_configured(self):
        with patch.object(settings, "api_token", ""):
            self.assertEqual(self.client.get("/api/v1/services/status").status_code, 200)

    def test_api_requires_token_when_configured(self):
        with patch.object(settings, "api_token", "secret-token"):
            self.assertEqual(self.client.get("/api/v1/services/status").status_code, 401)
            self.assertEqual(
                self.client.get(
                    "/api/v1/services/status", headers={"Authorization": "Bearer wrong"}
                ).status_code,
                401,
            )

    def test_health_stays_public_even_with_token(self):
        with patch.object(settings, "api_token", "secret-token"):
            self.assertEqual(self.client.get("/health").status_code, 200)

    def test_bearer_and_header_tokens_work(self):
        with patch.object(settings, "api_token", "secret-token"):
            bearer = self.client.get(
                "/api/v1/services/status",
                headers={"Authorization": "Bearer secret-token"},
            )
            self.assertEqual(bearer.status_code, 200)
            self.assertIsInstance(bearer.json(), list)

            custom = self.client.get(
                "/api/v1/services/status", headers={"X-API-Token": "secret-token"}
            )
            self.assertEqual(custom.status_code, 200)

    def test_401_keeps_cors_header(self):
        """前端要读得到 401 的内容，就必须带跨域头（否则浏览器只报"后端不可达"）。"""
        with patch.object(settings, "api_token", "secret-token"):
            response = self.client.get("/api/v1/services/status", headers=LOCAL_ORIGIN)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.headers.get("access-control-allow-origin"), "http://localhost:3000"
        )
        self.assertIn("访问令牌", response.json()["detail"])

    def test_preflight_is_not_blocked(self):
        with patch.object(settings, "api_token", "secret-token"):
            response = self.client.options(
                "/api/v1/services/status",
                headers={
                    **LOCAL_ORIGIN,
                    "Access-Control-Request-Method": "GET",
                },
            )
        self.assertNotEqual(response.status_code, 401)


class ServicesStatusShapeTests(unittest.TestCase):
    """顺带补一个真实端点的形状检查（不依赖数据库）。"""

    def test_status_lists_managed_services(self):
        client = TestClient(app)
        with patch.object(settings, "api_token", ""):
            data = client.get("/api/v1/services/status").json()
        platforms = {item["platform"] for item in data}
        self.assertTrue({"telegram", "facebook", "worker", "beat"} <= platforms)
        for item in data:
            self.assertIn("running", item)
            self.assertIn("label", item)


if __name__ == "__main__":
    unittest.main()
