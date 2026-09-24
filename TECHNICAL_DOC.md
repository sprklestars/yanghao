# OSINT 社交情报平台 — 技术文档

> 版本: v0.1.0 | 更新日期: 2026-09-23

---

## 1. 系统概览

授权社交情报采集系统，支持 Telegram / Facebook / Zalo 三平台。核心能力：AI Agent 自动对话、情报提取、账号养号管理、实时监控。

### 技术栈

| 层级 | 技术 |
|------|------|
| 后端 API | FastAPI + Uvicorn (async) |
| 任务队列 | Celery + Redis |
| 数据库 | PostgreSQL 16 + SQLAlchemy (asyncpg) |
| AI 引擎 | DeepSeek-V3 (OpenAI-compatible API) |
| Telegram | Telethon MTProto |
| Facebook | Playwright Chromium |
| Zalo | zlapi SDK |
| 前端 | Next.js 14 App Router + TypeScript + TailwindCSS |
| 实时通信 | WebSocket (FastAPI ↔ persistent daemon ↔ frontend) |
| 部署 | Docker Compose (5 services) |

---

## 2. Agent 构建详解

### 2.1 架构分层

```
┌─────────────────────────────────────────────────────┐
│                    Frontend (Next.js)                │
│   Accounts · Conversations · Groups · Intelligence   │
└──────────────────────┬──────────────────────────────┘
                       │ REST / WebSocket
┌──────────────────────▼──────────────────────────────┐
│               FastAPI Gateway (:8000)                │
│   Routes · WebSocket Hub · persist_message()         │
└───────┬──────────────────┬──────────────────────────┘
        │                  │
┌───────▼───────┐  ┌──────▼──────────────────────────┐
│ Persistent    │  │       Celery Worker              │
│ Chat Daemon   │  │  run_task · process_incoming_msg  │
│ (Telethon)    │  └──────┬──────────────────────────┘
└───────────────┘         │
                  ┌───────▼──────────────────────────┐
                  │     ConversationEngine            │
                  │  State Machine · DeepSeek LLM     │
                  │  Context Memory · Verification    │
                  └───────┬──────────────────────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
         Telegram      Facebook     Zalo
         Adapter       Adapter     Adapter
```

### 2.2 对话状态机

Agent 使用 7 阶段有限状态机驱动对话流程：

```
IDLE → VERIFICATION → GREETING → PROBING → EXTRACTION → PIVOT → EXIT
                         ↓                                      ↑
                      COOLDOWN ─────────────────────────────────┘
```

| 状态 | 触发条件 | Agent 行为 |
|------|----------|-----------|
| `IDLE` | 新会话开始 | 等待首条消息 |
| `VERIFICATION` | 未验证用户 | 发送算术挑战题（如 "30 + 23 = ?"），过滤机器人 |
| `GREETING` | 验证通过 | 友好问候，建立信任，≤2轮 |
| `PROBING` | 问候完成 | 自然提问目标类别相关信息 |
| `EXTRACTION` | 检测到业务信号词（giá/service/zalo/phone等） | 深入采集联系方式、价格、服务详情 |
| `PIVOT` | PROBING >8轮无进展 | 换角度继续探测 |
| `EXIT` | EXTRACTION >15轮 或 采集完成 | 礼貌结束对话 |
| `COOLDOWN` | 检测到敏感词（bot/fake/police/lừa đảo） | 道歉并退出 |

### 2.3 LLM Prompt 工程

**System Prompt 结构：**

```
[角色设定] name, age, occupation, location, backstory
[语言规则] 主语言越南语，自适应中/英
[对话风格] tone, 15-40词/条, 偶尔emoji, 5%打字错误自纠正
[任务目标] Gather intelligence about {category}
[安全规则] 不涉及暴力/毒品/政治/未成年人
[阶段指令] STAGE_HINTS[state].format(category)
[上下文记忆] context_summary (前序交互摘要)
```

**调用参数：**
- Model: `deepseek-chat` (DeepSeek-V3)
- Temperature: 0.8
- Max tokens: 300
- Sliding window: 最近 20 条历史消息

### 2.4 上下文记忆机制

每轮对话后异步更新 `context_summary`（存于 Conversation 表）：

```python
# 独立 LLM 调用生成摘要
prompt = "Given existing summary + latest exchange → updated concise summary"
# temperature=0.3, max_tokens=300
# 聚焦: key facts, topics, trust level, next steps, language preference
# 限制: ≤200 words
```

**当前上下文窗口分析：**

| 组件 | 预估 Token 数 |
|------|-------------|
| System Prompt (角色+规则+目标) | ~350 tokens |
| Stage Hint | ~30 tokens |
| Context Summary | ~200 tokens (上限) |
| History (20条 × ~30词) | ~2,000 tokens |
| User Message | ~50 tokens |
| **输入合计** | **~2,630 tokens** |
| Response (max_tokens=300) | ~300 tokens |
| **单次请求总计** | **~2,930 tokens** |

### 2.5 10K 上下文升级方案

当前每次请求仅用 ~3K tokens，距离 10K 上限有充足空间。升级路径：

#### 方案 A：扩大滑动窗口（推荐）

```python
# 从 20 条扩展到 50 条
for msg in history[-50:]:  # was [-20:]
```

- 预估增量: +3,000 tokens → 总计 ~6K
- 优点: 保留更多对话细节，减少信息丢失
- 成本: 每次请求增加 ~$0.001

#### 方案 B：增强 Context Summary

```python
# 从 200 words 扩展到 500 words
"Keep it under 500 words."  # was 200
# max_tokens: 300 → 600
```

- 预估增量: +400 tokens
- 优点: 长期记忆更丰富
- 适合: 跨会话的长线情报采集

#### 方案 C：注入情报知识库

```python
# 在 system prompt 中注入已知情报
if intel_context:
    system_content += f"\n\nKnown intelligence about this target:\n{intel_context}"
```

- 可从 IntelligenceRecord 表查询该用户的已有情报
- 避免重复提问已掌握的信息
- 预估: +500-1,500 tokens

#### 组合推荐 (A+B+C ≈ 9K tokens)

```
System Prompt:        350
Stage Hint:            30
Context Summary:      400  (expanded)
Intel Context:      1,000  (new)
History (50 msgs):  5,000  (expanded)
User Message:          50
Response:             300
─────────────────────────
Total:             ~7,130 tokens (峰值 ~9K)
```

### 2.6 验证模块 (Bot Filter)

```
VerificationManager (内存存储)
├── get_challenge(user_id) → 生成随机两位数加减法, TTL=15min
├── check_answer(user_id, answer) → 全角数字归一化 + 答案比对
└── is_verified(user_id) → bool
```

### 2.7 策略引擎

每个目标类别配备多种策略：

| 策略类型 | 描述 | 适用场景 |
|---------|------|---------|
| GROUP_MIXING | 混入相关群组自然互动 | 社群型目标 |
| FRIEND_ADDING | 主动添加好友 | 一对一型目标 |
| DIRECT_OUTREACH | 直接私信 | 已有联系方式 |

账号健康度联动：
- GREEN: 全策略可用
- YELLOW: 减少好友请求量
- RED: 仅被动策略
- BLACK: 停用

---

## 3. 平台适配器

### 3.1 Telegram Adapter

- **库:** Telethon (MTProto)
- **代理:** `http://127.0.0.1:7890`
- **设备指纹:** Samsung Galaxy S24 / Android 14 / Telegram 10.12.0
- **反检测:** 打字延迟(0.05s/char)、操作冷却(30-120s)、FloodWait处理
- **媒体组:** 2秒缓冲合并发送
- **Session:** `.session` 文件 + `_meta.json` 元数据

### 3.2 Facebook Adapter

- **库:** Playwright (headless Chromium)
- **反检测:** stealth mode、真实viewport(1920×1080)、vi-VN locale
- **Session:** Cookie JSON 持久化
- **消息监听:** 轮询 Messenger.com 未读对话

### 3.3 Zalo Adapter

- **库:** zlapi (非官方SDK)
- **设备标识:** MD5+Luhn IMEI生成
- **Session:** Cookie + 48小时过期刷新
- **消息轮询:** 10秒间隔

### 3.4 统一接口 (PlatformAdapter ABC)

```python
class PlatformAdapter(ABC):
    async def authenticate(credentials) -> bool
    async def disconnect()
    async def search_groups(query, limit) -> list[GroupInfo]
    async def join_group(group_id) -> bool
    async def send_friend_request(user_id) -> bool
    async def send_message(target, text) -> bool
    async def listen_messages(callback)
    async def get_user_profile(user_id) -> dict
    async def get_group_members(group_id) -> list
    async def get_health_status() -> AccountHealth
```

---

## 4. 安全与养号体系

### 4.1 账号养号阶段

| 阶段 | 天数 | 群加入/天 | 消息/天 | 陌生人消息/天 | 好友请求/天 |
|------|------|----------|--------|-------------|-----------|
| NEW | 0-7 | 2 | 20 | 3 | 1 |
| WARMING | 8-30 | 5 | 50 | 10 | 3 |
| STABLE | 31-90 | 10 | 100 | 20 | 7 |
| MATURE | 90+ | 15 | 200 | 30 | 10 |

### 4.2 速率限制

Redis 滑动窗口限流（降级为本地内存）：

| 平台 | 每小时 | 每天 |
|------|-------|------|
| Telegram | 20 msg | 100 msg |
| Facebook | 10 msg | 50 msg |
| Zalo | 15 msg | 80 msg |

行为模拟：打字延迟、阅读延迟(5-45s)、操作冷却(30-120s)、活跃时段(越南时间 08:00-23:00)

### 4.3 Reply Policy（回复策略）

每个账号独立配置，运行时动态加载：

```json
{
  "private": true,    // 私聊回复
  "groups": false,    // 群组回复
  "channels": false,  // 频道回复
  "bots": false       // 机器人回复
}
```

存储位置: `sessions/{account}_meta.json`，每条消息到达时重新读取，修改即时生效无需重启。

---

## 5. 数据模型

### 5.1 ER 关系

```
Persona ──1:N── Account ──1:N── Task ──1:N── Conversation ──1:N── Message
                                              │
                                              └──1:N── IntelligenceRecord
```

### 5.2 核心表

| 表 | 用途 | 关键字段 |
|----|------|---------|
| `accounts` | 平台账号 | platform, health(GREEN/YELLOW/RED/BLACK), proxy_url, credentials(JSON) |
| `tasks` | 采集任务 | category, keywords(JSON), status, config(JSON) |
| `conversations` | 对话会话 | state(7种), turn_count, context_summary, target_user_id |
| `messages` | 消息记录 | direction(INBOUND/OUTBOUND), content, language, metadata(JSON) |
| `intelligence_records` | 情报记录 | category, confidence, signals(JSON), extracted_contacts(JSON), dedup_fingerprint |
| `audit_logs` | 审计日志 | action, entity_type, entity_id, details(JSON) |

### 5.3 情报分类

| 类别 | 说明 |
|------|------|
| `private_investigator` | 私家侦探/调查服务 |
| `currency_exchanger` | 换汇/地下钱庄 |
| `freelancer` | 自由职业者/外包服务 |
| `data_seller` | 数据贩卖/信息交易 |

---

## 6. 实时通信架构

```
Telegram ←→ persistent_chat_demo.py ←→ WebSocket ←→ FastAPI ←→ WebSocket ←→ Frontend
                                         ↕
                                    PostgreSQL
                                  (persist_message)
```

**WebSocket Channel 模型：**
- `global` — 全局消息广播
- `task:<id>` — 任务进度
- `conv:<id>` — 单会话消息

**消息持久化流程：**
1. Daemon 收到 TG 消息 → WS 发送到 FastAPI
2. FastAPI `persist_message()` 自动创建 Account/Task/Conversation/Message 记录
3. 使用 `uuid5(namespace, account_name)` 确定性 UUID 保证幂等
4. 广播给所有订阅该 channel 的前端客户端

---

## 7. API 端点一览

### 账号管理

| Method | Path | 功能 |
|--------|------|------|
| GET | `/accounts` | 列出所有账号（扫描 session 文件） |
| PATCH | `/accounts/{id}` | 更新 display_name / health / reply_policy |
| DELETE | `/accounts/{id}` | 删除账号及 session 文件 |
| POST | `/accounts/telegram/test-connection` | 测试 TG 连通性 |
| POST | `/accounts/telegram/send-code` | 发送验证码 |
| POST | `/accounts/telegram/verify-code` | 验证登录码 |
| POST | `/accounts/facebook/login` | Facebook 登录 |
| POST | `/accounts/zalo/login` | Zalo 登录 |

### 群组管理

| Method | Path | 功能 |
|--------|------|------|
| POST | `/groups/search` | 搜索群组（支持 AI 关键词优化） |
| POST | `/groups/join` | 按 ID 加入群组 |
| POST | `/groups/add-by-link` | 按链接/用户名加入 |

### 任务 & 对话 & 情报

| Method | Path | 功能 |
|--------|------|------|
| POST/GET | `/tasks` | 创建/列出任务 |
| POST | `/tasks/{id}/start` | 启动 Celery 任务 |
| GET | `/conversations` | 对话列表（支持 task_id 过滤） |
| GET | `/conversations/{id}` | 对话详情含消息 |
| POST | `/conversations/{id}/end` | 结束对话并拉黑 |
| GET | `/intelligence` | 情报记录（分页+过滤） |

### 服务管理

| Method | Path | 功能 |
|--------|------|------|
| GET | `/services/status` | 各平台服务状态 |
| POST | `/services/{platform}/start` | 启动持久聊天服务 |
| POST | `/services/{platform}/stop` | 停止服务 |
| GET | `/services/{platform}/logs` | 查看日志 |

---

## 8. 部署架构

### Docker Compose (5 Services)

```yaml
services:
  api:       FastAPI :8000      # uvicorn --reload
  worker:    Celery             # concurrency=2
  web:       Next.js :3000      # npm run dev
  postgres:  PostgreSQL :5432   # postgres:16-alpine
  redis:     Redis :6379        # redis:7-alpine
```

### 本地开发

```bash
# 后端
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# 持久聊天守护进程
./venv/bin/python3 persistent_chat_demo.py start

# 前端
cd frontend && npm run dev
```

---

## 9. 待优化项

| 优先级 | 项目 | 现状 | 目标 |
|--------|------|------|------|
| P0 | 上下文窗口 | ~3K tokens/请求 | 10K tokens（扩展history+summary+intel注入） |
| P1 | Verification 存储 | 内存 dict | Redis 持久化 |
| P1 | Blocklist 存储 | 内存 set | Redis 持久化 |
| P2 | Facebook/Zalo 实测 | 代码就绪未实测 | 完整 E2E 验证 |
| P2 | 多账号并发 | 单 daemon | 多账号并行聊天 |
| P3 | 情报去重 | SHA-256 fingerprint | 定期清理 + 合并 |
| P3 | 前端国际化 | 中文 UI + 越南语 Agent | 可切换语言 |
