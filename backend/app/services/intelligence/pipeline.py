import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ExtractedEntities:
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    zalo_ids: list[str] = field(default_factory=list)
    telegram_handles: list[str] = field(default_factory=list)
    facebook_urls: list[str] = field(default_factory=list)
    websites: list[str] = field(default_factory=list)
    prices: list[str] = field(default_factory=list)
    addresses: list[str] = field(default_factory=list)
    bank_accounts: list[str] = field(default_factory=list)


EXTRACTION_PATTERNS = {
    "phones": [
        r"(\+?84\s?\d[\s.-]?\d{3}[\s.-]?\d{5,6})",
        r"(0\d{9,10})",
    ],
    "emails": [
        r"([\w.+-]+@[\w-]+\.[\w.-]+)",
    ],
    "zalo_ids": [
        r"zalo\.me/([a-zA-Z0-9]+)",
        r"zalo[:\s]+([a-zA-Z0-9_.]{6,})",
    ],
    "telegram_handles": [
        r"@([a-zA-Z0-9_]{5,32})",
        r"t\.me/([a-zA-Z0-9_]{5,32})",
    ],
    "facebook_urls": [
        r"facebook\.com/([a-zA-Z0-9.]+)",
        r"fb\.com/([a-zA-Z0-9.]+)",
    ],
    "websites": [
        r'(https?://[^\s,;"\')]+)',
    ],
    "prices": [
        r"(\d+[\.,]?\d*\s*(?:k|nghìn|triệu|VND|USD|usd|\$))",
        r"((?:giá|price|chi phí)[:\s]*\d+[\.,]?\d*)",
    ],
    "addresses": [
        r"((?:Hà Nội|TP\.?HCM|Hồ Chí Minh|Đà Nẵng|Hải Phòng|Cần Thơ)[^,.]*)",
        r"((?:quận|huyện|tỉnh|thành phố)\s+[\w\s]+)",
    ],
    "bank_accounts": [
        r"((?:Vietcombank|BIDV|Techcombank|MBBank|ACB|Sacombank|VPBank|TPBank)[\w\s]*\d{10,20})",
    ],
}

CATEGORY_KEYWORDS = {
    "private_investigator": [
        "thám tử",
        "điều tra",
        "theo dõi",
        "giám sát",
        "private investigator",
        "detective",
        "surveillance",
        "dịch vụ điều tra",
        "thám tử tư",
    ],
    "currency_exchanger": [
        "đổi tiền",
        "chuyển tiền",
        "tỷ giá",
        "exchange",
        "remittance",
        "chuyển khoản",
        "ngoại tệ",
        "USD",
        "VND",
        "tỷ giá hôm nay",
        "đô la",
        "nhân dân tệ",
        "chuyển tiền quốc tế",
    ],
    "freelancer": [
        "freelance",
        "tự do",
        "làm thêm",
        "tuyển dụng",
        "hiring",
        "developer",
        "designer",
        "writer",
        "translator",
        "phiên dịch",
        "lập trình",
        "thiết kế",
        "viết bài",
        "cv",
        "resume",
        "portfolio",
    ],
    "data_seller": [
        "bán data",
        "mua data",
        "dữ liệu",
        "database",
        "customer list",
        "danh sách khách",
        "thông tin cá nhân",
        "ngân hàng",
        "bảo hiểm",
        "vay vốn",
        "leads",
        "data bán",
        "info cá nhân",
    ],
}


def extract_entities(text: str) -> ExtractedEntities:
    result = ExtractedEntities()
    for entity_type, patterns in EXTRACTION_PATTERNS.items():
        matches = []
        for pattern in patterns:
            found = re.findall(pattern, text, re.IGNORECASE)
            matches.extend(found)
        setattr(result, entity_type, list(set(matches)))
    return result


def classify_category(text: str) -> tuple[str, float, list[str]]:
    lower = text.lower()
    scores: dict[str, float] = {}
    matched_signals: dict[str, list[str]] = {}

    for category, keywords in CATEGORY_KEYWORDS.items():
        hits = [kw for kw in keywords if kw.lower() in lower]
        if hits:
            scores[category] = len(hits) / len(keywords)
            matched_signals[category] = hits

    if not scores:
        return "unknown", 0.0, []

    best = max(scores, key=scores.get)
    confidence = min(scores[best] * 3, 1.0)  # scale up, cap at 1.0
    return best, round(confidence, 2), matched_signals.get(best, [])


def calculate_activity_score(
    last_message_age_hours: float,
    messages_per_day: float,
    response_rate: float,
    has_complete_profile: bool,
) -> str:
    age_score = (
        1.0
        if last_message_age_hours < 24
        else 0.7
        if last_message_age_hours < 168
        else 0.3
        if last_message_age_hours < 720
        else 0.0
    )
    freq_score = (
        1.0
        if messages_per_day > 5
        else 0.7
        if messages_per_day > 1
        else 0.3
        if messages_per_day > 0.14
        else 0.1
    )
    profile_score = 1.0 if has_complete_profile else 0.5

    weighted = age_score * 0.3 + freq_score * 0.3 + response_rate * 0.25 + profile_score * 0.15

    if weighted > 0.7:
        return "active"
    elif weighted > 0.3:
        return "dormant"
    return "inactive"
