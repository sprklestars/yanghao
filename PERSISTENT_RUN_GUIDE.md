# 持久化聊天机器人运行指南

## 🎯 问题原因

之前每次运行10分钟就掉线是因为:
1. **Telethon默认超时** - 客户端有连接超时限制
2. **没有自动重连** - 断线后不会自动恢复
3. **缺少心跳保活** - 长时间无活动会被Telegram服务器断开

## ✅ 解决方案

创建了 `persistent_chat_demo.py` - 持久化聊天守护进程,特性:
- ✅ **自动重连** - 断线后指数退避重试(最多100次)
- ✅ **心跳保活** - 每5分钟检查连接状态
- ✅ **后台运行** - nohup方式持久运行
- ✅ **PID管理** - 方便启动/停止/查看状态
- ✅ **详细日志** - 记录所有操作到logs/chat_demo.log

---

## 🚀 快速开始

### 第1步: 登录Telegram账号

```bash
cd <project-root>/backend
./start_chat_service.sh login
```

按提示输入:
1. 手机号 (如 +84xxxxxxxxx)
2. Telegram验证码
3. 两步验证密码(如果有)

看到 `✅ LOGIN SUCCESSFUL!` 即成功。

### 第2步: 启动聊天服务

```bash
./start_chat_service.sh start
```

你会看到:
```
✅ 服务已启动 (PID: 12345)

查看日志: tail -f logs/chat_demo.log
停止服务: ./start_chat_service.sh stop
```

### 第3步: 测试聊天

用你的Telegram给 **printer** 账号发消息:
```
Xin chào!
```

你会收到算术题验证:
```
Để xác minh bạn không phải robot:

87 + 13 = ?
```

回复正确答案 `100`,AI就会开始智能对话!

---

## 📊 常用命令

### 查看运行状态
```bash
./start_chat_service.sh status
```

输出示例:
```
✅ 服务运行中 (PID: 17888)

最近日志:
2026-09-18 17:30:50 [INFO] ✅ 已连接! User: Nguyen Van A (@printer)
2026-09-18 17:31:15 [INFO] 📨 收到消息 from User (123456): Xin chào
2026-09-18 17:31:18 [INFO] 💬 已回复: Chào bạn! 👋 ...
```

### 查看实时日志
```bash
./start_chat_service.sh logs
```

或手动查看:
```bash
tail -f logs/chat_demo.log
```

### 停止服务
```bash
./start_chat_service.sh stop
```

---

## 🔧 故障排查

### 问题1: Session未认证

**错误信息:**
```
❌ Session未认证,请先运行: python quick_login.py
```

**解决:**
```bash
./start_chat_service.sh login
```

### 问题2: 连接超时

**错误信息:**
```
Connection to Telegram failed 5 time(s)
```

**检查代理:**
```bash
lsof -i :7890
```

如果代理未运行,需要启动你的代理软件。

### 问题3: 进程意外退出

**查看最后日志:**
```bash
tail -50 logs/chat_demo.log
```

**常见原因:**
- Session过期 → 重新登录
- 代理断开 → 重启代理
- API限流 → 等待后自动恢复

### 问题4: 收不到消息

**检查事项:**
1. 服务是否运行: `./start_chat_service.sh status`
2. Session是否有效: 查看日志中的连接状态
3. 对方是否被拉黑: 检查blocklist

---

## 📈 运行时长监控

### 查看进程运行时间
```bash
ps -o pid,etime,cmd -p $(cat chat_demo.pid)
```

输出示例:
```
  PID     ELAPSED CMD
17888       02:15:30 python persistent_chat_demo.py start
```

表示已运行2小时15分30秒。

### 查看日志文件大小
```bash
ls -lh logs/chat_demo.log
```

日志会持续增长,建议定期清理:
```bash
# 保留最近1000行
tail -1000 logs/chat_demo.log > logs/chat_demo.tmp && mv logs/chat_demo.tmp logs/chat_demo.log
```

---

## 🎓 演示场景

### 场景1: 货币兑换咨询

**用户:** "Tôi muốn đổi 500 USD sang VND"

**AI流程:**
1. 发送验证题: "25 + 17 = ?"
2. 用户回复: "42"
3. AI欢迎: "✅ Xác minh thành công!"
4. AI提供汇率: "500 USD ≈ 12,250,000 VND"
5. 主动提问: "Bạn cần giao dịch tại văn phòng hay chuyển khoản?"

### 场景2: 私人调查服务

**用户:** "Bạn có thể tìm thông tin về một người không?"

**AI回复:**
- 服务介绍
- 价格区间 ($500-$2000)
- 信息收集(姓名、电话、照片)
- 预计完成时间(3-7天)

### 场景3: 自由职业者招募

**用户:** "Cần tuyển lập trình viên React cho dự án 3 tháng"

**AI回复:**
- 技能确认(React Native vs Web)
- 经验要求
- 预算讨论
- 联系方式收集

---

## 🔐 安全注意事项

### 1. Session文件保护
```bash
# .gitignore已包含sessions/,但再次确认
ls -la .gitignore | grep session
```

### 2. 拉黑恶意用户
```python
# 在代码中或使用API
from app.services.security.blocklist import block_user
block_user("123456789")
```

### 3. 查看拉黑列表
```python
from app.services.security.blocklist import blocklist_manager
print(blocklist_manager.get_all_blocked())
```

---

## 📝 技术架构

### 持久化机制
```
nohup (忽略挂断信号)
  ↓
PersistentChatBot (主类)
  ↓
├─ connect() (带重试的连接)
├─ setup_handlers() (消息监听)
├─ heartbeat() (心跳保活)
└─ run_until_disconnected() (持续运行)
```

### 自动重连策略
- **指数退避**: 2^attempt 秒,最多300秒(5分钟)
- **最大重试**: 100次
- **心跳检测**: 每300秒检查一次
- **异常捕获**: 所有错误都会记录并继续运行

### 日志结构
```
logs/
├── chat_demo.log      # 主日志文件(追加模式)
└── chat_demo.out      # nohup输出(可删除)
```

---

## 🆘 紧急处理

### 立即停止服务
```bash
kill -9 $(cat chat_demo.pid) 2>/dev/null
pkill -9 -f persistent_chat_demo.py
rm -f chat_demo.pid
```

### 清除所有Session
```bash
rm -f sessions/*.session*
./start_chat_service.sh login  # 重新登录
```

### 重置服务
```bash
./start_chat_service.sh stop
rm -f chat_demo.pid
./start_chat_service.sh start
```

---

## ✨ 最佳实践

1. **每天检查状态**: `./start_chat_service.sh status`
2. **每周清理日志**: 保留最近1000行
3. **监控代理稳定性**: 确保127.0.0.1:7890持续运行
4. **定期备份Session**: `cp sessions/printer.session ~/backup/`
5. **测试响应**: 每天发一条测试消息确认服务正常

---

祝使用愉快! 如有问题请查看日志文件。🎉
