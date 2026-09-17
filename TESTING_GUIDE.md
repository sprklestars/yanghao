# 🧪 Telegram测试账号配置指南

## 📋 当前状态

- ✅ Telegram API凭证已配置 (见 backend/.env)
- ⚠️ PostgreSQL数据库未启动
- ⚠️ Redis服务未启动
- ⚠️ 需要至少1个Telegram测试账号

---

## 🎯 方案选择

### 方案A: 仅前端演示(无需任何账号)
**适合**: 展示界面设计、功能概念
**优点**: 立即可用,零配置
**缺点**: 无法测试真实Telegram功能

**操作**:
```bash
# 前端已在运行
访问: http://localhost:3001
```

---

### 方案B: 完整功能测试(推荐)
**适合**: 验证Telegram自动化功能
**需要**:
1. Docker Desktop(或本地PostgreSQL+Redis)
2. 至少1个Telegram测试账号

---

## 🔑 Telegram测试账号获取

### 方式1: 使用备用手机号(推荐)
如果您有备用手机卡:
1. 下载Telegram App
2. 用备用号注册新账号
3. 完善资料(头像、昵称、简介)
4. 正常使用3-7天
5. 用于自动化测试

### 方式2: 购买虚拟号码
**服务商推荐**:
- SMS-Activate: https://sms-activate.org (越南号约$0.5-1)
- 5sim: https://5sim.net
- Receive-SMS: 搜索"virtual phone number telegram"

**步骤**:
1. 注册服务商账号
2. 充值($5-10足够)
3. 选择国家(建议越南🇻🇳)
4. 购买Telegram接收验证码服务
5. 获取手机号和验证码
6. 注册Telegram账号

### 方式3: Google Voice(可能受限)
1. 申请Google Voice号码
2. 尝试注册Telegram
3. **注意**: Telegram可能拒绝VoIP号码

---

## 🚀 快速启动完整系统

### 选项1: 安装Docker Desktop(推荐)

#### 1. 下载Docker Desktop
https://www.docker.com/products/docker-desktop

#### 2. 安装后启动服务
```bash
cd "D:\360MoveData\Users\张浩楠\Desktop\任务-杨"
docker-compose up -d
```

#### 3. 初始化数据库
```bash
cd backend
alembic upgrade head
```

#### 4. 启动后端
```bash
# Terminal 1 - API服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 - Celery Worker
celery -A app.workers.tasks worker --loglevel=info
```

---

### 选项2: 不使用Docker(简化版)

如果不想安装Docker,可以创建一个简化的测试脚本直接测试Telegram适配器:

#### 创建测试脚本
文件: `backend/test_telegram_manual.py`

```python
"""
手动测试Telegram适配器 - 无需数据库
"""
import asyncio
from telethon import TelegramClient

# API凭证(从.env读取)
API_ID = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")

async def test_login():
    """测试Telegram登录"""
    print("🔐 开始Telegram登录测试...")

    # 创建客户端
    client = TelegramClient('test_session', API_ID, API_HASH)

    # 启动(会要求输入手机号和验证码)
    await client.start()

    # 获取自己的信息
    me = await client.get_me()
    print(f"✅ 登录成功!")
    print(f"   用户名: @{me.username}")
    print(f"   显示名: {me.first_name} {me.last_name or ''}")
    print(f"   ID: {me.id}")

    # 测试搜索群组
    print("\n🔍 测试搜索群组...")
    results = await client(functions.messages.SearchRequest(
        q="freelancer",
        filter=None,
        min_date=None,
        max_date=None,
        offset_id=0,
        add_offset=0,
        limit=5,
        max_id=0,
        min_id=0,
        hash=0,
    ))

    print(f"找到 {len(results.chats)} 个群组:")
    for chat in results.chats[:3]:
        print(f"  - {chat.title} ({getattr(chat, 'participants_count', 0)} 成员)")

    # 清理
    await client.disconnect()
    print("\n✅ 测试完成!")

if __name__ == "__main__":
    asyncio.run(test_login())
```

#### 运行测试
```bash
cd backend
python test_telegram_manual.py
```

首次运行会提示:
1. 输入手机号(带国家代码,如+84xxx)
2. 接收短信验证码
3. 输入验证码
4. Session保存为`test_session.session`

---

## 📊 测试清单

### 基础功能测试
- [ ] Telegram账号登录成功
- [ ] 能搜索到相关群组
- [ ] 能加入群组
- [ ] 能获取群组成员列表
- [ ] 能发送消息
- [ ] 能接收消息

### 高级功能测试
- [ ] AI对话引擎正常工作
- [ ] 话术库正确加载
- [ ] 策略引擎选择合适的策略
- [ ] 情报提取准确
- [ ] WebSocket实时推送工作

---

## 💡 建议的测试流程

### 第1步: 单账号基础测试(30分钟)
1. 准备1个Telegram账号
2. 运行`test_telegram_manual.py`
3. 验证登录和基本信息获取
4. 测试搜索群组功能

### 第2步: 多账号场景测试(1小时)
1. 准备2-3个账号
2. 测试不同账号的角色扮演
3. 验证Persona切换
4. 测试并发对话

### 第3步: 完整流程测试(2小时)
1. 启动完整系统(API + Worker)
2. 通过Web界面创建任务
3. 观察自动化执行过程
4. 检查情报提取结果

---

## ⚠️ 注意事项

### 账号安全
1. **永远不要用主账号** - 准备专门的测试号
2. **控制频率** - 严格遵守速率限制
3. **监控健康** - 注意Flood Wait警告
4. **准备备用号** - 以防账号被封

### 反检测
1. **新号预热** - 至少7天正常使用
2. **模拟真人** - 打字延迟、阅读延迟
3. **活跃时段** - 越南时间8:00-23:00
4. **代理IP** - 生产环境建议使用住宅代理

### 合规性
1. **授权测试** - 确保有合法授权
2. **数据最小化** - 只收集必要信息
3. **审计日志** - 保留所有操作记录
4. **遵守ToS** - 尊重平台服务条款

---

## 🆘 常见问题

### Q1: 登录时收不到验证码?
**A**: 
- 检查手机号格式(需带国家代码,如+84)
- 等待60秒后重试
- 尝试其他手机号
- 可能是Telegram限制了该号码

### Q2: Flood Wait错误?
**A**:
- 这是正常的风控机制
- 系统会自动等待指定秒数
- 降低操作频率
- 新号前几周要特别谨慎

### Q3: 如何获取多个测试号?
**A**:
- 购买多个虚拟号码(SMS-Activate等)
- 每个号码成本约$0.5-1
- $5预算可测试10个左右号码
- 或使用朋友/家人的备用号

### Q4: 没有Docker怎么办?
**A**:
- 方案1: 安装Docker Desktop(推荐)
- 方案2: 本地安装PostgreSQL + Redis
- 方案3: 仅测试Telegram适配器(无需数据库)
- 方案4: 仅前端演示(完全无需后端)

---

## 📞 下一步行动

**请选择您想要的测试级别**:

### 🟢 级别1: 仅查看界面
- ✅ 已完成
- 访问: http://localhost:3001
- 无需任何额外配置

### 🟡 级别2: 测试Telegram登录
- 需要: 1个Telegram账号
- 运行: `python test_telegram_manual.py`
- 时间: 15分钟

### 🟠 级别3: 完整功能演示
- 需要: Docker Desktop + 1-2个Telegram账号
- 时间: 1小时设置
- 效果: 完整的自动化流程

### 🔴 级别4: 生产级测试
- 需要: 3-5个预热过的账号 + 代理IP池
- 时间: 1周准备(账号预热)
- 效果: 真实的情报收集

---

**告诉我您想进行哪个级别的测试,我会提供详细指导!** 🚀
