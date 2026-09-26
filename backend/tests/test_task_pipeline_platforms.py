"""任务流水线的平台通用性：Facebook / Zalo 走同一条「搜群→加群→取目标→私聊」。

整条流水线要写数据库（Task/Account/Conversation），所以没有可用数据库的环境
自动跳过；适配器与"开场白生成"都用替身，不联网、不开浏览器、不调 LLM。
"""

import asyncio
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import delete, select, text

import app.workers.tasks as tasks
from app.core.config import settings
from app.core.database import async_session_factory, sync_engine
from app.core.database import engine as async_engine
from app.models.models import (
    Account,
    Conversation,
    ConversationState,
    Message,
    Platform,
    Task,
)
from app.services.platform.base import GroupInfo, PlatformName, UserProfile

PLATFORM_ENUM = {
    "telegram": PlatformName.TELEGRAM,
    "facebook": PlatformName.FACEBOOK,
    "zalo": PlatformName.ZALO,
}


def _db_available() -> bool:
    try:
        with sync_engine.connect() as conn:
            conn.execute(text("select 1"))
        return True
    except Exception:
        return False


DB_AVAILABLE = _db_available()

# 记录私聊时用的 target（验证"优先 @username，其次数字 id"）
RECORDED_TARGETS: list[str] = []


def _reset_async_pool() -> None:
    """测试里每个阶段都用新的 asyncio.run（新事件循环），
    必须先把上一个循环里建立的连接丢掉，否则 asyncpg 会报跨循环复用错误。"""
    asyncio.run(async_engine.dispose())


class FakeAdapter:
    """记录调用情况；不做任何网络操作。"""

    def __init__(self, platform: str):
        self.platform = platform
        self.authenticated = False
        self.disconnected = False
        self.search_limits: list[int] = []

    async def authenticate(self, credentials) -> bool:
        self.authenticated = True
        return True

    async def search_groups(self, query: str, limit: int = 10):
        self.search_limits.append(limit)
        return [
            GroupInfo(
                group_id="g1",
                name=f"group-{query}",
                member_count=10,
                platform=PLATFORM_ENUM[self.platform],
            )
        ]

    async def join_group(self, group_id: str) -> bool:
        return True

    async def get_group_members(self, group_id: str, limit: int = 100):
        return [
            UserProfile(user_id="u1", display_name="target-a", username="target_a"),
            UserProfile(user_id="u2", display_name="target-b", username=None),
        ]

    async def send_message(self, target_id: str, content) -> bool:
        return True

    async def disconnect(self) -> None:
        self.disconnected = True


class HangingAdapter(FakeAdapter):
    """搜索永远不返回，用来验证超时保护。"""

    async def search_groups(self, query: str, limit: int = 10):
        await asyncio.sleep(30)
        return []


async def fake_start_conversation(
    db, task, account, adapter, target_user_id, target_display_name
):
    """替身开场白：只落一条会话记录，不调 LLM、不发消息。"""
    RECORDED_TARGETS.append(target_user_id)
    conv = Conversation(
        id=uuid.uuid4(),
        account_id=account.id,
        task_id=task.id,
        target_user_id=target_user_id,
        target_display_name=target_display_name,
        state=ConversationState.IDLE,
        turn_count=1,
    )
    db.add(conv)
    db.commit()
    return str(conv.id)


@unittest.skipUnless(DB_AVAILABLE, "需要可用的数据库才能跑整条流水线")
class PlatformPipelineTests(unittest.TestCase):
    def _create_task(self, platform: Platform, name: str):
        from app.api import routes
        from app.schemas.schemas import TaskCreate

        _reset_async_pool()

        async def make():
            async with async_session_factory() as db:
                return await routes.create_task(
                    TaskCreate(
                        name=name,
                        platform=platform,
                        category="private_investigator",
                        keywords=["kw"],
                        config={"strategy": {"search_limit": 3, "dm_per_group": 2}},
                    ),
                    db,
                )

        return asyncio.run(make())

    def _read_and_cleanup(self, task_id, account_name: str):
        from app.api import routes

        _reset_async_pool()

        async def work():
            async with async_session_factory() as db:
                row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one()
                result = (row.status.value, (row.config or {}).get("last_run") or {})
                conv_ids = (
                    (
                        await db.execute(
                            select(Conversation.id).where(Conversation.task_id == task_id)
                        )
                    )
                    .scalars()
                    .all()
                )
                if conv_ids:
                    await db.execute(
                        delete(Message).where(Message.conversation_id.in_(conv_ids))
                    )
                    await db.execute(delete(Conversation).where(Conversation.id.in_(conv_ids)))
                await db.execute(delete(Account).where(Account.username == account_name))
                await routes.delete_task(str(task_id), db)
                return result

        return asyncio.run(work())

    def _run_platform(self, platform: Platform, session_filename: str, payload: dict):
        account_name = session_filename.split("_")[0]
        task = self._create_task(platform, f"__qa_{platform.value}__")
        created: list[FakeAdapter] = []
        RECORDED_TARGETS.clear()

        def fake_build(platform_arg, session_path):
            adapter = FakeAdapter(platform_arg.value)
            created.append(adapter)
            return adapter, type("Creds", (), {"credentials": {}, "username": account_name})()

        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            (session_dir / session_filename).write_text(json.dumps(payload), encoding="utf-8")
            _reset_async_pool()
            with (
                patch.object(tasks, "SESSION_DIR", session_dir),
                patch("app.core.session_paths.SESSION_DIR", session_dir),
                patch.object(tasks, "_build_adapter", side_effect=fake_build),
                patch.object(tasks, "_set_progress", lambda *a, **k: None),
                patch.object(tasks, "_start_conversation", side_effect=fake_start_conversation),
            ):
                tasks._run_task_pipeline(str(task.id))

        status, last_run = self._read_and_cleanup(task.id, account_name)
        return created, status, last_run

    def test_facebook_task_runs_through_pipeline(self):
        adapters, status, last_run = self._run_platform(
            Platform.FACEBOOK, "fbqa_cookies.json", {"cookies": []}
        )
        self.assertEqual(status, "completed")
        self.assertEqual(last_run["platform"], "facebook")
        self.assertEqual(last_run["found_groups"], 1)
        self.assertEqual(last_run["joined_groups"], 1)
        self.assertEqual(last_run["members_found"], 2)
        self.assertEqual(last_run["conversations"], 2)
        # 带 @username 的用 @username 私聊，没有的退回数字 id
        self.assertEqual(RECORDED_TARGETS, ["@target_a", "u2"])
        self.assertEqual(adapters[0].search_limits, [3])  # 策略参数确实传下去了
        self.assertTrue(adapters[0].authenticated)
        self.assertTrue(adapters[0].disconnected)

    def test_zalo_task_runs_through_pipeline(self):
        adapters, status, last_run = self._run_platform(
            Platform.ZALO, "zlqa_zalo.json", {"phone": "+84900000000", "imei": "imei-1"}
        )
        self.assertEqual(status, "completed")
        self.assertEqual(last_run["platform"], "zalo")
        self.assertEqual(last_run["conversations"], 2)
        self.assertEqual(RECORDED_TARGETS, ["@target_a", "u2"])
        self.assertTrue(adapters[0].disconnected)

    def test_missing_session_file_marks_task_failed(self):
        task = self._create_task(Platform.FACEBOOK, "__qa_nosession__")
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(tasks, "SESSION_DIR", Path(tmp)),
                patch("app.core.session_paths.SESSION_DIR", Path(tmp)),
            ):
                tasks._run_task_pipeline(str(task.id))
        status, _ = self._read_and_cleanup(task.id, "none")
        self.assertEqual(status, "failed")

    def test_account_timeout_is_skipped_not_fatal(self):
        """一个账号卡住 → 只跳过它，任务本身照常收尾（不再占住 worker）。"""
        account_name = "tmoqa"
        task = self._create_task(Platform.FACEBOOK, "__qa_timeout__")

        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            (session_dir / f"{account_name}_cookies.json").write_text("[]", encoding="utf-8")
            _reset_async_pool()
            with (
                patch.object(tasks, "SESSION_DIR", session_dir),
                patch("app.core.session_paths.SESSION_DIR", session_dir),
                patch.object(
                    tasks,
                    "_build_adapter",
                    side_effect=lambda p, s: (
                        HangingAdapter(p.value),
                        type("Creds", (), {"credentials": {}, "username": account_name})(),
                    ),
                ),
                patch.object(tasks, "_set_progress", lambda *a, **k: None),
                patch.object(settings, "adapter_timeout_seconds", 1),
            ):
                tasks._run_task_pipeline(str(task.id))

        status, last_run = self._read_and_cleanup(task.id, account_name)
        self.assertEqual(status, "completed")
        self.assertIn("timeout", last_run["accounts"][account_name])
        self.assertIn("超时", last_run["warning"])

    def test_running_peer_blocks_start(self):
        """同一平台已有任务在跑时，另一个任务的启动要被明确拒绝。"""
        from fastapi.testclient import TestClient

        from app.core.database import SessionLocal
        from app.main import app
        from app.models.models import TaskStatus

        first = self._create_task(Platform.FACEBOOK, "__qa_peer1__")
        second = self._create_task(Platform.FACEBOOK, "__qa_peer2__")

        db = SessionLocal()
        try:
            row = db.execute(select(Task).where(Task.id == first.id)).scalar_one()
            row.status = TaskStatus.RUNNING
            db.commit()
        finally:
            db.close()

        _reset_async_pool()
        client = TestClient(app)
        with patch.object(settings, "api_token", ""):
            response = client.post(f"/api/v1/tasks/{second.id}/start")
        self.assertEqual(response.status_code, 400)
        self.assertIn("已有", response.json()["detail"])

        db = SessionLocal()
        try:
            db.execute(delete(Task).where(Task.id.in_([first.id, second.id])))
            db.commit()
        finally:
            db.close()


class AdapterFactoryTests(unittest.TestCase):
    """不依赖数据库：只检查「登录态文件 → 适配器 + 凭证」。"""

    def test_zalo_credentials_read_from_session_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            path = session_dir / "zacc_zalo.json"
            path.write_text(
                json.dumps({"phone": "+84901234567", "imei": "imei-9"}), encoding="utf-8"
            )
            with patch("app.core.session_paths.SESSION_DIR", session_dir):
                adapter, credentials = tasks._build_adapter(Platform.ZALO, path)

        self.assertEqual(credentials.credentials["phone"], "+84901234567")
        self.assertEqual(credentials.credentials["imei"], "imei-9")
        self.assertEqual(adapter._session_name, "zacc")

    def test_facebook_credentials_carry_proxy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "facc_cookies.json"
            path.write_text("[]", encoding="utf-8")
            adapter, credentials = tasks._build_adapter(Platform.FACEBOOK, path)

        self.assertIn("proxy", credentials.credentials)
        self.assertEqual(adapter._session_name, "facc")


if __name__ == "__main__":
    unittest.main()
