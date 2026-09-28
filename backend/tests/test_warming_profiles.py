import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from app.services.security.account_warming import AccountWarmingManager


class WarmingProfilePersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "state" / "warming_profiles.json"
        self.manager = AccountWarmingManager(self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_ensure_profile_creates_once(self):
        created = datetime.now() - timedelta(days=40)
        first = self.manager.ensure_profile("acc", created_at=created, ip_region="VN-HCM")
        second = self.manager.ensure_profile("acc")

        self.assertIs(first, second)  # 幂等：不重复建、引用不变
        self.assertEqual(first.age_days, 40)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertIn("acc", data)

    def test_other_process_sees_profile(self):
        self.manager.ensure_profile("acc", created_at=datetime.now() - timedelta(days=100))
        other = AccountWarmingManager(self.path)
        profile = other.get_profile("acc")
        self.assertIsNotNone(profile)
        self.assertGreaterEqual(profile.age_days, 99)

    def test_record_operation_persists_and_keeps_reference(self):
        profile = self.manager.ensure_profile(
            "acc", created_at=datetime.now() - timedelta(days=100)
        )
        self.manager.record_operation("acc", "join_group")
        self.manager.record_operation("acc", "send_message")

        # 调用方持有的引用能看到最新计数（不要每次访问都换对象）
        self.assertEqual(profile.groups_joined_today, 1)
        self.assertEqual(profile.messages_sent_today, 1)

        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["acc"]["groups_joined_today"], 1)
        self.assertEqual(data["acc"]["messages_sent_today"], 1)

    def test_settings_update_persists(self):
        self.manager.ensure_profile("acc", created_at=datetime.now() - timedelta(days=1))
        self.manager.update_settings("acc", two_factor_enabled=True, enforce_setup_check=False)

        other = AccountWarmingManager(self.path)
        profile = other.get_profile("acc")
        self.assertTrue(profile.two_factor_enabled)
        self.assertFalse(profile.enforce_setup_check)


if __name__ == "__main__":
    unittest.main()
