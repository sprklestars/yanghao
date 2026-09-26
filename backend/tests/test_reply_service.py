import unittest

from app.models.models import ConversationState
from app.services.conversation.engine import ConvState, db_state_for, engine_state_from


class ReplyServiceStateMappingTests(unittest.TestCase):
    def test_verification_maps_to_idle(self):
        # DB 枚举没有 VERIFICATION，验证挑战是瞬态的
        self.assertEqual(db_state_for(ConvState.VERIFICATION), ConversationState.IDLE)

    def test_other_states_roundtrip(self):
        for engine_state in ConvState:
            if engine_state == ConvState.VERIFICATION:
                continue
            with self.subTest(engine_state=engine_state):
                self.assertEqual(engine_state_from(db_state_for(engine_state)), engine_state)

    def test_db_state_to_engine(self):
        self.assertEqual(engine_state_from(ConversationState.PROBING), ConvState.PROBING)
        self.assertEqual(engine_state_from(ConversationState.EXIT), ConvState.EXIT)


if __name__ == "__main__":
    unittest.main()
