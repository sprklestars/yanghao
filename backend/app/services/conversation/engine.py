import logging
import random
from enum import Enum

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


class ConvState(str, Enum):
    IDLE = "idle"
    GREETING = "greeting"
    PROBING = "probing"
    EXTRACTION = "extraction"
    PIVOT = "pivot"
    EXIT = "exit"
    COOLDOWN = "cooldown"


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
    ConvState.GREETING: "Start with a friendly greeting. Be casual and warm. Keep it short.",
    ConvState.PROBING: "Ask natural questions related to {category}. Show genuine curiosity. Don't be pushy.",
    ConvState.EXTRACTION: "The person seems interested. Ask for more details: contact info, pricing, website, specific services. Be polite.",
    ConvState.PIVOT: "The current topic isn't yielding results. Shift to a related angle naturally.",
    ConvState.EXIT: "Wrap up politely. Thank them and say you'll follow up later.",
    ConvState.COOLDOWN: "The person seems wary. Apologize if needed, say goodbye gracefully. Do NOT continue probing.",
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
    ) -> tuple[str, ConvState]:
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

        messages = [{"role": "system", "content": f"{system_prompt}\n\nCurrent stage instruction: {stage_hint}"}]

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
            reply = self._fallback_reply(state)

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

        if current == ConvState.IDLE:
            return ConvState.GREETING

        if current == ConvState.GREETING and turn_count >= 2:
            return ConvState.PROBING

        if current == ConvState.PROBING:
            business_signals = [
                "giá", "price", "chi phí", "dịch vụ", "service",
                "liên hệ", "contact", "zalo", "phone", "sdt",
                "website", "fanpage", "telegram",
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

    def _fallback_reply(self, state: ConvState) -> str:
        fallbacks = {
            ConvState.GREETING: "Chào bạn! 😊",
            ConvState.PROBING: "À hay quá, bạn kể thêm được không?",
            ConvState.EXTRACTION: "Cảm ơn bạn! Cho mình xin thêm thông tin nhé.",
            ConvState.EXIT: "Cảm ơn bạn nhiều! Chúc bạn một ngày tốt lành 😊",
            ConvState.COOLDOWN: "Xin lỗi nếu làm phiền bạn. Chúc bạn vui!",
        }
        return fallbacks.get(state, "Ok, cảm ơn bạn!")
