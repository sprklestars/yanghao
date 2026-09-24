from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # Telegram
    tg_api_id: int = 0
    tg_api_hash: str = ""

    # Database (must be set in .env)
    database_url: str = ""
    database_url_sync: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Security
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 1440

    # App
    app_env: str = "development"
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("tg_api_id", mode="before")
    @classmethod
    def _tolerate_blank_tg_api_id(cls, value):
        """允许 TG_API_ID 留空或填占位文本。

        .env.example 里给的是占位字符串、真实部署时也常常先留空，
        而 tg_api_id 声明为 int，空串会让 pydantic 直接抛 ValidationError，
        导致连 `alembic upgrade head` 都跑不起来。这里统一降级为 0。
        """
        if value is None or value == "":
            return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0


settings = Settings()
