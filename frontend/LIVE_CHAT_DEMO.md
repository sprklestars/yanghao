# 实时对话演示页面使用说明

## 访问地址
http://localhost:3001/live-chat

## 功能特性

### 📺 实时滚动屏幕
- 自动显示所有对话消息
- 新消息自动滚动到底部
- 区分用户消息(蓝色/右侧)和机器人回复(白色/左侧)

### 🔐 算术验证机制
- 首次对话自动触发数学题验证
- 防止机器人骚扰
- 验证通过后才能继续对话

### 🤖 AI智能回复
- 基于DeepSeek-V3大模型
- 支持越南语/中文/英语三语对话
- 模拟真实打字延迟
- 主动提取关键信息(电话、邮箱、地址等)

### 💬 演示模式
当前使用模拟数据,无需后端服务即可展示完整功能:
- 预加载6条示例对话
- 随机生成新消息模拟真实互动
- 显示验证状态图标(✅已验证, ⏳发送中)

## 如何切换到真实模式

1. 完成Telegram登录(参考 `backend/LOGIN_INSTRUCTIONS.md`)
2. 启动后端服务:
   ```bash
   cd backend
   source venv/bin/activate
   python live_chat_demo.py
   ```
3. 修改前端代码,将 `DEMO_MODE` 改为 `false`

## 演示场景建议

### 场景1: 货币兑换咨询
用户发送: "Xin chào! Tôi muốn đổi tiền USD sang VND."
AI回复: 验证问题 → 汇率信息 → 地址详情

### 场景2: 私人调查服务
用户发送: "Bạn có thể giúp tôi tìm thông tin về một người không?"
AI回复: 服务说明 → 价格区间 → 联系方式

### 场景3: 自由职业者招募
用户发送: "Tôi cần thuê một lập trình viên React"
AI回复: 技能要求 → 项目报价 → 合作流程

## 界面元素

- **顶部**: 连接状态指示器(绿色=已连接,红色=未连接)
- **中部**: 可滚动消息区域,显示时间戳和验证状态
- **底部**: 输入框 + 发送按钮,支持Enter快捷键
- **提示栏**: 功能说明和技术栈展示

## 技术亮点

1. **React Hooks**: useState, useEffect, useRef实现响应式更新
2. **自动滚动**: messagesEndRef确保新消息始终可见
3. **TypeScript类型安全**: ChatMessage接口定义
4. **Tailwind CSS**: 现代化UI设计,无需额外CSS文件
5. **Next.js 14**: App Router架构,服务端渲染支持
