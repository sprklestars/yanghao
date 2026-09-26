"""Telegram 会话文件的目录工具。

Telethon 在 **构造 TelegramClient 的那一瞬间** 就会创建 SQLite 会话文件，
因此文件所在目录必须在此之前已经存在，否则会直接抛
``sqlite3.OperationalError: unable to open database file``。
"""

import re
from enum import Enum
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
SESSION_DIR = BACKEND_DIR / "sessions"

# 会话名会直接拼成文件名（sessions/<name>.session），必须限定字符集，
# 否则 "..\..\x" 这种输入能写到目录外面去。前端的"添加账号"也用同一套规则。
SESSION_NAME_PATTERN = r"[a-z0-9][a-z0-9_-]{0,47}"
_SESSION_NAME_RE = re.compile(rf"^{SESSION_NAME_PATTERN}$")


def is_valid_session_name(name: str) -> bool:
    """会话名是否合法：1-48 位小写字母/数字/下划线/短横线，且不能以符号开头。"""
    return bool(_SESSION_NAME_RE.fullmatch(name or ""))


# 各平台"登录态文件"的命名约定（sessions/ 目录就是账号真源）
PLATFORM_SESSION_SUFFIX: dict[str, str] = {
    "telegram": ".session",
    "facebook": "_cookies.json",
    "zalo": "_zalo.json",
}


def _platform_key(platform) -> str:
    """平台名归一化：传枚举或字符串都行。"""
    return platform.value if isinstance(platform, Enum) else str(platform)


def platform_session_path(platform, name: str) -> Path:
    return SESSION_DIR / f"{name}{PLATFORM_SESSION_SUFFIX[_platform_key(platform)]}"


def platform_session_name(platform, path: Path | str) -> str:
    """从登录态文件路径反推账号名。"""
    path = Path(path)
    suffix = PLATFORM_SESSION_SUFFIX[_platform_key(platform)]
    return path.name[: -len(suffix)] if path.name.endswith(suffix) else path.stem


def ensure_session_dir(session_path: str | Path | None = None) -> Path:
    """确保 Telethon 即将写入的 session 文件所在目录存在。

    兼容调用方现有的三种传法：

    - ``None``：创建默认的 ``backend/sessions/``；
    - 绝对路径（API 端点传 ``str(SESSION_DIR / name)``）：创建其父目录；
    - 带目录的相对路径（脚本传 ``sessions/printer``）：按当前工作目录创建。

    纯会话名（如 ``printer``）的父目录就是当前工作目录，``mkdir`` 是幂等的空操作。
    返回创建（或已存在）的目录。
    """
    if session_path is None:
        directory = SESSION_DIR
    else:
        directory = Path(str(session_path)).expanduser().parent
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def remove_session_files(session_path: str | Path) -> list[Path]:
    """删除 Telethon 为某个会话名写出的文件（``.session`` 与 ``.session-journal``）。

    参数是 ``backend/sessions/<name>`` 这种不含 ``.session`` 后缀的路径。
    只用于清理「刚新建、但登录没成功」的会话：Telethon 构造客户端时就会建好
    ``.session`` 文件，失败也会留个空壳，而账号列表是直接扫描 ``sessions/`` 目录的，
    会把这个空壳显示成一个真实账号。
    """
    base = Path(str(session_path))
    removed: list[Path] = []
    for suffix in (".session", ".session-journal"):
        path = Path(f"{base}{suffix}")
        if not path.exists():
            continue
        try:
            path.unlink()
        except OSError:
            continue
        removed.append(path)
    return removed


def session_in_use(session_path: str | Path) -> bool:
    """会话文件是否被别的连接/进程占用（SQLite 写锁）。

    一个 `.session` 同一时刻只能被一个客户端用：常驻服务、任务流水线、或者
    「上次运行没关干净的残留连接」都会让它一直锁着，表现就是别人一用就报
    `sqlite3.OperationalError: database is locked`。
    """
    base = Path(str(session_path))
    path = base if base.suffix == ".session" else Path(f"{base}.session")
    if not path.exists():
        return False

    # Windows 上还可能被别的进程占着句柄（删不掉、但 SQLite 未必报锁），
    # 所以先试一次普通读写打开。
    try:
        with open(path, "r+b"):
            pass
    except OSError:
        return True

    import sqlite3

    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=rw", uri=True, timeout=0.3)
    except sqlite3.Error:
        return False
    try:
        con.execute("BEGIN IMMEDIATE")  # 拿不到写锁就说明有人在用
        con.execute("ROLLBACK")
    except sqlite3.Error:
        return True
    finally:
        con.close()
    return False
