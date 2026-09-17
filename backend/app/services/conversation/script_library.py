"""
Script Library Management System with multi-language support and LLM-based humanization.
Manages conversation templates for different stages and categories.
"""

import logging
import random
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ScriptTemplate:
    """A single script template with metadata."""
    id: str
    category: str  # private_investigator, currency_exchanger, freelancer, data_seller
    stage: str     # greeting, probing, extraction, pivot, exit
    language: str  # vi, zh, en
    text: str
    effectiveness_score: float = 0.5  # 0-1, updated based on A/B testing
    usage_count: int = 0


@dataclass
class ScriptLibrary:
    """Complete script library organized by category and stage."""

    templates: dict[str, list[ScriptTemplate]] = field(default_factory=dict)

    def add_template(self, template: ScriptTemplate):
        """Add a new template to the library."""
        key = f"{template.category}:{template.stage}:{template.language}"
        if key not in self.templates:
            self.templates[key] = []
        self.templates[key].append(template)

    def get_templates(
        self,
        category: str,
        stage: str,
        language: str,
        limit: int = 5
    ) -> list[ScriptTemplate]:
        """Get top templates for given criteria, sorted by effectiveness."""
        key = f"{category}:{stage}:{language}"
        available = self.templates.get(key, [])

        # Sort by effectiveness score (descending)
        sorted_templates = sorted(
            available,
            key=lambda t: t.effectiveness_score,
            reverse=True
        )

        return sorted_templates[:limit]

    def record_usage(self, template_id: str, success: bool):
        """Record template usage for A/B testing."""
        for templates_list in self.templates.values():
            for template in templates_list:
                if template.id == template_id:
                    template.usage_count += 1
                    # Update effectiveness score (simple moving average)
                    alpha = 0.1  # Learning rate
                    reward = 1.0 if success else 0.0
                    template.effectiveness_score = (
                        (1 - alpha) * template.effectiveness_score +
                        alpha * reward
                    )
                    break


# Pre-loaded default script library
DEFAULT_SCRIPTS = {
    "greeting": {
        "group_join": [
            {
                "vi": "Chào mọi người! Mình mới tham gia nhóm 😊",
                "zh": "大家好!我刚加入这个群 😊",
                "en": "Hi everyone! Just joined the group 😊"
            },
            {
                "vi": "Xin chào cả nhà! Rất vui được làm quen với mọi người 🙏",
                "zh": "大家好!很高兴认识各位 🙏",
                "en": "Hello all! Nice to meet everyone 🙏"
            },
            {
                "vi": "Chào anh chị em! Mình là thành viên mới, mong được giúp đỡ!",
                "zh": "各位好!我是新成员,请多关照!",
                "en": "Hey folks! I'm new here, looking forward to your help!"
            }
        ],
        "direct_message": [
            {
                "vi": "Chào bạn! Mình thấy bạn trong nhóm {group_name}",
                "zh": "你好!我在{group_name}群里看到你",
                "en": "Hi! I saw you in the {group_name} group"
            },
            {
                "vi": "Chào bạn! Mình có xem profile của bạn và thấy rất thú vị",
                "zh": "你好!我看了你的资料觉得很有趣",
                "en": "Hi! I checked your profile and found it interesting"
            }
        ]
    },
    "probing": {
        "private_investigator": [
            {
                "vi": "Bạn có biết ai làm dịch vụ điều tra tư nhân không? Mình cần tìm hiểu một số chuyện.",
                "zh": "你知道有谁做私人侦探服务吗?我需要调查一些事情。",
                "en": "Do you know anyone who does private investigation? I need to look into something."
            },
            {
                "vi": "Có dịch vụ nào theo dõi hoặc giám sát không bạn? Giá cả sao?",
                "zh": "有什么跟踪或监控的服务吗?价格如何?",
                "en": "Are there any surveillance or monitoring services? What's the price?"
            }
        ],
        "currency_exchanger": [
            {
                "vi": "Tỷ giá USD-VND hôm nay tốt nhất ở đâu vậy bạn?",
                "zh": "今天哪里美元兑越南盾汇率最好?",
                "en": "Where's the best USD-VND exchange rate today?"
            },
            {
                "vi": "Bạn có biết chỗ đổi tiền uy tín không? Mình cần đổi khoảng $2000.",
                "zh": "你知道可靠的换汇地方吗?我需要换大约2000美元。",
                "en": "Do you know a reliable place to exchange money? I need to change about $2000."
            }
        ],
        "freelancer": [
            {
                "vi": "Mình cần thuê người làm website, giá bao nhiêu vậy?",
                "zh": "我需要找人做网站,多少钱?",
                "en": "I need to hire someone to build a website, how much would it cost?"
            },
            {
                "vi": "Bạn có nhận dự án thiết kế logo không? Ngân sách khoảng 2-3 triệu.",
                "zh": "你接logo设计项目吗?预算大概2-3百万。",
                "en": "Do you take logo design projects? Budget is around 2-3 million VND."
            }
        ],
        "data_seller": [
            {
                "vi": "Ai biết chỗ mua data khách hàng tiềm năng không? Cần cho kinh doanh.",
                "zh": "谁知道哪里可以买到潜在客户数据?需要用于业务。",
                "en": "Anyone know where to buy customer lead data? Need it for business."
            },
            {
                "vi": "Có ai bán database theo ngành không? Giá thế nào?",
                "zh": "有人卖行业数据库吗?价格怎么样?",
                "en": "Is anyone selling industry-specific databases? What's the price?"
            }
        ]
    },
    "extraction": [
        {
            "vi": "Cho mình xin contact trực tiếp được không? Zalo hoặc SĐT.",
            "zh": "能给我你的直接联系方式吗?Zalo或电话。",
            "en": "Can I get your direct contact? Zalo or phone number."
        },
        {
            "vi": "Bên bạn có website hay fanpage không? Cho mình xem thêm thông tin.",
            "zh": "你们有网站或主页吗?让我看看更多信息。",
            "en": "Do you have a website or fanpage? Let me see more info."
        },
        {
            "vi": "Giá cụ thể thế nào? Có báo giá chi tiết không bạn?",
            "zh": "具体价格是多少?有详细报价吗?",
            "en": "What's the exact price? Do you have a detailed quote?"
        }
    ],
    "pivot": [
        {
            "vi": "À mà này, bạn có biết ai làm về lĩnh vực khác không?",
            "zh": "对了,你知道还有谁做其他领域的吗?",
            "en": "By the way, do you know anyone working in other fields?"
        },
        {
            "vi": "Nhân tiện, bạn có thể giới thiệu mình vài người khác được không?",
            "zh": "顺便问一下,你能介绍其他人给我吗?",
            "en": "By the way, could you introduce me to a few others?"
        }
    ],
    "exit": [
        {
            "vi": "Cảm ơn bạn nhiều! Mình sẽ liên hệ lại sau nhé 😊",
            "zh": "非常感谢!我稍后再联系你 😊",
            "en": "Thanks so much! I'll contact you later 😊"
        },
        {
            "vi": "Ok bạn! Chúc bạn một ngày tốt lành! 🙏",
            "zh": "好的!祝你一天愉快! 🙏",
            "en": "OK! Have a great day! 🙏"
        }
    ]
}


def load_default_scripts() -> ScriptLibrary:
    """Load the default script library."""
    library = ScriptLibrary()

    template_counter = 0

    # Load greeting scripts
    for scenario, languages in DEFAULT_SCRIPTS["greeting"].items():
        for lang_dict in languages:
            for lang, text in lang_dict.items():
                template_counter += 1
                library.add_template(ScriptTemplate(
                    id=f"tmpl_{template_counter:04d}",
                    category="general",
                    stage="greeting",
                    language=lang,
                    text=text
                ))

    # Load probing scripts by category
    for category, examples in DEFAULT_SCRIPTS["probing"].items():
        for lang_dict in examples:
            for lang, text in lang_dict.items():
                template_counter += 1
                library.add_template(ScriptTemplate(
                    id=f"tmpl_{template_counter:04d}",
                    category=category,
                    stage="probing",
                    language=lang,
                    text=text
                ))

    # Load extraction scripts
    for lang_dict in DEFAULT_SCRIPTS["extraction"]:
        for lang, text in lang_dict.items():
            template_counter += 1
            library.add_template(ScriptTemplate(
                id=f"tmpl_{template_counter:04d}",
                category="general",
                stage="extraction",
                language=lang,
                text=text
            ))

    # Load pivot scripts
    for lang_dict in DEFAULT_SCRIPTS["pivot"]:
        for lang, text in lang_dict.items():
            template_counter += 1
            library.add_template(ScriptTemplate(
                id=f"tmpl_{template_counter:04d}",
                category="general",
                stage="pivot",
                language=lang,
                text=text
            ))

    # Load exit scripts
    for lang_dict in DEFAULT_SCRIPTS["exit"]:
        for lang, text in lang_dict.items():
            template_counter += 1
            library.add_template(ScriptTemplate(
                id=f"tmpl_{template_counter:04d}",
                category="general",
                stage="exit",
                language=lang,
                text=text
            ))

    logger.info("Loaded %d default script templates", template_counter)
    return library


async def humanize_with_llm(
    original_text: str,
    persona_config: dict,
    context: Optional[str] = None
) -> str:
    """Use LLM to humanize and contextualize script templates."""

    from openai import AsyncOpenAI
    from app.core.config import settings

    client = AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )

    system_prompt = f"""
You are an expert at making AI-generated text sound more natural and human-like.

Persona: {persona_config.get('name', 'User')}, {persona_config.get('age', 28)} years old, {persona_config.get('occupation', 'freelancer')}

Instructions:
1. Rewrite the message to sound more casual and natural
2. Add occasional minor typos (about 5% chance) but keep it readable
3. Use emoji sparingly if the persona uses them
4. Match the tone: {persona_config.get('tone', 'casual')}
5. Keep the same meaning and intent
6. Respond in the same language as the input

Context: {context or 'No additional context'}
"""

    try:
        response = await client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": original_text}
            ],
            temperature=0.7,
            max_tokens=200,
        )

        humanized = response.choices[0].message.content or original_text
        return humanized.strip()

    except Exception as e:
        logger.error("LLM humanization failed: %s", e)
        return original_text


def select_best_template(
    library: ScriptLibrary,
    category: str,
    stage: str,
    language: str,
    use_ab_testing: bool = True
) -> Optional[ScriptTemplate]:
    """Select the best template using A/B testing strategy."""

    templates = library.get_templates(category, stage, language)

    if not templates:
        # Fallback to general category
        templates = library.get_templates("general", stage, language)

    if not templates:
        return None

    if use_ab_testing:
        # Epsilon-greedy strategy: 90% exploit, 10% explore
        if random.random() < 0.9:
            # Choose best performing template
            return templates[0]
        else:
            # Random exploration
            return random.choice(templates)
    else:
        # Always choose best
        return templates[0] if templates else None
