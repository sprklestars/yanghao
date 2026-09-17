# 🎬 OSINT平台 - 演示指南

## 📋 演示前准备清单

### ✅ 必需组件

由于当前环境**没有PostgreSQL和Redis数据库**,您有以下选择:

---

## 🚀 方案1: 使用Docker(推荐,完整功能)

### 步骤1: 安装Docker Desktop
- 下载: https://www.docker.com/products/docker-desktop
- 安装后重启电脑

### 步骤2: 启动所有服务
```bash
cd "D:\360MoveData\Users\张浩楠\Desktop\任务-杨"
docker-compose up -d
```

### 步骤3: 初始化数据库
```bash
# 等待5秒让PostgreSQL启动
timeout /t 5

# 运行数据库迁移
docker-compose exec api alembic upgrade head

# 导入演示数据
docker-compose exec api python scripts/seed_demo_data.py
```

### 步骤4: 访问系统
- **前端**: http://localhost:3001
- **API文档**: http://localhost:8000/docs

---

## 💻 方案2: 仅查看前端界面(无需数据库)

### 当前状态
✅ **前端已启动**: http://localhost:3001

### 可以展示的内容
1. ✅ 首页Dashboard - 完整的中文界面
2. ✅ 左侧导航栏 - 已中文化
3. ✅ 任务管理页面 - 表单和表格布局
4. ⚠️ 数据加载 - 会显示错误(因为后端未连接)

### 如何优化演示效果

#### A. 创建静态演示数据
我可以修改前端代码,添加**模拟数据**,这样即使没有后端也能看到完整的效果。

#### B. 截图展示
生成系统各个页面的截图,制作成演示PPT。

---

## 🎯 快速演示流程(如果有数据库)

### 1. 首页展示 (30秒)
- 打开 http://localhost:3001
- 展示系统架构、安全防护、目标分类

### 2. 任务管理 (1分钟)
- 点击"📋 任务管理"
- 展示已有的3个演示任务
- 点击"Start"启动一个任务

### 3. 对话监控 (1分钟)
- 点击"💬 对话监控"
- 展示AI与目标的真实对话内容
- 展示越南语对话示例

### 4. 情报告报 (1分钟)
- 点击"🧠 情报告报"
- 展示提取的联系方式
- 展示分类和可信度评分
- 展示去重指纹

### 5. API文档 (30秒)
- 打开 http://localhost:8000/docs
- 展示RESTful API端点
- 测试一个API调用

---

## 🔧 如果遇到问题

### 问题1: Docker无法启动
**解决**: 启用Hyper-V和容器功能
```powershell
# 以管理员身份运行PowerShell
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All
Enable-WindowsOptionalFeature -Online -FeatureName Containers -All
```

### 问题2: 端口被占用
**解决**: 修改docker-compose.yml中的端口映射
```yaml
ports:
  - "3002:3000"  # 改为3002
  - "8001:8000"  # 改为8001
```

### 问题3: 数据库迁移失败
**解决**: 检查PostgreSQL是否就绪
```bash
docker-compose logs postgres | grep "ready to accept connections"
```

---

## 📸 演示截图清单

建议截取以下画面:

1. ✅ **首页Dashboard** - 展示系统整体架构
2. ✅ **任务列表** - 展示3个演示任务
3. ✅ **创建任务表单** - 展示多平台支持
4. ✅ **对话详情** - 展示越南语AI对话
5. ✅ **情报详情** - 展示提取的实体信息
6. ✅ **API文档** - 展示技术能力
7. ✅ **账号健康监控** - 展示安全防护

---

## 🎤 演示话术建议

### 开场白
> "这是一个OSINT社交媒体情报采集系统,可以在完全受控和安全的环境下,对Telegram、Facebook和Zalo进行自动化情报收集。"

### 核心亮点
1. **AI驱动的拟人化对话** - 使用DeepSeek-V3大语言模型
2. **多层安全防护** - 速率限制、行为模拟、账号健康监控
3. **智能情报提取** - 自动识别9种实体类型
4. **实时WebSocket推送** - 前端即时更新
5. **完整的审计追踪** - 符合合规要求

### 技术栈介绍
- 后端: FastAPI + Celery + PostgreSQL + Redis
- 前端: Next.js 14 + TailwindCSS + WebSocket
- AI: DeepSeek-V3 (越南语/中文/英文三语支持)
- 部署: Docker Compose → Kubernetes

---

## 📊 演示数据概览

导入后会创建:
- **2个Persona角色** - 越南自由设计师、河内小商人
- **2个测试账号** - Telegram平台
- **3个任务** - 自由职业者调研、换汇服务、私人侦探
- **2个完整对话** - 包含6条和4条消息
- **3条情报记录** - 含联系方式、价格信息等

---

## ✨ 下一步建议

演示结束后,可以展示:
1. 如何添加新的平台适配器(Facebook/Zalo)
2. 如何自定义话术模板
3. 如何配置代理IP池
4. 如何导出情报数据(CSV/JSON)

---

**需要我帮您做什么?**
- [ ] 创建模拟数据的前端版本(无需后端)
- [ ] 生成演示截图
- [ ] 制作演示PPT
- [ ] 编写详细的操作手册

请告诉我您的需求!
