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

注意：`run_task` 里只有 Telegram 分支是实现的，其他平台直接置为 `PAUSED`。（早期文档里的 FB/Zalo「代码就绪待实测」指适配器已写好，但任务流水线未接入。）

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

---

## 7. API 一览（前缀 `/api/v1`）

账号：`GET /accounts`（扫描会话目录）、`DELETE /accounts/{id}`（删会话文件 + meta）、`PATCH /accounts/{id}`（display_name / health / reply_policy / paused / persona）、`GET /accounts/personas`、`POST /accounts/{id}/check-session`、`POST /accounts/telegram/test-connection`、`POST /accounts/telegram/send-code`、`POST /accounts/telegram/verify-code`、`POST /accounts/facebook/login`、`POST /accounts/facebook/login-complete`、`POST /accounts/zalo/login`

群组：`POST /groups/search`（支持 AI 关键词扩展）、`POST /groups/join`、`POST /groups/add-by-link`

任务/对话/情报：`POST|GET /tasks`、`GET /tasks/{id}`、`POST /tasks/{id}/start`、`GET /conversations`、`GET /conversations/{id}`、`POST /conversations/{id}/end`（前端「拉黑」按钮走这里：只置 `ended_at` + 状态为 exit + WebSocket 通知，**并不写入 blocklist**）、`GET /intelligence`

服务：`GET /services/status`、`POST /services/{platform}/start|stop`、`GET /services/{platform}/logs`（`platform ∈ {telegram, facebook}`，分别对应 `persistent_chat_demo.py` / `persistent_facebook_demo.py`，PID 文件 `chat_demo.pid` / `facebook_demo.pid`，日志在 `logs/`）

其他：`GET /health`、`WS /ws`

---

## 8. 实时通信

```
Telegram ↔ persistent_chat_demo.py ↔ WS ↔ FastAPI(manager) ↔ WS ↔ Next.js
                                     ↕
                             PostgreSQL (persist_message)
```

- Channel：`global`（全局广播）、`task:<id>`（任务进度）、`conv:<id>`（单会话）；客户端发 `{"type":"subscribe","channel":...}` 切换频道。
- `persist_message()`（`main.py`）收到 `telegram_message` 事件后自动补齐 Account / Task / Conversation / Message 记录：用 `uuid5(NAMESPACE_DNS, "account-<名字>")` 和 `uuid5(..., "task-auto-<平台>")` 生成确定性 UUID 保证幂等；找不到未结束会话就新建（新建时初始状态直接是 `PROBING`）。
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

`DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`、`TG_API_ID` / `TG_API_HASH`、`DATABASE_URL`（异步，`postgresql+asyncpg://`）/ `DATABASE_URL_SYNC`（`postgresql://`）、`REDIS_URL`、`SECRET_KEY`、`ACCESS_TOKEN_EXPIRE_MINUTES`、`APP_ENV`、`LOG_LEVEL`。

**硬编码的代理**：`('http', '127.0.0.1', 7890)` 出现在 `routes.py`（`TG_PROXY`）、`quick_login.py`、`persistent_chat_demo.py`、`live_chat_demo.py` 等。本机不跑这个代理时，Telegram 相关功能全部连不上——这是最常见的「连接超时」原因。适配器类本身支持传入代理，只是各调用点写死了。

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
   仍待处理：登录类端点（`telegram/test-connection`、`send-code` 等）**没有像 `quick_login.py` 那样先建 `backend/sessions/` 目录**，目录不存在时 Telethon 会报 `sqlite3.OperationalError: unable to open database file`。

3. **回复逻辑有三份实现**
   `engine.ConversationEngine`（被 `tasks.py` 用）、`persistent_chat_demo.py` 的 `generate_response()`、以及 `routes.py` 里一段内联 LLM 调用（约 473-560 行）。三者行为并不完全一致，改对话流程时要一起看。

4. **`classify_category()` 可能返回 `"unknown"`**，而 `IntelligenceRecord.category` 是枚举 → 落库会抛错，错误被 `_process_intelligence_sync` 的 except 吞掉，只留一条日志。

5. **大量状态存内存**：`VerificationManager`（挑战 + 已通过集合）、`BlockListManager`（拉黑集合）、`AccountWarmingManager._profiles`、`AccountHealthMonitor._stats` 全是进程内字典/集合，重启即失忆。技术文档的 P1 项就是把前两者迁到 Redis。

6. **文档与代码的数字有出入，以代码为准**。例：`TECHNICAL_DOC.md` 与 `ACCOUNT_WARMING_GUIDE.md` 写 WARMING 陌生人 10/天、STABLE 20/天、STABLE 加群 10/天，代码实际是 8 / 15 / 8；`TECHNICAL_DOC.md` 自称「7 阶段状态机」但表里列了 8 个状态（含 `VERIFICATION`），而 DB 枚举 `ConversationState` 只有 7 个（无 `VERIFICATION`）。

7. **旧文档中的路径与端口已过时**：大量 md 里出现 `D:\360MoveData\Users\张浩楠\Desktop\任务-杨`、`http://localhost:3001`、`<project-root>`，以及「数据库未启动 / 仅演示模式」之类的告警，都是写作当时的快照，不代表现状（前端默认 3000）。

8. **`live-chat` 页面的演示开关不一致**：`frontend/src/app/live-chat/page.tsx` 里 `demoMode` 初始为 `true`，而仓库根的 `REAL_DEMO_GUIDE.md` 让人去改 `DEMO_MODE`；`frontend/LIVE_CHAT_DEMO.md` 描述的又是另一种状态。

9. **Celery 里同步/异步混用**：`tasks.py` 用 `asyncio.new_event_loop()` 逐个桥接异步适配器，每次调用都新建事件循环，属于权宜实现；改动这块要留意事件循环关闭与连接复用。

10. **bash 脚本在 Windows 上不能直接跑**：`scripts/*.sh`、`backend/start_chat_service.sh` 依赖 `source venv/bin/activate`、`nohup`、`ps`、`lsof` 等 POSIX 设施，需要 WSL / Git Bash。Windows 下请直接用 `uvicorn` / `celery` / `python xxx.py`；同时注意 `routes.py` 的 `os.kill(pid, 0)` 与 `start_new_session=True` 也是类 Unix 语义。

11. **架构设计稿里的 MinIO / Nginx / K8s / Prometheus / Celery Beat / 情报图谱均无代码落地**（`architecture-design.md` 属设计意图，不是现状描述）。

12. **有若干模块写好了但没接进主流程**（全仓库搜索无任何 import）：`RateLimiter` / `AccountHealthMonitor`（`security/rate_limiter.py`）、`StrategyEngine`（`conversation/strategy_engine.py`）、`ScriptLibrary`（`conversation/script_library.py`）。目前真正拦截操作的是 `account_warming.warming_manager`，另外打字/冷却延迟是直接写在适配器里的。所以文档里描述的平台级限流、A/B 话术、策略优先级，实际都还没有生效——评估「系统现在能做到什么」时别被文档带跑。

13. **拉黑链路不完整**：`BlockListManager` 是进程内集合，且只在 `persistent_chat_demo.py` 里被判读（`is_blocked(user_id)`）；`routes.py` 的 `POST /conversations/{id}/end` 并不写入 blocklist（**且因为它是独立进程，写内存也传不到守护进程那边，要真生效得落 Redis/DB/文件**）。
    ~~该端点用 `conv.state = "exit"` 赋小写字符串~~ ✅ **已修复**（改用 `ConversationState.EXIT`），同时修掉了同一处 `datetime.now(datetime.timezone.utc)` 这种取不到时区、必然 `AttributeError` 的写法——也就是说这个端点在修复前每次调用都会 500。

14. **前端演示数据已全部移除**（2026-09-25）：`DEMO_ACCOUNTS` / `DEMO_CONVERSATIONS` / `DEMO_INTELLIGENCE` / `MOCK_TASKS` / `DEMO_MESSAGES` 及 live-chat 的随机假消息定时器都已删除。因此现在"列表为空"会如实显示空状态，而 `backend/scripts/seed_demo_data.py` 仍会写入演示数据——要干净环境就别跑它。

---

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
