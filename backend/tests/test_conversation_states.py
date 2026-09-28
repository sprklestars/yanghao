"""对话状态机迁移规则的单元测试（纯逻辑，不调用 LLM）。

`_transition_state` 不使用实例状态，所以这里用 None 当 self 调用，
避免为了测试去构造会创建 LLM 客户端的 ConversationEngine 实例。
"""

from app.services.conversation.engine import ConversationEngine, ConvState

transition = ConversationEngine._transition_state


def test_new_conversation_requires_verification():
    assert transition(None, ConvState.IDLE, "Xin chào", "", 0) is ConvState.VERIFICATION


def test_verification_moves_to_greeting():
    assert transition(None, ConvState.VERIFICATION, "100", "", 1) is ConvState.GREETING


def test_greeting_moves_to_probing_after_two_turns():
    assert transition(None, ConvState.GREETING, "ok", "", 1) is ConvState.GREETING
    assert transition(None, ConvState.GREETING, "ok", "", 2) is ConvState.PROBING


def test_business_signal_triggers_extraction():
    assert transition(None, ConvState.PROBING, "giá bao nhiêu?", "", 3) is ConvState.EXTRACTION
    assert transition(None, ConvState.PROBING, "cho mình xin zalo", "", 3) is ConvState.EXTRACTION


def test_probing_without_progress_pivots_after_eight_turns():
    assert transition(None, ConvState.PROBING, "hmm", "", 8) is ConvState.PROBING
    assert transition(None, ConvState.PROBING, "hmm", "", 9) is ConvState.PIVOT


def test_pivot_returns_to_probing():
    assert transition(None, ConvState.PIVOT, "à vậy à", "", 9) is ConvState.PROBING


def test_extraction_exits_after_fifteen_turns():
    assert transition(None, ConvState.EXTRACTION, "ok", "", 15) is ConvState.EXTRACTION
    assert transition(None, ConvState.EXTRACTION, "ok", "", 16) is ConvState.EXIT


def test_alert_keywords_trigger_cooldown():
    for message in ["mày là bot à", "you are a scam", "tôi sẽ báo công an", "police"]:
        assert transition(None, ConvState.PROBING, message, "", 3) is ConvState.COOLDOWN


def test_cooldown_leads_to_exit():
    assert transition(None, ConvState.COOLDOWN, "xin lỗi", "", 4) is ConvState.EXIT
