import unittest

from app.services.security.rate_limiter import AccountHealthMonitor, RateLimiter


class RateLimiterAllowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.limiter = RateLimiter()
        self.limiter.LIMITS = {
            "telegram": {
                "messages_per_hour": 2,
                "messages_per_day": 10,
                "group_joins_per_day": 1,
            }
        }

    async def test_allow_consumes_only_when_all_pass(self):
        for _ in range(2):
            self.assertEqual(
                await self.limiter.allow("telegram", ["messages_per_hour"], "acc"),
                (True, ""),
            )
        allowed, blocked = await self.limiter.allow("telegram", ["messages_per_hour"], "acc")
        self.assertFalse(allowed)
        self.assertEqual(blocked, "messages_per_hour")

    async def test_failed_day_limit_does_not_consume_hour_counter(self):
        # 天额度只有 1：第一次通过（小时+天各记 1 次），第二次应在天额度被拒，
        # 且小时计数器不能被白白扣掉
        self.limiter.LIMITS["telegram"]["messages_per_day"] = 1
        self.limiter.LIMITS["telegram"]["messages_per_hour"] = 99

        allowed, _ = await self.limiter.allow(
            "telegram", ["messages_per_hour", "messages_per_day"], "acc"
        )
        self.assertTrue(allowed)
        allowed, blocked = await self.limiter.allow(
            "telegram", ["messages_per_hour", "messages_per_day"], "acc"
        )
        self.assertFalse(allowed)
        self.assertEqual(blocked, "messages_per_day")
        hour_key = "telegram:acc:messages_per_hour"
        self.assertEqual(len(self.limiter._local_counters[hour_key]), 1)

    async def test_unknown_action_is_unlimited(self):
        self.assertEqual(
            await self.limiter.allow("telegram", ["not_a_limit"], "acc"), (True, "")
        )


class HealthMonitorTests(unittest.TestCase):
    def test_status_transitions(self):
        monitor = AccountHealthMonitor()
        self.assertEqual(monitor.evaluate("acc"), "green")

        monitor.record_action("acc", True)
        self.assertEqual(monitor.snapshot("acc")["status"], "green")

        for _ in range(5):
            monitor.record_action("acc", False)
        self.assertEqual(monitor.evaluate("acc"), "black")

        monitor.reset("acc")
        self.assertEqual(monitor.evaluate("acc"), "green")


if __name__ == "__main__":
    unittest.main()
