"""Telegram account warming and anti-ban strategy module.

Implements best practices for new Telegram accounts to avoid bans:
1. Registration day: minimal operations
2. Daily group join limit: max 5 groups
3. Post-join behavior: observe first, message later
4. IP consistency: same region IP for 3 months
5. Account settings: privacy, 2FA, auto-delete
"""

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from app.core.json_store import JsonStore

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[3]
DEFAULT_PROFILE_PATH = BACKEND_DIR / "state" / "warming_profiles.json"


class AccountAge(Enum):
    """Account age categories for warming strategy."""

    NEW = "new"  # 0-7 days
    WARMING = "warming"  # 8-30 days
    STABLE = "stable"  # 31-90 days
    MATURE = "mature"  # 90+ days


@dataclass
class WarmingConfig:
    """Configuration for account warming based on account age."""

    # Group join limits
    max_groups_per_day: int

    # Message limits
    max_messages_per_hour: int
    max_messages_per_day: int
    max_stranger_messages_per_day: int

    # Friend request limits
    max_friend_requests_per_day: int

    # Behavior settings
    min_observe_time_minutes: int  # Time to observe before messaging in new group
    require_delay_after_join: bool  # Whether to delay after joining group

    # IP consistency (days)
    ip_consistency_days: int = 90  # Keep same region IP for 3 months


# Predefined warming configs by account age
WARMING_CONFIGS = {
    AccountAge.NEW: WarmingConfig(
        max_groups_per_day=2,
        max_messages_per_hour=5,
        max_messages_per_day=20,
        max_stranger_messages_per_day=3,
        max_friend_requests_per_day=1,
        min_observe_time_minutes=30,
        require_delay_after_join=True,
    ),
    AccountAge.WARMING: WarmingConfig(
        max_groups_per_day=5,
        max_messages_per_hour=10,
        max_messages_per_day=50,
        max_stranger_messages_per_day=8,
        max_friend_requests_per_day=3,
        min_observe_time_minutes=15,
        require_delay_after_join=True,
    ),
    AccountAge.STABLE: WarmingConfig(
        max_groups_per_day=8,
        max_messages_per_hour=20,
        max_messages_per_day=100,
        max_stranger_messages_per_day=15,
        max_friend_requests_per_day=5,
        min_observe_time_minutes=5,
        require_delay_after_join=False,
    ),
    AccountAge.MATURE: WarmingConfig(
        max_groups_per_day=15,
        max_messages_per_hour=30,
        max_messages_per_day=200,
        max_stranger_messages_per_day=30,
        max_friend_requests_per_day=10,
        min_observe_time_minutes=0,
        require_delay_after_join=False,
    ),
}


@dataclass
class AccountProfile:
    """Tracks account warming status and settings."""

    account_id: str
    created_at: datetime
    registration_ip_region: str | None = None  # IP region at registration
    current_ip_region: str | None = None

    # Settings checklist (from the image)
    interface_localized: bool = False  # 汉化界面
    contacts_sync_disabled: bool = False  # 关闭通讯录同步
    two_factor_enabled: bool = False  # 开启两步验证
    auto_delete_enabled: bool = False  # 启用自动删除
    privacy_settings_complete: bool = False  # 补全隐私设置

    # 是否强制要求上面 5 项自检全部完成（新号）。默认 False：
    # 自动建立的档案只套用数字限额，避免刚接入就把现有账号卡死；
    # 想严格执行"新号必须先完成自检"时，把它设为 True。
    enforce_setup_check: bool = True

    # Operation tracking
    groups_joined_today: int = 0
    messages_sent_today: int = 0
    stranger_messages_today: int = 0
    friend_requests_today: int = 0
    last_group_join_time: datetime | None = None

    @property
    def age_days(self) -> int:
        return (datetime.now() - self.created_at).days

    @property
    def account_age(self) -> AccountAge:
        if self.age_days < 7:
            return AccountAge.NEW
        elif self.age_days < 30:
            return AccountAge.WARMING
        elif self.age_days < 90:
            return AccountAge.STABLE
        else:
            return AccountAge.MATURE

    @property
    def config(self) -> WarmingConfig:
        return WARMING_CONFIGS[self.account_age]

    @property
    def is_fully_configured(self) -> bool:
        """Check if all required settings are configured."""
        return all(
            [
                self.interface_localized,
                self.contacts_sync_disabled,
                self.two_factor_enabled,
                self.auto_delete_enabled,
                self.privacy_settings_complete,
            ]
        )

    @property
    def ip_consistent(self) -> bool:
        """Check if IP region is consistent with registration."""
        if not self.registration_ip_region or not self.current_ip_region:
            return True  # Can't verify, assume OK
        return self.registration_ip_region == self.current_ip_region

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "created_at": self.created_at.isoformat(),
            "registration_ip_region": self.registration_ip_region,
            "current_ip_region": self.current_ip_region,
            "interface_localized": self.interface_localized,
            "contacts_sync_disabled": self.contacts_sync_disabled,
            "two_factor_enabled": self.two_factor_enabled,
            "auto_delete_enabled": self.auto_delete_enabled,
            "privacy_settings_complete": self.privacy_settings_complete,
            "enforce_setup_check": self.enforce_setup_check,
            "groups_joined_today": self.groups_joined_today,
            "messages_sent_today": self.messages_sent_today,
            "stranger_messages_today": self.stranger_messages_today,
            "friend_requests_today": self.friend_requests_today,
            "last_group_join_time": (
                self.last_group_join_time.isoformat() if self.last_group_join_time else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AccountProfile":
        created = data.get("created_at")
        last_join = data.get("last_group_join_time")
        return cls(
            account_id=str(data.get("account_id", "")),
            created_at=datetime.fromisoformat(created) if created else datetime.now(),
            registration_ip_region=data.get("registration_ip_region"),
            current_ip_region=data.get("current_ip_region"),
            interface_localized=bool(data.get("interface_localized", False)),
            contacts_sync_disabled=bool(data.get("contacts_sync_disabled", False)),
            two_factor_enabled=bool(data.get("two_factor_enabled", False)),
            auto_delete_enabled=bool(data.get("auto_delete_enabled", False)),
            privacy_settings_complete=bool(data.get("privacy_settings_complete", False)),
            enforce_setup_check=bool(data.get("enforce_setup_check", False)),
            groups_joined_today=int(data.get("groups_joined_today", 0) or 0),
            messages_sent_today=int(data.get("messages_sent_today", 0) or 0),
            stranger_messages_today=int(data.get("stranger_messages_today", 0) or 0),
            friend_requests_today=int(data.get("friend_requests_today", 0) or 0),
            last_group_join_time=(
                datetime.fromisoformat(last_join) if last_join else None
            ),
        )

    def can_join_group(self) -> bool:
        """Check if account can join another group today."""
        return self.groups_joined_today < self.config.max_groups_per_day

    def can_send_message(self, is_stranger: bool = False) -> bool:
        """Check if account can send more messages today."""
        if is_stranger:
            return self.stranger_messages_today < self.config.max_stranger_messages_per_day
        return self.messages_sent_today < self.config.max_messages_per_day

    def can_send_friend_request(self) -> bool:
        """Check if account can send more friend requests today."""
        return self.friend_requests_today < self.config.max_friend_requests_per_day

    def record_group_join(self):
        """Record a group join operation."""
        self.groups_joined_today += 1
        self.last_group_join_time = datetime.now()

    def record_message_sent(self, is_stranger: bool = False):
        """Record a message sent."""
        self.messages_sent_today += 1
        if is_stranger:
            self.stranger_messages_today += 1

    def record_friend_request(self):
        """Record a friend request sent."""
        self.friend_requests_today += 1

    def reset_daily_counters(self):
        """Reset daily counters (call this at midnight or start of day)."""
        self.groups_joined_today = 0
        self.messages_sent_today = 0
        self.stranger_messages_today = 0
        self.friend_requests_today = 0


class AccountWarmingManager:
    """Manages account warming strategies and enforces limits."""

    def __init__(self, path: Path | str | None = None):
        # 档案落到 backend/state/warming_profiles.json：守护进程和 API 共享，
        # 重启后限额不会"失忆"（以前是纯内存字典，重启即清空）。
        self._path = Path(path) if path else DEFAULT_PROFILE_PATH
        self._lock = threading.RLock()
        self._store = JsonStore(self._path)
        self._profiles: dict[str, AccountProfile] = {}
        self._reload()

    # ── 文件读写 ──
    def _refresh(self) -> None:
        """别的进程改过文件才重载：避免每次访问都换掉档案对象（调用方可能还持有引用）。"""
        if self._store.changed():
            self._reload()

    def _reload(self) -> None:
        raw = self._store.load()
        profiles: dict[str, AccountProfile] = {}
        for account_id, data in raw.items():
            try:
                profiles[account_id] = AccountProfile.from_dict(
                    {**(data or {}), "account_id": account_id}
                )
            except (TypeError, ValueError) as e:
                logger.warning("跳过损坏的养号档案 %s: %s", account_id, e)
        self._profiles = profiles

    def _save(self) -> None:
        self._store.save({aid: profile.to_dict() for aid, profile in self._profiles.items()})

    def ensure_profile(
        self,
        account_id: str,
        created_at: datetime | None = None,
        ip_region: str | None = None,
    ) -> AccountProfile:
        """没有档案就补一个（用会话文件时间近似账号注册时间），有则原样返回。

        自动补的档案默认只套用**数字限额**（日加群/发消息等），不强制"新号 5 项自检"——
        否则刚接入存量账号会被直接卡死。需要严格模式就把它设成 True
        （``PATCH /accounts/{id}/warming {"enforce_setup_check": true}``）。
        """
        with self._lock:
            self._refresh()
            profile = self._profiles.get(account_id)
            if profile is not None:
                return profile
            return self._create_locked(
                account_id, created_at, ip_region, enforce_setup_check=False
            )

    def create_profile(
        self,
        account_id: str,
        created_at: datetime | None = None,
        ip_region: str | None = None,
    ) -> AccountProfile:
        """Create a new account profile."""
        with self._lock:
            self._refresh()
            return self._create_locked(
                account_id, created_at, ip_region, enforce_setup_check=True
            )

    def _create_locked(
        self,
        account_id: str,
        created_at: datetime | None,
        ip_region: str | None,
        enforce_setup_check: bool = True,
    ) -> AccountProfile:
        profile = AccountProfile(
            account_id=account_id,
            created_at=created_at or datetime.now(),
            registration_ip_region=ip_region,
            current_ip_region=ip_region,
            enforce_setup_check=enforce_setup_check,
        )
        self._profiles[account_id] = profile
        self._save()
        logger.info(
            "Created warming profile for account %s (age: %d days)", account_id, profile.age_days
        )
        return profile

    def get_profile(self, account_id: str) -> AccountProfile | None:
        """Get account profile."""
        with self._lock:
            self._refresh()
            return self._profiles.get(account_id)

    def update_ip_region(self, account_id: str, new_region: str):
        """Update current IP region and check consistency."""
        with self._lock:
            self._refresh()
            profile = self._profiles.get(account_id)
        if not profile:
            return

        old_region = profile.current_ip_region
        profile.current_ip_region = new_region
        with self._lock:
            self._save()

        if profile.registration_ip_region and old_region != new_region:
            if profile.age_days < profile.config.ip_consistency_days:
                logger.warning(
                    "IP region changed for account %s: %s -> %s "
                    "(account age: %d days, should be consistent for %d days)",
                    account_id,
                    old_region,
                    new_region,
                    profile.age_days,
                    profile.config.ip_consistency_days,
                )

    def check_and_enforce_limits(
        self,
        account_id: str,
        operation: str,  # "join_group", "send_message", "friend_request"
        is_stranger: bool = False,
    ) -> tuple[bool, str]:
        """Check if operation is allowed under warming strategy.

        Returns: (allowed, reason)
        """
        with self._lock:
            self._refresh()
            profile = self._profiles.get(account_id)
        if not profile:
            return True, "No warming profile, using default limits"

        # Check IP consistency for accounts < 90 days
        if not profile.ip_consistent and profile.age_days < 90:
            return False, f"IP region inconsistent (account age: {profile.age_days} days)"

        # Check required settings for new accounts
        if (
            profile.account_age == AccountAge.NEW
            and profile.enforce_setup_check
            and not profile.is_fully_configured
        ):
            missing = []
            if not profile.interface_localized:
                missing.append("interface localization")
            if not profile.contacts_sync_disabled:
                missing.append("contacts sync disabled")
            if not profile.two_factor_enabled:
                missing.append("2FA enabled")
            if not profile.auto_delete_enabled:
                missing.append("auto-delete enabled")
            if not profile.privacy_settings_complete:
                missing.append("privacy settings")

            return False, f"Missing required settings: {', '.join(missing)}"

        # Check operation-specific limits
        if operation == "join_group":
            if not profile.can_join_group():
                return (
                    False,
                    f"Daily group join limit reached ({profile.config.max_groups_per_day})",
                )

            # Check observe time if recently joined a group
            if profile.last_group_join_time and profile.config.require_delay_after_join:
                elapsed = (datetime.now() - profile.last_group_join_time).total_seconds() / 60
                if elapsed < profile.config.min_observe_time_minutes:
                    remaining = profile.config.min_observe_time_minutes - elapsed
                    return (
                        False,
                        f"Must observe {remaining:.0f} more minutes before next group join",
                    )

        elif operation == "send_message":
            if not profile.can_send_message(is_stranger):
                limit_type = "stranger messages" if is_stranger else "messages"
                limit = (
                    profile.config.max_stranger_messages_per_day
                    if is_stranger
                    else profile.config.max_messages_per_day
                )
                return False, f"Daily {limit_type} limit reached ({limit})"

        elif operation == "friend_request":
            if not profile.can_send_friend_request():
                return (
                    False,
                    f"Daily friend request limit reached "
                    f"({profile.config.max_friend_requests_per_day})",
                )

        return True, "Operation allowed"

    def record_operation(
        self,
        account_id: str,
        operation: str,
        is_stranger: bool = False,
    ):
        """Record an operation for tracking."""
        with self._lock:
            self._refresh()
            profile = self._profiles.get(account_id)
            if not profile:
                return

        if operation == "join_group":
            profile.record_group_join()
        elif operation == "send_message":
            profile.record_message_sent(is_stranger)
        elif operation == "friend_request":
            profile.record_friend_request()

        with self._lock:
            self._save()

        logger.debug(
            "Recorded %s for account %s (today: %d groups, %d msgs, %d strangers, %d friends)",
            operation,
            account_id,
            profile.groups_joined_today,
            profile.messages_sent_today,
            profile.stranger_messages_today,
            profile.friend_requests_today,
        )

    def update_settings(
        self,
        account_id: str,
        **kwargs,
    ):
        """Update account settings."""
        with self._lock:
            self._refresh()
            profile = self._profiles.get(account_id)
            if not profile:
                return

        valid_fields = [
            "interface_localized",
            "contacts_sync_disabled",
            "two_factor_enabled",
            "auto_delete_enabled",
            "privacy_settings_complete",
            "enforce_setup_check",
        ]

        for key, value in kwargs.items():
            if key in valid_fields:
                setattr(profile, key, value)
                logger.info("Updated %s for account %s: %s", key, account_id, value)

        # 允许纠正"账号注册时间"：阶段（NEW/WARMING/...）是按它推算的
        created_at = kwargs.get("created_at")
        if isinstance(created_at, datetime):
            profile.created_at = created_at
            logger.info("Updated created_at for account %s: %s", account_id, created_at)

        with self._lock:
            self._save()

    def reset_daily_counters(self, account_id: str | None = None):
        """Reset daily counters for one or all accounts."""
        with self._lock:
            self._refresh()
        if account_id:
            profile = self._profiles.get(account_id)
            if profile:
                profile.reset_daily_counters()
                logger.info("Reset daily counters for account %s", account_id)
        else:
            for profile in self._profiles.values():
                profile.reset_daily_counters()
            logger.info("Reset daily counters for all accounts")
        with self._lock:
            self._save()


# Global instance
warming_manager = AccountWarmingManager()
