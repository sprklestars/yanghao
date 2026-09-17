# 快速启动指南 ⚡

## 5分钟快速开始

### 1️⃣ 配置环境变量 (2分钟)

```bash
cd backend
cp .env.example .env
```

编辑 `backend/.env`,填写:
```env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxx  # DeepSeek API密钥
TG_API_ID=12345678                  # Telegram API ID
TG_API_HASH=abcdef1234567890        # Telegram API Hash
```

> 获取Telegram凭证: https://my.telegram.org

### 2️⃣ 一键启动 (2分钟)

```bash
# 方法1: Docker Compose (推荐)
docker-compose up -d

# 方法2: 使用启动脚本
chmod +x scripts/setup.sh
./scripts/setup.sh
```

### 3️⃣ 初始化数据库 (1分钟)

```bash
docker-compose exec api alembic upgrade head
```

### 4️⃣ 访问系统

打开浏览器访问:
- **前端界面**: http://localhost:3000
- **API文档**: http://localhost:8000/docs

---

## 第一个任务

1. 点击 "Create Task"
2. 填写:
   - Name: `测试任务`
   - Platform: `Telegram`
   - Category: `freelancer`
   - Keywords: `thiết kế website, lập trình`
3. 点击 "Create"
4. 点击 "Start" 按钮启动任务

系统会自动:
- 🔍 搜索相关群组
- 👥 加入群组并获取成员
- 💬 发起对话
- 🤖 AI生成回复
- 📊 提取情报

---

## 常用命令

```bash
# 查看日志
docker-compose logs -f api
docker-compose logs -f worker
docker-compose logs -f web

# 重启服务
docker-compose restart

# 停止所有服务
docker-compose down

# 进入容器
docker-compose exec api bash

# 查看数据库
docker-compose exec postgres psql -U osint -d osint
```

---

## 故障排查

### 问题: 服务无法启动
```bash
# 检查Docker状态
docker ps

# 查看详细日志
docker-compose logs
```

### 问题: 数据库连接失败
```bash
# 等待PostgreSQL就绪
docker-compose logs postgres | grep "ready to accept connections"

# 重新运行迁移
docker-compose exec api alembic upgrade head
```

### 问题: WebSocket连接失败
- 确认后端API正在运行
- 检查浏览器控制台是否有CORS错误
- 刷新页面重试

---

## 开发模式

```bash
# 后端
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload

# Celery Worker
celery -A app.workers.tasks worker --loglevel=info

# 前端
cd frontend
npm install
npm run dev
```

---

## 下一步

- 📖 阅读完整文档: [README.md](README.md)
- 🔐 了解安全实践: [architecture-design.md](architecture-design.md)
- 🛠️ 查看完善总结: [COMPLETION_SUMMARY.md](COMPLETION_SUMMARY.md)

---

**需要帮助?** 查看API文档或提交Issue
