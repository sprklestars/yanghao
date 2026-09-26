import re
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings

# 固定按 backend/.env 读取，避免从仓库根目录启动 uvicorn 时找不到 .env，
# 导致 TG_API_ID=0 / TG_API_HASH="" 却仍能启动，直到发验证码才报错。
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
_API_HASH_RE = re.compile(r"[0-9a-fA-F]{32}")

# .env.example 与文档里出现过的示例值：用户经常直接照抄，这里显式识别出来。
_PLACEHOLDER_API_IDS = {"1234567", "12345678"}
_PLACEHOLDER_API_HASHES = {
    "your-telegram-api-hash",
    "0123456789abcdef0123456789abcdef",
}


class Settings(BaseSettings):
    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # Telegram
    tg_api_id: int = 0
    tg_api_hash: str = ""
    # 代理协议必须与代理软件实际监听的协议一致：socks5:// / socks4:// / http://，
    # 留空则直连。协议写错时 Telethon 只会报 "Connection to Telegram failed N time(s)"，
    # 详见 app/core/proxy.py。
    tg_proxy_url: str = "socks5://127.0.0.1:7890"
    # 单个适配器调用（搜索/加群/取成员/发消息）的超时秒数。
    # 卡死的连接必须在有限时间内放弃，否则会占住 worker 的执行位。
    adapter_timeout_seconds: int = 90

    # Database (must be set in .env)
    database_url: str = ""
    database_url_sync: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Security
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 1440
    # API 访问令牌：留空 = 不鉴权（本机开发的默认状态）。
    # 一旦在 .env 里填了 API_TOKEN，所有 /api/v1/* 请求都必须带
    # Authorization: Bearer <token>（或 X-API-Token），/ws 需带 ?token=。
    api_token: str = ""

    # App
    app_env: str = "development"
    log_level: str = "INFO"

    model_config = {"env_file": _ENV_FILE, "env_file_encoding": "utf-8"}

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

    def telegram_credentials_error(self) -> str | None:
        """返回 TG_API_ID / TG_API_HASH 不可用的中文原因，配置正常时返回 None。

        最常见的两种误填是「把手机号当成 api_id」和「api_hash 少抄/多抄字符」。
        这两种情况 Telethon 只会抛 `The api_id/api_hash combination is invalid`，
        看不出错在哪个字段（此时网络其实是通的），所以在真正调 API 前先自己挡一层。
        """
        api_id = str(self.tg_api_id)
        api_hash = self.tg_api_hash.strip()

        if self.tg_api_id <= 0 or not api_hash:
            return (
                "未配置 TG_API_ID / TG_API_HASH：请到 https://my.telegram.org 的 "
                "API development tools 申请（或用同一手机号登录查看已有 App），"
                "填入 backend/.env 后重启后端"
            )
        if api_id in _PLACEHOLDER_API_IDS or api_hash.lower() in _PLACEHOLDER_API_HASHES:
            return (
                f"TG_API_ID / TG_API_HASH 还是示例占位值（{api_id} / {api_hash[:4]}…）："
                "请到 https://my.telegram.org → API development tools，复制你自己 App 的 "
                "api_id 与 api_hash 覆盖这两行，然后重启后端"
            )
        # 手机号是 11-15 位，真实 api_id 不会这么长。
        if len(api_id) > 10:
            return (
                f"TG_API_ID 填错了（当前长度 {len(api_id)} 位，值 {api_id}）：这里要填 "
                "my.telegram.org 上的 App api_id（通常 7-9 位数字），不是手机号"
            )
        if not _API_HASH_RE.fullmatch(api_hash):
            return (
                "TG_API_HASH 格式不对：应为 my.telegram.org 上的 32 位十六进制字符串"
                f"（当前长度 {len(api_hash)}）"
            )
        return None


settings = Settings()
