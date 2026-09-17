# 🔧 GitHub推送故障排除指南

## ❌ 当前错误

```
fatal: unable to access 'https://github.com/sprklestars/yanghao.git/':
Recv failure: Connection was reset
```

---

## 🔍 可能原因

### 1. GitHub仓库不存在
如果 `yanghao` 仓库还没有在GitHub上创建,推送会失败。

### 2. 网络连接问题
- 防火墙阻止
- 代理设置问题
- GitHub访问受限

### 3. 认证问题
- 需要GitHub登录凭证
- Personal Access Token过期

---

## ✅ 解决方案

### 方案1: 先在GitHub创建仓库(最可能的问题)

#### 步骤1: 手动创建仓库
1. 打开浏览器访问: https://github.com/new
2. Repository name: **yanghao**
3. Description (可选): OSINT Social Media Intelligence Platform
4. **重要**: 不要勾选 "Initialize this repository with a README"
5. Visibility: Public 或 Private (根据需要)
6. 点击 **"Create repository"**

#### 步骤2: 推送代码
```bash
cd "D:\360MoveData\Users\张浩楠\Desktop\任务-杨"
git push -u origin master
```

首次推送会弹出认证窗口:
- Username: `sprklestars`
- Password: [GitHub Personal Access Token](https://github.com/settings/tokens)

---

### 方案2: 使用GitHub CLI自动创建并推送

```bash
# 安装GitHub CLI (如果还没有)
winget install GitHub.cli

# 登录
gh auth login

# 自动创建仓库并推送
cd "D:\360MoveData\Users\张浩楠\Desktop\任务-杨"
gh repo create yanghao --private --source=. --remote=origin --push
```

---

### 方案3: 检查网络连接

#### 测试GitHub连接
```bash
# 测试HTTPS连接
curl -I https://github.com

# 或使用Git
git ls-remote https://github.com/sprklestars/yanghao.git
```

#### 如果使用代理
```bash
# 配置Git代理
git config --global http.proxy http://your-proxy:port
git config --global https.proxy http://your-proxy:port
```

---

### 方案4: 生成Personal Access Token

如果认证失败:

1. 访问: https://github.com/settings/tokens
2. 点击 **"Generate new token (classic)"**
3. Note: `OSINT Platform Push`
4. Expiration: 选择90天或更长
5. Select scopes:
   - ✅ **repo** (全选下面的子项)
   - ✅ **workflow** (如果需要CI/CD)
6. 点击 **"Generate token"**
7. **复制token**(只显示一次!)
8. 推送时使用token作为密码

---

## 🚀 推荐操作流程

### 第1步: 确认仓库存在
访问: https://github.com/sprklestars/yanghao

如果显示404,说明仓库不存在,需要先创建。

### 第2步: 创建仓库(如果需要)
- 方式A: 手动在网页创建 (https://github.com/new)
- 方式B: 使用 `gh repo create`

### 第3步: 推送代码
```bash
cd "D:\360MoveData\Users\张浩楠\Desktop\任务-杨"

# 查看状态
git status

# 应该显示: On branch master, nothing to commit

# 推送
git push -u origin master
```

### 第4步: 验证
访问: https://github.com/sprklestars/yanghao
应该能看到所有文件。

---

## 📊 准备推送的文件统计

```
66 files changed, 9688 insertions(+)

主要内容包括:
- backend/     (Python后端代码)
- frontend/    (Next.js前端应用)
- docs/        (7个文档文件)
- infra/       (Docker配置)
- scripts/     (启动脚本)
```

---

## ⚠️ 敏感信息检查

推送前确认这些文件**不会**被上传:

```bash
# 检查是否有.env文件
git ls-files | grep "\.env"
# 应该只显示 .env.example

# 检查sessions目录
git ls-files | grep "session"
# 应该没有输出
```

✅ 已确认 `.gitignore` 正确配置,敏感文件不会被推送。

---

## 🆘 仍然失败?

### 临时方案: 导出为ZIP上传

如果Git推送一直失败,可以:

1. 压缩项目文件夹
2. 在GitHub仓库页面
3. 点击 "Add file" → "Upload files"
4. 上传ZIP并解压

**注意**: 这种方式后续无法使用Git版本控制,仅作为备选。

---

## 📞 下一步

请告诉我:
1. GitHub仓库是否已创建?
2. 推送时的具体错误信息?
3. 是否需要我帮您生成Personal Access Token?

我会根据具体情况提供针对性帮助!
