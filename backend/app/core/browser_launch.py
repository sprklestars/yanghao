"""挑一个「真的能启动」的 Playwright 浏览器。

2026-09-26 现场排查（Windows 本机）结论：

Playwright 自带的 Chromium **只能起无头（headless）**。带 ``headless=False``
启动时 Windows 报「应用程序的并行配置不正确」，Playwright 侧只能看到
``BrowserType.launch: spawn UNKNOWN``：

    chrome.exe 内嵌清单要求从属程序集 ``153.0.8010.12``（内含 chrome_elf.dll），
    而本机 SxS 解析不到这个程序集 → CreateProcess 直接失败（事件日志 SideBySide）。

同一时刻 ``chrome-headless-shell.exe``（无头用的那个可执行文件）和系统里已安装的
Edge / Chrome 都能正常启动，所以这不是我们代码的问题，也不该让「打开浏览器」
这个按钮永久坏掉——改成按顺序探测，谁先起来就用谁：

* 有头（人工登录 Facebook）：优先系统已装的 Edge → Chrome → 自带 Chromium；
* 无头（任务流水线自动采集）：优先自带 Chromium（版本固定），再退到 Edge / Chrome。

选中的结果缓存在 ``sessions/.browser_channel.json``，下次直接命中，不用每次先失败一次。
想强制指定浏览器可以设环境变量 ``FB_BROWSER_CHANNEL=msedge|chrome|chromium``。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from app.core.session_paths import SESSION_DIR, ensure_session_dir

logger = logging.getLogger(__name__)

# Playwright 的 channel 取值；None 表示「自带的 Chromium」
CHANNEL_BUNDLED = "chromium"
KNOWN_CHANNELS: tuple[str, ...] = (CHANNEL_BUNDLED, "chrome", "msedge")

ENV_VAR = "FB_BROWSER_CHANNEL"
CACHE_FILE = SESSION_DIR / ".browser_channel.json"

# 探测顺序：headless=True 走 self-contained 的 headless shell，最稳，放第一
HEADLESS_ORDER: tuple[str, ...] = (CHANNEL_BUNDLED, "msedge", "chrome")
# 人工登录要有窗口：自带的 Chromium 在这台机器上有头起不来，所以先试真浏览器
HEADED_ORDER: tuple[str, ...] = ("msedge", "chrome", CHANNEL_BUNDLED)


def channel_label(channel: str | None) -> str:
    """给人看的名字，日志/错误信息里用。"""
    return {
        CHANNEL_BUNDLED: "Playwright 自带 Chromium",
        "chrome": "Google Chrome",
        "msedge": "Microsoft Edge",
    }.get(channel or CHANNEL_BUNDLED, str(channel))


def normalize_channel(value: Any) -> str | None:
    """把用户/缓存里的写法归一化成 channel 值；无效或空值返回 None（=不指定）。"""
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text in ("auto", "bundled", "chromium", "chrome-headless-shell"):
        return CHANNEL_BUNDLED
    if text in ("chrome", "google-chrome"):
        return "chrome"
    if text in ("msedge", "edge", "microsoft-edge", "microsoft edge"):
        return "msedge"
    return None


def playwright_channel(channel: str | None) -> str | None:
    """归一化后的值 → 传给 ``chromium.launch(channel=...)`` 的参数。"""
    return None if channel in (None, CHANNEL_BUNDLED) else channel


def candidate_order(
    *,
    headless: bool,
    preferred: Any = None,
    cached: Any = None,
) -> list[str]:
    """探测顺序：环境变量 > 上次成功记录 > 默认顺序（去重）。"""
    default = list(HEADLESS_ORDER if headless else HEADED_ORDER)
    order: list[str] = []
    for item in (normalize_channel(preferred), normalize_channel(cached)):
        if item and item not in order:
            order.append(item)
    for item in default:
        if item not in order:
            order.append(item)
    return order


def _read_cache() -> dict:
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_cached_channel(mode: str) -> str | None:
    """``mode`` 取 "headed" / "headless"；没有记录时返回 None。"""
    value = _read_cache().get(mode)
    key = str(value).strip().lower() if value is not None else ""
    return key if key in KNOWN_CHANNELS else None


def save_cached_channel(mode: str, channel: str | None) -> None:
    key = channel or CHANNEL_BUNDLED
    if key not in KNOWN_CHANNELS:
        return
    data = _read_cache()
    if data.get(mode) == key:
        return
    data[mode] = key
    try:
        ensure_session_dir()
        Path(CACHE_FILE).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:  # 缓存写不进去不影响功能
        logger.debug("无法写入浏览器缓存 %s", CACHE_FILE, exc_info=True)


def clear_cached_channel(mode: str) -> None:
    """记录的浏览器已经起不来了：清掉，下次重新探测。"""
    data = _read_cache()
    if mode not in data:
        return
    data.pop(mode, None)
    try:
        Path(CACHE_FILE).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def _launch_hint() -> str:
    return (
        "可用的补救办法：1) 安装 Microsoft Edge 或 Google Chrome；"
        "2) 执行 `python -m playwright install chromium` 重装自带浏览器；"
        f"3) 用环境变量 {ENV_VAR}=msedge 强制指定浏览器。"
    )


async def launch_browser(
    playwright: Any,
    *,
    headless: bool,
    proxy: dict | None = None,
    args: list[str] | None = None,
    log: Any = None,
) -> tuple[Any, str]:
    """按顺序试，返回 ``(browser, channel)``；全失败抛 RuntimeError。"""
    mode = "headless" if headless else "headed"
    order = candidate_order(
        headless=headless,
        preferred=os.environ.get(ENV_VAR, ""),
        cached=load_cached_channel(mode),
    )
    emit = log or (lambda message: logger.info("%s", message))
    failures: list[str] = []

    for channel in order:
        kwargs: dict[str, Any] = {"headless": headless}
        pw_channel = playwright_channel(channel)
        if pw_channel:
            kwargs["channel"] = pw_channel
        if proxy:
            kwargs["proxy"] = proxy
        if args:
            kwargs["args"] = list(args)
        try:
            browser = await playwright.chromium.launch(**kwargs)
        except Exception as exc:  # 换下一个候选，别让一个坏浏览器把流程堵死
            reason = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
            failures.append(f"{channel_label(channel)}：{reason}")
            clear_cached_channel(mode)
            emit(f"⚠️ {channel_label(channel)} 启动失败（{reason}），换下一个浏览器…")
            continue
        save_cached_channel(mode, channel)
        emit(f"🚀 已启动浏览器：{channel_label(channel)}")
        return browser, channel

    raise RuntimeError("没有可用的浏览器 —— " + "；".join(failures) + "。" + _launch_hint())
