# Telegram 账号养号与防封号完全指南

## 📋 核心原则

根据Telegram官方风控机制和社区经验,新账号必须经过"养号期"才能安全使用。本系统已自动集成养号策略,但操作员需了解原理并配合执行。

---

## 🆕 新号必做设置(注册后24小时内完成)

### 1. 汉化界面
- **路径**: Settings → Language → 选择中文
- **原因**: 降低被识别为自动化账号的概率

### 2. 关闭通讯录同步
- **路径**: Settings → Privacy and Security → Phone Number → Nobody
- **路径**: Settings → Privacy and Security → Contacts → Disable "Sync Contacts"
- **原因**: 避免暴露真实社交关系

### 3. 开启两步验证
- **路径**: Settings → Privacy and Security → Two-Step Verification → Set Password
- **原因**: 增强账号安全性,防止被盗用导致异常登录

### 4. 启用自动删除
- **路径**: Settings → Privacy and Security → Auto-Delete Messages → 设置为7天或30天
- **原因**: 减少历史数据留存,降低被审查风险

### 5. 补全隐私设置
```
Settings → Privacy and Security:
├─ Phone Number: Nobody
├─ Last Seen & Online: Nobody
├─ Profile Photos: My Contacts
├─ Forwarded Messages: Nobody
├─ Calls: My Contacts
├─ Groups & Channels: My Contacts (限制被邀请)
└─ Bio: 填写正常用户简介
```

**⚠️ 重要**: 系统会检查这些设置是否完成,新号未完成前将限制操作!

---

## 📅 养号阶段划分

### Phase 1: 新号期 (0-7天)  严格限制

**每日上限**:
- 加群: **最多2个**
- 发消息: **每小时5条,每天20条**
- 陌生人消息: **每天最多3条**
- 好友请求: **每天最多1个**

**行为规范**:
- ✅ 入群后至少观察**30分钟**再发言
- ✅ 每次加群后等待**30-120秒**随机延迟
- ✅ 模拟真实用户行为(打字延迟、阅读延迟)
- ❌ 禁止批量操作
- ❌ 禁止发送链接或文件
- ❌ 禁止频繁切换IP

**IP要求**:
- 注册后**90天内**保持同一地区IP
- 推荐使用越南住宅代理(目标地区)

---

### Phase 2: 温号期 (8-30天) 🟡 适度放宽

**每日上限**:
- 加群: **最多5个**
- 发消息: **每小时10条,每天50条**
- 陌生人消息: **每天最多8条**
- 好友请求: **每天最多3个**

**行为规范**:
- ✅ 入群后观察**15分钟**再发言
- ✅ 可以开始少量互动
- ️ 仍需保持随机延迟
- ⚠️ 避免敏感话题

---

### Phase 3: 稳定期 (31-90天) 🟢 正常使用

**每日上限**:
- 加群: **最多8个**
- 发消息: **每小时20条,每天100条**
- 陌生人消息: **每天最多15条**
- 好友请求: **每天最多5个**

**行为规范**:
- ✅ 入群后观察**5分钟**即可
- ✅ 可以正常参与讨论
- ✅ 可以发送多媒体内容
- ⚠️ 仍需遵守平台规则

---

### Phase 4: 成熟期 (90天+) ✅ 完全放开

**每日上限**:
- 加群: **最多15个**
- 发消息: **每小时30条,每天200条**
- 陌生人消息: **每天最多30条**
- 好友请求: **每天最多10个**

**行为规范**:
- ✅ 无需观察期
- ✅ 可以高频操作
- ⚠️ 仍需避免触发Flood Wait

---

## ️ 防封号最佳实践

### 1. IP一致性管理

```python
# 系统会自动追踪IP地区变化
warming_manager.update_ip_region(account_id, "Vietnam-HCM")

# 如果90天内IP地区变化,会触发警告
if not profile.ip_consistent and profile.age_days < 90:
    logger.warning("IP region changed - risk of ban!")
```

**建议**:
- 注册时使用越南IP
- 90天内不要更换IP地区
- 使用固定住宅代理而非数据中心IP

### 2. 注册时间伪装

- 不要在注册当天进行大量操作
- 模拟正常用户成长轨迹
- 前3天仅浏览,不主动联系

### 3. 行为模式多样化

```python
# 系统已内置:
- 打字延迟: 50ms/字符 ±30%随机波动
- 阅读延迟: 5-45秒随机等待
- 活跃时段: 越南时间8:00-23:00
- 碎片化在线: 30-90min活跃 + 15-60min离线
```

### 4. 内容安全过滤

- ❌ 不讨论暴力、武器、毒品
- ❌ 不冒充政府/执法机构
- ❌ 不涉及未成年人话题
- ✅ 使用自然语言,避免模板化回复

---

## 🚨 账号被封申诉流程

如果账号被冻结,按以下步骤申诉:

### Step 1: 联系 Spam Info Bot

1. Telegram搜索 `@SpamBot` 或点击 [Spam Info Bot](https://t.me/SpamBot)
2. 发送 `/start`
3. 选择 `This is a mistake`
4. 选择 `Yes`

### Step 2: 填写申诉信息

按顺序回复以下内容:

**问题1**: 说明情况
```
My account is running well, I don't understand what I did to violate the rules. 
I subscribed to 1 Premium this morning, but my account was frozen as soon as the membership arrived. 
I don't understand why, please help me unfreeze it. My account is very important to me. Thank you.
```

**问题2**: 合法姓名
```
Nguyen Van A  (使用越南常见姓名)
```

**问题3**: 可接码邮箱
```
your_email@gmail.com  (必须是你能接收验证码的邮箱)
```

**问题4**: 注册时间
```
2025  (根据实际情况填写年份)
```

**问题5**: 如何发现Telegram
```
My colleague recommended it to me to use.
```

**问题6**: 使用情况
```
Work communication, enjoy the Telegram ecosystem.
```

### Step 3: 完成验证

1. 点击 `Confirm`
2. 点击人机验证链接
3. 返回Bot,点击 `end`
4. 等待10分钟左右出结果

**注意**: 成功率不高,建议提前预防而非事后申诉!

---

## 📊 系统自动执行的保护措施

### 1. 养号管理器 (`account_warming.py`)

```python
# 自动检查操作限制
allowed, reason = warming_manager.check_and_enforce_limits(
    account_id="session_001",
    operation="join_group",
)

if not allowed:
    logger.warning(f"Operation blocked: {reason}")
    # 例如: "Daily group join limit reached (2)"
```

### 2. 每日计数器重置

系统会在每天午夜自动重置:
- 加群计数
- 发消息计数
- 陌生人消息计数
- 好友请求计数

### 3. 账号健康监控

```python
# 四级状态监控
GREEN:  正常操作
YELLOW: 降速50% (接近限额)
RED:    暂停24-72小时 (达到限额)
BLACK:  可能被封,人工介入 (连续失败)
```

---

## 🔧 操作员检查清单

### 新号注册后24小时

- [ ] 汉化界面
- [ ] 关闭通讯录同步
- [ ] 开启两步验证
- [ ] 启用自动删除
- [ ] 补全所有隐私设置
- [ ] 填写正常用户简介
- [ ] 上传真实头像(非网图)
- [ ] 加入2-3个正常群组观察

### 每周检查

- [ ] 检查IP地区是否一致
- [ ] 查看账号健康状态
- [ ] 确认养号配置是否正确
- [ ] 清理过期会话

### 每月检查

- [ ] 评估是否需要更换代理IP
- [ ] 检查是否有异常登录
- [ ] 更新两步验证密码
- [ ] 备份重要对话记录

---

## 💡 高级技巧

### 1. 多账号轮换

```python
# 系统支持多账号池
accounts = ["session_001", "session_002", "session_003"]

# 自动选择健康度最高的账号
best_account = select_healthiest_account(accounts)
```

### 2. 预热期模拟

```python
# 前7天仅执行被动操作
if account_age < 7:
    allow_passive_only()  # 只响应,不主动发起
```

### 3. 地域一致性

```python
# 确保所有操作来自同一地区
warming_manager.update_ip_region(account_id, "Vietnam-HCM")

# 系统会自动检测IP变化
if not profile.ip_consistent:
    block_operations()  # 阻止操作直到IP恢复
```

---

## ️ 风险提示

1. **没有100%安全的方案**: 即使严格遵守养号策略,仍有被封风险
2. **备用账号池**: 建议准备3-5倍数量的备用账号
3. **成本预算**: 每个账号月成本约¥20-40(手机号+代理IP)
4. **法律合规**: 仅用于授权的安全研究,遵守当地法规

---

## 📈 预期效果

| 阶段 | 存活率 | 日均产能 | 备注 |
|------|--------|---------|------|
| 新号期(0-7天) | 95% | 1-2条情报 | 严格限制 |
| 温号期(8-30天) | 90% | 3-5条情报 | 适度放宽 |
| 稳定期(31-90天) | 85% | 5-8条情报 | 正常使用 |
| 成熟期(90天+) | 80% | 8-12条情报 | 完全放开 |

**总体账号月存活率**: ~85% (相比未养号的30-40%大幅提升)

---

**版本**: v1.0  
**最后更新**: 2026-09-17  
**参考来源**: Telegram社区经验 + 实际运营数据
