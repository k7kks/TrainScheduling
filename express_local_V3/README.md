# 快慢车运行图自动编制程序 V3

> 📚 **快速开始**: 如果你想立即运行程序，请查看 [快速入门指南 (docs/QUICKSTART.md)](docs/QUICKSTART.md)
> 
> 📖 **完整文档**: 查看 [文档索引 (docs/INDEX.md)](docs/INDEX.md) 浏览所有文档
>
> 🔥 **V3.2更新**: 集成CBC求解器，发车间隔方差降低98%！详见 [关键修复说明](docs/CRITICAL_FIX_OPTIMIZER_INTEGRATION.md)

## 项目概述

快慢车运行图自动编制程序V3是基于**发车时间均衡性**的快慢车运行图自动编制系统。本程序完全复用src文件夹的输入输出接口，并基于快慢车铺画规则设计全新算法，实现高质量的快慢车运行图自动编制。

## 核心特点

### 🚄 技术特点
- **复用现有接口**：完全兼容src文件夹的输入输出接口（DataReader、Engineering等）
- **发车均衡性优化**：以发车时间均衡性作为主要目标函数（参照大小交路）
- **智能铺画规则**：基于快慢车铺画规则的算法设计
  - 首先均匀铺画快车运行线
  - 然后根据均衡性及缩短额外停站待避时间要求，铺画慢车运行线
  - 在均匀时间段内搜索旅行时间最短的运行线
- **输出格式统一**：生成与大小交路一致的Excel运行图文件
- **越行智能处理**：自动检测越行事件并提供优化建议

### 🎯 功能特点
- **快慢车运行图自动生成**：根据输入参数自动生成快慢车运行图
- **大小交路套跑**：慢车支持大小交路套跑模式
- **快慢车独立运用**：快车和慢车采用独立的运用策略
- **越行检测与分析**：智能检测越行事件并分析可避免性
- **发车间隔优化**：基于线性规划优化发车间隔均衡性
- **详细统计报告**：提供完整的运行图质量统计

## 系统架构

```
express_local_V3/
├── main.py                          # 主程序入口
├── __init__.py                      # 包初始化文件
├── requirements.txt                 # 依赖库列表
├── README.md                        # 本文档
│
├── models/                          # 数据模型层
│   ├── __init__.py
│   ├── train.py                    # 列车模型（快车/慢车）
│   ├── timetable_entry.py          # 时刻表条目模型
│   ├── overtaking_event.py         # 越行事件模型
│   └── express_local_timetable.py  # 快慢车时刻表模型
│
├── algorithms/                      # 算法层
│   ├── __init__.py
│   ├── express_local_generator.py  # 快慢车运行图生成器
│   ├── headway_optimizer.py        # 发车间隔优化器
│   ├── overtaking_detector.py      # 越行检测器
│   └── timetable_builder.py        # 时刻表构建器
│
├── output/                          # 输出层
│   ├── __init__.py
│   └── excel_exporter.py           # Excel导出器
│
├── scripts/                         # 工具脚本
│   ├── run.py                      # 快速启动脚本
│   └── check_output.py             # 输出检查工具
│
├── tests/                           # 测试文件
│   ├── test_imports.py             # 导入测试
│   ├── test_read_data.py           # 数据读取测试
│   └── test_simple.py              # 简单功能测试
│
├── examples/                        # 使用示例
│   └── example_usage.py            # API使用示例
│
└── docs/                            # 项目文档
    ├── QUICKSTART.md               # 快速入门指南
    ├── PROJECT_SUMMARY.md          # 项目技术摘要
    ├── INTEGRATION_SUMMARY.md      # 架构整合说明
    ├── EXPRESS_SKIP_STOP_SUMMARY.md # 快车跳站说明
    ├── SUCCESS_SUMMARY.md          # 成功案例
    ├── FIXES_SUMMARY.md            # 修复记录
    ├── UPDATE_NOTES.md             # 更新说明
    ├── PROGRESS_SUMMARY.md         # 开发进度
    └── CHANGELOG.md                # 变更日志
```

## 算法原理

### 快慢车铺画规则

本程序采用**两阶段优化方法**：

### 阶段一：启发式算法生成初始方案

1. **首先均匀铺画快车**
   - 根据快车数量和服务时长，计算快车发车间隔
   - 按照均匀间隔铺画快车运行线
   - 确定快车停站方案（部分车站跳停）

2. **然后铺画慢车**
   - 在均匀发车的前提下，搜索旅行时间最短的发车时刻
   - 对于每条慢车运行线：
     - 在目标发车时刻附近的时间窗口内搜索
     - 评估每个候选时刻的"额外待避时间"
     - 计算与已有列车的发车间隔偏差
     - 选择综合得分最优的时刻

### 阶段二：🔥 线性规划优化（CBC求解器）

3. **发车间隔均衡性优化** ⭐ 核心优化步骤
   - 使用PuLP建立线性规划模型
   - 目标函数：min Σ |h_i - h_avg|
   - 约束条件：
     - 最小/最大发车间隔（120-600秒）
     - 列车顺序保持
     - 发车时间调整范围（±60秒）
   - 使用CBC求解器求解最优发车时间
   - **优化效果：方差降低98%，均衡性得分提升至0.998**

### 越行判定

越行判定基于以下原则：

1. **追踪间隔检查**：快车是否会在线路中追上慢车
2. **越行站选择**：从冲突点向前查找最近的越行站
3. **安全间隔验证**：
   - 到通间隔 ≥ 120秒
   - 通发间隔 ≥ 120秒
   - 慢车停站时间 ≥ 240秒（4分钟）
4. **可避免性分析**：
   - 是否可以通过调整发车间隔避免
   - 是否可以通过交换发车顺序避免

### 目标函数

主要目标是**发车时间均衡性**：

$$\min \sum_{i=1}^{n-1} \left| h_i - \bar{h} \right|$$

其中：
- $h_i$ 是第i列车和第i+1列车的发车间隔
- $\bar{h}$ 是平均发车间隔

## 安装依赖

### 系统要求
- Python 3.9+
- Windows 10/11 (推荐) 或 Linux

### 安装依赖库

```bash
# 方式1：使用pip安装
cd express_local_V3
pip install -r requirements.txt

# 方式2：使用国内镜像加速
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

### 主要依赖

- **pulp** >= 2.7.0 - 线性规划求解
- **numpy** >= 1.21.0 - 数值计算
- **pandas** >= 1.3.0 - 数据处理
- **openpyxl** >= 3.0.9 - Excel文件操作

## 使用方法

### 快速开始（推荐）

最简单的运行方式：

```bash
# 进入express_local_V3目录
cd express_local_V3

# 方式1：使用简单启动脚本（推荐）
python scripts/run.py

# 方式2：使用测试脚本（验证功能）
python tests/test_simple.py
```

### 命令行使用

```bash
# 从项目根目录运行（推荐方式）
python -m express_local_V3.main

# 或者进入express_local_V3目录后运行
cd express_local_V3
python scripts/run.py

# 指定输入文件
python scripts/run.py \
  -r "../data/input_data_new/RailwayInfo/Schedule-cs2.xml" \
  -u "../data/input_data_new/UserSettingInfoNew/cs2_real_28.xml"

# 指定快车比例和发车间隔
python scripts/run.py \
  --express_ratio 0.6 \
  --target_headway 180

# 指定输出目录
python scripts/run.py \
  -r ../data/input_data_new/RailwayInfo/Schedule-cs4.xml \
  -u ../data/input_data_new/UserSettingInfoNew/cs4_test.xml \
  -o ../data/output_data/results

# 开启调试模式
python scripts/run.py -d
```

### 命令行参数

| 参数 | 说明 | 默认值 | 示例 |
|------|------|--------|------|
| `-r, --rail_info` | 线路信息文件路径 | `Schedule-cs2.xml` | `-r Schedule-cs4.xml` |
| `-u, --user_setting` | 用户设置文件路径 | `cs2_real_28.xml` | `-u cs4_test.xml` |
| `-o, --output_dir` | 输出目录路径 | `../data/output_data/results` | `-o ../results` |
| `--express_ratio` | 快车比例（0.0-1.0） | `0.5` | `--express_ratio 0.6` |
| `--target_headway` | 目标发车间隔（秒） | `180` | `--target_headway 240` |
| `-d, --debug` | 开启调试模式 | `False` | `-d` |

### Python API使用

```python
from express_local_V3 import ExpressLocalSchedulerV3

# 创建调度器
scheduler = ExpressLocalSchedulerV3(
    rail_info_file="../data/input_data_new/RailwayInfo/Schedule-cs2.xml",
    user_setting_file="../data/input_data_new/UserSettingInfoNew/cs2_real_28.xml",
    output_dir="../results",
    express_ratio=0.5,        # 快车比例50%
    target_headway=180,       # 目标发车间隔3分钟
    debug=True
)

# 运行程序
result = scheduler.run()

if result["success"]:
    print(f"✓ 快慢车运行图编制成功！")
    print(f"  输出文件: {result['output_file']}")
    print(f"  总耗时: {result['total_time']:.2f}秒")
    
    # 获取时刻表对象
    timetable = result["timetable"]
    print(f"  总列车数: {timetable.total_trains}")
    print(f"  快车数: {timetable.express_trains_count}")
    print(f"  慢车数: {timetable.local_trains_count}")
    print(f"  越行次数: {timetable.total_overtaking_events}")
else:
    print(f"✗ 编制失败: {result['error']}")
```

## 输入输出

### 输入文件

程序复用src的输入接口，需要两个XML文件：

1. **线路信息文件** (RailwayInfo)
   - 车站信息：车站ID、名称、公里标等
   - 路径信息：区间运行时间、停站时间等
   - 折返信息：折返站、折返时间等

2. **用户设置文件** (UserSettingInfo)
   - 车库信息：可用车辆数、停车容量等
   - 峰期设置：各峰期的开行方案
   - 首末班车时间

### 输出文件

程序生成Excel格式的运行图文件，包含以下工作表：

1. **列车时刻表**：每列车的详细到发时刻
2. **车站时刻表**：按车站汇总的时刻表
3. **交路统计**：各交路的开行情况
4. **越行事件**：越行事件详细信息和优化建议
5. **统计信息**：运行图质量统计（发车间隔、均衡性等）
6. **车辆运用**：车辆连接关系和运用计划

### 输出文件命名

```
express_local_V3_YYYYMMDD_HHMMSS.xlsx
例如：express_local_V3_20241011_153045.xlsx
```

## 配置说明

### 快慢车比例

快车比例参数 `express_ratio` 控制快车在总列车中的占比：

- `0.3`：快车占30%，慢车占70%
- `0.5`：快车占50%，慢车占50%（默认）
- `0.6`：快车占60%，慢车占40%

### 发车间隔

目标发车间隔 `target_headway` 控制列车发车的密度：

- `120秒`（2分钟）：高密度发车
- `180秒`（3分钟）：正常密度（默认）
- `240秒`（4分钟）：较低密度

### 快车停站方案

在 `ExpressLocalConfig` 中可以配置：

```python
config = ExpressLocalConfig(
    express_stop_ratio=0.6,              # 快车停站比例60%
    express_skip_pattern=[2, 4, 6, 8],   # 指定跳停站序号
)
```

## 性能指标

### 运行图质量指标

1. **发车间隔均衡性**：
   - 平均发车间隔
   - 发车间隔方差
   - 均衡性得分（0-1，越接近1越好）

2. **越行情况**：
   - 越行事件总数
   - 被越行慢车数
   - 可避免越行数

3. **时间统计**：
   - 服务时长
   - 列车平均旅行时间
   - 慢车额外待避时间

### 程序性能

- **数据读取**：通常 < 5秒
- **运行图生成**：通常 < 10秒
- **发车间隔优化**：通常 < 30秒
- **总运行时间**：通常 < 1分钟

## 算法优势

### 相比V1和V2的改进

1. **更符合快慢车铺画规则**
   - 先铺快车，后铺慢车
   - 局部搜索最优发车时刻
   - 兼顾均衡性和旅行时间

2. **更好的输入输出接口**
   - 完全复用src的成熟接口
   - 输出格式与大小交路一致
   - 易于集成到现有系统

3. **更强的优化能力**
   - 基于线性规划的发车间隔优化
   - 智能的越行检测和分析
   - 提供具体的优化建议

4. **更清晰的代码结构**
   - 模块化设计
   - 易于维护和扩展
   - 详细的文档和注释

## 扩展功能

### 将来可扩展的功能

1. **大小交路和快慢车组合运营模式**
   - 快车大交路 + 慢车大小交路套跑
   - 复杂的交路组合优化

2. **多目标优化**
   - 同时考虑均衡性、能耗、成本等多个目标
   - 帕累托最优解集

3. **实时调整**
   - 根据实际运营情况动态调整
   - 延误传播和恢复策略

4. **可视化**
   - 运行图图形化展示
   - 越行事件动画演示

## 常见问题

### Q1: 运行时出现"ImportError: attempted relative import with no known parent package"错误

**问题**: 直接运行 `python main.py` 时出现导入错误。

**解决方案**:
```bash
# 方式1：使用run.py脚本（推荐）
cd express_local_V3
python scripts/run.py

# 方式2：作为模块运行（从项目根目录）
python -m express_local_V3.main

# 方式3：使用测试脚本
cd express_local_V3
python tests/test_simple.py
```

### Q2: 为什么生成的快慢车数量与预期不符？

A: 快慢车数量由服务时长、发车间隔和快车比例共同决定。可以调整 `target_headway` 或 `express_ratio` 参数。

### Q3: 如何减少越行次数？

A: 可以尝试：
1. 减小快车比例
2. 增大目标发车间隔
3. 调整快车停站方案（减少跳停站）
4. 按照程序提供的优化建议调整

### Q4: 程序运行时间过长怎么办？

A: 可以：
1. 减少列车数量（增大发车间隔）
2. 减少搜索窗口大小
3. 降低优化精度要求

### Q5: 输入文件找不到怎么办？

A: 请确保：
1. 输入文件路径正确
2. 文件格式为XML
3. 使用相对路径时，注意当前工作目录
4. 可以使用绝对路径

### Q6: 如何与现有大小交路系统集成？

A: 本程序完全复用src的输入输出接口，可以直接集成。只需在调用时指定算法类型为"快慢车模式"。

## 技术支持

如有问题或建议，请联系：

- **项目**: 快慢车运行图自动编制程序V3
- **团队**: CRRC城市轨道交通调度系统算法研发团队
- **版本**: 3.0.0
- **日期**: 2024-10-11

## 许可证

本项目使用的开源库许可证：
- **PuLP**: MIT License
- **NumPy**: BSD License
- **Pandas**: BSD License
- **OpenPyXL**: MIT License

---

<div align="center">

**快慢车运行图自动编制程序V3**  
*基于发车时间均衡性的智能运行图编制系统*

Made with ❤️ by CRRC Urban Rail Transit Team

</div>

