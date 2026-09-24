"""Telegram account warming and anti-ban strategy module.

Implements best practices for new Telegram accounts to avoid bans:
1. Registration day: minimal operations
2. Daily group join limit: max 5 groups
3. Post-join behavior: observe first, message later
4. IP consistency: same region IP for 3 months
5. Account settings: privacy, 2FA, auto-delete
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


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
        return all([
            self.interface_localized,
            self.contacts_sync_disabled,
            self.two_factor_enabled,
            self.auto_delete_enabled,
            self.privacy_settings_complete,
        ])

    @property
    def ip_consistent(self) -> bool:
        """Check if IP region is consistent with registration."""
        if not self.registration_ip_region or not self.current_ip_region:
            return True  # Can't verify, assume OK
        return self.registration_ip_region == self.current_ip_region

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

    def __init__(self):
        # In production, use Redis or database
        self._profiles: dict[str, AccountProfile] = {}

    def create_profile(
        self,
        account_id: str,
        created_at: datetime | None = None,
        ip_region: str | None = None,
    ) -> AccountProfile:
        """Create a new account profile."""
        profile = AccountProfile(
            account_id=account_id,
            created_at=created_at or datetime.now(),
            registration_ip_region=ip_region,
            current_ip_region=ip_region,
        )
        self._profiles[account_id] = profile
        logger.info("Created warming profile for account %s (age: %d days)", account_id, profile.age_days)
        return profile

    def get_profile(self, account_id: str) -> AccountProfile | None:
        """Get account profile."""
        return self._profiles.get(account_id)

    def update_ip_region(self, account_id: str, new_region: str):
        """Update current IP region and check consistency."""
        profile = self._profiles.get(account_id)
        if not profile:
            return

        old_region = profile.current_ip_region
        profile.current_ip_region = new_region

        if profile.registration_ip_region and old_region != new_region:
            if profile.age_days < profile.config.ip_consistency_days:
                logger.warning(
                    "IP region changed for account %s: %s -> %s (account age: %d days, should be consistent for %d days)",
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
        profile = self._profiles.get(account_id)
        if not profile:
            return True, "No warming profile, using default limits"

        # Check IP consistency for accounts < 90 days
        if not profile.ip_consistent and profile.age_days < 90:
            return False, f"IP region inconsistent (account age: {profile.age_days} days)"

        # Check required settings for new accounts
        if profile.account_age == AccountAge.NEW and not profile.is_fully_configured:
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
                return False, f"Daily group join limit reached ({profile.config.max_groups_per_day})"

            # Check observe time if recently joined a group
            if profile.last_group_join_time and profile.config.require_delay_after_join:
                elapsed = (datetime.now() - profile.last_group_join_time).total_seconds() / 60
                if elapsed < profile.config.min_observe_time_minutes:
                    remaining = profile.config.min_observe_time_minutes - elapsed
                    return False, f"Must observe {remaining:.0f} more minutes before next group join"

        elif operation == "send_message":
            if not profile.can_send_message(is_stranger):
                limit_type = "stranger messages" if is_stranger else "messages"
                limit = profile.config.max_stranger_messages_per_day if is_stranger else profile.config.max_messages_per_day
                return False, f"Daily {limit_type} limit reached ({limit})"

        elif operation == "friend_request":
            if not profile.can_send_friend_request():
                return False, f"Daily friend request limit reached ({profile.config.max_friend_requests_per_day})"

        return True, "Operation allowed"

    def record_operation(
        self,
        account_id: str,
        operation: str,
        is_stranger: bool = False,
    ):
        """Record an operation for tracking."""
        profile = self._profiles.get(account_id)
        if not profile:
            return

        if operation == "join_group":
            profile.record_group_join()
        elif operation == "send_message":
            profile.record_message_sent(is_stranger)
        elif operation == "friend_request":
            profile.record_friend_request()

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
        profile = self._profiles.get(account_id)
        if not profile:
            return

        valid_fields = [
            "interface_localized",
            "contacts_sync_disabled",
            "two_factor_enabled",
            "auto_delete_enabled",
            "privacy_settings_complete",
        ]

        for key, value in kwargs.items():
            if key in valid_fields:
                setattr(profile, key, value)
                logger.info("Updated %s for account %s: %s", key, account_id, value)

    def reset_daily_counters(self, account_id: str | None = None):
        """Reset daily counters for one or all accounts."""
        if account_id:
            profile = self._profiles.get(account_id)
            if profile:
                profile.reset_daily_counters()
                logger.info("Reset daily counters for account %s", account_id)
        else:
            for profile in self._profiles.values():
                profile.reset_daily_counters()
            logger.info("Reset daily counters for all accounts")


# Global instance
warming_manager = AccountWarmingManager()
