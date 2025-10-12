# Git 版本管理指南

**项目**: Express Local V3  
**更新日期**: 2025-10-12

---

## 📋 版本命名规则

本项目使用**时间戳**作为版本后缀，便于追踪和回退。

### 标签命名格式

```
express_local_V3_<feature>_<timestamp>
```

**组成部分**：
- `express_local_V3`: 项目名称
- `<feature>`: 功能描述（可选）
- `<timestamp>`: 时间戳 `yyyyMMdd_HHmmss`

### 示例

```bash
express_local_V3_20251012_143022          # 基础版本
express_local_V3_connection_20251012_150830  # 勾连功能版本
express_local_V3_optimize_20251012_163045    # 优化版本
```

---

## 🚀 创建新版本

### 方法1：快速提交（使用时间戳）

```powershell
# 生成时间戳
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

# 添加更改
git add express_local_V3/

# 提交（带时间戳）
git commit -m "feat(express_local_V3): 功能描述 - $timestamp

- 详细变更1
- 详细变更2
- 详细变更3"

# 创建标签（带时间戳）
$tag = "express_local_V3_feature_$timestamp"
git tag -a $tag -m "版本描述 $timestamp"

echo "✅ 创建版本: $tag"
```

### 方法2：使用脚本自动化

创建 `save_version.ps1` 脚本：

```powershell
# save_version.ps1
param(
    [string]$feature = "update",
    [string]$message = "更新express_local_V3"
)

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$tag = "express_local_V3_${feature}_$timestamp"

Write-Host "正在保存版本: $tag" -ForegroundColor Green

# 添加更改
git add express_local_V3/

# 提交
git commit -m "feat(express_local_V3): $message - $timestamp"

# 创建标签
git tag -a $tag -m "$message - $timestamp"

Write-Host "✅ 版本已保存: $tag" -ForegroundColor Green
git log --oneline -1
```

**使用方法**：

```powershell
# 基本用法
.\save_version.ps1

# 指定功能名
.\save_version.ps1 -feature "connection" -message "完成勾连功能"

# 指定优化
.\save_version.ps1 -feature "optimize" -message "性能优化"
```

---

## 📜 查看版本历史

### 查看所有标签

```bash
# 列出所有标签
git tag -l

# 列出express_local相关标签
git tag -l "express_local*"

# 按时间排序（最新在前）
git tag -l "express_local*" | Sort-Object -Descending
```

### 查看标签详情

```bash
# 查看标签信息
git show express_local_V3_connection_20251012_150830

# 查看标签的提交信息
git log express_local_V3_connection_20251012_150830 -1
```

### 查看提交历史

```bash
# 查看最近10次提交
git log --oneline -10

# 查看express_local_V3相关提交
git log --oneline --grep="express_local_V3"

# 查看某个文件的修改历史
git log --oneline -- express_local_V3/main.py
```

---

## ⏮️ 回退到指定版本

### 查看旧版本（只读）

```bash
# 切换到指定标签（查看代码）
git checkout express_local_V3_connection_20251012_150830

# 查看完毕，回到最新版本
git checkout main
```

### 临时回退（可修改）

```bash
# 基于旧版本创建新分支
git checkout -b temp_branch express_local_V3_connection_20251012_150830

# 在新分支上工作...

# 回到主分支
git checkout main

# 删除临时分支（如果不需要）
git branch -D temp_branch
```

### 永久回退（慎用）

```bash
# ⚠️ 警告：会丢失新提交！

# 回退到指定标签
git reset --hard express_local_V3_connection_20251012_150830

# 查看状态
git log --oneline -5
```

---

## 🔍 版本对比

### 对比两个版本

```bash
# 对比两个标签
git diff express_local_V3_20251012_143022 express_local_V3_connection_20251012_150830

# 只看文件列表
git diff --name-only express_local_V3_20251012_143022 express_local_V3_connection_20251012_150830

# 对比统计
git diff --stat express_local_V3_20251012_143022 express_local_V3_connection_20251012_150830
```

### 对比当前版本与旧版本

```bash
# 对比当前代码与旧标签
git diff express_local_V3_connection_20251012_150830

# 查看特定文件的差异
git diff express_local_V3_connection_20251012_150830 -- express_local_V3/main.py
```

---

## 📊 版本管理最佳实践

### 1. 提交频率

- ✅ **每个功能完成后立即提交**
- ✅ **重大修复后立即提交**
- ✅ **文件整理后立即提交**
- ❌ 不要积累太多更改再提交

### 2. 提交信息格式

```
feat(express_local_V3): 简短描述 - 20251012_150830

详细描述：
- 具体变更1
- 具体变更2
- 具体变更3

影响范围：
- 文件1
- 文件2
```

### 3. 标签使用

- ✅ **稳定版本必须打标签**
- ✅ **标签名包含时间戳**
- ✅ **标签信息包含版本说明**
- ✅ **重要里程碑额外添加描述性标签**

### 4. 版本命名示例

```bash
# 功能开发
express_local_V3_connection_20251012_150830    # 勾连功能
express_local_V3_optimize_20251012_163045      # 优化功能
express_local_V3_phase3_20251012_170230        # Phase3实现

# 修复版本
express_local_V3_bugfix_20251012_181520        # Bug修复
express_local_V3_hotfix_20251012_192030        # 紧急修复

# 里程碑版本
express_local_V3_milestone_20251012_200000     # 里程碑
express_local_V3_release_20251012_210000       # 发布版本
```

---

## 🔄 常用工作流

### 日常开发流程

```powershell
# 1. 开始工作
cd express_local_V3

# 2. 修改代码...

# 3. 测试
python main.py
python scripts/check_connection.py

# 4. 保存版本
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
git add express_local_V3/
git commit -m "feat: 功能描述 - $timestamp"

# 5. 打标签（重要版本）
$tag = "express_local_V3_feature_$timestamp"
git tag -a $tag -m "版本说明 $timestamp"
```

### 紧急回退流程

```bash
# 1. 查看版本列表
git tag -l "express_local*" | Sort-Object -Descending

# 2. 查看版本详情
git show express_local_V3_connection_20251012_150830

# 3. 回退（临时）
git checkout express_local_V3_connection_20251012_150830

# 4. 验证...

# 5. 回到最新
git checkout main
```

---

## 📁 版本记录示例

### 当前项目版本记录

| 标签 | 时间 | 功能 | 状态 |
|------|------|------|------|
| `express_local_V3.0` | 2025-10-12 14:30 | 基础功能完成 | ✅ |
| `express_local_V3_connection_20251012_150830` | 2025-10-12 15:08 | 勾连功能完成 | ✅ |
| ... | ... | ... | ... |

---

## 💡 提示和技巧

### 1. 快速查找版本

```bash
# 查找包含特定功能的提交
git log --oneline --grep="connection"

# 查找某日期之后的提交
git log --since="2025-10-12" --oneline

# 查找某个作者的提交
git log --author="username" --oneline
```

### 2. 清理旧标签

```bash
# 删除本地标签
git tag -d express_local_V3_old_version

# 批量删除旧标签（示例）
git tag -l "express_local*20251011*" | ForEach-Object { git tag -d $_ }
```

### 3. 导出版本信息

```bash
# 导出标签列表
git tag -l "express_local*" > versions.txt

# 导出提交历史
git log --oneline > history.txt
```

---

## 🆘 常见问题

### Q1: 如何撤销最近的提交？

```bash
# 撤销提交但保留更改
git reset --soft HEAD~1

# 撤销提交和更改（危险！）
git reset --hard HEAD~1
```

### Q2: 如何修改最后的提交信息？

```bash
git commit --amend -m "新的提交信息"
```

### Q3: 如何查看某个版本的文件？

```bash
# 查看文件内容
git show express_local_V3_connection_20251012_150830:express_local_V3/main.py

# 提取文件到当前目录
git show express_local_V3_connection_20251012_150830:express_local_V3/main.py > main_old.py
```

---

## ✅ 快速参考

### 常用命令速查

```bash
# 查看状态
git status

# 查看提交历史
git log --oneline -10

# 查看所有标签
git tag -l "express_local*"

# 查看标签详情
git show <tag_name>

# 创建标签
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
git tag -a "express_local_V3_feature_$timestamp" -m "说明"

# 回退查看
git checkout <tag_name>

# 回到最新
git checkout main
```

---

**最后更新**: 2025-10-12  
**维护者**: AI Assistant (Claude Sonnet 4.5)

