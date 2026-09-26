"""账号养号策略与限额的单元测试。"""

from datetime import datetime, timedelta

import pytest

from app.services.security.account_warming import AccountAge, AccountWarmingManager


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    """养号档案默认落在真实的 backend/state/ 下，测试必须隔离，别污染真数据。"""
    monkeypatch.setattr(
        "app.services.security.account_warming.DEFAULT_PROFILE_PATH",
        tmp_path / "warming_profiles.json",
    )


ALL_SETTINGS = {
    "interface_localized": True,
    "contacts_sync_disabled": True,
    "two_factor_enabled": True,
    "auto_delete_enabled": True,
    "privacy_settings_complete": True,
}


def _profile(
    manager: AccountWarmingManager, account_id: str, age_days: int, ip: str = "Vietnam-HCM"
):
    return manager.create_profile(
        account_id=account_id,
        created_at=datetime.now() - timedelta(days=age_days),
        ip_region=ip,
    )


class TestAccountAgeStages:
    def test_stage_boundaries(self):
        manager = AccountWarmingManager()
        cases = {
            0: AccountAge.NEW,
            7: AccountAge.WARMING,
            30: AccountAge.STABLE,
            90: AccountAge.MATURE,
        }
        for age, expected in cases.items():
            profile = _profile(manager, f"acc-{age}", age)
            assert profile.account_age is expected, f"{age} 天应为 {expected}"

    def test_limits_increase_with_age(self):
        manager = AccountWarmingManager()
        new = _profile(manager, "new", 3).config
        warming = _profile(manager, "warming", 15).config
        stable = _profile(manager, "stable", 40).config
        mature = _profile(manager, "mature", 120).config
        assert [c.max_groups_per_day for c in (new, warming, stable, mature)] == [2, 5, 8, 15]
        assert new.max_messages_per_day == 20
        assert mature.max_messages_per_day == 200


class TestLimitEnforcement:
    def test_new_account_blocked_until_required_settings_done(self):
        manager = AccountWarmingManager()
        _profile(manager, "acc", 2)
        allowed, reason = manager.check_and_enforce_limits("acc", "join_group")
        assert allowed is False
        assert "Missing required settings" in reason

    def test_new_account_allowed_after_settings_completed(self):
        manager = AccountWarmingManager()
        _profile(manager, "acc", 2)
        manager.update_settings("acc", **ALL_SETTINGS)
        allowed, reason = manager.check_and_enforce_limits("acc", "join_group")
        assert allowed is True, reason

    def test_group_join_daily_limit_is_enforced(self):
        manager = AccountWarmingManager()
        profile = _profile(manager, "acc", 2)
        manager.update_settings("acc", **ALL_SETTINGS)
        for _ in range(profile.config.max_groups_per_day):
            manager.record_operation("acc", "join_group")
        allowed, reason = manager.check_and_enforce_limits("acc", "join_group")
        assert allowed is False
        assert "Daily group join limit reached" in reason

    def test_observe_time_required_after_joining_group(self):
        manager = AccountWarmingManager()
        _profile(manager, "acc", 2)
        manager.update_settings("acc", **ALL_SETTINGS)
        manager.record_operation("acc", "join_group")
        allowed, reason = manager.check_and_enforce_limits("acc", "join_group")
        assert allowed is False
        assert "Must observe" in reason

    def test_mature_account_has_no_observe_time(self):
        manager = AccountWarmingManager()
        _profile(manager, "acc", 120)
        manager.record_operation("acc", "join_group")
        allowed, reason = manager.check_and_enforce_limits("acc", "join_group")
        assert allowed is True, reason

    def test_stranger_message_limit_is_separate(self):
        manager = AccountWarmingManager()
        profile = _profile(manager, "acc", 2)
        manager.update_settings("acc", **ALL_SETTINGS)
        for _ in range(profile.config.max_stranger_messages_per_day):
            manager.record_operation("acc", "send_message", is_stranger=True)
        allowed, reason = manager.check_and_enforce_limits("acc", "send_message", is_stranger=True)
        assert allowed is False
        assert "stranger messages" in reason
        # 普通消息额度不受影响
        allowed, _ = manager.check_and_enforce_limits("acc", "send_message", is_stranger=False)
        assert allowed is True

    def test_ip_region_change_blocks_young_account(self):
        manager = AccountWarmingManager()
        _profile(manager, "acc", 10, ip="Vietnam-HCM")
        manager.update_ip_region("acc", "Vietnam-Hanoi")
        allowed, reason = manager.check_and_enforce_limits("acc", "join_group")
        assert allowed is False
        assert "IP region inconsistent" in reason

    def test_unknown_account_uses_defaults(self):
        manager = AccountWarmingManager()
        allowed, reason = manager.check_and_enforce_limits("missing", "join_group")
        assert allowed is True
        assert "No warming profile" in reason

    def test_reset_daily_counters(self):
        manager = AccountWarmingManager()
        profile = _profile(manager, "acc", 120)
        manager.record_operation("acc", "join_group")
        manager.record_operation("acc", "send_message")
        assert profile.groups_joined_today == 1
        manager.reset_daily_counters("acc")
        assert profile.groups_joined_today == 0
        assert profile.messages_sent_today == 0
