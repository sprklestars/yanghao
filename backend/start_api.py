#!/usr/bin/env python3
"""启动后端（推荐用这个，而不是手打 uvicorn 命令）。

做三件事：

1. 从 `backend/.env` 读 `APP_HOST` / `APP_PORT`（默认 0.0.0.0:8000）；
2. 端口绑不上时**自动换一个能用的**（Windows 上 Hyper-V/WSL2/Docker 会动态预留
   一大片端口，8000 经常被圈进去，报 WinError 10013）；
3. 端口不是 8000 时，顺手把 `frontend/.env.local` 同步成正确的 API/WS 地址
   （该文件已在 .gitignore 里，不会被提交），这样前端不用手动改。

用法：

    cd backend
    .\\.venv\\Scripts\\python.exe start_api.py            # 正常启动
    .\\.venv\\Scripts\\python.exe start_api.py --reload    # 开发时自动重载
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# 输出编码：
# * 直接在控制台跑：保持控制台自己的编码（中文正常），遇到打不出的字符降级成 "?"，
#   免得一个 emoji 就把启动脚本搞崩（Windows 控制台默认 GBK，实测踩过）。
# * 被重定向到文件/管道（比如日志）：改用 UTF-8，日志文件才能正常读。
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.isatty():
            _stream.reconfigure(errors="replace")
        else:
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # 老解释器 / 已被替换的流
        pass

from app.core.config import settings  # noqa: E402
from app.core.net import pick_available_port  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_ENV_LOCAL = BACKEND_DIR.parent / "frontend" / ".env.local"


def sync_frontend_env(port: int) -> str | None:
    """把前端的 API/WS 地址同步成当前端口；内容没变就返回 None。"""
    content = (
        "# 由 backend/start_api.py 自动生成：保持与后端实际端口一致。\n"
        "# 该文件已被 .gitignore 忽略，不会提交。\n"
        f"NEXT_PUBLIC_API_URL=http://localhost:{port}/api/v1\n"
        f"NEXT_PUBLIC_WS_URL=ws://localhost:{port}/ws\n"
    )
    if FRONTEND_ENV_LOCAL.exists() and FRONTEND_ENV_LOCAL.read_text(
        encoding="utf-8"
    ) == content:
        return None
    FRONTEND_ENV_LOCAL.parent.mkdir(parents=True, exist_ok=True)
    FRONTEND_ENV_LOCAL.write_text(content, encoding="utf-8")
    return str(FRONTEND_ENV_LOCAL)


def main() -> int:
    parser = argparse.ArgumentParser(description="启动后端（端口可配置 + 自动避让）")
    parser.add_argument("--reload", action="store_true", help="开发模式：代码改动自动重载")
    parser.add_argument("--port", type=int, default=None, help="临时指定端口（覆盖 .env）")
    args = parser.parse_args()

    host = settings.app_host or "0.0.0.0"
    preferred = args.port or settings.app_port
    port = pick_available_port(host, preferred)

    if port != preferred:
        print(
            f"[提示] 端口 {preferred} 绑不上（被占用或被 Windows 预留），已自动改用 {port}",
            flush=True,
        )
    print(
        f"[启动] 后端地址：http://localhost:{port}  （API 文档 /docs，健康检查 /health）",
        flush=True,
    )

    synced = sync_frontend_env(port)
    if synced:
        print(
            f"[配置] 已同步前端配置：{synced}（如果 next dev 正在跑，请重启它生效）",
            flush=True,
        )

    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if args.reload:
        command.append("--reload")

    # 把实际端口作为环境变量传给 API 进程（环境变量优先级高于 .env），
    # 这样 API 拉起常驻守护进程时能带上同一个端口，两边不会错位。
    env = {**os.environ, "APP_PORT": str(port), "APP_HOST": host, "PYTHONUTF8": "1"}
    env.pop("PYTHONIOENCODING", None)
    try:
        return subprocess.call(command, cwd=str(BACKEND_DIR), env=env)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
