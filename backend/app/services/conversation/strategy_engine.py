"""
Scenario-based Conversation Strategy Engine.
Selects appropriate tactics based on target category and context:
- Group mixing vs friend adding strategies
- Active conversation flows
- Business channel probing logic
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class StrategyType(str, Enum):
    """Available conversation strategies."""
    GROUP_MIXING = "group_mixing"        # Join groups and interact with members
    FRIEND_ADDING = "friend_adding"      # Send friend requests then chat
    DIRECT_OUTREACH = "direct_outreach"  # Direct message without prior contact


class TargetCategory(str, Enum):
    """Target business categories."""
    PRIVATE_INVESTIGATOR = "private_investigator"
    CURRENCY_EXCHANGER = "currency_exchanger"
    FREELANCER = "freelancer"
    DATA_SELLER = "data_seller"


@dataclass
class StrategyConfig:
    """Configuration for a specific strategy."""

    strategy_type: StrategyType
    priority: int  # 1-10, higher means more preferred

    # Conversation parameters
    max_initial_greetings: int = 3  # Max greetings before pivoting
    probing_rounds: int = 5  # Rounds of probing questions
    extraction_triggers: list[str] = field(default_factory=list)  # Keywords that trigger extraction phase

    # Rate limiting
    messages_per_hour: int = 20
    friend_requests_per_day: int = 5
    group_joins_per_day: int = 3

    # Timing
    min_delay_between_messages: int = 30  # seconds
    max_delay_between_messages: int = 120  # seconds

    # Success criteria
    success_indicators: list[str] = field(default_factory=list)
    failure_indicators: list[str] = field(default_factory=list)


# Pre-defined strategies for each category
STRATEGIES = {
    TargetCategory.PRIVATE_INVESTIGATOR: [
        StrategyConfig(
            strategy_type=StrategyType.GROUP_MIXING,
            priority=8,
            max_initial_greetings=2,
            probing_rounds=8,
            extraction_triggers=[
                "thám tử", "điều tra", "theo dõi", "giám sát",
                "detective", "investigation", "surveillance"
            ],
            messages_per_hour=15,
            friend_requests_per_day=3,
            group_joins_per_day=5,
            success_indicators=["provides contact", "quotes price", "offers service details"],
            failure_indicators=["blocks user", "reports message", "explicit refusal"]
        ),
        StrategyConfig(
            strategy_type=StrategyType.FRIEND_ADDING,
            priority=6,
            max_initial_greetings=1,
            probing_rounds=10,
            extraction_triggers=["contact", "price", "service"],
            messages_per_hour=10,
            friend_requests_per_day=5,
            group_joins_per_day=2,
            success_indicators=["accepts friend request", "engages in conversation"],
            failure_indicators=["ignores request", "declines"]
        )
    ],
    TargetCategory.CURRENCY_EXCHANGER: [
        StrategyConfig(
            strategy_type=StrategyType.DIRECT_OUTREACH,
            priority=9,
            max_initial_greetings=1,
            probing_rounds=3,
            extraction_triggers=[
                "tỷ giá", "đổi tiền", "chuyển tiền",
                "exchange rate", "remittance", "USD", "VND"
            ],
            messages_per_hour=20,
            friend_requests_per_day=5,
            group_joins_per_day=3,
            success_indicators=["provides rate", "gives contact", "mentions location"],
            failure_indicators=["no response", "suspicious behavior"]
        ),
        StrategyConfig(
            strategy_type=StrategyType.GROUP_MIXING,
            priority=7,
            max_initial_greetings=2,
            probing_rounds=5,
            extraction_triggers=["rate", "fee", "location"],
            messages_per_hour=15,
            friend_requests_per_day=3,
            group_joins_per_day=5,
            success_indicators=["active in group", "responds to queries"],
            failure_indicators=["kicked from group", "warned by admin"]
        )
    ],
    TargetCategory.FREELANCER: [
        StrategyConfig(
            strategy_type=StrategyType.GROUP_MIXING,
            priority=9,
            max_initial_greetings=3,
            probing_rounds=6,
            extraction_triggers=[
                "giá", "dịch vụ", "portfolio", "website",
                "price", "service", "hire", "project"
            ],
            messages_per_hour=25,
            friend_requests_per_day=8,
            group_joins_per_day=5,
            success_indicators=["shares portfolio", "quotes price", "provides contact"],
            failure_indicators=["not interested", "too busy"]
        ),
        StrategyConfig(
            strategy_type=StrategyType.FRIEND_ADDING,
            priority=7,
            max_initial_greetings=2,
            probing_rounds=8,
            extraction_triggers=["work", "project", "collaboration"],
            messages_per_hour=15,
            friend_requests_per_day=10,
            group_joins_per_day=3,
            success_indicators=["accepts request", "shows interest"],
            failure_indicators=["declines", "no response"]
        )
    ],
    TargetCategory.DATA_SELLER: [
        StrategyConfig(
            strategy_type=StrategyType.DIRECT_OUTREACH,
            priority=8,
            max_initial_greetings=1,
            probing_rounds=4,
            extraction_triggers=[
                "data", "database", "customer list", "leads",
                "dữ liệu", "khách hàng", "ngân hàng"
            ],
            messages_per_hour=10,
            friend_requests_per_day=3,
            group_joins_per_day=2,
            success_indicators=["provides sample", "quotes price", "shares contact"],
            failure_indicators=["suspicious", "asks too many questions", "refuses"]
        ),
        StrategyConfig(
            strategy_type=StrategyType.GROUP_MIXING,
            priority=5,
            max_initial_greetings=2,
            probing_rounds=6,
            extraction_triggers=["data source", "quality", "price per record"],
            messages_per_hour=12,
            friend_requests_per_day=5,
            group_joins_per_day=4,
            success_indicators=["active seller", "transparent about data"],
            failure_indicators=["vague answers", "unwilling to share details"]
        )
    ]
}


@dataclass
class ConversationState:
    """Tracks the current state of a conversation."""

    current_stage: str = "greeting"  # greeting, probing, extraction, pivot, exit
    turn_count: int = 0
    last_strategy: Optional[StrategyConfig] = None
    extracted_info: dict = field(default_factory=dict)
    confidence_score: float = 0.0
    should_pivot: bool = False
    should_exit: bool = False


class StrategyEngine:
    """Selects and manages conversation strategies based on context."""

    def __init__(self):
        self.active_conversations: dict[str, ConversationState] = {}

    def select_strategy(
        self,
        category: TargetCategory,
        context: Optional[dict] = None
    ) -> StrategyConfig:
        """Select the best strategy for given category and context."""

        available_strategies = STRATEGIES.get(category, [])

        if not available_strategies:
            logger.warning("No strategies defined for category: %s", category)
            # Return default strategy
            return StrategyConfig(
                strategy_type=StrategyType.GROUP_MIXING,
                priority=5,
                messages_per_hour=15,
                friend_requests_per_day=5,
                group_joins_per_day=3,
            )

        # Sort by priority (descending)
        sorted_strategies = sorted(
            available_strategies,
            key=lambda s: s.priority,
            reverse=True
        )

        # Consider context if provided
        if context:
            platform = context.get('platform')
            account_health = context.get('account_health', 'green')

            # Adjust based on account health
            if account_health == 'yellow':
                # Reduce aggressive strategies
                for strategy in sorted_strategies:
                    if strategy.strategy_type == StrategyType.FRIEND_ADDING:
                        strategy.friend_requests_per_day = max(1, strategy.friend_requests_per_day - 2)
            elif account_health == 'red':
                # Only use passive strategies
                sorted_strategies = [
                    s for s in sorted_strategies
                    if s.strategy_type == StrategyType.GROUP_MIXING
                ]

        selected = sorted_strategies[0]
        logger.info(
            "Selected strategy: %s (priority: %d) for category: %s",
            selected.strategy_type.value,
            selected.priority,
            category.value
        )

        return selected

    def update_conversation_state(
        self,
        conversation_id: str,
        incoming_message: str,
        current_stage: str
    ) -> ConversationState:
        """Update conversation state based on incoming message."""

        state = self.active_conversations.get(conversation_id, ConversationState())
        state.turn_count += 1
        state.current_stage = current_stage

        lower_msg = incoming_message.lower()

        # Check for extraction triggers
        if state.last_strategy:
            for trigger in state.last_strategy.extraction_triggers:
                if trigger.lower() in lower_msg:
                    state.current_stage = "extraction"
                    state.confidence_score = min(state.confidence_score + 0.2, 1.0)
                    break

        # Check for failure indicators
        if state.last_strategy:
            for indicator in state.last_strategy.failure_indicators:
                if indicator.lower() in lower_msg:
                    state.should_exit = True
                    logger.warning("Failure indicator detected: %s", indicator)
                    break

        # Check for success indicators
        if state.last_strategy:
            for indicator in state.last_strategy.success_indicators:
                if indicator.lower() in lower_msg:
                    state.confidence_score = min(state.confidence_score + 0.3, 1.0)
                    break

        # Auto-pivot if stuck in probing too long
        if current_stage == "probing" and state.turn_count > 10:
            state.should_pivot = True

        # Exit after successful extraction
        if current_stage == "extraction" and state.confidence_score > 0.7:
            state.current_stage = "exit"

        self.active_conversations[conversation_id] = state
        return state

    def should_send_message(self, conversation_id: str) -> bool:
        """Determine if it's appropriate to send next message."""

        state = self.active_conversations.get(conversation_id)

        if not state:
            return True

        if state.should_exit:
            return False

        if state.current_stage == "exit":
            return False

        return True

    def get_next_stage(self, conversation_id: str) -> str:
        """Get the recommended next conversation stage."""

        state = self.active_conversations.get(conversation_id, ConversationState())

        if state.should_exit:
            return "exit"

        if state.should_pivot:
            return "pivot"

        # Normal progression
        stage_order = ["greeting", "probing", "extraction", "exit"]
        current_idx = stage_order.index(state.current_stage) if state.current_stage in stage_order else 0

        if current_idx < len(stage_order) - 1:
            return stage_order[current_idx + 1]

        return "exit"

    def cleanup_conversation(self, conversation_id: str):
        """Remove completed conversation from tracking."""
        if conversation_id in self.active_conversations:
            del self.active_conversations[conversation_id]
            logger.info("Cleaned up conversation: %s", conversation_id)


# Global strategy engine instance
strategy_engine = StrategyEngine()
