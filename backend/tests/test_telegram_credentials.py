import unittest

from app.core.config import Settings


def make_settings(**overrides) -> Settings:
    """构造不读 .env 的 Settings（显式传参优先于环境变量），避免受本机配置影响。"""
    return Settings(_env_file=None, **overrides)


class TelegramCredentialsErrorTests(unittest.TestCase):
    def test_valid_pair_passes(self):
        settings = make_settings(tg_api_id=9876543, tg_api_hash="ab" * 16)
        self.assertIsNone(settings.telegram_credentials_error())

    def test_missing_credentials_is_reported(self):
        problem = make_settings(tg_api_id=0, tg_api_hash="").telegram_credentials_error()
        self.assertIsNotNone(problem)
        self.assertIn("my.telegram.org", problem)

    def test_phone_number_as_api_id_is_reported(self):
        settings = make_settings(tg_api_id=8801934061959, tg_api_hash="ab" * 16)
        problem = settings.telegram_credentials_error()
        self.assertIsNotNone(problem)
        self.assertIn("手机号", problem)

    def test_short_api_hash_is_reported(self):
        settings = make_settings(tg_api_id=9876543, tg_api_hash="66abcd")
        problem = settings.telegram_credentials_error()
        self.assertIsNotNone(problem)
        self.assertIn("32 位", problem)

    def test_non_hex_api_hash_is_reported(self):
        settings = make_settings(tg_api_id=9876543, tg_api_hash="z" * 32)
        problem = settings.telegram_credentials_error()
        self.assertIsNotNone(problem)
        self.assertIn("32 位", problem)

    def test_example_placeholder_pair_is_reported(self):
        settings = make_settings(
            tg_api_id=1234567, tg_api_hash="0123456789abcdef0123456789abcdef"
        )
        problem = settings.telegram_credentials_error()
        self.assertIsNotNone(problem)
        self.assertIn("示例占位值", problem)

    def test_env_example_placeholder_hash_is_reported(self):
        settings = make_settings(tg_api_id=12345678, tg_api_hash="your-telegram-api-hash")
        problem = settings.telegram_credentials_error()
        self.assertIsNotNone(problem)
        self.assertIn("示例占位值", problem)

    def test_negative_api_id_is_reported(self):
        settings = make_settings(tg_api_id=-1, tg_api_hash="ab" * 16)
        problem = settings.telegram_credentials_error()
        self.assertIsNotNone(problem)
        self.assertIn("my.telegram.org", problem)


if __name__ == "__main__":
    unittest.main()
