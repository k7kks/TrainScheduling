# Express Local V3 文件夹结构说明

**最后更新**：2025-10-12

---

## 📁 整理后的目录结构

```
express_local_V3/
│
├── 📄 核心文件
│   ├── README.md                          # 项目概述、安装说明 ⭐
│   ├── main.py                            # 主程序入口
│   ├── requirements.txt                   # Python依赖包列表
│   ├── __init__.py                        # 包初始化文件
│   ├── QUICK_REFERENCE.md                 # 快速参考手册
│   └── VERSION_HISTORY.md                 # 版本历史记录
│
├── 📚 docs/ - 文档目录
│   │
│   ├── 📄 主要文档
│   │   ├── INDEX.md                       # 文档总索引 ⭐
│   │   ├── QUICKSTART.md                  # 快速入门指南
│   │   ├── EXPRESS_LOCAL_MODEL_DESIGN.md  # 系统架构与算法设计 ⭐
│   │   ├── PROJECT_SUMMARY.md             # 项目总结
│   │   ├── CHANGELOG.md                   # 详细变更日志
│   │   └── UPDATE_NOTES.md                # 更新说明
│   │
│   ├── 🔧 fixes/ - 修复文档目录（重要）
│   │   ├── FIXES_INDEX.md                 # 修复文档总索引 ⭐
│   │   ├── PATH_BASED_GENERATION_FIX.md   # 基于路径生成的架构修复 ⭐⭐⭐
│   │   ├── EXPRESS_SKIP_FIX.md            # 快车跳站功能修复 ⭐⭐⭐
│   │   ├── DESTCODE_PATH_FIX.md           # 站台码与Path一致性修复 ⭐⭐
│   │   ├── PLATFORM_COUNT_FIX.md          # 站台数量匹配修复 ⭐⭐
│   │   ├── ROUTE_NUM_FIX_SUMMARY.md       # 路径编号修复 ⭐⭐
│   │   ├── DESTCODE_FIX_SUMMARY.md        # 站台目的地码修复 ⭐
│   │   └── FIXES_VALIDATION_REPORT.md     # 修复验证报告
│   │
│   └── 📝 其他文档
│       ├── INTEGRATION_SUMMARY.md         # 集成测试总结
│       ├── SUCCESS_SUMMARY.md             # 成功案例总结
│       ├── PROGRESS_SUMMARY.md            # 开发进度总结
│       ├── REORGANIZATION_SUMMARY.md      # 项目重组说明
│       ├── CRITICAL_FIX_OPTIMIZER_INTEGRATION.md
│       ├── EXPRESS_DESTCODE_FIX_V2.md     # （已归档）
│       ├── EXPRESS_SKIP_STOP_SUMMARY.md   # （已归档）
│       ├── FIXES_SUMMARY.md               # （已归档）
│       └── HOTFIX_SCRIPTS_PATH.md         # （已归档）
│
├── 🧮 algorithms/ - 算法模块
│   ├── __init__.py
│   ├── express_local_generator.py         # 快慢车生成器
│   ├── timetable_builder.py               # 时刻表构建器
│   ├── overtaking_detector.py             # 越行检测器
│   └── headway_optimizer.py               # 发车间隔优化器
│
├── 📊 models/ - 数据模型
│   ├── __init__.py
│   ├── train.py                           # 列车模型（Train, ExpressTrain, LocalTrain）
│   ├── timetable_entry.py                 # 时刻表条目
│   ├── express_local_timetable.py         # 快慢车时刻表
│   └── overtaking_event.py                # 越行事件
│
├── 📤 output/ - 输出模块
│   ├── __init__.py
│   └── excel_exporter.py                  # Excel导出器
│
├── 💡 examples/ - 示例代码
│   ├── __init__.py
│   └── example_usage.py                   # 使用示例
│
├── 🧪 tests/ - 测试代码
│   ├── __init__.py
│   ├── README.md                          # 测试说明
│   ├── test_imports.py                    # 导入测试
│   ├── test_read_data.py                  # 数据读取测试
│   └── test_simple.py                     # 简单功能测试
│
└── 🛠️ scripts/ - 工具脚本
    ├── __init__.py
    ├── README.md                          # 脚本说明
    ├── run.py                             # 运行脚本
    └── check_output.py                    # 输出检查脚本
```

---

## 🎯 整理原则

### 1. 文档集中管理
- **所有文档**统一放在 `docs/` 目录
- **修复文档**集中放在 `docs/fixes/` 子目录
- 创建清晰的索引文件：`docs/INDEX.md` 和 `docs/fixes/FIXES_INDEX.md`

### 2. 代码模块化
- `algorithms/` - 算法实现
- `models/` - 数据结构
- `output/` - 输出功能
- 每个模块都是独立的Python包

### 3. 辅助资源分类
- `examples/` - 示例代码
- `tests/` - 测试代码
- `scripts/` - 工具脚本

### 4. 根目录简洁
- 只保留最核心的文件
- README、main.py、requirements.txt
- 简单的参考文档（QUICK_REFERENCE、VERSION_HISTORY）

---

## 📖 文档层次

### 第1层：入口文档（根目录）
```
README.md                  # 项目入口 ⭐
QUICK_REFERENCE.md         # 速查手册
VERSION_HISTORY.md         # 版本历史
```

### 第2层：主要文档（docs/）
```
docs/INDEX.md              # 文档索引 ⭐
docs/QUICKSTART.md         # 快速入门
docs/EXPRESS_LOCAL_MODEL_DESIGN.md  # 设计文档 ⭐
docs/PROJECT_SUMMARY.md    # 项目总结
```

### 第3层：专题文档（docs/fixes/）
```
docs/fixes/FIXES_INDEX.md  # 修复索引 ⭐
docs/fixes/*.md            # 各个修复的详细文档
```

---

## 🗑️ 已删除内容

整理过程中已删除或移动：
- ✅ `test_output.txt` - 临时测试文件（已删除）
- ✅ 根目录散落的修复MD文档（已移到docs/fixes/）
- ✅ `__pycache__/` 目录保留（Python自动生成）

---

## 🔗 重要索引文件

### 1. [README.md](README.md)
- **位置**：根目录
- **用途**：项目第一入口
- **内容**：项目介绍、安装、快速开始

### 2. [docs/INDEX.md](docs/INDEX.md)
- **位置**：docs/
- **用途**：所有文档的总索引
- **内容**：文档分类、推荐阅读路径

### 3. [docs/fixes/FIXES_INDEX.md](docs/fixes/FIXES_INDEX.md)
- **位置**：docs/fixes/
- **用途**：所有修复文档的索引
- **内容**：修复时间线、核心原则、阅读建议

---

## 📌 使用建议

### 新用户
1. 从 [README.md](README.md) 开始
2. 查看 [docs/QUICKSTART.md](docs/QUICKSTART.md)
3. 运行 [examples/example_usage.py](examples/example_usage.py)

### 开发者
1. 阅读 [docs/EXPRESS_LOCAL_MODEL_DESIGN.md](docs/EXPRESS_LOCAL_MODEL_DESIGN.md)
2. 查看 [docs/fixes/FIXES_INDEX.md](docs/fixes/FIXES_INDEX.md)
3. 浏览源代码：algorithms/, models/, output/

### 问题排查
1. 查看 [docs/fixes/FIXES_INDEX.md](docs/fixes/FIXES_INDEX.md)
2. 根据问题类型找到对应的修复文档
3. 参考修复方案解决问题

---

## 🔄 维护记录

| 日期 | 操作 | 说明 |
|------|------|------|
| 2025-10-12 | 文件夹重组 | 创建docs/fixes/，移动所有修复文档 |
| 2025-10-12 | 创建索引 | 创建INDEX.md和FIXES_INDEX.md |
| 2025-10-12 | 清理临时文件 | 删除test_output.txt |

---

## 📞 说明

如果您对文件夹结构有疑问或建议，请参考：
- [docs/INDEX.md](docs/INDEX.md) - 完整文档索引
- [docs/fixes/FIXES_INDEX.md](docs/fixes/FIXES_INDEX.md) - 修复文档索引

**维护者**：AI Assistant (Claude Sonnet 4.5)

