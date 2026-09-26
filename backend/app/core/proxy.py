"""Telegram 代理配置解析。

本机代理端口相同、协议却可能不同（Clash 的 7890 往往是混合端口，v2rayN 的 7890
可能只监听 SOCKS5）。协议写错时握手会被代理拒绝（python-socks 抛
``ProxyError: Invalid proxy response``），Telethon 只会笼统地报
``Connection to Telegram failed N time(s)``，很难定位。

所以统一从 ``.env`` 的 ``TG_PROXY_URL`` 读取，支持 ``socks5://`` /
``socks4://`` / ``http://``，留空表示不使用代理。
"""

from urllib.parse import urlparse

_ALLOWED_SCHEMES = {"socks5", "socks4", "http", "https"}
_DEFAULT_PORT = 7890


def parse_proxy_url(url: str | None) -> tuple | None:
    """把 ``socks5://127.0.0.1:7890`` 解析成 Telethon 的 ``proxy`` 参数。

    返回 Telethon 的元组格式 ``(proxy_type, addr, port, rdns, username, password)``
    ——（脚本里还在用 ``PROXY[1]`` / ``PROXY[2]`` 取主机和端口，所以不能用 dict）。
    返回 ``None`` 表示不使用代理；地址非法时抛 ``ValueError``。
    """
    if url is None or not url.strip():
        return None

    raw = url.strip()
    if "://" not in raw:
        raw = f"socks5://{raw}"
    parsed = urlparse(raw)

    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"不支持的代理协议: {scheme or '(空)'}")
    if not parsed.hostname:
        raise ValueError(f"代理地址缺少主机名: {url}")

    return (
        # python-socks / PySocks 都不单独区分 TLS 代理，https 统一按 HTTP CONNECT 处理。
        "http" if scheme == "https" else scheme,
        parsed.hostname,
        parsed.port or _DEFAULT_PORT,
        True,
        parsed.username,
        parsed.password,
    )


def telegram_proxy() -> tuple | None:
    """当前生效的 Telegram 代理（来自 ``TG_PROXY_URL``，空值表示直连）。"""
    from app.core.config import settings

    return parse_proxy_url(settings.tg_proxy_url)
