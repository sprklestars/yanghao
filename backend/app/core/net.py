"""端口可用性判断与自动挑选。

为什么需要：Windows 上装了 Hyper-V / WSL2 / Docker Desktop 之后，系统会**动态预留**
一大片端口（本机实测 7681-8580 全被预留），落在里面的端口任何程序都绑不上，
报的是 `[WinError 10013] 以一种访问权限不允许的方式做了一个访问套接字的尝试`
——不是"端口被别的进程占用"，也不是代码问题。所以后端启动时应该先探一下，
绑不上就自动换一个能用的端口，而不是让用户对着报错干瞪眼。
"""

from __future__ import annotations

import logging
import socket

logger = logging.getLogger(__name__)


def is_port_bindable(host: str, port: int) -> bool:
    """这个端口现在能不能绑上（被占用或被系统预留都会返回 False）。"""
    if port <= 0:
        return False
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # 独占绑定：避免"刚好有个 TIME_WAIT 的旧连接"造成误判
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    except (AttributeError, OSError):
        pass  # 非 Windows 平台没有这个选项
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


# 首选端口绑不上时，依次试这些（都避开了 Windows 常见的动态预留段）
FALLBACK_PORTS: tuple[int, ...] = (
    8600, 8601, 8602, 8603, 8604,
    9000, 9001, 9002,
    6000, 6001,
)


def pick_available_port(
    host: str,
    preferred: int,
    *,
    fallbacks: tuple[int, ...] = FALLBACK_PORTS,
    is_bindable=is_port_bindable,
) -> int:
    """返回一个能绑的端口：优先 ``preferred``，不行就按 ``fallbacks`` 依次试。

    全都被占用时抛 RuntimeError（这时需要人工介入，别静默换到奇怪的地方去）。
    """
    if is_bindable(host, preferred):
        return preferred
    logger.warning("端口 %s 绑不上（被占用或被系统预留），开始自动换端口", preferred)
    for port in fallbacks:
        if is_bindable(host, port):
            logger.warning("改用端口 %s", port)
            return port
    raise RuntimeError(
        f"端口 {preferred} 及候选端口 {fallbacks} 都绑不上，请检查是否有别的实例在跑，"
        "或执行 `netsh interface ipv4 show excludedportrange protocol=tcp` 看被系统预留了哪些段"
    )
