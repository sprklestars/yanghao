"""算术验证模块（机器人过滤）的单元测试。"""

import re
from datetime import datetime, timedelta

from app.services.conversation.verification import (
    VerificationChallenge,
    VerificationManager,
)


def _parse_question(question: str) -> tuple[int, str, int]:
    match = re.search(r"(\d+)\s*([+\-])\s*(\d+)", question)
    assert match, f"题目格式不符合预期: {question}"
    return int(match.group(1)), match.group(2), int(match.group(3))


class TestChallengeGeneration:
    def test_question_and_answer_are_consistent(self):
        manager = VerificationManager()
        for _ in range(50):
            challenge = manager.create_challenge()
            left, operator, right = _parse_question(challenge.question)
            expected = left + right if operator == "+" else left - right
            assert challenge.answer == expected
            assert challenge.answer >= 0, "减法结果不应为负数"
            assert 10 <= left <= 99 and 10 <= right <= 99

    def test_challenge_is_15_minutes(self):
        challenge = VerificationManager().create_challenge()
        assert challenge.ttl_seconds == 900
        assert not challenge.is_expired()


class TestVerificationFlow:
    def setup_method(self):
        self.manager = VerificationManager()
        self.user = "user-1"

    def test_correct_answer_verifies_user(self):
        challenge = self.manager.start_verification(self.user)
        assert self.manager.check_answer(self.user, str(challenge.answer)) is True
        assert self.manager.is_verified(self.user) is True
        # 已验证用户不再收到验证题
        assert self.manager.get_challenge_message(self.user) is None

    def test_wrong_answer_does_not_verify(self):
        challenge = self.manager.start_verification(self.user)
        assert self.manager.check_answer(self.user, str(challenge.answer + 1)) is False
        assert self.manager.is_verified(self.user) is False

    def test_non_numeric_answer_does_not_raise(self):
        self.manager.start_verification(self.user)
        assert self.manager.check_answer(self.user, "不知道") is False

    def test_answer_with_full_width_digits_is_normalized(self):
        challenge = self.manager.start_verification(self.user)
        full_width = str(challenge.answer).translate(
            str.maketrans("0123456789", "０１２３４５６７８９")
        )
        assert self.manager.check_answer(self.user, full_width) is True

    def test_answer_with_surrounding_spaces_is_accepted(self):
        challenge = self.manager.start_verification(self.user)
        assert self.manager.check_answer(self.user, f"  {challenge.answer}  ") is True

    def test_expired_challenge_is_rejected(self):
        self.manager._challenges[self.user] = VerificationChallenge(
            question="1 + 1 = ?",
            answer=2,
            created_at=datetime.now() - timedelta(minutes=16),
        )
        assert self.manager.check_answer(self.user, "2") is False
        assert self.user not in self.manager._challenges, "过期题目应被清理"

    def test_challenge_message_only_created_once_per_user(self):
        first = self.manager.get_challenge_message(self.user)
        second = self.manager.get_challenge_message(self.user)
        assert first == second, "同一用户重复调用应返回同一道题"
        assert "15 phút" in first, "验证消息应包含有效期说明"

    def test_cleanup_expired_removes_only_expired(self):
        self.manager.start_verification("fresh")
        self.manager._challenges["stale"] = VerificationChallenge(
            question="1 + 1 = ?",
            answer=2,
            created_at=datetime.now() - timedelta(minutes=30),
        )
        self.manager.cleanup_expired()
        assert "stale" not in self.manager._challenges
        assert "fresh" in self.manager._challenges
