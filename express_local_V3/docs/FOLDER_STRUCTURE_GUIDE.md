# express_local_V3 项目文件夹结构说明

> 📅 最后更新：2025-10-13  
> 📝 版本：v1.0

## 📂 项目结构概览

```
express_local_V3/
├── 📁 algorithms/          核心算法实现
├── 📁 models/              数据模型定义
├── 📁 output/              输出模块
├── 📁 scripts/             工具和验证脚本
├── 📁 tests/               单元测试
├── 📁 examples/            示例和演示
├── 📁 docs/                📚 文档中心（你在这里）
├── 📁 logs/                📋 日志文件
├── 📁 data/                数据文件
├── 📄 main.py              主程序入口
├── 📄 requirements.txt     依赖包列表
├── 📄 __init__.py          包初始化
└── 📄 README.md            项目主文档
```

## 📖 详细说明

### 1️⃣ algorithms/ - 核心算法实现

存放项目的核心算法模块：

| 文件 | 说明 | 核心功能 |
|------|------|----------|
| `timetable_builder.py` | 时刻表构建器 | 四阶段优化模型主逻辑 |
| `express_local_generator.py` | 大小交路生成器 | 生成混合交路方案 |
| `headway_optimizer.py` | 发车间隔优化器 | 优化列车发车间隔 |
| `connection_manager.py` | 连接管理器 | 管理大小交路连接 |
| `overtaking_detector.py` | 越行检测器 | 检测和优化越行事件 |

**何时修改：**
- 优化算法性能
- 新增约束条件
- 修复算法 bug
- 实现新的优化策略

### 2️⃣ models/ - 数据模型定义

定义项目中使用的数据结构：

| 文件 | 说明 | 主要类 |
|------|------|--------|
| `train.py` | 列车模型 | `Train` |
| `timetable_entry.py` | 时刻表条目 | `TimetableEntry` |
| `express_local_timetable.py` | 大小交路时刻表 | `ExpressLocalTimetable` |
| `overtaking_event.py` | 越行事件 | `OvertakingEvent` |

**何时修改：**
- 添加新的数据字段
- 修改数据结构
- 添加数据验证逻辑

### 3️⃣ output/ - 输出模块

处理结果输出和格式化：

| 文件 | 说明 |
|------|------|
| `excel_exporter.py` | Excel 导出器，生成结果文件 |

**何时修改：**
- 修改输出格式
- 新增输出类型
- 修复导出 bug

### 4️⃣ scripts/ - 工具和验证脚本

存放各种工具脚本、验证脚本和调试脚本：

#### 分类说明

**运行脚本：**
- `run.py` - 主运行脚本

**验证脚本 (verify_\*.py)：**
- `verify_platform_codes.py` - 验证站台码
- `verify_all_paths.py` - 验证所有路径
- `verify_overtaking_timing_excel.py` - 验证越行时间

**检查脚本 (check_\*.py)：**
- `check_overtaking_timing.py` - 检查越行时序
- `check_train_*.py` - 检查特定列车
- `check_output.py` - 检查输出结果

**调试脚本 (debug_\*.py)：**
- `debug_connection.py` - 调试连接问题
- `debug_route_solution.py` - 调试路径求解

**分析脚本 (analyze_\*.py)：**
- `analyze_excel_structure.py` - 分析 Excel 结构
- `analyze_times.py` - 分析时间数据

**其他：**
- `complete_verification.py` - 完整验证流程
- `find_station_platforms.py` - 查找车站站台
- `test_overtaking_simple.py` - 简单越行测试

**何时使用：**
- 验证算法结果 → 使用 `verify_*.py`
- 检查数据问题 → 使用 `check_*.py`
- 调试特定问题 → 使用 `debug_*.py`
- 分析数据 → 使用 `analyze_*.py`

### 5️⃣ tests/ - 单元测试

存放单元测试和集成测试：

| 文件 | 说明 |
|------|------|
| `test_imports.py` | 测试模块导入 |
| `test_read_data.py` | 测试数据读取 |
| `test_simple.py` | 简单功能测试 |

**何时修改：**
- 添加新功能时编写对应测试
- 修复 bug 后添加回归测试
- 优化测试覆盖率

### 6️⃣ examples/ - 示例和演示

提供使用示例和功能演示：

| 文件 | 说明 |
|------|------|
| `example_usage.py` | 基础使用示例 |
| `overtaking_demo.py` | 越行功能演示 |
| `visualize_overtaking.py` | 越行可视化 |
| `*.md` | 示例说明文档 |

**何时使用：**
- 学习如何使用系统
- 演示特定功能
- 快速原型验证

### 7️⃣ docs/ - 📚 文档中心

**这是你现在所在的位置！**

所有项目文档集中存放在这里，包括：

#### 📘 核心文档
- `README_START_HERE.md` - 快速入门（推荐首先阅读）
- `使用指南_最终版.md` - 详细使用指南
- `PROJECT_COMPLETE_SUMMARY.md` - 项目完整总结
- `交付清单.md` - 项目交付清单

#### 📗 版本文档
- `VERSION_INFO.md` - 版本详细信息
- `最终版本说明.md` - 最终版本说明
- `GIT_VERSION_SUMMARY.md` - Git 版本管理总结
- `版本对比_优化前后.md` - 版本对比分析

#### 📙 功能文档
- `使用说明_越行功能.md` - 越行功能使用说明
- `越行功能验证报告.md` - 越行功能验证
- `越行功能集成完成报告.md` - 越行集成报告
- `越行优化说明_20251013.md` - 越行优化详解
- `越行时间验证.md` - 越行时间验证
- `如何在运行图中查看越行.md` - 越行查看指南

#### 📕 技术文档
- `站台码问题修复报告.md` - 站台码修复
- `运行图显示问题排查指南.md` - 问题排查
- `最终修复完成总结.md` - 修复总结
- `FINAL_VERIFICATION.md` - 最终验证报告

#### 📂 fixes/ - 问题修复文档
详细记录各类问题的修复过程：
- `FIXES_INDEX.md` - 修复索引
- `CONNECTION_*.md` - 连接相关修复
- `DESTCODE_*.md` - 目的地代码修复
- `PLATFORM_*.md` - 站台相关修复
- `ROUTE_*.md` - 路径相关修复

#### 📄 其他文档
- `FOLDER_STRUCTURE_GUIDE.md` - 本文档
- `INDEX.md` - 文档索引
- `QUICKSTART.md` - 快速开始
- `CHANGELOG.md` - 变更日志

**文档命名规范：**
- 所有 `.md` 文档都应该在这里
- 根目录只保留 `README.md`
- 子文件夹可以有自己的 `README.md`

### 8️⃣ logs/ - 📋 日志文件

存放所有运行、调试和测试产生的日志文件：

#### 日志分类

**调试日志 (debug_\*.log)：**
- `debug_281.log` - 281 车站调试
- `debug_dest_match.log` - 目的地匹配调试
- `debug_overtaking.log` - 越行调试

**检查日志 (check_\*.log)：**
- `check_filter.log` - 过滤检查
- `check_renumb.log` - 重编号检查

**验证日志 (verify_\*.log)：**
- `verify_addstop.log` - 停站验证
- `verify_rs.log` - 路径验证

**测试日志 (test_\*.log)：**
- `test_debug.log` - 测试调试
- `test_final2.log` - 最终测试

**运行日志 (run_\*.log)：**
- `run_optimized.log` - 优化运行
- `run_lower_threshold.log` - 阈值调整运行

**最终日志 (final_\*.log)：**
- `final_run.log` - 最终运行
- `final_test.log` - 最终测试

**日志管理：**
- ✅ 所有 `.log` 文件都应该在这里
- ✅ 根目录不应有日志文件
- ⚠️ 定期清理过期日志
- 💡 重要日志建议备份

### 9️⃣ data/ - 数据文件

存放数据相关文件：

```
data/
└── output/
    ├── *.xlsx    # Excel 输出文件
    └── *.png     # 图表文件
```

**注意：** 输入数据通常在项目根目录的 `data/input_data/` 或 `data/input_data_new/`

### 🔟 根目录文件

#### 核心文件

**main.py** - 主程序入口
- 系统的主入口文件
- 集成所有核心功能
- 提供命令行接口

**requirements.txt** - 依赖包列表
```
pulp>=2.7.0
pandas>=1.5.0
numpy>=1.23.0
openpyxl>=3.0.0
```

**README.md** - 项目主文档
- 项目简介
- 安装说明
- 快速开始
- 基本用法

**__init__.py** - 包初始化
- 定义包的公共接口
- 版本信息

## 📋 文件组织规范

### ✅ 正确的做法

1. **新建文档** → 放入 `docs/` 对应子文件夹
2. **生成日志** → 输出到 `logs/` 文件夹
3. **新建脚本** → 根据功能放入 `scripts/`, `tests/`, 或 `examples/`
4. **算法代码** → 放入 `algorithms/` 或 `models/`
5. **输出数据** → 放入 `data/output/`

### ❌ 应该避免

1. ❌ 在根目录创建 `.md` 文档（除了 README.md）
2. ❌ 在根目录保留 `.log` 文件
3. ❌ 在根目录编写业务代码
4. ❌ 创建临时文件不清理
5. ❌ 混淆不同类型的文件

## 🔍 快速查找

### 我想要...

**学习如何使用系统**
→ `docs/README_START_HERE.md` 或 `docs/使用指南_最终版.md`

**了解越行功能**
→ `docs/使用说明_越行功能.md` 或 `examples/overtaking_demo.py`

**查看版本信息**
→ `docs/VERSION_INFO.md` 或 `docs/最终版本说明.md`

**运行系统**
→ `main.py` 或 `scripts/run.py`

**查看运行日志**
→ `logs/` 文件夹

**修改核心算法**
→ `algorithms/timetable_builder.py`

**添加新的数据模型**
→ `models/` 文件夹

**验证结果**
→ `scripts/verify_*.py` 或 `scripts/check_*.py`

**运行测试**
→ `tests/` 文件夹

**查看问题修复历史**
→ `docs/fixes/FIXES_INDEX.md`

## 🎯 最佳实践

1. **保持整洁**：定期清理临时文件和过期日志
2. **文档先行**：新功能开发前先更新文档
3. **测试同步**：新功能开发时同步编写测试
4. **日志记录**：重要操作记录详细日志
5. **版本管理**：重要修改及时提交并记录
6. **命名规范**：遵循既定的命名约定
7. **模块化**：保持文件职责单一，避免过度耦合

## 📞 需要帮助？

- 📖 查看 `docs/README_START_HERE.md` - 快速入门
- 📚 查看 `docs/INDEX.md` - 完整文档索引
- 🔧 查看 `scripts/README.md` - 脚本使用说明
- 🧪 查看 `tests/README.md` - 测试指南
- 💡 查看 `examples/` - 示例代码

## 📝 维护记录

| 日期 | 版本 | 修改说明 | 修改人 |
|------|------|----------|--------|
| 2025-10-13 | v1.0 | 创建文档，整理项目结构 | AI Assistant |

---

**记住：一个清晰的结构是项目成功的一半！** 🎯

