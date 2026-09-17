# GitHub 推送故障排除指南

## 当前状态

✅ Git仓库已初始化
✅ 本地提交已完成（2个commit，68个文件）
❌ 远程推送失败 - 网络连接问题

## 问题诊断

### 1. HTTPS方式失败
```
fatal: unable to access 'https://github.com/sprklestars/yanghao.git/': 
Failed to connect to github.com port 443 after 21156 ms
```
**原因**: 防火墙或网络代理阻止HTTPS连接

### 2. SSH方式失败
```
Host key verification failed.
fatal: Could not read from remote repository.
```
**原因**: SSH密钥未配置或GitHub仓库不存在

## 解决方案（按优先级排序）

### 方案1: 使用GitHub Desktop（推荐）

1. 下载并安装 [GitHub Desktop](https://desktop.github.com/)
2. 登录GitHub账号
3. 点击 "Add" → "Add Existing Repository"
4. 选择目录: `D:\360MoveData\Users\张浩楠\Desktop\任务-杨`
5. 点击 "Publish repository"
6. 设置仓库名称为 `yanghao`，描述可选
7. 保持Private/Public设置，点击 "Publish"

### 方案2: 在GitHub网页创建仓库后推送

#### Step 1: 创建GitHub仓库

1. 访问 https://github.com/new
2. Repository name: `yanghao`
3. Description: `OSINT Platform - Multi-platform intelligence gathering system`
4. **不要勾选** "Initialize this repository with a README"
5. 点击 "Create repository"

#### Step 2: 使用Personal Access Token推送

```bash
cd "D:\360MoveData\Users\张浩楠\Desktop\任务-杨"

# 如果还没有PAT，先创建：
# https://github.com/settings/tokens -> Generate new token (classic)
# 权限: repo (Full control of private repositories)

# 使用Token推送（替换YOUR_TOKEN）
git remote set-url origin https://YOUR_TOKEN@github.com/sprklestars/yanghao.git
git push -u origin master
```

### 方案3: 配置SSH密钥

```bash
# 1. 生成SSH密钥（如果没有）
ssh-keygen -t ed25519 -C "your_email@example.com"

# 2. 复制公钥内容
cat ~/.ssh/id_ed25519.pub
# 或 Windows: type %USERPROFILE%\.ssh\id_ed25519.pub

# 3. 添加到GitHub: https://github.com/settings/keys -> New SSH key

# 4. 测试连接
ssh -T git@github.com

# 5. 推送代码
cd "D:\360MoveData\Users\张浩楠\Desktop\任务-杨"
git push -u origin master
```

### 方案4: 使用代理（如果有）

```bash
# 设置Git代理（替换为你的代理地址和端口）
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890

# 然后重试推送
cd "D:\360MoveData\Users\张浩楠\Desktop\任务-杨"
git push -u origin master
```

## 验证推送成功

推送成功后，应该能看到：

```bash
Enumerating objects: 72, done.
Counting objects: 100% (72/72), done.
Delta compression using up to 8 threads.
Compressing objects: 100% (70/70), done.
Writing objects: 100% (72/72), 95.23 KiB | 1.59 MiB/s, done.
Total 72 (delta 8), reused 0 (delta 0), pack-reused 0
remote: Resolving deltas: 100% (8/8), done.
To https://github.com/sprklestars/yanghao.git
 * [new branch]      master -> master
branch 'master' set up to track 'origin/master'.
```

## 快速检查清单

- [ ] GitHub账号已登录
- [ ] 仓库 `sprklestars/yanghao` 已创建
- [ ] 有有效的认证方式（PAT / SSH密钥 / GitHub Desktop）
- [ ] 网络连接正常（能访问github.com）
- [ ] 防火墙/杀毒软件未阻止Git

## 备用方案：导出代码包

如果以上方法都无法解决，可以导出代码包手动上传：

```bash
# 创建压缩包
cd "D:\360MoveData\Users\张浩楠\Desktop\任务-杨"
tar -czf osint-platform-code.tar.gz --exclude='.git' .

# 然后在GitHub网页：
# 1. 创建新仓库
# 2. 点击 "uploading an existing file"
# 3. 上传压缩包
```

## 联系支持

如果问题依然存在，请提供：
1. `git remote -v` 的输出
2. `git status` 的输出
3. 是否能通过浏览器访问 https://github.com
4. 是否使用了公司网络或VPN
