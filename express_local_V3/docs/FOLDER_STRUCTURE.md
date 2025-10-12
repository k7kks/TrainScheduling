# Express Local V3 - 文件夹结构说明

**更新日期**: 2025-10-12  
**版本**: V3.0

---

## 📁 项目结构总览

```
express_local_V3/
├── main.py                          # 主程序入口
├── requirements.txt                 # 依赖包列表
├── README.md                        # 项目说明
├── __init__.py                      # 包初始化文件
│
├── algorithms/                      # 核心算法模块
│   ├── __init__.py
│   ├── express_local_generator.py   # 快慢车生成器（优化算法）
│   ├── timetable_builder.py         # 时刻表构建器
│   ├── headway_optimizer.py         # 发车间隔优化器（线性规划）
│   ├── overtaking_detector.py       # 越行事件检测器
│   └── connection_manager.py        # 车次勾连管理器 🆕
│
├── models/                          # 数据模型
│   ├── __init__.py
│   ├── train.py                     # 列车模型（Train, ExpressTrain, LocalTrain）
│   ├── timetable_entry.py           # 时刻表条目
│   ├── express_local_timetable.py   # 快慢车时刻表
│   └── overtaking_event.py          # 越行事件
│
├── output/                          # 输出模块
│   ├── __init__.py
│   └── excel_exporter.py            # Excel导出器
│
├── scripts/                         # 实用脚本 🆕整理
│   ├── __init__.py
│   ├── README.md
│   ├── run.py                       # 运行脚本
│   ├── check_output.py              # 输出检查脚本
│   ├── check_connection.py          # 勾连检查脚本 🆕
│   ├── debug_connection.py          # 勾连调试脚本 🆕
│   └── analyze_times.py             # 时间分析脚本 🆕
│
├── examples/                        # 使用示例
│   ├── __init__.py
│   └── example_usage.py
│
├── tests/                           # 测试代码
│   ├── __init__.py
│   ├── README.md
│   ├── test_simple.py
│   ├── test_imports.py
│   └── test_read_data.py
│
└── docs/                            # 文档目录 🆕整理
    ├── INDEX.md                     # 文档总索引
    ├── QUICKSTART.md                # 快速开始指南
    ├── README.md                    # 文档说明
    │
    ├── fixes/                       # 修复文档子目录
    │   ├── FIXES_INDEX.md           # 修复索引
    │   ├── DESTCODE_FIX_SUMMARY.md
    │   ├── DESTCODE_PATH_FIX.md
    │   ├── ROUTE_NUM_FIX_SUMMARY.md
    │   ├── PLATFORM_COUNT_FIX.md
    │   ├── PATH_BASED_GENERATION_FIX.md
    │   ├── EXPRESS_SKIP_FIX.md
    │   ├── FIXES_VALIDATION_REPORT.md
    │   ├── CONNECTION_SUCCESS_REPORT.md          🆕
    │   └── CONNECTION_IMPLEMENTATION_SUMMARY.md  🆕
    │
    ├── EXPRESS_LOCAL_MODEL_DESIGN.md    # 模型设计文档
    ├── INTEGRATION_SUMMARY.md           # 集成总结
    ├── PROJECT_SUMMARY.md               # 项目总结
    ├── PROGRESS_SUMMARY.md              # 进度总结
    ├── SUCCESS_SUMMARY.md               # 成功总结
    ├── REORGANIZATION_SUMMARY.md        # 重组总结
    ├── UPDATE_NOTES.md                  # 更新说明
    ├── CHANGELOG.md                     # 变更日志
    ├── GIT_ROLLBACK_GUIDE.md            # Git回退指南 🆕
    ├── VERSION_SNAPSHOT.md              # 版本快照 🆕
    ├── VERSION_HISTORY.md               # 版本历史 🆕
    └── QUICK_REFERENCE.md               # 快速参考 🆕

```

---

## 📂 各目录详细说明

### 1. 根目录文件

| 文件 | 说明 | 重要性 |
|------|------|--------|
| `main.py` | 主程序入口，包含`ExpressLocalSchedulerV3`类 | ⭐⭐⭐⭐⭐ |
| `requirements.txt` | Python依赖包列表 | ⭐⭐⭐⭐ |
| `README.md` | 项目整体说明文档 | ⭐⭐⭐⭐⭐ |
| `__init__.py` | 包初始化文件 | ⭐⭐ |

### 2. algorithms/ - 核心算法模块

**功能**：实现快慢车运行图生成的核心算法。

| 文件 | 说明 | 算法 |
|------|------|------|
| `express_local_generator.py` | 快慢车生成器 | 优化算法 |
| `timetable_builder.py` | 时刻表构建器 | 到发时间计算 |
| `headway_optimizer.py` | 发车间隔优化器 | 线性规划（CBC） |
| `overtaking_detector.py` | 越行事件检测器 | 时间冲突检测 |
| `connection_manager.py` 🆕 | 车次勾连管理器 | 贪心算法+递归 |

**重要类**：
- `ExpressLocalGenerator`: 生成快慢车列表
- `TimetableBuilder`: 构建详细时刻表
- `HeadwayOptimizer`: 优化发车间隔
- `ConnectionManager`: 建立车次勾连

### 3. models/ - 数据模型

**功能**：定义数据结构和对象模型。

| 文件 | 说明 | 核心类 |
|------|------|--------|
| `train.py` | 列车模型 | `Train`, `ExpressTrain`, `LocalTrain` |
| `timetable_entry.py` | 时刻表条目 | `TimetableEntry` |
| `express_local_timetable.py` | 快慢车时刻表 | `ExpressLocalTimetable` |
| `overtaking_event.py` | 越行事件 | `OvertakingEvent` |

**关键属性**：
- `Train.skip_stations`: 快车跳过的站点集合
- `TimetableEntry.is_stop`: 是否停站
- `ExpressLocalTimetable.train_schedules`: 车次时刻表映射

### 4. output/ - 输出模块

**功能**：将结果导出为Excel文件。

| 文件 | 说明 | 输出格式 |
|------|------|----------|
| `excel_exporter.py` | Excel导出器 | 多Sheet Excel文件 |

**输出内容**：
- 列车时刻表
- 车站时刻表
- 交路统计
- 越行事件
- 统计信息

### 5. scripts/ - 实用脚本 🆕整理

**功能**：提供各种实用工具脚本。

| 文件 | 说明 | 用途 |
|------|------|------|
| `run.py` | 运行脚本 | 快速启动程序 |
| `check_output.py` | 输出检查 | 验证输出文件 |
| `check_connection.py` 🆕 | 勾连检查 | 验证车次勾连结果 |
| `debug_connection.py` 🆕 | 勾连调试 | 分析勾连问题 |
| `analyze_times.py` 🆕 | 时间分析 | 分析车次时间分布 |

**使用方法**：
```bash
cd express_local_V3

# 运行主程序
python scripts/run.py

# 检查勾连结果
python scripts/check_connection.py

# 调试勾连（需先运行main.py）
python scripts/debug_connection.py

# 分析时间数据
python scripts/analyze_times.py
```

### 6. examples/ - 使用示例

**功能**：提供使用示例代码。

| 文件 | 说明 |
|------|------|
| `example_usage.py` | 基本使用示例 |

### 7. tests/ - 测试代码

**功能**：单元测试和集成测试。

| 文件 | 说明 | 测试内容 |
|------|------|----------|
| `test_simple.py` | 简单测试 | 基本功能 |
| `test_imports.py` | 导入测试 | 模块导入 |
| `test_read_data.py` | 数据读取测试 | XML解析 |

### 8. docs/ - 文档目录 🆕整理

**功能**：存放所有项目文档。

#### 主文档

| 文件 | 说明 | 类型 |
|------|------|------|
| `INDEX.md` | 文档总索引 | 索引 |
| `QUICKSTART.md` | 快速开始 | 教程 |
| `EXPRESS_LOCAL_MODEL_DESIGN.md` | 模型设计 | 设计文档 |
| `INTEGRATION_SUMMARY.md` | 集成总结 | 总结 |
| `PROJECT_SUMMARY.md` | 项目总结 | 总结 |
| `GIT_ROLLBACK_GUIDE.md` 🆕 | Git回退指南 | 操作指南 |
| `VERSION_SNAPSHOT.md` 🆕 | 版本快照 | 版本记录 |
| `VERSION_HISTORY.md` 🆕 | 版本历史 | 版本记录 |
| `QUICK_REFERENCE.md` 🆕 | 快速参考 | 参考手册 |

#### fixes/ - 修复文档子目录

**功能**：存放所有bug修复和改进的文档。

| 文件 | 说明 | 状态 |
|------|------|------|
| `FIXES_INDEX.md` | 修复索引 | - |
| `DESTCODE_FIX_SUMMARY.md` | 站台码修复总结 | ✅ |
| `DESTCODE_PATH_FIX.md` | 站台码路径修复 | ✅ |
| `ROUTE_NUM_FIX_SUMMARY.md` | 路径编号修复 | ✅ |
| `PLATFORM_COUNT_FIX.md` | 站台数量修复 | ✅ |
| `PATH_BASED_GENERATION_FIX.md` | 基于路径生成修复 | ✅ |
| `EXPRESS_SKIP_FIX.md` | 快车跳站修复 | ✅ |
| `FIXES_VALIDATION_REPORT.md` | 验证报告 | ✅ |
| `CONNECTION_SUCCESS_REPORT.md` 🆕 | 勾连成功报告 | ✅ |
| `CONNECTION_IMPLEMENTATION_SUMMARY.md` 🆕 | 勾连实现总结 | ✅ |

---

## 🎯 文件查找指南

### 我想查看...

| 需求 | 查看文件 |
|------|----------|
| 快速开始使用 | `README.md` 或 `docs/QUICKSTART.md` |
| 了解项目架构 | `docs/EXPRESS_LOCAL_MODEL_DESIGN.md` |
| 查看所有修复 | `docs/fixes/FIXES_INDEX.md` |
| 了解勾连功能 | `docs/fixes/CONNECTION_SUCCESS_REPORT.md` |
| Git版本管理 | `docs/GIT_ROLLBACK_GUIDE.md` |
| 验证勾连结果 | `scripts/check_connection.py` |
| 调试勾连问题 | `scripts/debug_connection.py` |
| 查看版本信息 | `docs/VERSION_SNAPSHOT.md` |
| 快速参考API | `docs/QUICK_REFERENCE.md` |

### 我想修改...

| 需求 | 修改文件 |
|------|----------|
| 算法逻辑 | `algorithms/` 目录下的文件 |
| 数据结构 | `models/` 目录下的文件 |
| 输出格式 | `output/excel_exporter.py` |
| 勾连策略 | `algorithms/connection_manager.py` |
| 主流程 | `main.py` |

---

## 🆕 近期更新（2025-10-12）

### 新增功能

1. ✅ **车次勾连功能**
   - 新增 `algorithms/connection_manager.py`
   - 实现Phase2勾连算法
   - 递归分配表号

2. ✅ **脚本整理**
   - 移动调试脚本到 `scripts/`
   - 新增勾连验证工具

3. ✅ **文档整理**
   - 移动文档到 `docs/` 和 `docs/fixes/`
   - 更新索引文件
   - 新增勾连相关文档

### 文件移动

| 原位置 | 新位置 | 说明 |
|--------|--------|------|
| `check_connection.py` | `scripts/check_connection.py` | 勾连检查 |
| `debug_connection.py` | `scripts/debug_connection.py` | 勾连调试 |
| `analyze_times.py` | `scripts/analyze_times.py` | 时间分析 |
| `CONNECTION_SUCCESS_REPORT.md` | `docs/fixes/CONNECTION_SUCCESS_REPORT.md` | 成功报告 |
| `CONNECTION_IMPLEMENTATION_SUMMARY.md` | `docs/fixes/CONNECTION_IMPLEMENTATION_SUMMARY.md` | 实现总结 |
| `GIT_ROLLBACK_GUIDE.md` | `docs/GIT_ROLLBACK_GUIDE.md` | Git指南 |
| `VERSION_SNAPSHOT.md` | `docs/VERSION_SNAPSHOT.md` | 版本快照 |
| `VERSION_HISTORY.md` | `docs/VERSION_HISTORY.md` | 版本历史 |
| `QUICK_REFERENCE.md` | `docs/QUICK_REFERENCE.md` | 快速参考 |
| `FOLDER_STRUCTURE.md` | `docs/FOLDER_STRUCTURE.md` | 本文档 |

---

## 📊 目录统计

| 目录 | 文件数 | 主要内容 |
|------|--------|----------|
| 根目录 | 4 | 主程序和配置 |
| `algorithms/` | 5 | 核心算法 |
| `models/` | 4 | 数据模型 |
| `output/` | 1 | 输出模块 |
| `scripts/` | 5 | 实用脚本 |
| `examples/` | 1 | 使用示例 |
| `tests/` | 3 | 测试代码 |
| `docs/` | 11 | 主文档 |
| `docs/fixes/` | 10 | 修复文档 |
| **总计** | **44** | - |

---

## ✅ 维护建议

### 文件命名规范

1. **Python文件**：使用小写+下划线（snake_case）
   - 例：`connection_manager.py`

2. **Markdown文档**：使用大写+下划线（UPPER_SNAKE_CASE）
   - 例：`CONNECTION_SUCCESS_REPORT.md`

3. **目录名**：使用小写+下划线
   - 例：`algorithms/`, `docs/fixes/`

### 文件组织原则

1. **代码文件**：按功能分类到对应目录
2. **文档文件**：统一放到 `docs/` 目录
3. **脚本文件**：统一放到 `scripts/` 目录
4. **测试文件**：统一放到 `tests/` 目录

### 新增文件时

1. 确认文件类型和功能
2. 放到对应目录
3. 更新相关索引文档
4. 添加 `__init__.py`（如果是新目录）

---

**本文档最后更新**: 2025-10-12  
**维护者**: AI Assistant (Claude Sonnet 4.5)
