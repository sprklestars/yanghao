#!/usr/bin/env python3
import argparse
import asyncio
import re
import sys
from getpass import getpass
from pathlib import Path

from telethon import TelegramClient

from app.core.config import Settings

BACKEND_DIR = Path(__file__).resolve().parent
SESSION_DIR = BACKEND_DIR / "sessions"


def session_name(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", value):
        raise argparse.ArgumentTypeError("会话名请使用1–48位小写字母、数字、下划线或短横线")
    return value


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="逐个登录Telegram账号，每个名称保存独立会话")
    parser.add_argument(
        "sessions", nargs="*", type=session_name, default=["printer"],
        help="例如 test1 test2 test3；不指定时使用 printer",
    )
    args = parser.parse_args(argv)
    if len(set(args.sessions)) != len(args.sessions):
        parser.error("会话名称不能重复")
    return args


async def login_account(name: str, settings: Settings) -> bool:
    print(f"\n正在登录会话 [{name}]，请使用对应测试账号的手机号。")
    print("请勿同时用其他进程操作同一个会话文件。")
    client = TelegramClient(
        str(SESSION_DIR / name),
        settings.tg_api_id,
        settings.tg_api_hash,
        proxy=("http", "127.0.0.1", 7890),
        timeout=10,
        connection_retries=2,
    )
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await client.start(
                phone=lambda: input(f"[{name}] 手机号（含国家区号）: ").strip(),
                code_callback=lambda: getpass(f"[{name}] Telegram验证码（输入隐藏）: ").strip(),
                password=lambda: getpass(f"[{name}] 两步验证密码（输入隐藏）: "),
            )
        else:
            print(f"[{name}] 已认证，跳过重复登录。")
        if await client.get_me() is None:
            print(f"[{name}] 尚未完成认证。")
            return False
    finally:
        await client.disconnect()
    print(f"[{name}] LOGIN SUCCESSFUL — 已保存 sessions/{name}.session")
    return True


async def main(names: list[str]) -> int:
    if not sys.stdin.isatty():
        print("请在自己的交互式终端运行登录命令；不要把验证码或密码发送到聊天窗口。")
        return 1
    settings = Settings(_env_file=BACKEND_DIR / ".env")
    if not settings.tg_api_id or not settings.tg_api_hash:
        print("请先在 backend/.env 配置 TG_API_ID 和 TG_API_HASH。")
        return 1
    SESSION_DIR.mkdir(exist_ok=True)
    succeeded = 0
    for name in names:
        try:
            succeeded += await login_account(name, settings)
        except EOFError:
            print("终端输入已关闭，停止登录；已保存的会话保留。")
            return 1
        except Exception as exc:
            print(f"[{name}] 登录失败（{type(exc).__name__}）；会话文件保留，不自动切换代理或删除会话。")
            print("请检查代理、登录信息，以及是否有其他进程占用会话。")
    print(f"\n认证成功 {succeeded}/{len(names)} 个会话；本命令只登录，不启动自动回复。")
    return 0 if succeeded == len(names) else 1


if __name__ == "__main__":
    args = parse_args()
    try:
        sys.exit(asyncio.run(main(args.sessions)))
    except KeyboardInterrupt:
        print("\n已取消登录，已保存的会话保留。")
        sys.exit(130)
