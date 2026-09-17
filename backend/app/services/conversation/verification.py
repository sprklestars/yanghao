"""Arithmetic verification module to filter out bots and automated scripts."""

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class VerificationChallenge:
    """Represents an arithmetic challenge for user verification."""
    question: str
    answer: int
    created_at: datetime = field(default_factory=datetime.now)
    ttl_seconds: int = 900  # 15 minutes

    def is_expired(self) -> bool:
        return datetime.now() > self.created_at + timedelta(seconds=self.ttl_seconds)


class VerificationManager:
    """Manages verification challenges for conversations.

    Each target user must pass a simple arithmetic test before the conversation
    engine starts real dialogue. This helps filter out bots and automated scripts.
    """

    def __init__(self):
        # In-memory storage: {target_user_id: VerificationChallenge}
        # For production, this should be moved to Redis
        self._challenges: dict[str, VerificationChallenge] = {}
        self._verified_users: set[str] = set()

    def create_challenge(self) -> VerificationChallenge:
        """Generate a random arithmetic challenge (addition or subtraction)."""
        left = random.randint(10, 99)
        right = random.randint(10, 99)
        use_subtraction = random.choice([True, False])

        if use_subtraction:
            # Ensure non-negative result
            first = max(left, right)
            second = min(left, right)
            operator = "-"
            answer = first - second
        else:
            first = left
            second = right
            operator = "+"
            answer = first + second

        question = f"{first} {operator} {second} = ?"
        return VerificationChallenge(question=question, answer=answer)

    def start_verification(self, target_user_id: str) -> VerificationChallenge:
        """Start verification process for a new user."""
        challenge = self.create_challenge()
        self._challenges[target_user_id] = challenge
        logger.info("Created verification challenge for %s: %s", target_user_id, challenge.question)
        return challenge

    def check_answer(self, target_user_id: str, user_answer: str) -> bool:
        """Check if the user's answer is correct.

        Returns True if verified, False otherwise.
        """
        challenge = self._challenges.get(target_user_id)
        if not challenge:
            logger.warning("No challenge found for %s", target_user_id)
            return False

        if challenge.is_expired():
            logger.warning("Challenge expired for %s", target_user_id)
            del self._challenges[target_user_id]
            return False

        # Normalize input (handle full-width digits)
        normalized = self._normalize_digits(user_answer.strip())

        try:
            answer_int = int(normalized)
            is_correct = answer_int == challenge.answer
        except ValueError:
            is_correct = False

        if is_correct:
            self._verified_users.add(target_user_id)
            del self._challenges[target_user_id]
            logger.info("User %s passed verification", target_user_id)
        else:
            logger.info("User %s failed verification (answered: %s)", target_user_id, user_answer)

        return is_correct

    def is_verified(self, target_user_id: str) -> bool:
        """Check if a user has already passed verification."""
        return target_user_id in self._verified_users

    def get_challenge_message(self, target_user_id: str) -> str | None:
        """Get the verification message to send to user.

        Returns the challenge question if user needs verification, None if already verified.
        """
        if self.is_verified(target_user_id):
            return None

        challenge = self._challenges.get(target_user_id)
        if not challenge:
            challenge = self.start_verification(target_user_id)

        return (
            "👋 Chào bạn! Để đảm bảo an toàn, vui lòng trả lời câu hỏi đơn giản sau:\n\n"
            f"{challenge.question}\n\n"
            "Hãy trả lời bằng số. Thời hạn: 15 phút."
        )

    @staticmethod
    def _normalize_digits(text: str) -> str:
        """Convert full-width digits to normal digits."""
        return text.translate(str.maketrans(
            "０１２３４５６７８９",
            "0123456789"
        ))

    def cleanup_expired(self):
        """Remove expired challenges to prevent memory leak."""
        now = datetime.now()
        expired = [
            uid for uid, challenge in self._challenges.items()
            if now > challenge.created_at + timedelta(seconds=challenge.ttl_seconds)
        ]
        for uid in expired:
            del self._challenges[uid]
        if expired:
            logger.info("Cleaned up %d expired challenges", len(expired))


# Global instance
verification_manager = VerificationManager()
