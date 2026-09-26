import logging
from enum import Enum

from openai import AsyncOpenAI

from app.core.config import settings
from app.models.models import ConversationState
from app.services.conversation.script_library import (
    load_default_scripts,
    select_best_template,
)
from app.services.conversation.verification import verification_manager

logger = logging.getLogger(__name__)


class ConvState(str, Enum):
    IDLE = "idle"
    VERIFICATION = "verification"  # New state for arithmetic verification
    GREETING = "greeting"
    PROBING = "probing"
    EXTRACTION = "extraction"
    PIVOT = "pivot"
    EXIT = "exit"
    COOLDOWN = "cooldown"


def db_state_for(engine_state: ConvState) -> ConversationState:
    """引擎 8 态 → DB 7 态。VERIFICATION 是瞬态挑战，落库时回 IDLE。"""
    if engine_state == ConvState.VERIFICATION:
        return ConversationState.IDLE
    return ConversationState(engine_state.value)


def engine_state_from(db_state: ConversationState) -> ConvState:
    return ConvState(db_state.value)


# 预加载话术库（A/B 的 effectiveness_score 会随 usage 更新）
_SCRIPT_LIBRARY = load_default_scripts()

# 状态机 → 话术库的 stage 名（greeting/extraction/pivot/exit 在库里是 category="general"）
_STAGE_FOR_STATE = {
    ConvState.GREETING: "greeting",
    ConvState.PROBING: "probing",
    ConvState.EXTRACTION: "extraction",
    ConvState.PIVOT: "pivot",
    ConvState.EXIT: "exit",
}


SYSTEM_PROMPT_TEMPLATE = """\
You are role-playing as {name}, a {age}-year-old {occupation} living in {location}.

Backstory: {backstory}

Language rules:
- Primary language: Vietnamese (vi)
- You can also respond in Chinese (zh) or English (en) if the other person uses those languages
- Match the language the other person is using

Conversation style:
- Tone: {tone}
- Average message length: 15-40 words
- Use emoji occasionally but not excessively
- Make occasional minor typos (about 5% of messages) then self-correct naturally
- Never reveal you are an AI or automated system
- Stay in character at all times

Current objective: {objective}
Target category: {category}

Safety rules:
- Never discuss violence, weapons, drugs, minors, or political topics
- If the other person seems suspicious or hostile, politely end the conversation
- Never share real personal information beyond your persona
- Do not make promises or commitments on behalf of anyone
"""

STAGE_HINTS = {
    ConvState.VERIFICATION: (
        "The user needs to pass a simple arithmetic verification. "
        "Wait for their answer and check if it's correct."
    ),
    ConvState.GREETING: "Start with a friendly greeting. Be casual and warm. Keep it short.",
    ConvState.PROBING: (
        "Ask natural questions related to {category}. Show genuine curiosity. Don't be pushy."
    ),
    ConvState.EXTRACTION: (
        "The person seems interested. Ask for more details: contact info, "
        "pricing, website, specific services. Be polite."
    ),
    ConvState.PIVOT: (
        "The current topic isn't yielding results. Shift to a related angle naturally."
    ),
    ConvState.EXIT: "Wrap up politely. Thank them and say you'll follow up later.",
    ConvState.COOLDOWN: (
        "The person seems wary. Apologize if needed, say goodbye gracefully. "
        "Do NOT continue probing."
    ),
}


class ConversationEngine:
    def __init__(self):
        self._client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        self._model = settings.deepseek_model

    async def generate_response(
        self,
        incoming_message: str,
        persona_config: dict,
        state: ConvState,
        category: str,
        history: list[dict[str, str]],
        target_user_id: str | None = None,
        context_summary: str | None = None,
    ) -> tuple[str, ConvState]:
        # Handle verification first
        if state == ConvState.IDLE and target_user_id:
            if not verification_manager.is_verified(target_user_id):
                # Check if this is a verification answer
                challenge_msg = verification_manager.get_challenge_message(target_user_id)
                if challenge_msg:
                    return challenge_msg, ConvState.VERIFICATION

                # User sent an answer, check it
                if verification_manager.check_answer(target_user_id, incoming_message):
                    reply = "✅ Xác minh thành công! Bây giờ chúng ta có thể bắt đầu trò chuyện."
                    return reply, ConvState.GREETING
                else:
                    reply = (
                        "❌ Câu trả lời không đúng. Vui lòng thử lại hoặc liên hệ quản trị viên."
                    )
                    return reply, ConvState.COOLDOWN

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            name=persona_config.get("name", "User"),
            age=persona_config.get("age", 28),
            occupation=persona_config.get("occupation", "freelancer"),
            location=persona_config.get("location", "Ho Chi Minh City"),
            backstory=persona_config.get("backstory", ""),
            tone=persona_config.get("tone", "casual, friendly"),
            objective=f"Gather intelligence about {category}",
            category=category,
        )

        stage_hint = STAGE_HINTS.get(state, "").format(category=category)

        system_content = f"{system_prompt}\n\nCurrent stage instruction: {stage_hint}"
        if context_summary:
            system_content += f"\n\nPrevious interactions with this user:\n{context_summary}"

        # 话术库：给模型一条该阶段的参考说法（让它改写而不是照抄，保留人设语气）
        reference = select_best_template(
            _SCRIPT_LIBRARY, category, _STAGE_FOR_STATE.get(state, ""), "vi"
        )
        if reference:
            system_content += (
                f"\n\nReference phrasing for this stage (rewrite it in your own words, "
                f"do not copy verbatim): {reference.text}"
            )

        messages = [{"role": "system", "content": system_content}]

        # sliding window: last 20 messages
        for msg in history[-20:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": incoming_message})

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.8,
                max_tokens=300,
            )
            reply = response.choices[0].message.content or ""
        except Exception as e:
            logger.error("DeepSeek API error: %s", e)
            reply = self._fallback_reply(state, category=category)

        new_state = self._transition_state(state, incoming_message, reply, len(history))
        return reply, new_state

    def _transition_state(
        self, current: ConvState, incoming: str, reply: str, turn_count: int
    ) -> ConvState:
        lower = incoming.lower()

        # cooldown triggers
        alert_keywords = ["bot", "fake", "scam", "report", "block", "công an", "police", "lừa đảo"]
        if any(kw in lower for kw in alert_keywords):
            return ConvState.COOLDOWN

        if current == ConvState.VERIFICATION:
            # Verification is handled separately in generate_response
            return ConvState.GREETING

        if current == ConvState.IDLE:
            return ConvState.VERIFICATION  # Changed from GREETING to VERIFICATION

        if current == ConvState.GREETING and turn_count >= 2:
            return ConvState.PROBING

        if current == ConvState.PROBING:
            business_signals = [
                "giá",
                "price",
                "chi phí",
                "dịch vụ",
                "service",
                "liên hệ",
                "contact",
                "zalo",
                "phone",
                "sdt",
                "website",
                "fanpage",
                "telegram",
            ]
            if any(sig in lower for sig in business_signals):
                return ConvState.EXTRACTION
            if turn_count > 8:
                return ConvState.PIVOT

        if current == ConvState.EXTRACTION:
            if turn_count > 15:
                return ConvState.EXIT

        if current == ConvState.PIVOT:
            return ConvState.PROBING

        if current == ConvState.COOLDOWN:
            return ConvState.EXIT

        return current

    def _fallback_reply(self, state: ConvState, category: str = "general") -> str:
        # 先用话术库（按 stage + 分类 + 越南语挑一条），没有再退回内置短句
        template = select_best_template(
            _SCRIPT_LIBRARY, category, _STAGE_FOR_STATE.get(state, ""), "vi"
        )
        if template:
            _SCRIPT_LIBRARY.record_usage(template.id, success=True)
            return template.text

        fallbacks = {
            ConvState.VERIFICATION: "Vui lòng trả lời câu hỏi xác minh.",
            ConvState.GREETING: "Chào bạn! 😊",
            ConvState.PROBING: "À hay quá, bạn kể thêm được không?",
            ConvState.EXTRACTION: "Cảm ơn bạn! Cho mình xin thêm thông tin nhé.",
            ConvState.EXIT: "Cảm ơn bạn nhiều! Chúc bạn một ngày tốt lành 😊",
            ConvState.COOLDOWN: "Xin lỗi nếu làm phiền bạn. Chúc bạn vui!",
        }
        return fallbacks.get(state, "Ok, cảm ơn bạn!")

    async def update_context_summary(
        self,
        existing_summary: str | None,
        incoming_message: str,
        reply: str,
        state: ConvState,
    ) -> str:
        """Generate an updated context summary after each exchange."""
        prompt = (
            "You are maintaining a memory profile of a person you're chatting with "
            "for OSINT purposes.\n"
            "Given the existing summary (if any) and the latest message exchange, "
            "produce an updated concise summary.\n"
            "Focus on: key facts learned, topics discussed, trust level, next steps, "
            "language preference.\n"
            "Keep it under 200 words. Write in the same language as the conversation.\n\n"
            f"Existing summary: {existing_summary or 'None yet'}\n"
            f"Latest exchange:\n  Them: {incoming_message}\n  You: {reply}\n"
            f"Current stage: {state.value}\n\n"
            "Updated summary:"
        )
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning("Failed to update context summary: %s", e)
            return existing_summary or ""
