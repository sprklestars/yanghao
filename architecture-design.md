# OSINT 社交媒体情报采集系统 — 完整技术架构设计文档

## 1. 系统总览

### 1.1 高层架构

```
┌──────────────────────────────────────────────────────────┐
│                    Web 管理面板 (前端)                      │
│         Next.js 14 + TailwindCSS + Shadcn/UI             │
├──────────────────────────────────────────────────────────┤
│                  API Gateway / BFF 层                      │
│              FastAPI (Python 3.12+) REST API              │
├──────────┬───────────┬───────────┬────────────────────────┤
│ 任务调度器 │ 对话引擎   │ 平台集成层  │    情报处理管道           │
│ (Celery + │ (LLM +   │ (适配器    │  (提取/分类/标签/去重)      │
│  Redis)   │  Persona) │  模式)    │                          │
├──────────┴───────────┴───────────┴────────────────────────┤
│                    数据持久化层                              │
│     PostgreSQL (结构化) + Redis (队列/缓存) + MinIO (文件)   │
├──────────────────────────────────────────────────────────┤
│                  基础设施 & 运维层                            │
│       Docker Compose + Nginx + Prometheus + Grafana        │
└──────────────────────────────────────────────────────────┘
```

### 1.2 数据流

```
1. 操作员在 Web 面板创建任务（目标平台、类别、关键词、地区）
2. API Gateway 校验参数，写入 PostgreSQL task 表
3. Celery Worker 从 Redis Broker 拉取任务
4. 任务调度器选择平台适配器 + 分配可用账号
5. 平台适配器执行操作（加群/加好友/发消息）
6. 对话引擎通过 LLM 生成拟人化回复，多轮对话
7. 平台适配器将对话数据推入情报管道
8. 情报管道执行：实体提取 → 分类标注 → 去重 → 存储
9. 结果写入 PostgreSQL，触发 Web 面板实时更新（WebSocket）
10. 操作员审核 → 导出（CSV/JSON/Excel）
```

### 1.3 技术栈选型

| 层级 | 技术 | 理由 |
|------|------|------|
| **主语言** | Python 3.12+ | 三个平台的 SDK/库均为 Python 生态最成熟；LLM 调用库原生支持；OSINT 社区工具链丰富 |
| **Web 框架** | FastAPI | 异步原生支持、自动 OpenAPI 文档、性能优异、类型安全 |
| **前端** | Next.js 14 (App Router) + TailwindCSS | SSR/CSR 混合、实时数据展示好、组件生态丰富 |
| **数据库** | PostgreSQL 16 + Redis 7 | PG 存结构化情报和任务；Redis 做 Celery broker + 速率限制计数器 + 会话缓存 |
| **消息队列** | Celery + Redis (POC) → RabbitMQ (MVP) | POC 阶段 Redis 足够，生产环境切换为 RabbitMQ |
| **对象存储** | MinIO | S3 兼容，存储截图、头像、聊天记录附件 |
| **容器化** | Docker Compose (POC) → K8s (生产) | POC 单机部署简化运维 |
| **监控** | Prometheus + Grafana | 账号健康度、API 调用量、任务成功率可视化 |
| **LLM** | DeepSeek-V3 | 成本低、越南语/中文/英文三语能力强、兼容 OpenAI API 格式 |

**辅助库清单：**
- `telethon` — Telegram MTProto 用户态操作
- `facebook-scraper` / `fbchat` — Facebook 非官方操作
- `zlapi` — Zalo 非官方 Python SDK
- `openai` — DeepSeek API 客户端（兼容 OpenAI SDK 格式）
- `sqlalchemy 2.0` + `alembic` — ORM + 数据库迁移
- `httpx` — 异步 HTTP 客户端
- `playwright` + `playwright-stealth` — 浏览器自动化

---

## 2. 平台集成层

### 2.1 Facebook

#### API 与限制

| 接口 | 能力 | 限制 |
|------|------|------|
| Graph API (官方) | Page 管理、Public Post 读取 | 不支持好友列表查询、无法加群/加好友、需 App Review |
| Messenger Platform API | Bot 收发消息 | 仅限 Page 关联对话，无法主动联系陌生人 |
| facebook-scraper (非官方) | 公开帖子/群组抓取 | 不稳定，依赖前端解析 |
| fbchat (非官方) | 用户态 Messenger 操作 | 需登录 cookie，Meta 积极封堵，高风险 |

#### 认证方式
- Graph API: OAuth2 用户令牌 + App 审批
- 非官方操作: Playwright 自动化登录后提取 Cookie

#### 反检测策略
- 使用 Playwright 模拟真实浏览器操作
- 每次操作间注入随机延迟（3-15秒）
- 使用住宅代理 IP，每个账号绑定固定 IP
- 账号预热期至少 7 天
- 新号前 2 周不超过 5 个好友请求/天、2 个加群/天

### 2.2 Telegram

#### API 与限制

| 接口 | 能力 | 限制 |
|------|------|------|
| Bot API | 机器人收发消息、群组管理 | 无法加入其他群、无法主动联系用户 |
| MTProto (Telethon) | 完整用户能力：搜索/加群/加好友/发消息 | Flood Wait 频繁、需要 api_id + api_hash |

#### 核心能力（Telethon）
- 搜索群组: `SearchRequest(q=keyword, filter=ChatFilter())`
- 加入群组: `JoinChannelRequest(channel)`
- 加好友: `AddContactRequest(first_name, last_name, phone)`
- 发送私信: `SendMessageRequest(peer=user, message=text)`
- 获取群成员: `GetParticipantsRequest(channel, filter, offset, limit)`

#### 反检测策略
- 新号 48 小时预热期
- 单账号每日上限: 群消息 50 条，私信 20 条（陌生人 5 条）
- 操作间隔: 随机 30-120 秒
- FloodWaitError 异常捕获 + 自动等待
- 不频繁加入/退出群组

### 2.3 Zalo

#### API 与限制

| 接口 | 能力 | 限制 |
|------|------|------|
| Zalo OA API (官方) | OA 账号发消息、管理关注者 | 需企业资质、只能与关注 OA 的用户交互 |
| zlapi (非官方) | 个人账号发消息/创建群/监听事件 | Cookie + IMEI 认证、不稳定 |

#### 特殊注意事项
- Cookie 有效期有限（24-72 小时需刷新）
- Zalo 更新可能导致非官方 API 完全失效
- 建议优先级最低，先验证 Telegram 和 Facebook 后再加入

### 2.4 统一适配器接口

```python
class PlatformAdapter(ABC):
    async def authenticate(self, credentials: AccountCredentials) -> bool: ...
    async def search_groups(self, query: str, limit: int) -> list[GroupInfo]: ...
    async def join_group(self, group_id: str) -> bool: ...
    async def send_friend_request(self, user_id: str) -> bool: ...
    async def send_message(self, target_id: str, content: MessageContent) -> bool: ...
    async def receive_messages(self, callback: MessageCallback) -> None: ...
    async def get_user_profile(self, user_id: str) -> UserProfile: ...
    async def get_group_members(self, group_id: str) -> list[UserProfile]: ...
    def get_health_status(self) -> AccountHealth: ...
```

---

## 3. 对话引擎

### 3.1 LLM 编排架构

```
用户消息 → 预处理（语言检测/敏感内容过滤）
         → 上下文组装（Persona + 对话历史 + 任务目标 + 脚本提示）
         → LLM API 调用（函数调用模式）
         → 后处理（安全过滤/格式规范/延迟模拟）
         → 发送回复
```

### 3.2 Persona 角色模板

```yaml
persona_template:
  id: "vietnam_freelancer_01"
  name: "Nguyen Van A"
  age: 28
  location: "Ho Chi Minh City"
  occupation: "Freelance graphic designer"
  backstory: |
    在胡志明市做自由设计师3年，经常需要换汇和找外包合作。
  language: "vi"
  secondary_languages: ["zh", "en"]
  tone: "casual, friendly, slightly naive"
  conversation_style:
    avg_message_length: 15-40 words
    uses_emoji: true
    response_time_pattern: "30s-3min"
```

### 3.3 话术库结构

```yaml
script_library:
  greeting:
    group_join:
      - "Chào mọi người! Mình mới tham gia nhóm 😊"
    direct_message:
      - "Chào bạn! Mình thấy bạn trong nhóm {group_name}"
  probing:
    private_investigator:
      - "Bạn có biết ai làm dịch vụ điều tra tư nhân không?"
    currency_exchange:
      - "Tỷ giá USD-VND hôm nay tốt nhất ở đâu?"
    freelancer:
      - "Mình cần thuê người làm website, giá bao nhiêu?"
    data_seller:
      - "Ai biết chỗ mua data khách hàng tiềm năng không?"
  extraction:
    - "Cho mình xin contact trực tiếp được không?"
    - "Bên bạn có website hay fanpage không?"
  exit:
    - "Cảm ơn bạn nhiều! Mình sẽ liên hệ lại sau nhé"
```

### 3.4 对话状态机

```
IDLE → GREETING → PROBING → EXTRACTION → EXIT
                    ↓
                  PIVOT (转移话题)
                    
任何状态 → COOLDOWN (对方警觉时)
```

转换条件：
- GREETING → PROBING: 对方回复且对话进入第 3 轮
- PROBING → EXTRACTION: LLM 判断回应中包含业务信号
- PROBING → PIVOT: 当前话题无收获
- EXTRACTION → EXIT: 获得联系方式/价格/服务详情，或超时 15 分钟

### 3.5 安全护栏

- 关键词黑名单过滤（暴力、武器、毒品、未成年人等）
- LLM 内容安全评估（低成本小模型快速判断）
- 操作范围检查（偏离任务目标时重写或拦截）

### 3.6 上下文窗口管理

- 滑动窗口: 保留最近 20 条消息
- 摘要压缩: 超过 20 条时用 LLM 压缩早期对话
- Token 预算: System Prompt ~800 + 对话历史 ~2000 + 生成空间 ~1200 = 总计 ≤4000

---

## 4. 情报处理管道

### 4.1 处理流水线

```
原始消息流 → 预处理 → 实体提取 → 分类标注 → 可信度评分 → 去重 → 存储
```

### 4.2 实体提取规则

```python
EXTRACTION_PATTERNS = {
    "phone_number": r'(\+?84|0)\d{9,10}',
    "zalo_id": r'zalo\.me/([a-zA-Z0-9]+)',
    "facebook_url": r'facebook\.com/([a-zA-Z0-9.]+)',
    "telegram_username": r'@([a-zA-Z0-9_]{5,32})',
    "website": r'https?://[^\s]+',
    "price_range": r'(\d+[\.,]?\d*)\s*(k|nghìn|triệu|VND|USD)',
    "address": r'(Hà Nội|HCM|Đà Nẵng|[\w\s]+quận|huyện)',
    "email": r'[\w.+-]+@[\w-]+\.[\w.-]+',
    "bank_account": r'(Vietcombank|BIDV|Techcombank|MBBank)[\w\s]*\d+',
}
```

### 4.3 四分类输出 Schema

```json
{
  "intelligence_record": {
    "id": "uuid-v4",
    "collected_at": "ISO-8601",
    "platform": "facebook | telegram | zalo",
    "target": {
      "platform_user_id": "...",
      "display_name": "...",
      "profile_url": "...",
      "avatar_hash": "..."
    },
    "classification": {
      "category": "private_investigator | currency_exchanger | freelancer | data_seller",
      "confidence": 0.85,
      "signals": ["mentions surveillance", "quotes exchange rate"]
    },
    "extracted_data": {
      "contacts": { "phone": [], "zalo": [], "email": [] },
      "business_info": { "service_description": "", "price_range": "", "website": "" }
    },
    "activity": {
      "status": "active | inactive | dormant",
      "last_seen": "ISO-8601",
      "response_rate": 0.8
    },
    "audit": {
      "task_id": "...",
      "review_status": "pending | reviewed | approved | rejected"
    }
  }
}
```

### 4.4 活跃度评分

```python
factors = {
    "last_message_age":     1.0 if <24h else 0.7 if <7d else 0.3 if <30d else 0.0,
    "message_frequency":    1.0 if >5/day else 0.7 if >1/day else 0.3,
    "response_rate":        replies / messages_received,
    "profile_completeness": 1.0 if has_photo+bio+posts else 0.5,
}
# 加权: 0.3 + 0.3 + 0.25 + 0.15
# >0.7 active, >0.3 dormant, else inactive
```

### 4.5 跨平台去重

1. 精确匹配: 手机号 / 邮箱 / Zalo ID
2. 模糊匹配: 显示名 + 头像 pHash 相似度 >90%
3. 关联推断: 对话中对方提及其他平台账号

---

## 5. 反检测与操作安全

### 5.1 行为模拟

| 行为 | 模拟方式 | 参数 |
|------|---------|------|
| 打字延迟 | 按消息长度计算 + 随机波动 | 50ms/字符 ±30% |
| 阅读延迟 | 收到消息后等待 | 5-45 秒 |
| 会话时段 | 越南时区 UTC+7 | 活跃 8:00-23:00，高峰 19:00-22:00 |
| 消息长度 | 正态分布 | 均值 25 词，标准差 15 |
| 打字错误 | 随机注入 + 自我纠正 | 概率 5% |
| 在线状态 | 碎片化模式 | 30-90min 活跃 + 15-60min 离线 |

### 5.2 代理 IP 策略（POC）

- 每账号绑定 1 个固定住宅代理 IP
- 服务商: Bright Data / SmartProxy / IPRoyal
- 地区: 越南优先
- 成本: ~$5-15/IP/月 × 15 IP ≈ $75-225/月

### 5.3 账号健康监控

```
GREEN: 正常操作
YELLOW: 降速 50%
RED: 暂停 24-72 小时
BLACK: 可能被封，人工介入
```

### 5.4 速率限制

```python
LIMITS = {
    "telegram": { "messages/hour": 20, "messages/day": 100, "joins/day": 3 },
    "facebook": { "messages/hour": 10, "messages/day": 50, "joins/day": 2 },
    "zalo":     { "messages/hour": 15, "messages/day": 80, "joins/day": 2 },
}
```

冷却规则：
- Flood Wait → 等待时间 + 30 分钟额外冷却
- 连续失败 3 次 → 冷却 1 小时
- 验证码挑战 → 冷却 2 小时 + 人工通知
- 日限额达到 → 冷却至次日

---

## 6. Web 管理面板

### 6.1 核心页面

- **Dashboard**: 任务总览、账号健康矩阵、实时消息流、统计图表
- **Tasks**: 创建向导、任务列表、进度跟踪、定时调度
- **Accounts**: 账号列表+状态、Persona 绑定、代理 IP 绑定、凭证管理
- **Conversations**: 实时对话流、历史回放、人工接管按钮
- **Intelligence**: 多维筛选、详情面板、审核工作流、导出功能
- **Scripts**: 话术编辑器、A/B 测试、效果统计
- **Settings**: 代理池、LLM 配置、告警规则、用户权限、审计日志

### 6.2 实时监控

- WebSocket 推送新消息/状态变更/告警
- 多窗口对话监控面板
- 地图视图标注情报地理分布
- 账号状态灯: 绿/黄/红/黑

### 6.3 用户角色

| 角色 | 权限 |
|------|------|
| Admin | 全权 |
| Operator | 任务管理、对话监控、情报审核、导出 |
| Analyst | 查看情报、分析数据（只读） |
| Viewer | 仅仪表盘和统计 |

---

## 7. 基础设施与部署

### 7.1 POC 服务器规格

- CPU: 4 核, RAM: 16 GB, SSD: 100 GB NVMe
- 云: AWS t3.xlarge (~$120/月) 或阿里云 ecs.c7.xlarge (~¥400/月)

### 7.2 Docker Compose 服务

```yaml
services:
  api:        # FastAPI 后端
  web:        # Next.js 前端
  worker:     # Celery Worker (×2)
  beat:       # Celery Beat
  playwright: # 浏览器服务
  postgres:   # PostgreSQL 16
  redis:      # Redis 7
  minio:      # 文件存储
  nginx:      # 反向代理
```

### 7.3 数据库关键表

```sql
accounts, tasks, conversations, messages, intelligence,
dedup_fingerprints, audit_logs, script_templates, personas, proxies
```

### 7.4 监控指标

- `osint_task_success_total{platform, category}`
- `osint_account_health{account_id, platform}`
- `osint_llm_token_usage{model}`
- `osint_intelligence_collected_total{category}`

### 7.5 备份策略

- PostgreSQL: 每日全量 + WAL 增量
- Redis: RDB 每 6 小时
- 保留: 日备 7 天 + 周备 4 周 + 月备 12 月

---

## 8. 风险评估

### 8.1 平台 ToS 风险

| 平台 | 风险 | 缓解 |
|------|------|------|
| Facebook | 极高 | 非官方库 + 低频操作 + 备用号 |
| Telegram | 中 | 严格频率限制 + 优先群内互动 |
| Zalo | 高 | 优先 OA API + 非官方仅作辅助 |

### 8.2 合规红线

- 保存完整授权文档
- 遵守越南《网络安全法》
- 数据最小化原则
- 不可篡改审计日志
- 自动过期删除机制
- 绝不生成违法/有害内容
- 不冒充政府/执法机构
- 不涉及未成年人

### 8.3 应急预案

| 级别 | 触发 | 响应 |
|------|------|------|
| L0 自动 | Flood Wait / 单条失败 / LLM 超时 | 自动等待/重试/回退话术 |
| L1 告警 | YELLOW 状态 / 完成率 <50% | Slack/邮件通知 |
| L2 人工 | RED 状态 / 验证码 | 操作员手动处理 |
| L3 紧急 | BLACK 状态 / 合规警报 | 全系统暂停 |

---

## 9. 开发路线图

### Phase 1: POC (6-8 周) — Telegram 单平台验证

| 周 | 里程碑 |
|----|--------|
| 1-2 | Docker 环境、PostgreSQL、FastAPI 骨架 |
| 2-3 | Telegram 适配器 (Telethon) |
| 3-4 | 对话引擎 v1 (LLM + Persona + 状态机) |
| 4-5 | 情报管道 (提取/分类/存储) |
| 5-6 | Web 面板 v1 (任务/对话/情报) |
| 6-7 | 反检测基础 (速率限制/延迟/健康监控) |
| 7-8 | 联调测试、第一份情报报告 |

人力: 3 人 × 8 周

### Phase 2: MVP (8-10 周) — 多平台扩展

- Facebook 适配器 (Playwright)
- Zalo 适配器 (zlapi + Cookie 刷新)
- 跨平台去重
- Web 面板完善
- 任务调度器

人力: 4.5 人 × 10 周

### Phase 3: 生产化 (10-12 周)

- K8s 部署
- 账号池生命周期管理
- 高级反检测 (ML)
- 情报分析/图谱可视化

人力: 8 人 × 12 周

### POC 月度成本估算

| 项目 | 费用 |
|------|------|
| 服务器 4C16G | ¥400-800 |
| 住宅代理 IP ×15 | ¥500-1500 |
| LLM API (DeepSeek-V3) ~50万 token | ¥30-80 |
| Telegram 手机号 ×5 | ¥100-200 |
| **总计** | **¥1030-2580/月** |

---

## 附录 A: 项目目录结构

```
osint-platform/
├── backend/
│   ├── app/
│   │   ├── api/               # REST 路由
│   │   ├── core/              # 配置、安全、依赖注入
│   │   ├── models/            # SQLAlchemy 模型
│   │   ├── schemas/           # Pydantic 数据模型
│   │   ├── services/
│   │   │   ├── platform/      # 平台适配器
│   │   │   │   ├── base.py
│   │   │   │   ├── telegram_adapter.py
│   │   │   │   ├── facebook_adapter.py
│   │   │   │   └── zalo_adapter.py
│   │   │   ├── conversation/  # 对话引擎
│   │   │   ├── intelligence/  # 情报管道
│   │   │   └── security/      # 反检测、速率限制
│   │   ├── workers/           # Celery 任务
│   │   └── utils/
│   ├── tests/
│   ├── alembic/
│   └── pyproject.toml
├── frontend/
│   ├── src/app/               # Next.js App Router
│   ├── src/components/
│   └── package.json
├── infra/
│   ├── docker/
│   └── k8s/
└── docs/
```
