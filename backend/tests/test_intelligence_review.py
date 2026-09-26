import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.models import ReviewStatus
from app.services.intelligence.review import apply_review, parse_review_status


def _record(**overrides):
    base = dict(
        review_status=ReviewStatus.PENDING,
        reviewed_at=None,
        operator_notes=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class ParseReviewStatusTests(unittest.TestCase):
    def test_accepts_case_and_space(self):
        self.assertEqual(parse_review_status("APPROVED"), ReviewStatus.APPROVED)
        self.assertEqual(parse_review_status(" rejected "), ReviewStatus.REJECTED)

    def test_accepts_enum(self):
        self.assertEqual(parse_review_status(ReviewStatus.REVIEWED), ReviewStatus.REVIEWED)

    def test_rejects_unknown(self):
        with self.assertRaises(ValueError):
            parse_review_status("bogus")


class ApplyReviewTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)

    def test_pending_clears_reviewed_at(self):
        record = _record(reviewed_at=self.now)
        apply_review(record, ReviewStatus.PENDING, None, self.now)
        self.assertIsNone(record.reviewed_at)

    def test_first_review_sets_reviewed_at(self):
        record = _record()
        apply_review(record, ReviewStatus.APPROVED, None, self.now)
        self.assertEqual(record.review_status, ReviewStatus.APPROVED)
        self.assertEqual(record.reviewed_at, self.now)

    def test_reviewed_at_keeps_first_time(self):
        record = _record(review_status=ReviewStatus.REVIEWED, reviewed_at=self.now)
        later = self.now + timedelta(days=1)
        apply_review(record, ReviewStatus.APPROVED, None, later)
        self.assertEqual(record.reviewed_at, self.now)

    def test_notes_none_keeps_existing(self):
        record = _record(operator_notes="原有备注")
        apply_review(record, ReviewStatus.REVIEWED, None, self.now)
        self.assertEqual(record.operator_notes, "原有备注")

    def test_notes_are_trimmed_and_can_be_cleared(self):
        record = _record()
        apply_review(record, ReviewStatus.REVIEWED, "  可疑  ", self.now)
        self.assertEqual(record.operator_notes, "可疑")
        apply_review(record, ReviewStatus.REVIEWED, "", self.now)
        self.assertIsNone(record.operator_notes)


if __name__ == "__main__":
    unittest.main()
