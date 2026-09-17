# OSINT 社交媒体情报采集系统

一个用于在完全受控和安全环境下对Telegram、Facebook和Zalo进行自动化情报收集的系统。

## ⚠️ 重要声明

本系统仅用于**授权的安全研究、渗透测试和教育目的**。使用前必须:
- 获得完整的书面授权
- 遵守当地法律法规(包括越南《网络安全法》)
- 遵循数据最小化原则
- 保留完整的审计日志

## 🏗️ 技术架构

### 后端
- **框架**: FastAPI (Python 3.12+)
- **数据库**: PostgreSQL 16 + Redis 7
- **消息队列**: Celery + Redis
- **LLM**: DeepSeek-V3 (兼容OpenAI API)
- **平台SDK**: Telethon (Telegram), Playwright (Facebook), zlapi (Zalo)

### 前端
- **框架**: Next.js 14 (App Router)
- **样式**: TailwindCSS
- **实时通信**: WebSocket

### 基础设施
- Docker Compose容器化部署
- MinIO对象存储
- Nginx反向代理

## 🚀 快速开始

### 前置要求
- Docker & Docker Compose
- Python 3.12+ (本地开发)
- Node.js 20+ (本地开发)

### 1. 环境配置

复制环境变量模板并填写配置:

```bash
cd backend
cp .env.example .env
```

编辑 `.env` 文件:

```env
# DeepSeek LLM
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# Telegram (从 https://my.telegram.org 获取)
TG_API_ID=12345678
TG_API_HASH=your_api_hash_here

# Database (Docker Compose会自动配置)
DATABASE_URL=postgresql+asyncpg://osint:osint@postgres:5432/osint
DATABASE_URL_SYNC=postgresql://osint:osint@postgres:5432/osint
REDIS_URL=redis://redis:6379/0
```

### 2. 初始化数据库

```bash
cd backend
alembic upgrade head
```

### 3. 启动服务

使用Docker Compose一键启动所有服务:

```bash
docker-compose up -d
```

服务地址:
- **前端**: http://localhost:3000
- **后端API**: http://localhost:8000
- **API文档**: http://localhost:8000/docs
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379

### 4. 本地开发模式

#### 后端

```bash
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

启动Celery Worker:

```bash
celery -A app.workers.tasks worker --loglevel=info --concurrency=2
```

#### 前端

```bash
cd frontend
npm install
npm run dev
```

## 📋 核心功能

### 1. 任务管理
- 创建情报收集任务(选择平台、类别、关键词)
- 启动/暂停/停止任务
- 实时查看任务进度

### 2. 自动化对话
- AI驱动的拟人化对话引擎
- Persona角色模板系统
- 多轮对话状态机(IDLE → GREETING → PROBING → EXTRACTION → EXIT)
- 越南语/中文/英文三语支持

### 3. 情报处理
- 实体提取(手机号、邮箱、社交账号、价格、地址等)
- 自动分类(私人侦探/换汇/自由职业者/数据贩卖者)
- 可信度评分
- 活跃度评估
- 跨平台去重

### 4. 安全防护
- 速率限制(每平台独立限制)
- 行为模拟(打字延迟、阅读延迟、活跃时段)
- 账号健康监控(四级状态: GREEN/YELLOW/RED/BLACK)
- 内容安全过滤(黑名单关键词)
- Flood Wait自动处理

### 5. 实时更新
- WebSocket实时推送
- 新消息通知
- 任务状态变更
- 情报记录更新

## 📊 API端点

### 任务管理
- `POST /api/v1/tasks` - 创建任务
- `GET /api/v1/tasks` - 列出所有任务
- `GET /api/v1/tasks/{task_id}` - 获取任务详情
- `POST /api/v1/tasks/{task_id}/start` - 启动任务

### 对话管理
- `GET /api/v1/conversations` - 列出对话
- `GET /api/v1/conversations/{conv_id}` - 获取对话详情

### 情报查询
- `GET /api/v1/intelligence` - 查询情报记录(支持筛选)

### WebSocket
- `ws://localhost:8000/ws` - 实时通信端点

## 🔐 安全最佳实践

### 反检测策略
1. **速率限制**: 严格遵守各平台频率限制
   - Telegram: 每小时20条消息,每天100条
   - Facebook: 每小时10条消息,每天50条
   - Zalo: 每小时15条消息,每天80条

2. **行为模拟**:
   - 打字延迟: 50ms/字符 ±30%随机波动
   - 阅读延迟: 5-45秒随机等待
   - 活跃时段: 越南时间8:00-23:00

3. **账号保护**:
   - 新号预热期至少7天
   - 住宅代理IP绑定
   - 连续失败5次自动暂停

### 合规要求
- ✅ 保存完整授权文档
- ✅ 遵守数据最小化原则
- ✅ 不可篡改的审计日志
- ✅ 自动过期删除机制
- ❌ 不讨论暴力、武器、毒品、未成年人话题
- ❌ 不冒充政府/执法机构

## 🛠️ 开发指南

### 项目结构

```
osint-platform/
├── backend/
│   ├── app/
│   │   ├── api/               # REST API路由
│   │   ├── core/              # 配置、数据库连接
│   │   ├── models/            # SQLAlchemy模型
│   │   ├── schemas/           # Pydantic数据模型
│   │   ├── services/
│   │   │   ├── platform/      # 平台适配器(Telegram/Facebook/Zalo)
│   │   │   ├── conversation/  # 对话引擎(LLM编排)
│   │   │   ├── intelligence/  # 情报处理管道
│   │   │   └── security/      # 速率限制、账号健康监控
│   │   └── workers/           # Celery任务
│   ├── alembic/               # 数据库迁移
│   └── tests/                 # 单元测试
├── frontend/
│   ├── src/app/               # Next.js页面
│   └── src/lib/               # API客户端、WebSocket
├── infra/docker/              # Docker配置
└── docker-compose.yml         # 服务编排
```

### 添加新的平台适配器

1. 继承 `PlatformAdapter` 基类
2. 实现所有抽象方法
3. 在 `run_task` Celery任务中集成

示例参考: `backend/app/services/platform/telegram_adapter.py`

### 自定义话术模板

编辑 `backend/app/services/conversation/engine.py` 中的 `SYSTEM_PROMPT_TEMPLATE` 和 `STAGE_HINTS`。

## 📈 监控与运维

### 健康检查
- `GET /health` - 系统健康状态

### 日志查看
```bash
docker-compose logs -f api
docker-compose logs -f worker
docker-compose logs -f web
```

### 数据库备份
```bash
docker-compose exec postgres pg_dump -U osint osint > backup.sql
```

## 💰 成本估算(POC阶段)

| 项目 | 月度费用 |
|------|---------|
| 服务器(4C16G) | ¥400-800 |
| 住宅代理IP×15 | ¥500-1500 |
| LLM API(~50万token) | ¥30-80 |
| Telegram手机号×5 | ¥100-200 |
| **总计** | **¥1030-2580/月** |

## 🗺️ 开发路线图

### Phase 1: POC (当前阶段) ✅
- [x] 基础架构搭建
- [x] Telegram适配器
- [x] 对话引擎v1
- [x] 情报处理管道
- [x] WebSocket实时推送
- [x] Celery任务调度

### Phase 2: MVP (下一步)
- [ ] Facebook适配器(Playwright)
- [ ] Zalo适配器(zlapi)
- [ ] 跨平台去重
- [ ] 任务定时调度
- [ ] 导出功能(CSV/JSON/Excel)

### Phase 3: 生产化
- [ ] Kubernetes部署
- [ ] 高级反检测(ML)
- [ ] 情报图谱可视化
- [ ] 多租户支持

## 📝 许可证

本项目仅供教育和研究用途。使用前请确保符合当地法律法规。

## 🤝 贡献

欢迎提交Issue和Pull Request!

---

**版本**: 0.1.0  
**最后更新**: 2026-09-14
