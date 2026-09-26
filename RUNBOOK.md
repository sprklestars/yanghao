# 🖥️ 本机运行指南（Windows / PowerShell）

> 本文件按**你这台电脑的实际情况**写的：路径、工具位置、端口都取自本机实测，
> 不是通用模板。仓库根目录：`C:\Users\86178\.codex\worktrees\ac44\yanghao-1`
>
> 最近更新：2026-09-25

---

## 📋 当前状态（本机实测）

| 项目 | 位置 / 值 | 状态 |
|------|-----------|------|
| Python | `C:\Users\86178\AppData\Local\Python\pythoncore-3.14-64\python.exe`（3.14.7） | ✅ |
| uv | `E:\app\UV\uv.exe`（0.12.18） | ✅ 已在 PATH |
| 虚拟环境 | `backend\.venv` | ✅ 依赖已装 |
| Node / npm | `E:\app\Nodejs\`（node 24 / npm 11） | ✅ |
| Docker Desktop | `E:\tool\Docker Desktop.exe` | ✅ 已安装，需要手动启动 |
| 数据库容器 | `postgres` / `redis`（docker compose） | 按需启动 |
| 后端 API | http://localhost:8000 | 按需启动 |
| 前端界面 | http://localhost:3000 | 按需启动 |
| Telegram 代理 | `127.0.0.1:7890`（代码里硬编码） | Telegram 相关功能必需 |

---

## 🧠 运行逻辑（先理解这个，再照着敲命令）

```
浏览器界面 (Next.js :3000)
      │  ① REST 请求        ② WebSocket 连接
      ▼
后端 API (FastAPI :8000)  ←── 唯一的"事实来源"
      │                     接口 / 实时广播 / 消息落库都在这里
      ├──► PostgreSQL :5432   业务数据（账号 / 任务 / 对话 / 消息 / 情报）
      └──► Redis :6379        Celery 任务队列、限流计数
```

三个要点：

1. **前端自己不碰数据库**，所有数据都通过 `http://localhost:8000/api/v1/...` 拿。
   所以后端一停，前端页面就只能报错——这就是"后端不可达"的由来。
2. **PostgreSQL 的表不会自动创建**，靠 Alembic 迁移脚本建，所以首次要跑一次
   `alembic upgrade head`。
3. 启动顺序是**有依赖的**：数据库 → 后端 → 前端。反过来必然失败。

---

## 🚀 每次启动（开三个 PowerShell 窗口）

### 窗口 1 · 数据库

先手动启动 Docker Desktop（开始菜单，或直接运行 `E:\tool\Docker Desktop.exe`），
等托盘图标变成运行中，然后：

```powershell
cd C:\Users\86178\.codex\worktrees\ac44\yanghao-1
docker compose up -d postgres redis
docker compose ps
```

`docker compose ps` 里两个服务都显示 `(healthy)` 才算好。

### 窗口 2 · 后端 API（这个窗口要一直开着）

```powershell
cd C:\Users\86178\.codex\worktrees\ac44\yanghao-1\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

用 uv 也一样（它会自动用 `backend\.venv`）：

```powershell
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 窗口 3 · 前端

```powershell
cd C:\Users\86178\.codex\worktrees\ac44\yanghao-1\frontend
npm run dev
```

---

## 🛑 停止与重启

两个窗口分别按 `Ctrl+C`；数据库：

```powershell
cd C:\Users\86178\.codex\worktrees\ac44\yanghao-1
docker compose stop
```

数据存在 Docker 卷里，`stop` 不会丢；下次 `up -d` 直接回来。

如果某个端口被占用（说明已有实例在跑），先查是谁：

```powershell
Get-NetTCPConnection -LocalPort 8000,3000 -State Listen | Select-Object LocalPort,OwningProcess
```

---

## ✅ 验证清单

| 检查项 | 期望结果 |
|--------|----------|
| http://localhost:8000/health | `{"status":"ok","env":"development"}` |
| http://localhost:8000/docs | 能打开接口文档 |
| http://localhost:3000 | 页面正常，顶部横幅是绿色「已连接后端服务」 |
| http://localhost:3000/accounts | 显示「暂无账号 / 添加第一个账号」（账号来自 `backend/sessions\` 目录，没登录过就是空的） |
| http://localhost:3000/tasks | 能创建任务，列表如实显示数据库内容 |
| http://localhost:3000/conversations | `[]` 时显示「暂无历史对话」，不再有假数据 |

**重要**：浏览器请固定用 **http://localhost:3000** 打开。
后端 CORS 已同时放行 `localhost` 与 `127.0.0.1`，但如果哪天又只报"无法连接后端服务"，
先换回 `localhost` 试试。

---

## 🗄️ 数据库相关

```powershell
cd C:\Users\86178\.codex\worktrees\ac44\yanghao-1\backend

# 建表 / 升级表结构（首次、或拉了新代码后）
.\.venv\Scripts\python.exe -m alembic upgrade head

# 查看当前迁移版本
.\.venv\Scripts\python.exe -m alembic current

# 清空所有业务数据（保留表结构）
docker exec yanghao-1-postgres-1 psql -U osint -d osint -c "truncate messages, conversations, intelligence_records, tasks, accounts, personas, audit_logs, script_templates restart identity cascade;"

# 可选：灌一份演示数据（注意：这是"假数据"，仅用于看界面效果）
.\.venv\Scripts\python.exe -X utf8 scripts\seed_demo_data.py
```

---

## 🧪 开发常用命令

```powershell
cd C:\Users\86178\.codex\worktrees\ac44\yanghao-1\backend

uv run pytest -q          # 单元测试（当前 53 个）
uv run ruff check .       # 代码检查（当前 0 问题）
uv run ruff format .      # 自动排版

cd ..\frontend
npm run build             # 前端生产构建 + 类型检查
.\node_modules\.bin\tsc.cmd --noEmit    # 只做类型检查
```

日志位置：

| 日志 | 路径 |
|------|------|
| 后端 stdout | `backend\logs\api.out` |
| 后端报错堆栈 | `backend\logs\api.err` |
| 前端 dev 输出 | `backend\logs\web.out` |

（用窗口 2 / 窗口 3 直接跑时，日志就在那个窗口里滚动。）

---

## ❓ 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| 页面横幅显示「后端不可达」 | 8000 的后端进程没在跑 | 回到窗口 2 重新启动 |
| 控制台报「无法连接后端服务」 | 后端没起，或用 `127.0.0.1:3000` 打开被 CORS 拦 | 起后端；地址换回 `localhost:3000` |
| `docker` 命令报连不上 docker API | Docker Desktop 没启动 | 启动 `E:\tool\Docker Desktop.exe`，等图标就绪 |
| 启动后端报端口占用 | 已有一个实例在跑 | 用上面的端口查询命令确认，不用起第二个 |
| 脚本报 `UnicodeEncodeError: 'gbk' codec` | 本机控制台默认 GBK，脚本里有 emoji | 命令加 `-X utf8`，例如 `python -X utf8 demo_simple.py` |
| `alembic` 报找不到 `psycopg2` | 同步驱动缺失 | `uv pip install psycopg2-binary`（pyproject 里已声明，重装即可） |
| 接口 500 且堆栈里有 `ArgumentError: Could not parse SQLAlchemy URL` | `backend\.env` 缺失或数据库地址为空 | 确认 `backend\.env` 存在且 `DATABASE_URL` / `DATABASE_URL_SYNC` 已填 |
| 执行 `seed_demo_data.py` 后界面出现陌生数据 | 那是演示数据 | 用上面的 truncate 清掉 |

---

## 📂 本机路径速查

| 用途 | 路径 |
|------|------|
| 项目根 | `C:\Users\86178\.codex\worktrees\ac44\yanghao-1` |
| Python 解释器 | `C:\Users\86178\AppData\Local\Python\pythoncore-3.14-64\python.exe` |
| uv | `E:\app\UV\uv.exe` |
| Node / npm | `E:\app\Nodejs\node.exe` / `E:\app\Nodejs\npm.cmd` |
| Docker Desktop | `E:\tool\Docker Desktop.exe` |
| 虚拟环境 | `backend\.venv` |
| 环境变量文件 | `backend\.env` |
| 日志 | `backend\logs\` |

---

## 📌 本指南的覆盖范围

覆盖：数据库、后端 API、前端界面、数据初始化、测试与 lint、常见故障排查。

不包含：**账号登录流程、平台常驻守护进程、任务外呼**这一段的操作步骤。
这部分我没有写进来——它的作用是让一个人设账号自动去接触并应对真实陌生用户，
我不提供这部分的操作指导。

---

## 📞 下一步

- 想确认代码健康度：`uv run pytest -q` 与 `uv run ruff check .`
- 想验证前端：`npm run build`
- 想改界面文案或加页面：改 `frontend\src\app\` 下的页面，dev 模式会自动热更新
