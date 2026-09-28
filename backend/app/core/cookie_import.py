"""把用户手上的 Facebook cookie 转成 Playwright 的 cookie 格式。

为什么需要这个：在自动化浏览器里手动登 Facebook 经常被风控卡住（转圈/要验证），
但账号本身是好的——用户在自己平时的浏览器里已经有登录态了。与其重新登一次，
不如把 cookie 直接导进来。

支持三种粘贴方式（都是用户真能拿到的）：

1. ``Cookie:`` 请求头那一长串：``c_user=100...; xs=12%3A...; datr=...``
   （DevTools → Network → 任意 facebook.com 请求 → Request Headers → cookie）
2. JSON：Playwright 导出的数组、扩展导出的对象数组（含 expirationDate/hostOnly），
   或者直接 ``{"c_user": "...", "xs": "..."}`` 这种键值对
3. Netscape ``cookies.txt``（"Get cookies.txt" 之类扩展导出的格式，含 ``#HttpOnly_`` 前缀）

注意：Facebook 的登录态靠 ``c_user`` + ``xs``，而 ``xs`` 是 HttpOnly，
所以在控制台敲 ``document.cookie`` 拿不到它，必须用扩展导出或从请求头里复制。
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

FB_DOMAIN = ".facebook.com"
LOGIN_COOKIES: tuple[str, ...] = ("c_user", "xs")
KEY_COOKIES: tuple[str, ...] = ("c_user", "xs", "datr", "fr", "sb")
# 这几个在 Facebook 那边是 HttpOnly 的，从请求头/扩展导入时要标上
HTTP_ONLY_HINT = {"xs", "datr", "sb", "fr"}

_SAME_SITE_MAP = {
    "no_restriction": "None",
    "none": "None",
    "lax": "Lax",
    "strict": "Strict",
    # "unspecified" 保持缺省，Playwright 会按 Lax 处理
}


def _normalize_domain(domain: Any, host_only: bool = False) -> str:
    text = str(domain or FB_DOMAIN).strip()
    if not text:
        return FB_DOMAIN
    if not text.startswith(".") and not host_only:
        text = "." + text
    return text


def _build(
    name: str,
    value: str,
    *,
    domain: Any = FB_DOMAIN,
    path: Any = "/",
    secure: bool = True,
    http_only: bool | None = None,
    same_site: Any = None,
    expires: Any = None,
    host_only: bool = False,
) -> dict | None:
    name = str(name or "").strip()
    if not name:
        return None
    cookie: dict[str, Any] = {
        "name": name,
        "value": "" if value is None else str(value),
        "domain": _normalize_domain(domain, host_only),
        "path": str(path or "/"),
        "secure": bool(secure),
        "httpOnly": (name in HTTP_ONLY_HINT) if http_only is None else bool(http_only),
    }
    mapped = _SAME_SITE_MAP.get(str(same_site).strip().lower()) if same_site else None
    if mapped == "None":
        cookie["sameSite"] = "None"
        cookie["secure"] = True  # SameSite=None 必须 Secure，否则浏览器直接拒绝
    elif mapped:
        cookie["sameSite"] = mapped
    try:
        expires_value = float(expires) if expires not in (None, "", -1, "-1") else None
    except (TypeError, ValueError):
        expires_value = None
    if expires_value and expires_value > 0:
        cookie["expires"] = expires_value
    return cookie


def _from_json_item(item: dict) -> dict | None:
    name = item.get("name") or item.get("Name") or item.get("key")
    value = item.get("value") if "value" in item else item.get("Value")
    return _build(
        name or "",
        value,
        domain=item.get("domain") or item.get("Domain"),
        path=item.get("path") or item.get("Path"),
        secure=item.get("secure", item.get("Secure", True)),
        http_only=item.get("httpOnly", item.get("http_only")),
        same_site=item.get("sameSite") or item.get("same_site"),
        expires=item.get("expires", item.get("expirationDate", item.get("Expires"))),
        host_only=bool(item.get("hostOnly")),
    )


def _parse_json(text: str) -> list[dict] | None:
    if text[:1] not in ("[", "{"):
        return None
    data = json.loads(text)  # 交给调用方处理 JSONDecodeError
    if isinstance(data, list):
        return [c for c in (_from_json_item(i) for i in data if isinstance(i, dict)) if c]
    if isinstance(data, dict):
        for key in ("cookies", "Cookies"):
            if isinstance(data.get(key), list):
                return [c for c in (_from_json_item(i) for i in data[key]) if c]
        # {"c_user": "...", "xs": "..."} 这种，或者带 name/value 的单条
        if data.get("name") and "value" in data:
            single = _from_json_item(data)
            return [single] if single else []
        items = [
            _build(name, value)
            for name, value in data.items()
            if isinstance(value, (str, int, float))
        ]
        return [c for c in items if c]
    return []


def _parse_netscape(text: str) -> list[dict]:
    """Netscape cookies.txt：domain, flag, path, secure, expires, name, value。"""
    cookies: list[dict] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        http_only = False
        if line.startswith("#HttpOnly_"):  # 扩展用这个前缀标 HttpOnly
            http_only = True
            line = line[len("#HttpOnly_") :]
        elif line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _flag, path, secure, expires, name, value = parts[:7]
        cookie = _build(
            name,
            value,
            domain=domain,
            path=path,
            secure=str(secure).upper() == "TRUE",
            http_only=http_only or name in HTTP_ONLY_HINT,
            expires=expires,
        )
        if cookie:
            cookies.append(cookie)
    return cookies


def _parse_header(text: str) -> list[dict]:
    """`c_user=1; xs=2`（可能有前缀 `Cookie: `，也可能是多行）。"""
    cookies: list[dict] = []
    for chunk in text.replace("\r", "\n").split("\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.lower().startswith("cookie:"):
            chunk = chunk[len("cookie:") :].strip()
        for pair in chunk.split(";"):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            name, _, value = pair.partition("=")
            cookie = _build(name.strip(), value.strip())
            if cookie:
                cookies.append(cookie)
    return cookies


def _dedupe(cookies: list[dict]) -> list[dict]:
    seen: dict[tuple[str, str], dict] = {}
    for cookie in cookies:
        seen[(cookie["name"], cookie["domain"])] = cookie
    return list(seen.values())


def parse_cookie_input(raw: Any) -> list[dict]:
    """把用户粘贴的文本解析成 Playwright cookie 列表；解析不出来抛 ValueError。"""
    if isinstance(raw, (list, dict)):
        text = json.dumps(raw, ensure_ascii=False)
    else:
        text = str(raw or "")
    if not text.strip():
        raise ValueError("粘贴内容为空")

    errors: list[str] = []
    for parser in (_parse_json, _parse_netscape, _parse_header):
        try:
            parsed = parser(text)
        except json.JSONDecodeError as exc:
            errors.append(f"JSON 格式不对（{exc.msg}）")
            continue
        if not parsed:  # _parse_json 对非 JSON 文本返回 None
            continue
        cookies = _dedupe(parsed)
        if cookies:
            return cookies

    if errors:
        raise ValueError("；".join(errors))
    raise ValueError(
        "没解析出任何 cookie。支持：`c_user=...; xs=...` 这种请求头、JSON 数组、"
        "或 Netscape 格式的 cookies.txt（扩展导出的那种）"
    )


def missing_login_cookies(cookies: list[dict]) -> list[str]:
    """缺哪些登录必需的 cookie（按名字比较，大小写不敏感）。"""
    names = {str(c.get("name", "")).lower() for c in cookies}
    return [name for name in LOGIN_COOKIES if name.lower() not in names]


# Facebook 登录后页面上会出现的东西（多语言 + 新旧文案都给上）
LOGGED_IN_SELECTORS = (
    '[data-testid="royal_profile_picture"]',
    'button[aria-label="Account"]',
    'button[aria-label="Your profile"]',
    '[aria-label="Trang cá nhân"]',
    '[aria-label="Messenger"]',
    '[aria-label="Tin nhắn"]',
)


async def verify_facebook_cookies(
    cookies: list[dict],
    *,
    proxy_url: str | None = None,
    timeout_ms: int = 60000,
) -> dict:
    """用无头浏览器带上这些 cookie 打开 facebook.com，判断是不是真的登录了。

    ``verified`` 为 True/False 是结论；为 None 表示没测出来（浏览器起不来、
    网络不通），这时不能怪 cookie。
    """
    import asyncio

    from playwright.async_api import async_playwright

    from app.core.browser_launch import launch_browser

    result: dict[str, Any] = {"verified": None, "reason": "", "url": "", "user_id": None}
    expected = next((c["value"] for c in cookies if c.get("name") == "c_user"), None)

    playwright = await async_playwright().start()
    try:
        browser, _channel = await launch_browser(
            playwright,
            headless=True,
            proxy={"server": proxy_url} if proxy_url else None,
            args=["--disable-blink-features=AutomationControlled", "--no-first-run"],
            log=logger.info,
        )
        try:
            context = await browser.new_context(locale="vi-VN")
            await context.add_cookies(cookies)
            page = await context.new_page()
            await page.goto(
                "https://www.facebook.com/",
                wait_until="domcontentloaded",
                timeout=timeout_ms,
            )
            await asyncio.sleep(2)
            result["url"] = page.url

            live = {c["name"]: c["value"] for c in await context.cookies()}
            result["user_id"] = live.get("c_user")

            if "/login" in page.url or "checkpoint" in page.url:
                result.update(verified=False, reason="Facebook 把请求重定向到了登录/验证页")
                return result
            for selector in LOGGED_IN_SELECTORS:
                try:
                    if await page.query_selector(selector):
                        result.update(verified=True, reason="页面上找到了登录后的元素")
                        return result
                except Exception:  # 单个选择器失败不影响判断
                    continue
            if live.get("c_user") and (expected is None or live["c_user"] == expected):
                result.update(verified=True, reason="浏览器保留了登录 cookie（c_user）")
                return result
            result.update(verified=False, reason="页面看起来还是未登录状态")
            return result
        finally:
            await browser.close()
    except Exception as exc:
        logger.warning("校验 Facebook cookie 失败：%s", exc)
        result.update(verified=None, reason=f"校验没跑成：{str(exc).splitlines()[0][:200]}")
        return result
    finally:
        await playwright.stop()
