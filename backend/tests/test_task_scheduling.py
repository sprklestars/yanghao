import unittest
from datetime import datetime, timedelta, timezone

from app.services.scheduling import compute_next_run, normalize_schedule, parse_iso

TZ8 = timezone(timedelta(hours=8))


class NormalizeScheduleTests(unittest.TestCase):
    def test_disabled_or_empty_returns_none(self):
        for raw in (None, {}, {"enabled": False}, {"enabled": False, "mode": "daily"}):
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_schedule(raw))

    def test_daily_is_normalized(self):
        self.assertEqual(
            normalize_schedule({"enabled": True, "mode": "daily", "at": "9:5"}),
            {"enabled": True, "mode": "daily", "at": "09:05"},
        )

    def test_interval_is_normalized(self):
        self.assertEqual(
            normalize_schedule({"enabled": True, "mode": "interval", "every_minutes": "90"}),
            {"enabled": True, "mode": "interval", "every_minutes": 90},
        )

    def test_default_mode_is_daily(self):
        self.assertEqual(
            normalize_schedule({"enabled": True})["mode"],
            "daily",
        )

    def test_invalid_values_raise(self):
        for raw in (
            {"enabled": True, "mode": "weekly"},
            {"enabled": True, "mode": "daily", "at": "25:00"},
            {"enabled": True, "mode": "daily", "at": "abc"},
            {"enabled": True, "mode": "interval", "every_minutes": 1},
        ):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                normalize_schedule(raw)


class ComputeNextRunTests(unittest.TestCase):
    def test_interval_adds_minutes(self):
        now = datetime(2026, 9, 26, 0, 0, tzinfo=timezone.utc)
        schedule = {"mode": "interval", "every_minutes": 90}
        self.assertEqual(compute_next_run(schedule, now), now + timedelta(minutes=90))

    def test_daily_same_day_when_still_ahead(self):
        # UTC 00:00 = 东八区 08:00，09:00 还没到 → 当天
        now = datetime(2026, 9, 26, 0, 0, tzinfo=timezone.utc)
        schedule = {"mode": "daily", "at": "09:00"}
        self.assertEqual(
            compute_next_run(schedule, now, tz=TZ8),
            datetime(2026, 9, 26, 1, 0, tzinfo=timezone.utc),
        )

    def test_daily_rolls_to_next_day_when_passed(self):
        # UTC 05:00 = 东八区 13:00，已过 09:00 → 顺延到次日
        now = datetime(2026, 9, 26, 5, 0, tzinfo=timezone.utc)
        schedule = {"mode": "daily", "at": "09:00"}
        self.assertEqual(
            compute_next_run(schedule, now, tz=TZ8),
            datetime(2026, 9, 27, 1, 0, tzinfo=timezone.utc),
        )

    def test_naive_now_is_treated_as_utc(self):
        now = datetime(2026, 9, 26, 0, 0)
        schedule = {"mode": "interval", "every_minutes": 60}
        self.assertEqual(
            compute_next_run(schedule, now),
            datetime(2026, 9, 26, 1, 0, tzinfo=timezone.utc),
        )


class ParseIsoTests(unittest.TestCase):
    def test_parses_and_defaults_to_utc(self):
        self.assertIsNone(parse_iso(None))
        self.assertIsNone(parse_iso("not-a-date"))
        aware = parse_iso("2026-09-26T01:00:00+00:00")
        self.assertEqual(aware, datetime(2026, 9, 26, 1, 0, tzinfo=timezone.utc))
        naive = parse_iso("2026-09-26T01:00:00")
        self.assertEqual(naive.tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
