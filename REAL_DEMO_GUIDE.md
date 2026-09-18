# 真实Telegram互动演示完整指南

## 📋 当前状态

### ✅ 已完成
- [x] 前端实时滚动对话页面 (/live-chat)
- [x] 算术验证机制 (verification.py)
- [x] AI智能回复引擎 (DeepSeek-V3集成)
- [x] 媒体组批量发送优化
- [x] 账号养号策略系统
- [x] 一键拉黑功能
- [x] 代理服务器运行中 (127.0.0.1:7890)
- [x] 前端运行在 http://localhost:3001

### ⚠️ 待完成
- [ ] Telegram会话认证(需要手动登录)
- [ ] WebSocket实时推送(可选,用于前后端联动)

---

## 🔐 Telegram登录步骤

### 方法1: 使用quick_login.py(推荐)

```bash
cd <project-root>/backend
source venv/bin/activate
python quick_login.py
```

**按提示操作:**
1. 输入printer账号的手机号(格式: +84xxxxxxxxx)
2. 查看手机Telegram应用,获取验证码
3. 输入6位验证码
4. 如果开启了两步验证,输入密码

### 方法2: 使用login_printer.py

```bash
python login_printer.py
```

### 常见问题

**Q: 连接超时 "Connection to Telegram failed 5 time(s)"**
- A: 检查代理是否运行: `lsof -i :7890`
- A: 重启代理或更换代理端口

**Q: 数据库锁定 "database is locked"**
- A: 删除journal文件: `rm sessions/printer.session-journal`

**Q: Session无效**
- A: 删除旧session重新登录: `rm sessions/printer.session*`

---

## 🚀 启动真实互动演示

### 第1步: 确认登录成功
```bash
ls -lh sessions/printer.session
# 应该看到约28KB的文件
```

### 第2步: 启动后端聊天服务
```bash
cd <project-root>/backend
source venv/bin/activate
python live_chat_demo.py
```

你会看到:
```
🔌 正在连接Telegram(使用代理)...
✅ 已连接! User: Nguyen Van A (@printer_bot)

⏳ 等待消息...
```

### 第3步: 用你的Telegram测试
1. 打开你的Telegram应用
2. 搜索printer账号(通过用户名或手机号)
3. 发送消息: "Xin chào" (越南语: 你好)
4. 你会收到算术题: "87 + 13 = ?"
5. 回复正确答案: "100"
6. AI开始智能对话!

---

## 💬 演示场景脚本

### 场景1: 货币兑换咨询(推荐)

**用户发送:**
```
Xin chào! Tôi muốn đổi tiền USD sang VND.
```

**AI回复流程:**
1. 验证问题: "Để xác minh bạn không phải robot:\n\n45 + 23 = ?"
2. 用户回复: "68"
3. AI欢迎: "✅ Xác minh thành công! ..."
4. AI提供汇率: "Tỷ giá hiện tại: 1 USD ≈ 24,500 VND..."
5. 主动提问: "Bạn muốn đổi số tiền bao nhiêu?"

### 场景2: 私人调查服务

**用户发送:**
```
Bạn có thể giúp tôi tìm thông tin về một người không?
```

**AI回复:**
- 服务介绍: "Chúng tôi cung cấp dịch vụ điều tra..."
- 价格区间: "Chi phí từ $500-$2000 tùy mức độ..."
- 信息收集: "Bạn có thể cung cấp tên và số điện thoại?"

### 场景3: 自由职业者招募

**用户发送:**
```
Tôi cần thuê một lập trình viên React cho dự án 3 tháng
```

**AI回复:**
- 技能确认: "Dự án cần React Native hay React Web?"
- 经验要求: "Cần bao nhiêu năm kinh nghiệm?"
- 预算讨论: "Ngân sách dự kiến là bao nhiêu?"

---

## 🎯 演示亮点展示

### 1. 算术验证机制
- **目的**: 过滤机器人,防止骚扰
- **效果**: 首次对话必须回答数学题
- **实现**: `backend/app/services/conversation/verification.py`

### 2. AI智能对话
- **模型**: DeepSeek-V3 (支持越/中/英三语)
- **特点**:
  - 自然的越南语表达
  - 主动提取关键信息(电话、邮箱、地址)
  - 上下文记忆能力
  - Emoji表情增强亲和力

### 3. 打字延迟模拟
- **目的**: 看起来更像真人
- **实现**: 根据回复长度动态计算延迟(1-3秒)

### 4. 账号养号策略
- **四阶段**: 新号(0-7天) →  warming(8-30天) → 稳定(31-90天) → 成熟(90+天)
- **动态限制**: 每天加群数、发消息数根据阶段调整
- **防封号**: 模拟真人作息,避免异常行为

### 5. 媒体组批量发送
- **优化**: 累积10条或2秒超时后批量发送
- **效果**: API调用减少约5倍

### 6. 一键拉黑
- **前端**: conversations页面红色🚫按钮
- **后端**: 实时更新blocked_users集合
- **效果**: 拉黑后立即停止回复

---

## 🖥️ 前端演示页面

### 访问地址
http://localhost:3001/live-chat

### 页面功能
- **实时滚动屏幕**: 自动显示所有对话
- **消息区分**: 用户(蓝色/右) vs AI(白色/左)
- **状态图标**: ✅已验证, ⏳发送中
- **演示模式**: 预加载6条示例对话
- **自动滚动**: 新消息到达时平滑滚动到底部

### 切换真实模式
修改 `frontend/src/app/live-chat/page.tsx`:
```typescript
const DEMO_MODE = false; // 改为false启用真实模式
```

然后需要配置WebSocket连接到后端(目前仅支持演示模式)。

---

## 🔧 故障排查

### 前端无法访问
```bash
# 检查进程
lsof -ti:3001

# 重启服务
cd <project-root>/frontend
./node_modules/.bin/next dev
```

### 后端连接失败
```bash
# 检查代理
lsof -i :7890

# 测试session
python -c "
import asyncio
from telethon import TelegramClient
from app.core.config import settings
client = TelegramClient('sessions/printer', settings.tg_api_id, settings.tg_api_hash)
asyncio.run(client.connect())
print('Authorized:', asyncio.run(client.is_user_authorized()))
"
```

### DeepSeek API错误
```bash
# 检查API Key
cat backend/.env | grep DEEPSEEK

# 测试API
python real_demo.py
```

---

## 📊 演示数据流

```
用户Telegram消息
    ↓
Telethon监听 (live_chat_demo.py)
    ↓
算术验证 (verification.py)
    ↓
DeepSeek-V3 API (生成越南语回复)
    ↓
打字延迟模拟 (1-3秒)
    ↓
发送回复到用户Telegram
```

---

## 🎓 演示话术建议

### 开场白
> "这是我们开发的OSINT社交情报采集系统,可以自动化管理多个社交媒体平台的客户对话。"

### 展示验证机制
> "首先,系统会进行简单的算术验证,确保对方不是机器人。这是防骚扰的第一道防线。"

### 展示AI能力
> "验证通过后,DeepSeek-V3大模型会生成自然的越南语回复,能够主动提取关键信息如电话号码、邮箱、地址等。"

### 展示养号策略
> "系统内置了四阶段账号养号机制,新账号每天只能加2个群,成熟账号可以加15个群,有效防止封号。"

### 展示批量优化
> "媒体组消息会自动缓冲,累积到10条或2秒后批量发送,API调用效率提升5倍。"

### 结束语
> "整个系统支持Telegram、Facebook、Zalo三个平台,可以实现跨平台的自动化客户情报采集。"

---

## 📝 下一步改进建议

1. **WebSocket实时推送**: 前后端双向通信,前端实时显示Telegram消息
2. **多账号管理**: 同时管理多个Telegram账号
3. **对话分析面板**: 统计回复率、转化率、平均响应时间
4. **模板库**: 预设常用回复模板,AI自动选择
5. **敏感词过滤**: 自动识别并标记可疑对话
6. **导出功能**: 将对话记录导出为PDF/Excel

---

## 🆘 技术支持

遇到问题请检查:
1. 代理服务器是否运行 (`lsof -i :7890`)
2. Telegram session是否有效 (`ls -lh sessions/*.session`)
3. DeepSeek API Key是否正确 (`cat .env`)
4. 网络连接是否正常 (`ping api.deepseek.com`)

祝演示顺利! 🎉
