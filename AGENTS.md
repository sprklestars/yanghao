# AGENTS.md — OSINT 社交情报平台 项目说明

> 本文档由通读整个仓库（代码 + 全部 Markdown 文档 + `TECHNICAL_DOC.md`）整理而成，
> 用于让后续接手的 AI/开发者快速建立正确的项目心智模型。
> 版本参考：代码 v0.1.0 / 文档标注 v0.2.0~v0.3.0 | 整理日期：2026-09-24

---

## 1. 这个项目是什么

一套**授权场景**下的多平台社交情报采集系统：用 AI 扮演真人，在 **Telegram / Facebook / Zalo** 上主动寻找目标（群组、个人），进行拟人化多轮对话，自动提取并归档情报。

核心能力四件套：

1. **找目标** — 关键词搜索群组（支持 AI 关键词扩展）、加群、获取群成员
2. **聊天** — DeepSeek-V3 驱动的人设对话，多阶段状态机推进（8 态，见 §5.2），越南语为主
3. **采集** — 手机号/邮箱/Zalo/TG/FB/网站/价格/地址/银行账号实体提取 + 四分类 + 置信度
4. **活下来** — 养号分级限额、速率限制、行为模拟、账号健康四级监控、拉黑名单（其中养号与行为延迟已生效，其余部分模块尚未接入主流程，见 §11.12）

**合规基调（贯穿全仓库）**：仅用于已获书面授权的安全研究 / 渗透测试 / 教育；遵守当地法律（含越南《网络安全法》）与平台 ToS；数据最小化；保留审计日志；绝不冒充政府或执法机构、不涉及未成年人。

---

## 2. 当前工作区状态（接手前必读）

| 项 | 值 |
|----|----|
| 仓库根 | 当前目录（`yanghao-1` 工作树） |
| 远程 | `https://github.com/sprklestars/yanghao.git`（origin，分支 `master`） |
| 当前分支 | `setup-and-fixes`（从 `fb0a365` 拉出），`master` 仍停在 `fb0a365` 未动 |
| 运行平台 | Windows + PowerShell（脚本却是 bash 风格，见 §11.10） |
| 未提交改动 | 运行 `git status` 查看；**本机运行手册见 [RUNBOOK.md](RUNBOOK.md)** |

最近提交脉络（自下向上）：初版骨架 → TG 养号/防封 → 实时对话演示与持久化 → 前后端真实数据链路 → 消息持久化 + 上下文记忆 → 账号添加流程 + Zalo 登录 → 移除硬编码凭证 → TG 群组管理 + AI 搜索 → 全平台 Session 检测 + FB 反检测。

**2026-09-25 这批改动（在 `setup-and-fixes` 分支）**：修复依赖安装与打包配置、修复 4 个真实 bug（CORS 白名单、会话结束端点的三种错误、TG 会话检测属性名）、**删除前端全部演示数据与降级逻辑**（现在空列表就是空列表，只有真连不上才报"后端不可达"）、ruff 从 360 项清零、单测从 14 个补到 53 个。

**2026-09-26 这批改动**：修掉几个「连不上 Telegram / 账号列表乱显示 / 启动服务没反应」的真因——① 补上 Telethon 走代理所需的 `python-socks[asyncio]`（缺失时报 `No module named 'socks'`）；② 把各调用点写死的 `('http', '127.0.0.1', 7890)` 改成 `.env` 的 `TG_PROXY_URL`（本机 7890 实际只认 SOCKS5，按 HTTP 连会一直报 `Connection to Telegram failed N time(s)`）；③ 新增 `Settings.telegram_credentials_error()` 前置校验，把 `api_id/api_hash` 误填（手机号、示例占位值、hash 长度不对）从英文报错变成中文提示，并把 `env_file` 固定为 `backend/.env` 的绝对路径；④ 新增 `app/core/session_paths.py`（构造 `TelegramClient` 前保证 `sessions/` 存在），并清理「登录失败留下的空会话」——`test-connection` 改用内存会话、`send-code`/`verify-code` 失败时删除本次新建的 `.session`，不再让账号列表凭空多出账号；⑤ 修服务启动链路：`PROXY` 从元组改 dict 曾让 `persistent_chat_demo.py` 以 `KeyError: 1` 启动即退出（已改回 Telethon 要求的元组），启动失败不再假装成功而是返回日志尾部，Windows 上 `os.kill(pid, 0)` 会杀进程改用 `app/core/processes.pid_alive()`，`/services/{platform}/start?session=` 可指定账号（经 `TG_SESSION_NAME` 传给守护进程），日志统一 UTF-8；⑥ 任务页可用性：`tasks/{id}/start` 不再把 `PENDING`（"等待中"）误判成"已在运行"，没有 Celery worker 时自动在 API 进程内执行并回 `mode: inline`，新增 `DELETE /tasks/{id}` 与前端删除按钮，前端报错改为显示后端真实原因。单测 53 → 82。

---

## 3. 技术栈

| 层级 | 技术 |
|------|------|
| 后端 API | FastAPI + Uvicorn（Python ≥3.12） |
| 任务队列 | Celery + Redis（`concurrency=2`） |
| 数据库 | PostgreSQL 16 + SQLAlchemy 2.0（asyncpg 异步 / sync 同步双引擎）+ Alembic |
| LLM | DeepSeek-V3，走 OpenAI 兼容 SDK（`deepseek-chat`） |
| Telegram | Telethon（MTProto 用户态） |
| Facebook | Playwright Chromium（stealth、headless） |
| Zalo | zlapi（非官方 SDK）+ IMEI / Cookie |
| 前端 | Next.js 14 App Router + TypeScript + TailwindCSS |
| 实时链路 | WebSocket（常驻守护进程 ↔ FastAPI ↔ 前端） |
| 部署 | Docker Compose（api / worker / web / postgres / redis 共 5 服务） |

依赖清单见 [pyproject.toml](backend/pyproject.toml)：可选 extra 为 `facebook`（playwright）与 `zalo`（zlapi），`dev` 为 pytest/ruff/mypy。

---

## 4. 目录结构导览

```
backend/
  app/
    main.py                      FastAPI 入口：CORS、/ws WebSocket、persist_message()、/health
    api/routes.py                全部 REST 端点（账号/群组/任务/对话/情报/服务管理）
    core/config.py               Settings（pydantic-settings，读 backend/.env）
    core/database.py             异步 engine + 同步 engine/SessionLocal（给 Celery/Alembic）
    models/models.py             SQLAlchemy 模型与全部枚举
    schemas/schemas.py           Pydantic 请求/响应模型
    services/
      platform/                  base.py 抽象基类 + telegram/facebook/zalo 适配器
      conversation/              engine.py(LLM对话) strategy_engine.py script_library.py verification.py
      intelligence/pipeline.py   实体提取 / 分类 / 活跃度评分
      security/                  account_warming.py rate_limiter.py blocklist.py
    workers/tasks.py             Celery：run_task / process_incoming_message / 情报入库
  alembic/versions/001_initial_schema.py   初始建表迁移
  sessions/                      【gitignored】账号凭证与会话元数据的唯一真源
  persistent_chat_demo.py        Telegram 常驻聊天守护进程（现场实际在跑的东西）
  persistent_facebook_demo.py    Facebook 常驻监听守护进程
  quick_login.py / login_printer.py / quick_login_facebook.py   登录脚本
  demo_simple.py / demo_test.py / real_demo.py / live_chat_demo.py  演示与联调脚本
  test_telegram_manual.py / tests/test_quick_login.py              手工 & 单元测试
  start_chat_service.sh         bash 管理脚本（start/stop/status/logs/login）
  scripts/seed_demo_data.py     演示数据写库
frontend/
  src/app/{page,accounts,groups,tasks,conversations,intelligence,live-chat}/page.tsx
  src/app/layout.tsx / globals.css
  package.json / tailwind.config.js / tsconfig.json（别名 @/* → ./src/*）
infra/docker/{Dockerfile.backend,Dockerfile.frontend}
scripts/{setup.sh,dev.sh}
docker-compose.yml
```

---

## 5. 核心业务逻辑

### 5.1 任务流水线

```
创建任务(API) → Celery run_task → 选账号 → 搜索群组(≤3个关键词)
 → 加群 → 取成员(≤20/群) → 对成员发起会话(≤5人/群)
 → LLM 生成开场白 → 发消息 → 收回复 → process_incoming_message
 → 生成回复 + 更新 context_summary → 发回复
 → EXTRACTION/EXIT 阶段触发情报提取入库
```

三个平台现在**走同一条流水线**（`run_task` 里已无平台分支）：账号从 `sessions/` 的登录态文件取（TG `.session` / FB `_cookies.json` / Zalo `_zalo.json`），依次「搜群 → 加群 → 取目标 → 私聊」，多账号串行。各平台适配器能力不同：**Facebook** 是真实的 Playwright 浏览器自动化（选择器会随 FB 改版失效）；**Zalo** 的非官方接口不支持群搜索，`search_groups` 只能列出账号已加入的群，加群通常需要邀请链接。平台级限流对 FB/Zalo 在流水线里统一施加（Telegram 由适配器内部处理，避免重复计数）。

> 选账号的顺序：先查 DB 的 `accounts` 表（`is_active`），**表里没有就取 `sessions/` 目录里第一个 `.session` 并在 `accounts` 表补登记一条**（会话表 `conversations.account_id` 是外键，没有这行没法落库）——账号列表本来就是扫这个目录的，两边以前对不上，会出现「界面上有账号、任务却报找不到可用账号直接 FAILED」。选定的账号再按 `sessions/<username>.session` 找会话文件，找到就直接用它登录（不需要手机号/验证码），找不到才退回 `osint_<account.id>`。所有 `TelegramAdapter` 都带上 `TG_PROXY_URL`，否则 Telegram 握手会失败。

### 5.2 对话状态机

`ConvState`（`engine.py`，8 态，含 `VERIFICATION`）：

```
IDLE → VERIFICATION → GREETING → PROBING → EXTRACTION → EXIT
                        ↑           ↓(无进展>8轮)          ↑
                        └──────── PIVOT ──────┘   COOLDOWN ─┘
```

| 状态 | 触发 | 行为 |
|------|------|------|
| IDLE | 新会话 | 等首条消息 |
| VERIFICATION | 未验证用户 | 发两位数加减算术题（TTL 15min），过滤机器人 |
| GREETING | 验证通过 | 友好寒暄（≤2 轮） |
| PROBING | 寒暄完成 | 自然提问目标类别 |
| EXTRACTION | 命中业务信号词（`giá/service/zalo/phone/sdt/...`） | 追问联系方式、价格、服务 |
| PIVOT | PROBING 超过 8 轮无进展 | 换角度 |
| EXIT | EXTRACTION 超过 15 轮或采集完成 | 礼貌收尾 |
| COOLDOWN | 命中警觉词（`bot/fake/scam/report/police/công an/lừa đảo`） | 道歉退出 |

> 这里存在**两套状态定义**：`engine.ConvState`（8 态，含 `VERIFICATION`）与 `models.ConversationState`（DB 枚举，7 态、**没有 VERIFICATION**）。写库时用 `ConvState(conv.state.value)` 转换，所以只有对得上的那 7 个状态是安全的。

### 5.3 LLM Prompt 组装

`SYSTEM_PROMPT_TEMPLATE` 注入：人设（name/age/occupation/location/backstory）、语言规则（**主越南语，自适应中/英**）、风格（15-40 词、偶尔 emoji、约 5% 轻微错字并自纠正、绝不承认是 AI）、目标 `Gather intelligence about {category}`、安全规则、`STAGE_HINTS[state]`、`context_summary`。

调用参数：`temperature=0.8`、`max_tokens=300`、历史滑动窗口 **最近 20 条**；请求失败回落到 `_fallback_reply()` 的越南语兜底话术。

`update_context_summary()` 用**独立一次 LLM 调用**（`temperature=0.3`、`max_tokens=300`、≤200 词）维护 `conversations.context_summary`，聚焦关键事实 / 话题 / 信任度 / 下一步 / 语言偏好。

### 5.4 10K 上下文升级（方案已定，尚未实施）

当前单请求约 **2.9K tokens**（system ~350 + stage ~30 + summary ~200 + 20 条历史 ~2000 + 用户 ~50 + 回复 300）。目标 ~9K：

- A 滑动窗口 20 → 50 条（+3K tokens）
- B 摘要 200 → 500 词、`max_tokens` 300 → 600（+0.4K）
- C 把 `IntelligenceRecord` 中该目标的已有情报注入 system prompt，避免重复提问（+0.5~1.5K）

### 5.5 情报管道

`extract_entities()` 用正则抓 9 类实体（phones / emails / zalo_ids / telegram_handles / facebook_urls / websites / prices / addresses / bank_accounts）；`classify_category()` 按越南语关键词表打分，`confidence = min(命中率×3, 1.0)`；`calculate_activity_score()` 按 `0.3*最近活跃 + 0.3*频率 + 0.25*回复率 + 0.15*资料完整度` 得出 active / dormant / inactive；去重指纹为 `sha256(target_user_id|phones|emails|zalo_ids)`，写入有索引的 `dedup_fingerprint`。

### 5.6 养号与风控

分阶段限额（`account_warming.py`，**以代码为准**）：

| 阶段 | 天数 | 加群/天 | 消息/天 | 陌生人消息/天 | 好友请求/天 | 入群观察 |
|------|------|--------|--------|-------------|-----------|---------|
| NEW | 0-7 | 2 | 20 | 3 | 1 | 30 min |
| WARMING | 8-30 | 5 | 50 | 8 | 3 | 15 min |
| STABLE | 31-90 | 8 | 100 | 15 | 5 | 5 min |
| MATURE | 90+ | 15 | 200 | 30 | 10 | 无 |

新号还必须先完成「汉化界面 / 关闭通讯录同步 / 开两步验证 / 开自动删除 / 补全隐私设置」5 项自检，否则 `check_and_enforce_limits()` 直接拒绝操作；注册后 90 天内 IP 地区变化会被判为不一致并阻断。

平台速率限制（`rate_limiter.py` 声明为 Redis 滑动窗口、无 Redis 时降级为进程内计数）：TG 20/时·100/天、FB 10/时·50/天、Zalo 15/时·80/天（另含加群、好友请求的日限额）。**注意：当前代码里真正生效的是养号模块（`telegram_adapter` 每次加群/发消息/加好友前都调 `warming_manager.check_and_enforce_limits`），而 `RateLimiter`、`AccountHealthMonitor`、`StrategyEngine`、`ScriptLibrary` 这几个模块没有被任何地方导入使用**（见 §11.12）。

行为模拟：打字 50ms/字符 ±30%（0.5-10s 夹取）、阅读 5-45s、操作冷却 30-120s、活跃时段越南时间 08:00-23:00。

健康度四级：GREEN 正常 / YELLOW 降速 / RED 暂停 / BLACK 人工介入；`AccountHealthMonitor` 阈值：连续失败 5 次 → black、错误率 ≥0.2 → red、错误率 >0.1 或超日限 → yellow。

### 5.7 回复策略（Reply Policy）

每账号一份，存 `sessions/{account}_meta.json`，**每条消息到达时重新读取**，改完即时生效、无需重启：

```json
{ "private": true, "groups": false, "channels": false, "bots": false }
```

同一文件还存 `display_name` / `health` / `persona` / `paused`。

---

### 5.8 运行模型：三种进程，各管一段

| 入口 | 实际进程 | 干什么 | 占用账号的 `.session`？ |
|------|----------|--------|------------------------|
| 账号管理 →「启动在线服务」 | `persistent_chat_demo.py`（API 拉起，写 `chat_demo.pid`，并把账号名记到 `chat_demo.session`） | 该账号**常驻在线**：监听私聊、按人设自动回复、顺便养号 | 是，独占 |
| 任务管理 →「启动」 | Celery worker 执行 `run_task`；**没有 worker 时**由 API 进程内直跑 | **一次性外呼**：搜群 → 加群 → 拉成员 → 主动私聊 → 采集情报 | 是，独占 |
| 任务管理 →「启动调度器」 | `celery -A app.workers.tasks worker`（API 拉起，写 `celery_worker.pid`） | 消费任务队列。缺它时任务退化为 API 进程内直跑，功能一样但不能排队/并发 | 否 |
| 任务开启定时后自动拉起 | `celery -A app.workers.tasks beat`（写 `celery_beat.pid`，状态文件 `logs/celerybeat-schedule`） | 每分钟跑 `scan_task_schedules`，把到点的定时任务派给 worker | 否 |

- **互斥规则**：同一个 Telegram 账号同一时刻只能有一个客户端（Telegram 侧限制 + 本地 SQLite 单写锁），所以「常驻在线服务」和「外呼任务」不能同时跑。API 现在**双向拦截**并给中文原因：任务启动时若服务在跑 → 400 提示先停止服务；服务启动时若有任务处于 RUNNING → 400 提示先结束任务。
- 想同时做"在线接客"和"主动外呼"，就用**两个账号**，各挂一个。
- **拉黑名单**是跨进程共享的 `backend/state/blocklist.json`（已 gitignore）：对话页点「拉黑」= 结束会话 + 写入名单，守护进程据此不再回复；`GET /blocklist` 查看、`DELETE /blocklist/{user_id}` 取消。
- 「未检测到 Celery worker」不再是错误：`POST /tasks/{id}/start` 会先 ping worker，没有就自动拉起一个，仍不可用才回退进程内直跑，并在响应里返回 `mode: celery|inline`；任务页顶部常显调度器状态和一键启动按钮。
- 每次外呼跑完会把摘要写进 `task.config["last_run"]`（搜了几个关键词 / 找到、加入多少群 / 起了多少会话），任务页直接显示，避免"完成了却不知道做了什么"。
- **定时执行**：`PUT /tasks/{id}/schedule` 把 `{enabled, mode: daily|interval, at|every_minutes}` 写进 `task.config["schedule"]` 并算出 `next_run_at`；开启时自动确保 worker + beat 在跑。`scan_task_schedules` 到点派发，遇到「上一次还在跑」或「常驻在线服务占用账号」就跳过并顺延（写 `last_skipped_reason`）。

## 6. 数据模型与存储

关系：`Persona 1:N Account 1:N Task 1:N Conversation 1:N Message`，`Conversation 1:N IntelligenceRecord`。

表（`models.py` + `001_initial_schema.py`）：`personas` / `accounts` / `tasks` / `conversations` / `messages` / `intelligence_records` / `script_templates` / `audit_logs`。

关键枚举：

- `Platform`: telegram / facebook / zalo
- `TaskStatus`: pending / running / paused / completed / failed
- `AccountHealth`: green / yellow / red / black
- `ConversationState`: idle / greeting / probing / extraction / pivot / exit / cooldown（**注意无 verification**）
- `IntelligenceCategory`: private_investigator（私家侦探）/ currency_exchanger（换汇）/ freelancer（自由职业）/ data_seller（数据贩卖）
- `ActivityStatus`: active / dormant / inactive；`ReviewStatus`: pending / reviewed / approved / rejected；`MessageDirection`: inbound / outbound

> DB 里存的是枚举**成员名**（如 `TELEGRAM`、`GREEN`），SQLAlchemy 层也接受 `.value`；手写 SQL 查询时要按成员名来。
>
> 另一处「真源」是 `backend/sessions/`：账号列表并不查库，而是**扫描会话文件**——TG `{name}.session`、FB `{name}_cookies.json`、Zalo `{name}_zalo.json`，元数据在同名 `_meta.json`。
>
> ⚠️ 因为 Telethon **一构造客户端就会建 `.session` 文件**，登录失败也会留下空壳，而账号列表只看文件存在与否——所以失败的空会话会被显示成一个（还标着"健康"的）账号。为此 `test-connection` 在没有同名会话时改用 `MemorySession`，`send-code` / `verify-code` 失败时会删掉本次新建的会话文件（`app/core/session_paths.remove_session_files`）。手工清理走前端垃圾桶按钮（`DELETE /accounts/{id}`）。

---

## 7. API 一览（前缀 `/api/v1`）

账号：`GET /accounts`（扫描会话目录）、`DELETE /accounts/{id}`（删会话文件 + meta）、`PATCH /accounts/{id}`（display_name / health / reply_policy / paused / persona）、`GET /accounts/personas`、`POST /accounts/{id}/check-session`、`POST /accounts/telegram/test-connection`、`POST /accounts/telegram/send-code`、`POST /accounts/telegram/verify-code`、`POST /accounts/facebook/login`、`POST /accounts/facebook/login-complete`、`POST /accounts/zalo/login`

> 养号档案：`GET /accounts/{id}/warming`（阶段 / 今日用量 / 5 项自检 / 当前限额）、`PATCH /accounts/{id}/warming`（改 5 项自检、`enforce_setup_check`、或 `created_at` 纠正账号年龄）。

群组：`POST /groups/search`（支持 AI 关键词扩展）、`POST /groups/join`、`POST /groups/add-by-link`

任务/对话/情报：`POST|GET /tasks`、`GET /tasks/{id}`、`POST /tasks/{id}/start`、`POST /tasks/{id}/cancel`（运行中则立 `cancel_requested` 标记，流水线在下个检查点停；未运行直接置 FAILED + `last_run.error=用户取消`）、`POST /tasks/{id}/pause`（仅未运行的任务；运行中的只能取消）、`DELETE /tasks/{id}`（按依赖顺序删消息 → 会话 → 情报 → 任务；外键没有 ondelete cascade）、`GET /conversations`、`GET /conversations/{id}`、`POST /conversations/{id}/end`（前端「拉黑」按钮走这里：只置 `ended_at` + 状态为 exit + WebSocket 通知，**并不写入 blocklist**）、`GET /intelligence`

> 上面那条「拉黑按钮不写 blocklist」已过期：现在 `POST /conversations/{id}/end` 会同时**结束会话 + 写入黑名单**（跨进程文件共享），另有 `GET /blocklist`、`DELETE /blocklist/{user_id}` 管理名单。

> `tasks/{id}/start` 只拦「正在运行」的任务（`PENDING` 是新建任务的默认状态、界面上叫"等待中"，不代表"已在运行"）；派发前先 ping Celery worker，**没有 worker 就在 API 进程内用 `run_task.apply()` 直接执行**并在响应里回 `mode: "inline"`，否则任务只会永远挂在"运行中"（本机通常只开 uvicorn + next，没有 worker）。

导出：`GET /export/intelligence?format=csv|json|xlsx`、`GET /export/conversations?format=csv|json|xlsx`（`app/api/export.py`）。情报是"每条一行"、对话是"每条消息一行"（聊天日志）；CSV 用 `utf-8-sig` 带 BOM，Excel 用 openpyxl。前端情报页/对话页有导出按钮，走 `downloadExport()`（fetch → blob → 触发保存），错误会显示后端原因而不是跳到错误页。

服务：`GET /services/status`、`POST /services/{platform}/start|stop`、`GET /services/{platform}/logs`（`platform ∈ {telegram, facebook, worker, beat}`；tg/fb 对应 `persistent_chat_demo.py` / `persistent_facebook_demo.py`，worker/beat 是 Celery 的消费进程与定时触发器，PID 文件分别是 `chat_demo.pid` / `facebook_demo.pid` / `celery_worker.pid` / `celery_beat.pid`，日志在 `logs/`）

> `start` 支持 `?session=<会话名>` 指定挂载哪个账号（前端会把该平台账号列表里的第一个传进来）：常驻进程一次只跑一个账号，`persistent_chat_demo.py` 通过 `TG_SESSION_NAME` 环境变量接收，默认 `printer`。目录里一个 `.session` 都没有时直接返回 400，而不是傻等一个并不存在的会话。

其他：`GET /health`、`WS /ws`

---

## 8. 实时通信

```
Telegram ↔ persistent_chat_demo.py ↔ WS ↔ FastAPI(manager) ↔ WS ↔ Next.js
                                     ↕
                             PostgreSQL (persist_message)
```

- Channel：`global`（全局广播）、`task:<id>`（任务进度）、`conv:<id>`（单会话）；客户端发 `{"type":"subscribe","channel":...}` 切换频道。
- `persist_message()`（`main.py`）收到 `telegram_message` 事件后自动补齐 Account / Task / Conversation / Message 记录：用 `uuid5(NAMESPACE_DNS, "account-<名字>")` 和 `uuid5(..., "task-auto-<平台>")` 生成确定性 UUID 保证幂等；找不到未结束会话就新建（新建时初始状态直接是 `PROBING`）。**入站消息还会顺带抽情报**（`_extract_intelligence()` → `intelligence_records`，按 `dedup_fingerprint` 去重），这是情报报告页唯一的数据来源；`Auto-*` 容器任务不会出现在任务列表里。
- 守护进程侧 `WSBridge` 连 `ws://localhost:8000/ws`，连不上只告警不影响聊天（但前端收不到实时更新）。

---

## 9. 运行方式

> 本机（Windows）的完整启动流程、路径速查与排错表见 **[RUNBOOK.md](RUNBOOK.md)**；下面是通用说明。

### 基础设施

```bash
cp backend/.env.example backend/.env   # 填 DEEPSEEK_API_KEY / TG_API_ID / TG_API_HASH
docker-compose up -d                   # api:8000  worker  web:3000  postgres:5432  redis:6379
docker-compose exec api alembic upgrade head
```

### 本地开发

```bash
# 后端
cd backend && pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
celery -A app.workers.tasks worker --loglevel=info --concurrency=2

# 前端（默认 3000 端口）
cd frontend && npm install && npm run dev
```

### 真实 Telegram 常驻服务

```bash
cd backend
python quick_login.py printer          # 交互式登录，落地 sessions/printer.session
./start_chat_service.sh start          # 或调 API：POST /api/v1/services/telegram/start
./start_chat_service.sh {status|logs|stop|login}
```

演示脚本：`python demo_simple.py`（验证 + 养号，不需要网络）、`python demo_test.py`、`python real_demo.py`、`python live_chat_demo.py`（前台实时聊天）。

### 质量检查

```bash
cd backend
pytest            # asyncio_mode=auto，testpaths=["tests"]
ruff check .      # line-length 100, target py312, select E,F,I,N,W
mypy .
```

---

## 10. 配置与环境变量（`backend/.env`）

`DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`、`TG_API_ID` / `TG_API_HASH`、`TG_PROXY_URL`、`DATABASE_URL`（异步，`postgresql+asyncpg://`）/ `DATABASE_URL_SYNC`（`postgresql://`）、`REDIS_URL`、`SECRET_KEY`、`ACCESS_TOKEN_EXPIRE_MINUTES`、`APP_ENV`、`LOG_LEVEL`。

**`API_TOKEN`（默认空）**：非空时 `/api/v1/*` 要 `Authorization: Bearer <token>`（或 `X-API-Token`），`/ws` 要 `?token=`；前端配 `NEXT_PUBLIC_API_TOKEN`、守护进程自动读取同一个值。本机开发默认留空（启动日志会提醒"未开鉴权"）。

**Telegram 代理**：统一从 `.env` 的 `TG_PROXY_URL` 读取（`app/core/proxy.py` 解析成 Telethon 的 `proxy` 参数），默认 `socks5://127.0.0.1:7890`，**留空即直连**。`routes.py` 的 `TG_PROXY`、`quick_login.py`、`login_printer.py`、`persistent_chat_demo.py`、`live_chat_demo.py` 都走它，不再各写各的。

**协议必须与代理软件实际监听的协议一致**：把 SOCKS5 端口当 `http://` 用时，python-socks 抛 `ProxyError: Invalid proxy response`，Telethon 只会笼统地报 `Connection to Telegram failed N time(s)`（本机 7890 实测是 SOCKS5，不是 HTTP，改成 `socks5://` 后连接成功）。本机不跑这个代理时，Telegram 相关功能全部连不上——这是最常见的「连接超时」原因。

代理实现本身还需要 `python-socks[asyncio]`（已声明在 `backend/pyproject.toml`）：Telethon 会先 `import python_socks`，失败才回落到 `import socks`(PySocks)，两者都缺失时报的是 **`No module named 'socks'`**——看到这条错误别只想着装 PySocks，装上 `python-socks[asyncio]` 即可。注意 `python_socks` 是在 `telethon.network.connection.connection` 导入时探测的，**装完依赖必须重启后端进程**才会生效。

**TG_API_ID / TG_API_HASH 必须成对且格式正确**：`TG_API_ID` 是 my.telegram.org 上 App 的 `api_id`（通常 7-9 位数字），**不是手机号**；`TG_API_HASH` 是 32 位十六进制字符串。填错时网络其实是通的，Telethon 只会报 `The api_id/api_hash combination is invalid (caused by SendCodeRequest)`。`Settings.telegram_credentials_error()`（`app/core/config.py`）会在「测试连接 / 发送验证码」前先给出中文提示；该文件还把 `env_file` 固定成 `backend/.env` 的绝对路径，所以从仓库根目录启动 uvicorn 也不会读不到配置。

文档、`.env.example` 里出现过的示例值（`1234567` / `12345678` / `0123456789abcdef0123456789abcdef` / `your-telegram-api-hash`）也会被 `telegram_credentials_error()` 单独识别并提示——这些占位串**最容易被直接照抄**，且格式恰好合法，只会在发验证码时才被 Telegram 拒绝。另注意「测试连接」按钮只验证网络与代理（不会校验凭证），真正校验 `api_id/api_hash` 的是发验证码那一步，所以它的成功提示里明确写了这一点。

**绝不提交**：`backend/.env`、`backend/sessions/**`。`.gitignore` 已覆盖 `.env`、`sessions/`、`*.session`、`*.session-journal`、`logs/`。历史上曾有硬编码数据库凭证被清理（commit `6bd4c98`），改动时别再引入。

---

## 11. 已知问题 / 坑（动手前先看这一节）

1. ~~**前端 API 客户端文件缺失**~~ ✅ **已修复**：`.gitignore` 的 `lib/` 已锚定为 `/lib/`，`frontend/src/lib/api.ts` 已重建并提交。
   各页面用到的导出面（后续改动请保持兼容）：
   - 函数 `fetchAPI(path, init)`，base 指向 `http://localhost:8000/api/v1`
   - 对象 `wsClient`（`connect` / `disconnect` / `on`），连 `ws://localhost:8000/ws`
   - `accountAPI`：`list` / `delete` / `updateDisplayName` / `updateReplyPolicy` / `setPaused` / `setPersona` / `listPersonas` / `checkSession` / `telegramTestConnection` / `telegramSendCode` / `telegramVerifyCode` / `facebookLoginStart` / `facebookLoginComplete`（各自对应 §7 的账号端点）
   - `serviceAPI`：`status` / `start` / `stop` / `logs`
   - 类型：`Account` / `ReplyPolicy` / `PersonaPreset` / `ServiceStatus` / `Task` / `Conversation` / `IntelligenceRecord`
   - 演示常量：`DEMO_ACCOUNTS` / `DEMO_CONVERSATIONS` / `DEMO_INTELLIGENCE`

2. ~~**`settings.TELEGRAM_API_ID` 不存在**~~ ✅ **已修复**：改用 `settings.tg_api_id / tg_api_hash`，并补上 `proxy=TG_PROXY`；`TelegramAdapter` 新增 `_session_file()`，绝对路径与纯会话名都能正确解析，不再拼出 `sessions/C:\...` 这种无效路径。
   ~~**登录类端点没有先建 `backend/sessions/` 目录**~~ ✅ **已修复**：新增 `app/core/session_paths.py`，
   `ensure_session_dir()` 统一在构造 `TelegramClient` 之前创建会话目录（`routes.py` 的
   `telegram/test-connection` / `send-code`、`TelegramAdapter.authenticate` / `is_session_valid`，
   以及 `login_printer.py` / `persistent_chat_demo.py` / `live_chat_demo.py` / `real_demo.py` / `demo_test.py`）。
   此前目录不存在时 Telethon 会在构造瞬间报 `sqlite3.OperationalError: unable to open database file`。

3. ~~**回复逻辑有三份实现**~~ ✅ **已收敛**：`routes.py` 那段其实是群搜索的 AI 扩词（不是回复）；真正的分歧是守护进程虽然调了 `ConversationEngine`，却把 `state` 写死成 `PROBING`、`history=[]`，等于状态机没跑。现在统一到 `app/services/conversation/reply_service.generate_reply()`：加载会话状态 + 最近 20 条消息历史 → 引擎走完状态机 → 把新状态/轮次/上下文摘要落库。守护进程只负责收消息、调它、发消息；`process_incoming_message()`（死代码）仍保留但不再被当成另一条回复链路。改对话流程看 `engine.py` 一处即可。

4. **`classify_category()` 可能返回 `"unknown"`**，而 `IntelligenceRecord.category` 是枚举 → 落库会抛错，错误被 `_process_intelligence_sync` 的 except 吞掉，只留一条日志。

5. **大量状态存内存**：`VerificationManager`（挑战 + 已通过集合）、`BlockListManager`（拉黑集合）、`AccountWarmingManager._profiles`、`AccountHealthMonitor._stats` 全是进程内字典/集合，重启即失忆。技术文档的 P1 项就是把前两者迁到 Redis。

6. **文档与代码的数字有出入，以代码为准**。例：`TECHNICAL_DOC.md` 与 `ACCOUNT_WARMING_GUIDE.md` 写 WARMING 陌生人 10/天、STABLE 20/天、STABLE 加群 10/天，代码实际是 8 / 15 / 8；`TECHNICAL_DOC.md` 自称「7 阶段状态机」但表里列了 8 个状态（含 `VERIFICATION`），而 DB 枚举 `ConversationState` 只有 7 个（无 `VERIFICATION`）。

7. **旧文档中的路径与端口已过时**：大量 md 里出现 `D:\360MoveData\Users\张浩楠\Desktop\任务-杨`、`http://localhost:3001`、`<project-root>`，以及「数据库未启动 / 仅演示模式」之类的告警，都是写作当时的快照，不代表现状（前端默认 3000）。

8. ~~**`live-chat` 页面是本地演示**~~ ✅ **已接成真数据**：现在左侧是 `/conversations` 拉来的真实会话列表（含 `account_name`），右侧显示该会话的真实历史消息，并通过 WebSocket 实时追加 `telegram_message`；底部输入框走新的 `POST /conversations/{id}/reply` 人工回复（以会话所属账号发出，账号被占用时返回 409）。`demoMode` / 随机假消息已不再存在。

9. ~~**Celery 里同步/异步混用**~~ ✅ **已修复**：以前 `tasks.py` 每个适配器调用都 `asyncio.new_event_loop()`，而 Telethon 明确要求「连接期间不能换事件循环」，于是鉴权之后的 search/join/send 全部报 `The asyncio event loop must not change after connection`，任务却照样显示"完成"（加上适配器把 search 异常吞掉返回空列表，问题被完全隐藏）。现在整个外呼流程（鉴权 → 搜索 → 加群 → 取成员 → 发开场白）跑在同一个 `asyncio.run(_campaign())` 里，`_start_conversation` 也改成 async；`search_groups` 不再吞异常而是向上抛，任务会如实 FAILED；每次跑完把 `searched_keywords / found_groups / joined_groups / conversations` 写进 `task.config["last_run"]`，任务页直接显示"上次运行：搜了 N 个关键词 · 找到 M 个群 · 发起 K 个会话"，避免"完成了但什么都没干"看不出原因。

10. **bash 脚本在 Windows 上不能直接跑**：`scripts/*.sh`、`backend/start_chat_service.sh` 依赖 `source venv/bin/activate`、`nohup`、`ps`、`lsof` 等 POSIX 设施，需要 WSL / Git Bash。Windows 下请直接用 `uvicorn` / `celery` / `python xxx.py`；同时注意 `routes.py` 的 `os.kill(pid, 0)` 与 `start_new_session=True` 也是类 Unix 语义。
    ~~`routes.py` / `persistent_chat_demo.py` 用 `os.kill(pid, 0)` 判断服务是否在跑~~ ✅ **已修复**：Windows 上 `os.kill(pid, 0)` 等价于 `TerminateProcess`，**会把服务直接杀掉**（「查看状态」反而弄停了服务）。现在统一走 `app/core/processes.pid_alive()`（Windows 用 `OpenProcess` + `GetExitCodeProcess`）；`start_new_session=True` 保留（Windows 忽略），另加 `DETACHED_PROCESS` 让守护进程不随 API 退出。

11. **架构设计稿里的 MinIO / Nginx / K8s / Prometheus / Celery Beat / 情报图谱均无代码落地**（`architecture-design.md` 属设计意图，不是现状描述）。

12. ~~**有若干模块写好了但没接进主流程**~~ 部分 ✅ **已接入**：`RateLimiter` / `AccountHealthMonitor`（`security/rate_limiter.py`）与 `ScriptLibrary`（`conversation/script_library.py`）现在都真的在用了——适配器每次加群/发消息/加好友前先过平台限流（小时+天两个额度"全通过才计数"）、每次成功/失败都记进健康监控并把结论同步到 `sessions/<账号>_meta.json`（前端徽章据此显示）；对话引擎会把话术库里该阶段的话术作为参考注入 prompt，LLM 失败时直接用库里的模板兜底并记录 A/B 使用次数。**仍**未接入的是 `StrategyEngine`（`conversation/strategy_engine.py`，策略优先级）；打字/阅读/冷却延迟仍写在适配器里。评估「系统现在能做到什么」时按这条来。

13. ~~**拉黑链路不完整**~~ ✅ **已打通**：`BlockListManager` 改成 **JSON 文件持久化**（`backend/state/blocklist.json`，已 gitignore），按 `(mtime, size)` 自动重载，所以 API 和守护进程这两个独立进程能看到同一份名单；`POST /conversations/{id}/end` 现在**真的写入黑名单**并返回 `blocked`，守护进程下次收到该用户消息就会跳过。新增 `GET /blocklist`（名单）与 `DELETE /blocklist/{user_id}`（取消拉黑），前端对话页有可展开的黑名单面板。选文件而不是 Redis 的理由：零新依赖、离线可用，而这份名单数据量极小。
     ~~该端点用 `conv.state = "exit"` 赋小写字符串~~ ✅ **已修复**（改用 `ConversationState.EXIT`），同时修掉了同一处 `datetime.now(datetime.timezone.utc)` 这种取不到时区、必然 `AttributeError` 的写法——也就是说这个端点在修复前每次调用都会 500。

14. **前端演示数据已全部移除**（2026-09-25）：`DEMO_ACCOUNTS` / `DEMO_CONVERSATIONS` / `DEMO_INTELLIGENCE` / `MOCK_TASKS` / `DEMO_MESSAGES` 及 live-chat 的随机假消息定时器都已删除。因此现在"列表为空"会如实显示空状态，而 `backend/scripts/seed_demo_data.py` 仍会写入演示数据——要干净环境就别跑它。

15. **一个账号同一时刻只能有一个客户端**：`sessions/<name>.session` 是 SQLite 文件，常驻服务（`persistent_chat_demo.py`）和任务流水线（`run_task`）同时用它就会 `sqlite3.OperationalError: database is locked`——表现是任务刚启动就 FAILED，之后连鉴权都过不去（`sessions/*.session-journal` 残留就是线索）。现在：① 任务流水线用 `try/finally` 保证 `adapter.disconnect()`；② `POST /tasks/{id}/start` 在 Telegram 常驻服务运行时直接返回 400，提示先停止服务；③ 进程内直跑改调 `_run_task_pipeline()`，不走 Celery 的 `self.retry()`（eager 模式下它会把整个任务体重跑最多 4 次，对会加群/私聊的任务太危险）；④ **光调 `client.disconnect()` 不够**：Telethon 只在 `_disconnect_coro` 的最后一步才 `session.close()`，中途抛错（例如状态写不进这个锁住的文件）就会永久占着 `.session`，所以 `TelegramAdapter.disconnect()` 现在无论如何都显式 `client.session.close()`；⑤ 启动任务前用 `session_paths.session_in_use()` 探测写锁，被占用直接 400 并提示「关掉多余后端进程 / 重启后端」，不再让人对着 `database is locked` 猜。遇到这种锁，最直接的解法就是重启占用它的后端进程。

16. **群组页的账号下拉、幽灵会话、以及"拉不到群成员"**：① `frontend/src/app/groups/page.tsx` 以前把账号名**硬编码**成 `printer / user3 / user4`（那是演示脚本的会话名）。选中后调 `/groups/*`，Telethon 一构造客户端就凭空建出 `sessions/printer.session`，账号管理里于是多出一个"删不掉的账号"——文件句柄被 API 进程占着，Windows 报 `WinError 32`。现在下拉改成读 `/accounts`；后端三个 `/groups/*` 端点统一用 `_open_telegram_adapter()`：**会话文件不存在就直接 400，不碰 Telethon**，并且 `finally` 一定 `disconnect()`；`DELETE /accounts/{id}` 遇到占用会回 409 + 中文说明（重启后端即可释放句柄）。
    ② **Telegram 从 2021 起只允许管理员拉群成员**（`GetParticipantsRequest` → 「Chat admin privileges are required」），所以「加入 10 个群、发起 0 个会话、情报为空」是平台限制，不是程序 bug。现在 `get_group_members()` 受限时会退回**扫描群最近消息收集发言者**：只收 `telethon.tl.types.User`（跳过频道自身与 bot），频道若带 `linked_chat_id` 就转去它的关联讨论群扫；私聊优先用 `@username`（裸数字 id 没有实体缓存时不可靠）。任务摘要新增 `members_found / dm_failed`，前端一并显示。
    ③ 选账号不再"取 `sessions/` 里第一个文件"（那里可能残留没登录成功的空会话），而是 `_telegram_session_candidates()` + 逐个 `authenticate()`，**试到第一个真正登录过的会话**；常驻服务启动同理（`_first_authorized_session()`），不会被幽灵会话带偏。

17. **情报报告为什么一直是空的** ✅ **已接上**：`intelligence_records` 以前只由 `workers.process_incoming_message()` 写，而那个 Celery 任务**全仓库没有任何调用点**（守护进程有自己的回复逻辑，也不写情报），所以情报页永远是 0 条。现在 `persist_message()` 在保存**入站**消息后会调用 `_extract_intelligence()`：`extract_entities` + `classify_category` + `calculate_activity_score`，按 `dedup_fingerprint` 去重更新（同一目标不重复建行）。注意：**没命中四类业务信号词（私家侦探/换汇/自由职业/数据贩卖）的消息不会建记录**，这是刻意的——情报只针对特定业务线索，不是聊天记录转储。另外 `persist_message()` 为守护进程消息自动创建的容器任务（`Auto-<平台>`）已在 `GET /tasks` 里过滤掉，不会出现在任务列表；它同时会建一个 `Account` 行（`uuid5("account-<会话名>")`），`run_task` 的账号解析会复用这一行。

18. **任务用哪个账号：显式选，不要猜**：任务创建表单新增账号下拉（按所选平台从 `/accounts` 过滤），选中的值写进 `task.config["account"]`，`run_task` 用 `_telegram_session_candidates(account, preferred_name)` **优先用它**，没选才自动挑（逐个试鉴权，跳过空会话）。同时三平台的行为对齐：**只有 Telegram 有外呼流水线**，所以 Facebook/Zalo 任务在界面上标注"尚未接入、无法启动"，后端 `POST /tasks/{id}/start` 也直接返回 400 说明原因（不再静默置 PAUSED）。会话名也不再"手输随便填"：前端在填手机号时自动生成 `tg<手机号数字>`（可改），前后端共用同一套规则 `app/core/session_paths.is_valid_session_name()`（1-48 位小写字母/数字/下划线/短横线，且不能以符号开头）——既统一体验，也挡住了 `../evil` 这类会写到 `sessions/` 目录之外的路径穿越。

19. **任务运行中的可观测性**：`run_task` 在每个检查点把进度写进 `task.config["progress"]`（`stage` / `keyword` / `group` / `target` / `members`），任务页在"运行中"时实时显示；跑完清空 `progress`、写 `last_run` 摘要。取消是异步的：`POST /tasks/{id}/cancel` 只立 `cancel_requested`，流水线在每个检查点读库、发现后抛 `TaskCancelledError`（**不重试**），把任务置 FAILED 并记 `error=用户取消`。暂停仅对未运行任务有效（置 PAUSED，再点"继续"即恢复）。

20. **情报/对话导出**：`app/api/export.py` 提供 `/export/intelligence` 与 `/export/conversations`（`format=csv|json|xlsx`）。情报一条记录一行、对话一条消息一行；Excel 依赖 `openpyxl`（已加进 `pyproject.toml`）。前端情报页右上角三个按钮、对话页历史列表右上角一个下拉，都走 `api.ts` 的 `downloadExport()`（fetch → blob → 触发浏览器保存，失败显示后端原因）。

21. **live-chat 真数据 + 多账号外呼**：① 会话模型加了 `account_name` 属性（`selectinload(Conversation.account)`），`/conversations` 响应带上它，live-chat 页据此做"会话 → 账号"的关联；新增 `POST /conversations/{id}/reply` 人工回复（会话文件不存在/被占用时给出 400/409 的明确提示）。② 任务支持多账号：`task.config["accounts"]` 是账号名数组（兼容单数 `account`），`run_task` 按它**串行**逐个账号跑完「搜群→加群→取目标→私聊」再断开换下一个，跳过多选里不存在或未登录的账号；`last_run.accounts` 记每个账号的分项统计，顶层数字是合计。前端任务表单从单选下拉改成**多选复选框**。

22. **任务定时调度（P2-6）**：调度只存 `task.config["schedule"]`（`enabled` / `mode` / `at` 或 `every_minutes` / `next_run_at` / `last_run_at` / `last_skipped_reason`），**不新增数据表**；纯计算在 `app/services/scheduling.py`（`normalize_schedule` 校验、`compute_next_run` 算下次时间，`daily` 按本机时区解释 HH:MM），有单测。Celery Beat 每分钟跑 `scan_task_schedules`：到点→标记 RUNNING 并 `run_task.delay`；`status==RUNNING` 或常驻在线服务在跑→本轮跳过并顺延。`PUT /tasks/{id}/schedule` 保存配置并自动拉起 worker + beat；前端任务行有「⏰ 定时」编辑器与下次运行时间/上次跳过原因。注意：**beat 必须和 worker 一起跑**，只开 beat 不会执行任务。

23. **情报审核闭环**：`PATCH /intelligence/{id}`（body `{review_status?, operator_notes?}`）改审核状态与备注，枚举校验走 `app/services/intelligence/review.py`（`parse_review_status` / `apply_review`，有单测）。规则：状态回到 `pending` 时清空 `reviewed_at`；其它状态只记**首次**审核时间（审计含义）；`operator_notes` 缺省不改动、传空串则清空。`IntelligenceResponse` 与前端类型加了 `reviewed_at`，导出 CSV/Excel 也带上 `operator_notes` / `reviewed_at`。前端情报页的状态列变成下拉（待审核/已审核/已通过/已拒绝，改动即时保存），新增「操作」列做备注的行内编辑。

24. **风控三件套 + 养号档案接线（P0-3 之后那一项）**：① **平台限流** `RateLimiter.allow(platform, actions, account)` —— 一次动作同时受"每小时/每天"两个额度约束时，**全部通过才计数**（否则会出现小时额度被扣、天额度没通过的错账）；适配器在加群/发消息/加好友前调用，超限就跳过并记一次健康失败。② **健康监控** `health_monitor` 记录每次动作成败，`evaluate()` 的结论（green/yellow/red/black）会写回 `sessions/<账号>_meta.json` 的 `health`，前端徽章和 `check-session` 看到的是同一份数据；连续 5 次失败→black、错误率≥0.2→red、>0.1 或日动作>50→yellow。③ **话术库** `script_library` 在 `engine.py` 里预加载：按 stage+分类+vi 挑一条作为 prompt 里的"参考说法"（要求模型改写而非照抄），LLM 调用失败时直接用该模板兜底并 `record_usage`（A/B 的 effectiveness 会随使用更新）。④ **养号档案**：`AccountWarmingManager` 改用 `backend/state/warming_profiles.json`（与黑名单同一套 `JsonStore`：跨进程可见、重启不丢），适配器鉴权成功后用**会话文件 mtime**近似注册时间自动建档案，数字限额（日加群/发消息/陌生人/好友请求）这才真正生效；档案里的 `enforce_setup_check` 决定是否强制"新号 5 项自检"——**自动创建的档案默认 False**（只套数字限额，避免刚接入就卡死存量账号），显式 `create_profile()` 默认 True，可用 `PATCH /accounts/{id}/warming` 改；同接口还支持 `created_at` 纠正账号年龄。新增 `GET/PATCH /accounts/{id}/warming`。测试隔离：`tests/test_account_warming.py` 用 fixture 把默认路径指到 tmp，避免污染真实 state。

---

25. **API 鉴权 + 路由层集成测试（第 5 项）**：新增 `API_TOKEN` 配置（`.env`，默认空=不鉴权，启动时会打一条"未开鉴权、别暴露到公网"的告警）。非空时 `/api/v1/*` 必须带 `Authorization: Bearer <token>` 或 `X-API-Token`，`/ws` 必须带 `?token=`（HTTP 中间件在 `main.py`，WS 在握手处校验，不通过直接 close 1008）；`/health` 与 CORS 预检始终放行。401 响应**手工补了跨域头**（否则浏览器只报"后端不可达"），前端 `fetchAPI`/`downloadExport` 会带 `NEXT_PUBLIC_API_TOKEN`，守护进程的 `WS_URL` 也会自动带 token。新增 `tests/test_api_auth.py`：这是仓库里第一批**接口层**测试（用 `TestClient`，导入前塞假 DSN 以免没 .env 的环境在收集阶段炸），覆盖鉴权关闭/开启、Bearer 与 X-API-Token、401 的跨域头、预检放行，以及 `/services/status` 的真实响应形状。

26. **FB/Zalo 外呼流水线接入（最后一项）**：`run_task` 去掉平台分支，三个平台共用「搜群→加群→取目标→私聊」；账号按 `config.accounts` 指定或自动挑第一个登录态文件（`sessions/*.session` / `*_cookies.json` / `*_zalo.json`，命名约定集中在 `app/core/session_paths.py` 的 `PLATFORM_SESSION_SUFFIX` / `platform_session_path` / `platform_session_name`）。适配器构造在 `_build_adapter()`：Telegram 用 `TG_PROXY_URL` 代理，Facebook 把同一个代理传给 Playwright（`credentials["proxy"]`），Zalo 从 `_zalo.json` 里读 `phone`/`imei`（zlapi 即使复用 cookie 也要 phone）。`POST /tasks/{id}/start` 与定时开关现在三平台都放行，但**要求该平台已有登录态文件**（否则 400 说明缺哪种文件）；常驻服务占用同一份登录态时也会被拦。FB/Zalo 的平台限流在 `_run_account_campaign` 里统一施加（Telegram 由适配器内部处理，避免重复计数）。`last_run` 新增 `platform` 与 `blocked_by_limit`。**能力差异**：FB 是真实 Playwright 自动化（选择器随改版可能失效）；Zalo 非官方接口不支持群搜索，只能列已加入的群，加群多需邀请链接。测试：`tests/test_task_pipeline_platforms.py` 用替身适配器跑完整流水线（无数据库环境自动跳过）。**已知缺口**：适配器调用没有超时保护——实测遇到 Telegram 连接被服务器重置时，solo 池的 worker 会卡在那次任务里不再应答（重启 worker 即可恢复），后续应给适配器调用加 `asyncio.wait_for`。

27. **适配器超时保护 + worker 线程池**（第 26 条末尾提到的"已知缺口"已在本条修掉）：新增 `app/core/async_utils.py` 的 `with_timeout()` / `OperationTimeoutError`，账户鉴权与所有外部动作（搜索/加群/取成员）都套上它，秒数由 `.env` 的 `ADAPTER_TIMEOUT_SECONDS`（默认 90）控制。**一个账号超时只跳过该账号**（`sub["timeout"]` 记原因、断开后换下一个账号），不会让整条任务挂住；`last_run.warning` 优先提示"有账号调用超时被跳过"。同时把 Windows 上的 worker 从 `--pool=solo` 换成 `--pool=threads --concurrency=2`：solo 只有一个执行位，一个卡住的连接会让整个 worker 不再应答（只能重启恢复），线程池至少留一个空位。因为并发变成 2，`POST /tasks/{id}/start` 新增守卫：**同一平台已有任务 RUNNING 时拒绝启动**（否则两个任务会抢同一批账号的登录态）。测试：`tests/test_async_utils.py`（超时/断连归类）+ `tests/test_task_pipeline_platforms.py` 的"卡住账号被跳过、任务照常收尾"与"同平台运行中的任务会拦住启动"。

## 12. 文档索引（均在仓库根目录）

| 文档 | 内容 | 时效 |
|------|------|------|
| [RUNBOOK.md](RUNBOOK.md) | **本机运行手册**：运行逻辑、三窗口启动、验证清单、数据操作、排错表、路径速查 | 最新（2026-09-25，按本机实测） |
| [TECHNICAL_DOC.md](TECHNICAL_DOC.md) | 最完整的技术说明：架构图、状态机、Prompt 工程、上下文窗口分析、平台适配器、养号表、数据模型、API、部署、待优化项 | 最权威（v0.1.0，2026-09-23） |
| [architecture-design.md](architecture-design.md) | 设计稿：选型理由、三平台 API 限制对比、情报 Schema、风险评估、应急预案、路线图、成本 | 设计意图，见 §11.11 |
| [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) | 面向非技术的产品说明：能做什么、怎么运作、后台模块、当前进度 | 适合快速理解价值 |
| [README.md](README.md) | 标准 README：快速开始、核心功能、API、安全实践、目录结构、路线图、成本 | 入口文档 |
| [MULTI_PLATFORM_FEATURES.md](MULTI_PLATFORM_FEATURES.md) | 三平台适配器能力、话术库 A/B、策略引擎、平台对比、产能估算 | v0.2.0 |
| [ACCOUNT_WARMING_GUIDE.md](ACCOUNT_WARMING_GUIDE.md) | 养号完全指南：新号 5 项设置、四阶段限额、IP 一致性、被封申诉流程、检查清单 | 操作手册，数字见 §11.6 |
| [QUICKSTART.md](QUICKSTART.md) | 5 分钟快速起步 | 简洁，路径有占位符 |
| [DEMO_GUIDE.md](DEMO_GUIDE.md) / [REAL_DEMO_GUIDE.md](REAL_DEMO_GUIDE.md) / [INTERACTIVE_DEMO.md](INTERACTIVE_DEMO.md) / [INTERACTIVE_DEMO_STEPS.md](INTERACTIVE_DEMO_STEPS.md) | 演示脚本、演练话术、逐步点击流程（含「必展示 5 个亮点」与效果数字） | 演示用，2026-09-14~18 |
| [PERSISTENT_RUN_GUIDE.md](PERSISTENT_RUN_GUIDE.md) | 常驻服务原理（指数退避重连、心跳、PID、日志）与排障 | 运维手册 |
| [TESTING_GUIDE.md](TESTING_GUIDE.md) | 测试级别选择、测试账号获取渠道、测试清单 | 含大量「待启动」旧状态 |
| [SETUP_COMPLETE.md](SETUP_COMPLETE.md) | 依赖安装与配置报告（含各包版本号） | 环境快照，2026-09-14 |
| [COMPLETION_SUMMARY.md](COMPLETION_SUMMARY.md) | POC 完成度总结（Celery / WebSocket / 适配器 / 迁移 / 前端客户端） | 2026-09-14 |
| [FRONTEND_STATUS.md](FRONTEND_STATUS.md) | 前端页面清单、配色与响应式约定、API 集成状态 | 与现状有偏差（api.ts 其实不在库里） |
| [GITHUB_PUSH_FIX.md](GITHUB_PUSH_FIX.md) / [PUSH_TO_GITHUB.md](PUSH_TO_GITHUB.md) / [README_GITHUB_PUSH.md](README_GITHUB_PUSH.md) | GitHub 推送过程与代理 / PAT 排障 | 历史记录 |
| [backend/LOGIN_INSTRUCTIONS.md](backend/LOGIN_INSTRUCTIONS.md) / [frontend/LIVE_CHAT_DEMO.md](frontend/LIVE_CHAT_DEMO.md) | TG 登录指引、实时对话页说明 | 局部说明 |

---

## 13. 改动约定

- **语言**：代码注释、提交信息、前端 UI 文案用中文；AI 人设话术与实体提取关键词用越南语。越南语关键词表在 `pipeline.py` 的 `CATEGORY_KEYWORDS`，要调分类效果就改这里。
- **前端风格**：TailwindCSS；`slate` 作中性色，状态色用 `emerald`(green) / `amber`(yellow) / `rose`(red) / `slate-900`(black)；卡片 `rounded-lg + shadow-sm + border-slate-200`。页面都是自包含的 client component，没有 `src/components`、没有状态管理库。
- **新增平台适配器**：继承 `PlatformAdapter`（`base.py`，注意含 `is_session_valid()` 抽象方法），实现全部抽象方法，再接进 `run_task` 与 `routes.SERVICE_MAP`。
- **改话术 / 对话风格**：真正生效的是 `engine.py` 的 `SYSTEM_PROMPT_TEMPLATE` 与 `STAGE_HINTS`；`script_library.py` 虽是话术库但尚未接入（§11.12）。
- **改限额 / 风控**：生效的阈值在 `account_warming.py`；`rate_limiter.py` 里那套平台级限额目前没被调用（§11.12），只改它不会有任何效果。
- **敏感文件纪律**：会话、Cookie、`.env`、日志一律不入库；涉及真实账号的操作只在用户明确授权下进行。
- **提交规范**：仓库使用 `feat:` / `fix:` / `docs:` / `security:` 前缀的中文提交信息；新建分支默认用 `codex/` 前缀。当前工作分支是 `setup-and-fixes`（用户指定命名）。
