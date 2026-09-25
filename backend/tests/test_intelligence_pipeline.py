"""情报管道（实体提取 / 分类 / 活跃度）的单元测试。"""

from app.services.intelligence.pipeline import (
    calculate_activity_score,
    classify_category,
    extract_entities,
)

SAMPLE = (
    "Chào bạn, mình cần đổi tiền. Tỷ giá hôm nay bao nhiêu? "
    "SĐT 0912345678, Zalo: zalo.me/doitienabc, email: tuan.webdev@gmail.com, "
    "telegram @tuanwebdev, website https://example.com, giá 25.500 VND, "
    "địa chỉ Hà Nội, Vietcombank 1234567890123"
)


class TestExtractEntities:
    def test_extracts_all_supported_entity_types(self):
        entities = extract_entities(SAMPLE)
        assert "0912345678" in entities.phones
        assert "tuan.webdev@gmail.com" in entities.emails
        assert "doitienabc" in entities.zalo_ids
        assert "tuanwebdev" in entities.telegram_handles
        assert any("example.com" in url for url in entities.websites)
        assert entities.prices, "应识别出价格"
        assert entities.addresses, "应识别出地址"
        assert entities.bank_accounts, "应识别出银行账号"

    def test_text_without_entities_returns_empty_lists(self):
        entities = extract_entities("Xin chào, hôm nay trời đẹp nhỉ")
        assert entities.phones == []
        assert entities.emails == []
        assert entities.prices == []

    def test_duplicate_matches_are_deduplicated(self):
        entities = extract_entities("0912345678 và 0912345678")
        assert entities.phones == ["0912345678"]


class TestClassifyCategory:
    def test_currency_exchange_text(self):
        category, confidence, signals = classify_category(SAMPLE)
        assert category == "currency_exchanger"
        assert confidence > 0.5
        assert signals

    def test_freelancer_text(self):
        text = "Mình là freelancer, nhận thiết kế và lập trình web, đây là portfolio của mình"
        category, confidence, _ = classify_category(text)
        assert category == "freelancer"
        assert confidence > 0

    def test_unrelated_text_returns_unknown(self):
        category, confidence, signals = classify_category("hello how are you today")
        assert category == "unknown"
        assert confidence == 0.0
        assert signals == []

    def test_confidence_is_capped_at_one(self):
        text = "đổi tiền chuyển tiền tỷ giá exchange remittance chuyển khoản ngoại tệ USD VND đô la"
        _, confidence, _ = classify_category(text)
        assert confidence <= 1.0


class TestActivityScore:
    def test_recent_active_profile_is_active(self):
        status = calculate_activity_score(
            last_message_age_hours=2,
            messages_per_day=10,
            response_rate=0.9,
            has_complete_profile=True,
        )
        assert status == "active"

    def test_stale_profile_is_dormant_or_inactive(self):
        assert (
            calculate_activity_score(
                last_message_age_hours=200,
                messages_per_day=2,
                response_rate=0.5,
                has_complete_profile=True,
            )
            == "dormant"
        )
        assert (
            calculate_activity_score(
                last_message_age_hours=1000,
                messages_per_day=0.1,
                response_rate=0.0,
                has_complete_profile=False,
            )
            == "inactive"
        )
