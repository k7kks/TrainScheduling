# Git版本快速参考

## 📌 当前版本

**标签**：`v3_overtaking_20251013_102814`
**提交ID**：`ed2c768`
**时间**：2025-10-13 10:28:14

## 🚀 快速命令

### 查看当前版本

```bash
git log --oneline -1
git describe --tags
```

### 切换到此版本

```bash
git checkout v3_overtaking_20251013_102814
```

### 查看所有越行相关版本

```bash
git tag -l "v3_overtaking*"
```

### 查看此版本的详细信息

```bash
git show v3_overtaking_20251013_102814
```

## ✅ 版本特性

- ✅ 快车越行慢车功能完全集成
- ✅ 站台码100%正确（64个车次，0个错误）
- ✅ 25次越行事件全部生效
- ✅ 越行站停站时间270-300秒

## 📁 快速运行

```bash
python express_local_V3/scripts/run.py
```

**输出**：`data/output_data/results_express_local_v3/result.xlsx`

## 📚 文档

- **快速开始**：`express_local_V3/README_越行功能.md`
- **版本详情**：`express_local_V3/GIT_VERSION_20251013_102814.md`
- **验证报告**：`express_local_V3/FINAL_VERIFICATION.md`

---

**当前版本已保存到Git，可随时恢复！**

