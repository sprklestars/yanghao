"""Telegram 会话文件的目录工具。

Telethon 在 **构造 TelegramClient 的那一瞬间** 就会创建 SQLite 会话文件，
因此文件所在目录必须在此之前已经存在，否则会直接抛
``sqlite3.OperationalError: unable to open database file``。
"""

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
SESSION_DIR = BACKEND_DIR / "sessions"


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
