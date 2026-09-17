# 🚀 多平台主动聊天智能体 - 功能实现总结

## ✅ 已完成的核心功能

### 1. **三大平台适配器**

#### ✈️ Telegram (已完成)
- **技术**: Telethon (MTProto协议)
- **能力**:
  - ✅ 搜索群组
  - ✅ 加入群组
  - ✅ 发送好友请求
  - ✅ 发送/接收消息
  - ✅ 获取用户资料
  - ✅ 获取群组成员
  - ✅ Flood Wait自动处理

#### 📘 Facebook (新增)
- **技术**: Playwright浏览器自动化
- **文件**: `backend/app/services/platform/facebook_adapter.py`
- **能力**:
  - ✅ 真实浏览器登录(Cookie持久化)
  - ✅ 搜索群组(模拟滚动加载)
  - ✅ 加入群组
  - ✅ 发送好友请求
  - ✅ Messenger发送消息(带打字延迟)
  - ✅ 监听新消息(轮询机制)
  - ✅ 获取用户资料
  - ✅ 获取群组成员
- **反检测**:
  - ✅ 隐藏webdriver特征
  - ✅ 真实User-Agent和视口
  - ✅ 随机延迟和滚动
  - ✅ Cookie会话保存

#### 💬 Zalo (新增)
- **技术**: zlapi非官方SDK
- **文件**: `backend/app/services/platform/zalo_adapter.py`
- **能力**:
  - ✅ 手机号+密码认证
  - ✅ IMEI设备标识生成
  - ✅ Cookie刷新机制(24-72小时有效期)
  - ✅ 获取已加入群组
  - ✅ 添加好友
  - ✅ 发送消息
  - ✅ 监听消息(轮询)
  - ✅ 获取用户资料
  - ✅ 获取群组成员
- **特殊处理**:
  - ✅ IMEI自动生成和绑定
  - ✅ Cookie过期检测
  - ✅ 自动刷新机制

---

### 2. **话术库管理系统**

**文件**: `backend/app/services/conversation/script_library.py`

#### 核心功能:
- ✅ **多语言支持**: 越南语(vi)、中文(zh)、英文(en)
- ✅ **分阶段管理**:
  - greeting(问候)
  - probing(试探)
  - extraction(提取)
  - pivot(转移话题)
  - exit(退出)
- ✅ **分类组织**: 按目标业务类型(private_investigator/currency_exchanger/freelancer/data_seller)
- ✅ **A/B测试**:
  - 效果评分(effective ness_score 0-1)
  - 使用次数统计(usage_count)
  - epsilon-greedy策略(90%利用最佳,10%探索)
- ✅ **LLM人性化润色**:
  - 使用DeepSeek-V3重写话术
  - 注入5%概率的轻微拼写错误
  - 匹配Persona语气风格
  - 保持原意但更自然

#### 预设话术示例:
```yaml
greeting.group_join.vi:
  - "Chào mọi người! Mình mới tham gia nhóm 😊"
  - "Xin chào cả nhà! Rất vui được làm quen với mọi người 🙏"

probing.currency_exchanger.vi:
  - "Tỷ giá USD-VND hôm nay tốt nhất ở đâu vậy bạn?"
  - "Bạn có biết chỗ đổi tiền uy tín không? Mình cần đổi khoảng $2000."

extraction.general.vi:
  - "Cho mình xin contact trực tiếp được không? Zalo hoặc SĐT."
  - "Bên bạn có website hay fanpage không? Cho mình xem thêm thông tin."
```

---

### 3. **场景化对话策略引擎**

**文件**: `backend/app/services/conversation/strategy_engine.py`

#### 核心能力:

##### A. **混群 vs 加好友策略选择**
根据目标类别自动选择最优策略:

| 目标类别 | 首选策略 | 次选策略 | 原因 |
|---------|---------|---------|------|
| 🔍 私人侦探 | 混群(优先级8) | 加好友(优先级6) | 群内互动更自然,降低警惕 |
| 💱 换汇服务 | 直接 outreach(优先级9) | 混群(优先级7) | 需求明确,可直接询问 |
| 💼 自由职业者 | 混群(优先级9) | 加好友(优先级7) | 群内展示作品,建立信任 |
| 📊 数据贩卖 | 直接 outreach(优先级8) | 混群(优先级5) | 敏感业务,需私下沟通 |

##### B. **主动聊天流程优化**
- ✅ **状态机跟踪**: greeting → probing → extraction → pivot/exit
- ✅ **触发词检测**: 自动识别业务信号(如"tỷ giá"、"portfolio")
- ✅ **成功/失败指标**:
  - 成功: 提供联系方式、报价、服务详情
  - 失败: 拉黑、举报、明确拒绝
- ✅ **自动转移**: 探测超过10轮无收获自动pivot

##### C. **业务渠道试探逻辑**
每个策略配置包含:
```python
StrategyConfig(
    strategy_type=StrategyType.GROUP_MIXING,
    priority=9,
    max_initial_greetings=3,       # 最多3次问候
    probing_rounds=6,              # 6轮试探
    extraction_triggers=[          # 提取触发词
        "giá", "dịch vụ", "portfolio",
        "price", "service", "hire"
    ],
    messages_per_hour=25,          # 每小时25条消息
    friend_requests_per_day=8,     # 每天8个好友请求
    group_joins_per_day=5,         # 每天加5个群
    success_indicators=[           # 成功标志
        "shares portfolio",
        "quotes price",
        "provides contact"
    ],
    failure_indicators=[           # 失败标志
        "not interested",
        "too busy"
    ]
)
```

---

## 🎯 完整工作流程

```
1. 用户创建任务
   ├─ 选择平台(Telegram/Facebook/Zalo)
   ├─ 选择类别(私人侦探/换汇/自由职业/数据贩卖)
   └─ 输入关键词和目标地区

2. 策略引擎选择最优策略
   ├─ 根据类别查找预定义策略
   ├─ 考虑账号健康状态调整参数
   └─ 确定混群或加好友为主策略

3. 平台适配器执行操作
   ├─ 搜索相关群组
   ├─ 加入群组(每日限额)
   ├─ 获取群组成员列表
   └─ 选择目标用户

4. 话术库生成对话内容
   ├─ 根据阶段选择模板(greeting/probing/extraction)
   ├─ A/B测试选择最佳话术
   ├─ LLM人性化润色(注入拼写错误、匹配语气)
   └─ 发送消息(带打字延迟模拟)

5. 监听并处理回复
   ├─ 接收对方消息
   ├─ 更新对话状态(检测触发词)
   ├─ 判断是否进入下一阶段
   ├─ 生成回复(LLM + Persona)
   └─ 发送回复

6. 情报提取与存储
   ├─ 检测到成功指标(提供联系方式等)
   ├─ 提取实体(电话、邮箱、Zalo ID等)
   ├─ 分类标注(置信度评分)
   ├─ 去重指纹生成
   └─ 存入数据库

7. 优雅退出
   ├─ 达到退出条件(成功提取或超时)
   ├─ 发送告别消息
   ├─ 标记对话完成
   └─ 清理资源
```

---

## 📊 平台对比

| 特性 | Telegram | Facebook | Zalo |
|------|----------|----------|------|
| **API稳定性** | ⭐⭐⭐⭐⭐ (官方MTProto) | ⭐⭐⭐ (Playwright模拟) | ⭐⭐ (非官方SDK) |
| **反检测难度** | 中(Flood Wait频繁) | 高(Meta积极封堵) | 高(Cookie易过期) |
| **群组功能** | ⭐⭐⭐⭐⭐ (公开搜索) | ⭐⭐⭐⭐ (半公开) | ⭐⭐ (需邀请) |
| **消息限制** | 较宽松 | 严格 | 非常严格 |
| **推荐优先级** | ✅✅✅ 首选 | ✅✅ 次选 | ✅ 辅助 |

---

## 🔐 安全防护升级

### 跨平台统一防护:
- ✅ **速率限制**: 每平台独立配置
- ✅ **行为模拟**: 打字延迟、阅读延迟、活跃时段
- ✅ **账号健康**: 四级监控(GREEN/YELLOW/RED/BLACK)
- ✅ **错误重试**: Flood Wait自动等待
- ✅ **Cookie管理**: Facebook/Zalo会话持久化

### 平台特有防护:
- **Telegram**: FloodWaitError捕获 + 自动冷却
- **Facebook**: webdriver隐藏 + 真实浏览器特征
- **Zalo**: IMEI轮换 + Cookie刷新机制

---

## 🛠️ 使用方法

### 1. 安装依赖
```bash
cd backend
pip install playwright zlapi telethon
playwright install chromium
```

### 2. 配置环境变量
编辑 `backend/.env`:
```env
# Telegram
TG_API_ID=12345678
TG_API_HASH=abcdef1234567890

# Facebook (通过Playwright登录,无需API密钥)

# Zalo
ZALO_PHONE=+84123456789
ZALO_PASSWORD=your_password
```

### 3. 创建任务时选择平台
在前端任务表单中:
- Platform下拉框选择: Telegram / Facebook / Zalo
- Category选择目标业务类型
- 输入相关关键词

### 4. 系统自动执行
- 策略引擎根据类别选择最优策略
- 平台适配器执行混群或加好友
- 话术库生成拟人化消息
- 智能对话直到提取到情报

---

## 📈 预期效果

### 成功率估算(POC阶段):
| 平台 | 混群成功率 | 加好友通过率 | 情报提取率 |
|------|-----------|------------|-----------|
| Telegram | 70-80% | 30-40% | 40-50% |
| Facebook | 50-60% | 20-30% | 30-40% |
| Zalo | 40-50% | 25-35% | 25-35% |

### 每日产能(单账号):
- **Telegram**: 10-15个有效对话,3-5条情报
- **Facebook**: 5-8个有效对话,2-3条情报
- **Zalo**: 4-6个有效对话,1-2条情报

---

## 🔜 后续优化方向

### 短期(P1):
1. **Facebook专用反检测**:
   - 住宅代理IP池
   - 浏览器指纹随机化
   - 鼠标移动轨迹模拟

2. **Zalo稳定性提升**:
   - 官方OA API集成
   - 多账号轮换机制
   - Cookie预热期管理

3. **话术库增强**:
   - 用户上传自定义话术
   - 基于历史数据的自动优化
   - 更多行业特定模板

### 中期(P2):
1. **AI策略学习**:
   - 强化学习优化对话流程
   - 自动发现新的触发词
   - 动态调整策略优先级

2. **跨平台关联**:
   - 同一目标多平台去重
   - 跨平台情报融合
   - 统一画像构建

3. **批量操作**:
   - 多账号并行执行
   - 负载均衡
   - 冲突检测

---

## 📝 重要提醒

⚠️ **合规使用**:
- 仅用于授权的安全研究和教育目的
- 遵守各平台服务条款
- 尊重用户隐私和数据保护法规
- 保留完整审计日志

⚠️ **风险控制**:
- 新号预热期至少7天
- 严格控制操作频率
- 定期更换代理IP
- 准备备用账号池

---

**版本**: v0.2.0  
**更新日期**: 2026-09-14  
**新增功能**: Facebook适配器、Zalo适配器、话术库管理、策略引擎
