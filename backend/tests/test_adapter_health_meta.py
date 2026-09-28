import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.platform.telegram_adapter import TelegramAdapter


class AdapterHealthMetaTests(unittest.TestCase):
    """适配器把健康监控结论写回 sessions/<账号>_meta.json（前端徽章据此显示）。"""

    def test_failures_degrade_meta_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            with patch(
                "app.services.platform.telegram_adapter.SESSION_DIR", session_dir
            ):
                adapter = TelegramAdapter(api_id=1, api_hash="x", session_name="acc")
                for _ in range(5):
                    adapter._record_health(False)

            meta = json.loads((session_dir / "acc_meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["health"], "black")

    def test_success_keeps_meta_health_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            with patch(
                "app.services.platform.telegram_adapter.SESSION_DIR", session_dir
            ):
                adapter = TelegramAdapter(api_id=1, api_hash="x", session_name="acc2")
                adapter._record_health(True)

            meta = json.loads((session_dir / "acc2_meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["health"], "green")


if __name__ == "__main__":
    unittest.main()
