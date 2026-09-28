import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.intelligence.pipeline import (
    ExtractedEntities,
    make_dedup_fingerprint,
    merge_intelligence,
)


def _record(**overrides):
    base = dict(
        confidence=0.0,
        signals=[],
        extracted_contacts={},
        business_info={},
        display_name=None,
        last_seen=None,
        platforms=None,
        platform=SimpleNamespace(value="telegram"),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class DedupFingerprintTests(unittest.TestCase):
    def test_same_contact_cross_platform_same_fingerprint(self):
        # 两个平台、不同目标ID，但留下的联系方式完全相同 → 同一指纹
        first = ExtractedEntities(phones=["0912345678"])
        second = ExtractedEntities(phones=["0912345678"])
        self.assertEqual(
            make_dedup_fingerprint("telegram", "111", first),
            make_dedup_fingerprint("zalo", "222", second),
        )

    def test_no_contact_falls_back_to_platform_and_id(self):
        empty = ExtractedEntities()
        self.assertEqual(
            make_dedup_fingerprint("telegram", "111", empty),
            make_dedup_fingerprint("telegram", "111", empty),
        )
        self.assertNotEqual(
            make_dedup_fingerprint("telegram", "111", empty),
            make_dedup_fingerprint("zalo", "111", empty),
        )


class MergeIntelligenceTests(unittest.TestCase):
    def test_merges_fields_keeping_earliest(self):
        existing = _record(
            confidence=0.3,
            signals=["USD"],
            extracted_contacts={"phones": ["0912345678"], "emails": ["a@b.com"]},
            business_info={"prices": ["25.5"]},
            display_name="First Name",
            platform=SimpleNamespace(value="telegram"),
            platforms=["telegram"],
        )
        incoming = _record(
            confidence=0.8,
            signals=["zalo"],
            extracted_contacts={"phones": ["0912345678"], "zalo_ids": ["z123"]},
            business_info={"bank_accounts": ["VND123"]},
            display_name="Second",
            platform=SimpleNamespace(value="zalo"),
            platforms=["zalo"],
        )

        merge_intelligence(existing, incoming)

        self.assertEqual(existing.confidence, 0.8)
        self.assertEqual(existing.signals, ["USD", "zalo"])
        self.assertEqual(existing.extracted_contacts["phones"], ["0912345678"])
        self.assertEqual(existing.extracted_contacts["zalo_ids"], ["z123"])
        self.assertEqual(existing.business_info["bank_accounts"], ["VND123"])
        self.assertEqual(existing.display_name, "First Name")
        self.assertEqual(existing.platforms, ["telegram", "zalo"])

    def test_last_seen_keeps_latest(self):
        older = datetime(2026, 1, 1, tzinfo=timezone.utc)
        newer = datetime(2026, 6, 1, tzinfo=timezone.utc)
        existing = _record(last_seen=older)
        incoming = _record(last_seen=newer)
        merge_intelligence(existing, incoming)
        self.assertEqual(existing.last_seen, newer)


if __name__ == "__main__":
    unittest.main()
