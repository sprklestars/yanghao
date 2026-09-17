import asyncio
import logging
import random
import time

logger = logging.getLogger(__name__)


class RateLimiter:
    """Redis-backed sliding window rate limiter with behavioral simulation."""

    LIMITS = {
        "telegram": {
            "messages_per_hour": 20,
            "messages_per_day": 100,
            "group_joins_per_day": 3,
            "friend_requests_per_day": 5,
        },
        "facebook": {
            "messages_per_hour": 10,
            "messages_per_day": 50,
            "group_joins_per_day": 2,
            "friend_requests_per_day": 5,
        },
        "zalo": {
            "messages_per_hour": 15,
            "messages_per_day": 80,
            "group_joins_per_day": 2,
            "friend_requests_per_day": 3,
        },
    }

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._local_counters: dict[str, list[float]] = {}

    async def check_and_consume(self, platform: str, action: str, account_id: str) -> bool:
        key = f"{platform}:{account_id}:{action}"
        now = time.time()

        limits = self.LIMITS.get(platform, {})
        if action not in limits:
            return True

        limit = limits[action]

        # local fallback when Redis is unavailable
        if self._redis is None:
            timestamps = self._local_counters.get(key, [])
            window_start = now - 3600 if "hour" in action else now - 86400
            timestamps = [t for t in timestamps if t > window_start]
            if len(timestamps) >= limit:
                return False
            timestamps.append(now)
            self._local_counters[key] = timestamps
            return True

        # Redis sliding window
        window = 3600 if "hour" in action else 86400
        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zcard(key)
        results = await pipe.execute()
        current_count = results[1]

        if current_count >= limit:
            return False

        await self._redis.zadd(key, {str(now): now})
        await self._redis.expire(key, window + 60)
        return True

    async def simulate_typing_delay(self, text: str) -> None:
        chars = len(text)
        base_delay = chars * 0.05
        jitter = base_delay * random.uniform(-0.3, 0.3)
        delay = max(0.5, min(base_delay + jitter, 10))
        await asyncio.sleep(delay)

    async def simulate_reading_delay(self) -> None:
        delay = random.uniform(5, 45)
        await asyncio.sleep(delay)

    async def simulate_action_cooldown(self) -> None:
        delay = random.uniform(30, 120)
        await asyncio.sleep(delay)

    def is_active_hours(self, tz_offset: int = 7) -> bool:
        """Check if current time is within Vietnam active hours (8:00-23:00 UTC+7)."""
        import datetime
        utc_now = datetime.datetime.now(datetime.timezone.utc)
        vn_now = utc_now + datetime.timedelta(hours=tz_offset)
        hour = vn_now.hour
        return 8 <= hour < 23


class AccountHealthMonitor:
    THRESHOLDS = {
        "daily_messages_max": 50,
        "error_rate_critical": 0.2,
        "consecutive_failures_pause": 5,
    }

    def __init__(self):
        self._stats: dict[str, dict] = {}

    def record_action(self, account_id: str, success: bool) -> None:
        stats = self._stats.setdefault(account_id, {
            "total": 0, "errors": 0, "consecutive_failures": 0, "daily_count": 0,
        })
        stats["total"] += 1
        stats["daily_count"] += 1
        if success:
            stats["consecutive_failures"] = 0
        else:
            stats["errors"] += 1
            stats["consecutive_failures"] += 1

    def evaluate(self, account_id: str) -> str:
        stats = self._stats.get(account_id)
        if not stats or stats["total"] == 0:
            return "green"

        error_rate = stats["errors"] / stats["total"]
        consec = stats["consecutive_failures"]
        daily = stats["daily_count"]

        if consec >= self.THRESHOLDS["consecutive_failures_pause"]:
            return "black"
        if error_rate >= self.THRESHOLDS["error_rate_critical"]:
            return "red"
        if error_rate > 0.1 or daily > self.THRESHOLDS["daily_messages_max"]:
            return "yellow"
        return "green"
