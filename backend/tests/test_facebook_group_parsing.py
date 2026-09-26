"""Facebook 群搜索/成员解析测试。

回归点：这一版 Facebook 页面里已经**没有 data-pagelet 属性**了，旧代码靠
`[data-pagelet="GroupsFeed::Group"]` 抓群，永远返回 0 条——用户看到的就是
「任务里 Facebook 搜不到群」。现在改成解析 role="article" 卡片。
样本取自 2026-09-26 用真实账号 cookie 抓下来的页面。
"""

import asyncio
import re
import unittest

from app.services.platform.facebook_adapter import (
    FacebookAdapter,
    detect_block_reason,
    parse_group_search_results,
    parse_member_cards,
    parse_member_count,
)

# 真实抓下来的三条（账号是法语界面，所以有 "membres"）
REAL_ITEMS = [
    {
        "href": "https://www.facebook.com/groups/sangquanchothuematbang/?__tn__=%3C",
        "text": (
            "CHỢ MUA BÁN ONLINE\n"
            "Public · 35 K membres · Plus de 50 publications par jour\n"
            "Rejoindre"
        ),
    },
    {
        "href": "https://www.facebook.com/groups/470999373384264/?__tn__=%3C",
        "text": "Mục Địa VNG - Giao Lưu Mua Bán Trao Đổi\nPublic · 6,2 K membres\nRejoindre",
    },
    {
        "href": "https://www.facebook.com/groups/1039124623281975/?__tn__=%3C",
        "text": "Chợ mua bán MŨ NÓN toàn quốc\nPublic · 4,1 K membres",
    },
]


class ParseMemberCountTests(unittest.TestCase):
    def test_french_thousands_with_k_suffix(self):
        self.assertEqual(parse_member_count("Public · 35 K membres"), 35_000)
        self.assertEqual(parse_member_count("Public · 6,2 K membres"), 6_200)  # 逗号是小数点
        self.assertEqual(parse_member_count("Public · 4,1 K membres"), 4_100)

    def test_english_and_vietnamese(self):
        self.assertEqual(parse_member_count("1,234 members"), 1_234)  # 逗号是千分位
        self.assertEqual(parse_member_count("12.5 M members"), 12_500_000)
        self.assertEqual(parse_member_count("900 thành viên"), 900)
        self.assertEqual(parse_member_count("không có số"), 0)


class DetectBlockReasonTests(unittest.TestCase):
    """账号被 FB 安全验证拦下时，任务告警要说真话，不能报"未搜到任何群"。"""

    REAL_CHECKPOINT_URL = (
        "https://www.facebook.com/checkpoint/1501092823525282/"
        "?next=https%3A%2F%2Fwww.facebook.com%2Fsearch%2Fgroups%2F%3Fq%3Dcamera"
    )

    def test_checkpoint_url_is_reported(self):
        reason = detect_block_reason(self.REAL_CHECKPOINT_URL)
        self.assertIsNotNone(reason)
        self.assertIn("安全验证", reason)

    def test_real_checkpoint_text_is_reported(self):
        # 实测页面文字（法语界面）
        text = (
            "David | David White, confirmez que vous êtes une personne réelle "
            "afin d'utiliser votre compte"
        )
        self.assertIsNotNone(detect_block_reason("https://www.facebook.com/", text))

    def test_normal_search_page_is_not_flagged(self):
        self.assertIsNone(
            detect_block_reason(
                "https://www.facebook.com/search/groups/?q=camera",
                "CHỢ MUA BÁN ONLINE Public · 35 K membres",
            )
        )


class ParseGroupSearchResultsTests(unittest.TestCase):
    def test_real_cards_are_parsed(self):
        groups = parse_group_search_results(REAL_ITEMS, limit=10)
        self.assertEqual(len(groups), 3)
        first = groups[0]
        self.assertEqual(first.group_id, "sangquanchothuematbang")
        self.assertEqual(first.name, "CHỢ MUA BÁN ONLINE")
        self.assertEqual(first.member_count, 35_000)
        self.assertIn("membres", first.description)
        self.assertEqual(groups[1].group_id, "470999373384264")
        self.assertEqual(groups[1].member_count, 6_200)

    def test_respects_limit_and_deduplicates(self):
        duplicated = REAL_ITEMS + [REAL_ITEMS[0]]
        groups = parse_group_search_results(duplicated, limit=2)
        self.assertEqual(len(groups), 2)
        self.assertEqual(len({g.group_id for g in groups}), 2)

    def test_cards_without_group_link_are_skipped(self):
        items = [{"href": "https://www.facebook.com/", "text": "广告"}, {"href": "", "text": "x"}]
        self.assertEqual(parse_group_search_results(items), [])


class ParseMemberCardsTests(unittest.TestCase):
    def test_user_links_are_parsed_and_deduped(self):
        items = [
            {
                "href": "https://www.facebook.com/profile.php?id=100012345&sk=about",
                "text": "Nguyễn A",
            },
            {"href": "/user/61590001112223/", "text": "Trần B"},
            {"href": "/user/61590001112223/", "text": "Trần B"},
            {"href": "https://www.facebook.com/groups/123/", "text": "群链接（不是人）"},
        ]
        members = parse_member_cards(items, limit=10)
        self.assertEqual([m.user_id for m in members], ["100012345", "61590001112223"])
        self.assertEqual(members[0].display_name, "Nguyễn A")


class FakePage:
    """只实现适配器用到的那几个方法，用来验证"不再依赖 data-pagelet"。"""

    def __init__(self, cards):
        self.cards = cards
        self.goto_url = ""
        self.waited_for = []
        self.scrolled = 0
        self.scripts = []

    async def goto(self, url, **kwargs):
        self.goto_url = url
        return None

    async def wait_for_selector(self, selector, **kwargs):
        self.waited_for.append(selector)
        return None

    async def evaluate(self, script, arg=None):
        self.scripts.append(script)
        if "scrollBy" in script:
            self.scrolled += 1
            return None
        return self.cards


class SearchGroupsOnPageTests(unittest.TestCase):
    def _adapter(self, page):
        adapter = FacebookAdapter(session_name="fbqa")
        adapter._page = page
        return adapter

    def test_search_uses_article_cards_and_encodes_query(self):
        page = FakePage(REAL_ITEMS)
        adapter = self._adapter(page)
        groups = asyncio.run(adapter.search_groups("chợ mua bán", limit=5))

        self.assertEqual(len(groups), 3)
        self.assertIn("search/groups/?q=ch%E1%BB%A3+mua+b%C3%A1n", page.goto_url)
        self.assertIn('div[role="article"]', page.waited_for)  # 等的是新结构
        self.assertNotIn("data-pagelet", " ".join(page.scripts))
        self.assertGreater(page.scrolled, 0)

    def test_empty_page_returns_empty_without_error(self):
        adapter = self._adapter(FakePage([]))
        self.assertEqual(asyncio.run(adapter.search_groups("nothing")), [])


class FakeButton:
    def __init__(self, aria: str = "", text: str = "", visible: bool = True):
        self.aria = aria
        self.text = text
        self.visible = visible


class FakeLocator:
    def __init__(self, buttons: list[FakeButton], page: "FakeButtonPage | None" = None):
        self._buttons = buttons
        self._page = page

    async def count(self) -> int:
        return len(self._buttons)

    def nth(self, index: int) -> "FakeLocator":
        return FakeLocator([self._buttons[index]], self._page)

    async def get_attribute(self, name: str):
        return self._buttons[0].aria if name == "aria-label" else None

    async def inner_text(self) -> str:
        return self._buttons[0].text

    async def is_visible(self) -> bool:
        if self._page is not None:
            self._page.visibility_checks += 1
            if (
                self._page.late_render_after
                and self._page.visibility_checks <= self._page.late_render_after
            ):
                return False  # 模拟"按钮还没渲染出来"
        return self._buttons[0].visible


class FakeButtonPage:
    """按选择器里出现的 aria-label / has-text 关键词筛按钮，模拟真实页面。"""

    def __init__(self, buttons: list[FakeButton]):
        self.buttons = buttons
        self.visibility_checks = 0
        self.late_render_after = 0  # >0 时模拟"按钮要过一会儿才真正可见"
        self.scrolls: list[str] = []

    async def evaluate(self, script: str, arg=None):
        # 只用来记录"催渲染"的滚动调用
        self.scrolls.append(script)
        return None

    def locator(self, selector: str) -> FakeLocator:
        aria_terms = re.findall(r'aria-label\*="([^"]+)"', selector, re.IGNORECASE)
        text_terms = re.findall(r':has-text\("([^"]+)"\)', selector)
        matched = [
            button
            for button in self.buttons
            if any(term.lower() in button.aria.lower() for term in aria_terms)
            or any(term.lower() in button.text.lower() for term in text_terms)
        ]
        return FakeLocator(matched, self)

    async def wait_for_selector(self, selector: str, **kwargs):
        return None


class FindJoinButtonTests(unittest.TestCase):
    def _adapter(self, buttons):
        adapter = FacebookAdapter(session_name="fbqa")
        adapter._page = FakeButtonPage(buttons)
        return adapter

    def test_matches_localized_french_label(self):
        """实测这个账号是法语界面，按钮是 "Rejoindre le groupe"。"""
        adapter = self._adapter(
            [
                FakeButton(aria="Votre profil"),
                FakeButton(aria="Rejoindre le groupe", text="Rejoindre le groupe"),
            ]
        )
        button = asyncio.run(adapter.find_join_button(timeout_s=1.0))
        self.assertIsNotNone(button)
        self.assertEqual(asyncio.run(button.get_attribute("aria-label")), "Rejoindre le groupe")
        self.assertEqual(asyncio.run(adapter.group_join_state(timeout_s=1.0)), "joinable")

    def test_never_picks_leave_button(self):
        """已加入的群只有「退出小组」按钮——绝不能把它当成加入按钮点下去。"""
        adapter = self._adapter(
            [
                FakeButton(aria="Partager le groupe"),
                FakeButton(aria="Quitter le groupe", text="Quitter le groupe"),
            ]
        )
        self.assertIsNone(asyncio.run(adapter.find_join_button(timeout_s=0.5)))
        self.assertEqual(asyncio.run(adapter.group_join_state(timeout_s=1.0)), "joined")

    def test_pending_request_is_reported(self):
        adapter = self._adapter([FakeButton(aria="Annuler la demande", text="Annuler la demande")])
        self.assertIsNone(asyncio.run(adapter.find_join_button(timeout_s=0.5)))
        self.assertEqual(asyncio.run(adapter.group_join_state(timeout_s=1.0)), "pending")

    def test_hidden_button_is_skipped(self):
        adapter = self._adapter(
            [FakeButton(aria="Rejoindre le groupe", visible=False)]
        )
        self.assertIsNone(asyncio.run(adapter.find_join_button(timeout_s=0.5)))

    def test_waits_for_late_rendered_button(self):
        """真实抓包发现：可见的加入按钮要 ~5 秒才出现，早一步判断就会误判成"没有"。"""
        page = FakeButtonPage([FakeButton(aria="Rejoindre le groupe")])
        page.late_render_after = 2  # 前两次可见性检查都回答 False
        adapter = FacebookAdapter(session_name="fbqa")
        adapter._page = page

        button = asyncio.run(adapter.find_join_button(timeout_s=5.0))
        self.assertIsNotNone(button)
        self.assertGreater(page.visibility_checks, 2)

    def test_scrolls_to_trigger_lazy_rendering(self):
        """实测：不滚动的话群页头的加入按钮一直是 0x0，必须先催渲染。"""
        page = FakeButtonPage([FakeButton(aria="Rejoindre le groupe")])
        adapter = FacebookAdapter(session_name="fbqa")
        adapter._page = page

        asyncio.run(adapter.find_join_button(timeout_s=1.0))
        self.assertTrue(any("scrollBy" in script for script in page.scrolls))
        # 催过一次就不再重复（避免每次判断都滚动，浪费时间）
        count_before = len(page.scrolls)
        asyncio.run(adapter.find_join_button(timeout_s=1.0))
        self.assertEqual(len(page.scrolls), count_before)

    def test_page_search_box_does_not_look_like_joined(self):
        """真实页面里搜索框的 aria-label 是"Quitter la saisie semi-automatique"，
        只匹配 "quitter" 会误判成已入群——必须用完整短语，而且以加入按钮为准。"""
        adapter = self._adapter(
            [
                FakeButton(aria="Quitter la saisie semi-automatique"),
                FakeButton(aria="Rejoindre le groupe", text="Rejoindre le groupe"),
            ]
        )
        self.assertEqual(asyncio.run(adapter.group_join_state(timeout_s=1.0)), "joinable")


if __name__ == "__main__":
    unittest.main()
