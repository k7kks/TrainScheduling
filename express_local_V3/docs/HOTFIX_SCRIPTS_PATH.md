# 热修复：脚本路径问题

**日期**: 2025-10-12  
**版本**: V3.1.1 (热修复)

## 问题描述

在目录重组后（V3.1），运行 `python scripts/run.py` 时出现以下错误：

```
C:\Users\HP\...\python.exe: can't open file '...\express_local_V3\scripts\main.py': [Errno 2] No such file or directory
```

**原因**: `scripts/run.py` 脚本错误地在 `scripts/` 目录下查找 `main.py`，但 `main.py` 实际在上一级目录（`express_local_V3/`）。

## 修复内容

### 修改文件
- ✅ `scripts/run.py`

### 修改前
```python
# 获取当前脚本所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
main_py = os.path.join(current_dir, "main.py")  # ❌ 错误：在scripts/下找main.py

# 构建命令
project_root = os.path.dirname(current_dir)
```

### 修改后
```python
# 获取当前脚本所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# main.py在上一级目录（express_local_V3根目录）
express_local_v3_dir = os.path.dirname(current_dir)
main_py = os.path.join(express_local_v3_dir, "main.py")  # ✅ 正确

# 数据文件在项目根目录（express_local_V3的上一级）
project_root = os.path.dirname(express_local_v3_dir)
```

## 路径层级说明

```
CRRC_URTS_AutoScheduler_20250929/        ← project_root (数据文件位置)
├── data/
│   ├── input_data_new/
│   └── output_data/
│
└── express_local_V3/                    ← express_local_v3_dir (main.py位置)
    ├── main.py                          ← 主程序
    ├── scripts/                         ← current_dir (run.py位置)
    │   └── run.py                       ← 启动脚本
    └── ...
```

## 验证测试

### 测试命令
```bash
cd express_local_V3
python scripts/run.py
```

### 测试结果
```
✅ 成功读取数据（24个车站，778条路径）
✅ 成功生成快慢车运行图（35辆快车 + 35辆慢车 = 70辆）
✅ 成功输出Excel文件
✅ 总耗时1.32秒
```

## 受影响的用户

如果您在重组后立即尝试运行程序，可能遇到此问题。请更新 `scripts/run.py` 文件。

## 解决方案

### 方案1：更新脚本（推荐）
拉取最新的 `scripts/run.py` 文件

### 方案2：使用模块运行
如果不想更新脚本，可以直接运行main.py：
```bash
python -m express_local_V3.main
```

### 方案3：直接运行main.py
```bash
cd express_local_V3
python main.py --rail_info ../data/input_data_new/RailwayInfo/Schedule-cs2.xml \
              --user_setting ../data/input_data_new/UserSettingInfoNew/cs2_real_28.xml
```

## 吸取的教训

1. **移动文件后需要更新路径引用**
2. **测试所有入口点**：重组后应该测试所有启动方式
3. **相对路径计算要小心**：需要明确理解目录层级关系

## 相关文档

- [重组总结](REORGANIZATION_SUMMARY.md)
- [快速入门](QUICKSTART.md)

---

**状态**: ✅ 已修复  
**影响范围**: 仅 `scripts/run.py`  
**修复时间**: 2025-10-12

