"""异步调用的小工具：给可能卡住的外部调用加超时。"""

import asyncio
import logging
from collections.abc import Awaitable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class OperationTimeoutError(RuntimeError):
    """外部调用超时（网络卡住、连接被重置后一直重连等）。"""


async def with_timeout(
    awaitable: Awaitable[T],
    seconds: float,
    what: str,
    on_timeout: tuple = (),
) -> T:
    """执行 ``awaitable``，超时抛 :class:`OperationTimeoutError`。

    ``on_timeout`` 里的异常也按超时处理（例如 Telethon 断连时抛的可能是
    ``ConnectionResetError`` 而不是 ``TimeoutError``）。
    """
    try:
        return await asyncio.wait_for(awaitable, timeout=seconds)
    except (asyncio.TimeoutError, *on_timeout) as e:
        raise OperationTimeoutError(f"{what} 超时（>{seconds:g}s）: {type(e).__name__}") from e
