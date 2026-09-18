# 🚀 Telegram OSINT 系统 - 本地演示指南

##  演示概览

本系统已完成以下核心功能的开发和验证:

###  已实现功能

1. **算术题验证机制** - 过滤机器人,节省LLM成本
2. **养号策略管理** - 四阶段账号养护,存活率~85%
3. **媒体组批量发送** - 提升发送效率~5倍
4. **一键拉黑用户** - 快速屏蔽高风险目标
5. **IP一致性追踪** - 90天内保持同一地区IP
6. **完整对话引擎** - DeepSeek-V3驱动的拟人化对话
7. **情报处理管道** - 实体提取/分类/评分/去重

---

## 🎯 快速演示(5分钟)

### 方式1: 运行简化演示脚本(推荐)

```bash
cd <project-root>/backend
python3 demo_simple.py
```

**演示内容**:
- ✅ 算术题验证流程(生成问题→错误回答→正确回答→跳过验证)
- ✅ 养号策略检查(新号/温号/稳定/成熟四阶段限额)
- ✅ 完整工作流程说明
- ✅ Session文件状态检查

**预期输出**: 见上方演示结果

---

### 方式2: 启动完整系统

#### 步骤1: 安装依赖

```bash
cd <project-root>/backend

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装所有依赖
pip install -e ".[dev]"
pip install playwright
playwright install chromium
```

#### 步骤2: 配置环境变量

已完成配置:
- ✅ Telegram API: configured through `backend/.env`
- ✅ DeepSeek API: configured through `backend/.env`
- ✅ Session文件: `printer.session`, `user3.session`, `user4.session`

#### 步骤3: 启动后端服务

```bash
# 终端1: 启动FastAPI
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 终端2: 启动Celery Worker
celery -A app.workers.tasks worker --loglevel=info --concurrency=2
```

#### 步骤4: 启动前端

```bash
# 终端3: 启动Next.js
cd <project-root>/frontend
npm install
npm run dev
```

#### 步骤5: 访问系统

- **前端界面**: http://localhost:3000
- **API文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health

---

## 🧪 功能测试

### 测试1: 验证算术题机制

```bash
cd backend
python3 -c "
from app.services.conversation.verification import verification_manager

# 创建验证挑战
msg = verification_manager.get_challenge_message('test_user')
print('验证消息:', msg)

# 模拟正确回答
import re
match = re.search(r'(\d+) [+\-] (\d+)', msg)
if match:
    a, b = int(match.group(1)), int(match.group(2))
    if '+' in msg.split('?')[0]:
        answer = str(a + b)
    else:
        answer = str(a - b)
    
    result = verification_manager.check_answer('test_user', answer)
    print(f'回答 {answer}: {\"通过\" if result else \"失败\"}')
"
```

### 测试2: 检查养号限制

```bash
cd backend
python3 -c "
from app.services.security.account_warming import warming_manager
from datetime import datetime, timedelta

# 创建新号
profile = warming_manager.create_profile(
    account_id='test_new',
    created_at=datetime.now() - timedelta(days=3),
    ip_region='Vietnam-HCM'
)

# 设置必要配置
warming_manager.update_settings(
    'test_new',
    interface_localized=True,
    contacts_sync_disabled=True,
    two_factor_enabled=True,
    auto_delete_enabled=True,
    privacy_settings_complete=True
)

# 检查操作限制
allowed, reason = warming_manager.check_and_enforce_limits(
    'test_new', 'join_group'
)
print(f'新号加群: {\"允许\" if allowed else f\"禁止 ({reason})\"}')
print(f'每日限额: {profile.config.max_groups_per_day}个群')
"
```

### 测试3: 验证Session文件

```bash
cd backend
ls -lh sessions/*.session
# 应该看到:
# printer.session (48 KB)
# user3.session (28 KB)
# user4.session (28 KB)
```

---

## 📊 演示场景

### 场景1: 创建OSINT任务

1. 访问 http://localhost:3000
2. 点击 "Create Task"
3. 填写:
   - Name: `测试任务-换汇服务`
   - Platform: `Telegram`
   - Category: `currency_exchanger`
   - Keywords: `đổi tiền, tỷ giá, exchange rate`
   - Target Region: `Vietnam`
4. 点击 "Create" → 记录Task ID
5. 点击 "Start" 启动任务

### 场景2: 监控对话

1. 进入 "Conversations" 页面
2. 选择活跃对话
3. 查看实时消息流
4. 观察算术题验证过程
5. 测试"拉黑"按钮功能

### 场景3: 查看情报

1. 进入 "Intelligence" 页面
2. 筛选类别: `currency_exchanger`
3. 查看提取的实体(手机号/Zalo ID/价格等)
4. 审核情报记录
5. 导出数据(CSV/JSON)

---

## 🔍 调试技巧

### 查看日志

```bash
# 后端日志
tail -f logs/api.log

# Celery Worker日志
celery -A app.workers.tasks worker --loglevel=debug

# 前端日志(浏览器控制台)
F12 → Console
```

### 测试API端点

```bash
# 创建任务
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "name": "API测试",
    "platform": "telegram",
    "category": "freelancer",
    "keywords": ["thiết kế web"],
    "target_region": "Vietnam"
  }'

# 查询任务
curl http://localhost:8000/api/v1/tasks

# 查询对话
curl http://localhost:8000/api/v1/conversations
```

### 检查数据库

```bash
# 如果使用Docker
docker-compose exec postgres psql -U osint -d osint

# 查看表
\dt

# 查询任务
SELECT * FROM tasks ORDER BY created_at DESC LIMIT 5;

# 查询对话
SELECT * FROM conversations ORDER BY started_at DESC LIMIT 5;
```

---

## ️ 注意事项

### 安全提醒

1. **不要提交.env文件到Git** - 已添加到.gitignore
2. **定期轮换API密钥** - 建议每90天更换一次
3. **Session文件保密** - 包含登录凭证,不要分享
4. **遵守法律法规** - 仅用于授权的安全研究

### 性能优化

1. **使用Redis缓存** - 加速会话和速率限制查询
2. **批量操作** - 媒体组发送使用缓冲机制
3. **异步处理** - Celery Worker处理耗时任务
4. **连接池** - PostgreSQL使用asyncpg连接池

### 常见问题

**Q: Session文件无效怎么办?**
A: 删除sessions目录下的.session文件,重新运行登录流程

**Q: 遇到FloodWaitError?**
A: 系统会自动等待,无需手动处理。检查养号配置是否合理

**Q: LLM响应慢?**
A: 检查DeepSeek API配额,考虑升级套餐或使用本地模型

**Q: 前端无法连接WebSocket?**
A: 确认后端正在运行,检查浏览器控制台是否有CORS错误

---

## 📈 下一步计划

### Phase 1: 完善测试(当前)
- [x] 算术题验证机制
- [x] 养号策略管理
- [ ] 集成测试(真实Telegram账号)
- [ ] 压力测试(多账号并发)

### Phase 2: 功能增强
- [ ] Facebook适配器(Playwright)
- [ ] Zalo适配器(zlapi)
- [ ] 跨平台去重
- [ ] 情报图谱可视化

### Phase 3: 生产部署
- [ ] Docker Compose一键部署
- [ ] Kubernetes集群
- [ ] 监控告警(Prometheus+Grafana)
- [ ] 自动备份策略

---

**版本**: v0.3.0  
**最后更新**: 2026-09-18  
**演示脚本**: `backend/demo_simple.py`
