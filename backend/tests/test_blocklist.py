import json
import tempfile
import unittest
from pathlib import Path

from app.services.security.blocklist import BlockListManager


class BlockListManagerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "state" / "blocklist.json"
        self.manager = BlockListManager(self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_block_persists_to_file(self):
        self.assertTrue(self.manager.block_user("111", reason="operator"))
        self.assertTrue(self.manager.is_blocked("111"))
        self.assertFalse(self.manager.block_user("111"))  # 重复拉黑返回 False

        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["111"]["reason"], "operator")
        self.assertIn("blocked_at", data["111"])

    def test_other_process_sees_blocks(self):
        """模拟守护进程：另一个实例（另一个进程）能看到 API 写入的黑名单。"""
        self.manager.block_user("222")
        other = BlockListManager(self.path)
        self.assertTrue(other.is_blocked("222"))

    def test_reloads_when_file_changes(self):
        self.manager.block_user("333")
        other = BlockListManager(self.path)
        other.block_user("444")
        # 本实例没有再次写入，但应通过 (mtime, size) 检测到外部改动
        self.assertTrue(self.manager.is_blocked("444"))

    def test_unblock_and_clear(self):
        self.manager.block_user("555")
        self.assertTrue(self.manager.unblock_user("555"))
        self.assertFalse(self.manager.is_blocked("555"))
        self.assertFalse(self.manager.unblock_user("555"))  # 不在名单里

        self.manager.block_user("666")
        self.manager.clear()
        self.assertEqual(self.manager.list_blocked(), [])
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {})

    def test_list_blocked_sorted_with_reason(self):
        self.manager.block_user("999", reason="b")
        self.manager.block_user("111", reason="a")
        items = self.manager.list_blocked()
        self.assertEqual([item["user_id"] for item in items], ["111", "999"])
        self.assertEqual(items[0]["reason"], "a")

    def test_missing_file_is_empty(self):
        manager = BlockListManager(Path(self._tmp.name) / "nope" / "blocklist.json")
        self.assertFalse(manager.is_blocked("111"))
        self.assertEqual(manager.get_all_blocked(), set())


if __name__ == "__main__":
    unittest.main()
