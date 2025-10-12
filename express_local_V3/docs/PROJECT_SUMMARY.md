# 快慢车运行图自动编制程序V3 - 项目摘要

## 项目信息

- **项目名称**: 快慢车运行图自动编制程序V3
- **版本**: 3.0.0
- **创建日期**: 2024-10-11
- **开发团队**: CRRC城市轨道交通调度系统算法研发团队

## 设计目标

基于快慢车运行图编制方案初稿文档，重新设计一套快慢车运行图自动编制程序，具有以下特点：

1. **复用现有接口**: 完全兼容src文件夹的输入输出接口
2. **目标函数优化**: 以发车时间均衡性作为主要目标函数（参照大小交路）
3. **算法创新**: 基于快慢车铺画规则的全新算法设计
4. **输出统一**: 生成与大小交路一致的Excel输出格式

## 核心算法

### 1. 快慢车铺画规则

参考文档中的铺画技巧，实现了：

```
第一步：均匀铺画快车
├─ 根据服务时长和快车数量计算快车发车间隔
├─ 按照均匀间隔铺画快车运行线
└─ 确定快车停站方案（部分车站跳停）

第二步：铺画慢车（考虑均衡性和旅行时间）
├─ 在均匀发车的前提下搜索最优发车时刻
├─ 评估每个候选时刻的额外待避时间
├─ 计算与已有列车的发车间隔偏差
└─ 选择综合得分最优的时刻

第三步：发车间隔优化
└─ 使用线性规划模型优化发车间隔均衡性
```

### 2. 目标函数设计

主要目标：**发车时间均衡性**

$$\min \sum_{i=1}^{n-1} \left| h_i - \bar{h} \right|$$

其中：
- $h_i$ = 第i列车和第i+1列车的发车间隔
- $\bar{h}$ = 平均发车间隔

### 3. 越行判定逻辑

基于以下规则判定越行：

1. **追踪间隔检查**: 快车发车时间 > 慢车发车时间，且会在线路中追上
2. **越行站选择**: 从冲突点向前查找最近的具有越行条件的车站
3. **安全间隔验证**:
   - 到通间隔 ≥ 120秒
   - 通发间隔 ≥ 120秒
   - 慢车停站时间 ≥ 240秒
4. **可避免性分析**: 分析是否可以通过调整间隔或交换顺序避免

## 技术架构

### 模块设计

```
express_local_V3/
│
├── models/ (数据模型层)
│   ├── train.py                    # 列车模型
│   │   ├── Train (基类)
│   │   ├── ExpressTrain (快车)
│   │   └── LocalTrain (慢车)
│   │
│   ├── timetable_entry.py          # 时刻表条目
│   ├── overtaking_event.py         # 越行事件
│   └── express_local_timetable.py  # 完整时刻表
│
├── algorithms/ (算法层)
│   ├── express_local_generator.py  # 快慢车生成器
│   │   └── ExpressLocalGenerator: 核心铺画算法
│   │
│   ├── headway_optimizer.py        # 发车间隔优化器
│   │   └── HeadwayOptimizer: 基于LP的优化
│   │
│   ├── overtaking_detector.py      # 越行检测器
│   │   └── OvertakingDetector: 越行检测和分析
│   │
│   └── timetable_builder.py        # 时刻表构建器
│       └── TimetableBuilder: 构建详细时刻
│
├── output/ (输出层)
│   └── excel_exporter.py           # Excel导出器
│       └── ExcelExporter: 复用src接口
│
└── main.py (主程序)
    └── ExpressLocalSchedulerV3: 整合所有模块
```

### 数据流

```
输入数据 (XML)
    ↓
DataReader (复用src)
    ↓
ExpressLocalGenerator (生成快慢车)
    ↓
TimetableBuilder (构建详细时刻)
    ↓
OvertakingDetector (检测越行)
    ↓
HeadwayOptimizer (优化间隔)
    ↓
ExcelExporter (复用src)
    ↓
输出文件 (Excel)
```

## 实现特点

### 1. 复用现有接口

- **输入**: 使用 `DataReader` 读取RailInfo和UserSetting
- **输出**: 使用与src一致的Excel格式
- **数据结构**: 兼容 `Station`, `Path`, `RailInfo` 等

### 2. 算法创新

**快车铺画**:
```python
# 均匀分布快车
express_headway = service_duration / express_count
for i in range(express_count):
    departure_time = start_time + i * express_headway
    create_express_train(departure_time)
```

**慢车铺画**:
```python
# 在均匀时间段内搜索最优时刻
for each_local_train:
    search_window = target_local_headway
    best_time = find_best_departure_time(
        target_time,
        search_window,
        minimize(overtaking_delay + headway_penalty)
    )
    create_local_train(best_time)
```

**发车间隔优化**:
```python
# 线性规划模型
model = LpProblem("Headway_Optimization", LpMinimize)

# 决策变量：发车时间
departure_vars = {train: LpVariable(...)}

# 目标函数：最小化间隔偏差
objective = lpSum(|h_i - h_avg|)

# 约束：最小/最大间隔
constraints = {
    h_i >= min_headway,
    h_i <= max_headway
}
```

### 3. 越行处理

**检测逻辑**:
```python
for express in express_trains:
    for local in local_trains:
        if will_overtake(express, local):
            overtaking_station = find_overtaking_station()
            event = create_overtaking_event()
            analyze_avoidability(event)
```

**可避免性分析**:
- 发车间隔是否可以调整
- 发车顺序是否可以交换（快车大交路追踪慢车小交路）
- 提供具体优化建议

## 输出格式

### Excel工作表

1. **列车时刻表** - 按列车展示到发时刻
2. **车站时刻表** - 按车站展示列车时刻
3. **交路统计** - 各交路开行情况统计
4. **越行事件** - 详细的越行信息和建议
5. **统计信息** - 运行图质量指标
6. **车辆运用** - 车底连接关系

### 关键统计指标

- 总列车数、快慢车数量和比例
- 平均发车间隔、发车间隔方差
- 均衡性得分（0-1分）
- 越行事件总数、被越行慢车数
- 可避免越行数量和优化建议

## 与V1、V2的对比

| 特性 | V1 | V2 | V3 (本版本) |
|------|----|----|-------------|
| 输入接口 | 自定义 | 部分复用 | **完全复用src** |
| 输出接口 | 自定义 | 部分复用 | **完全复用src** |
| 铺画规则 | 简单 | 中等 | **完整实现** |
| 目标函数 | 多目标 | 多目标 | **发车均衡性** |
| 优化方法 | MILP | MILP | **LP+搜索** |
| 越行处理 | 基础 | 改进 | **智能分析** |
| 代码结构 | 一般 | 良好 | **模块化清晰** |
| 文档完善度 | 中等 | 良好 | **详细完整** |

## 优势

1. **✓ 完全兼容现有系统**: 复用src接口，易于集成
2. **✓ 算法更科学**: 基于实际铺画规则设计
3. **✓ 目标更明确**: 以发车均衡性为主要目标
4. **✓ 分析更深入**: 提供越行优化建议
5. **✓ 代码更清晰**: 模块化设计，易于维护
6. **✓ 文档更完善**: 详细的说明和示例

## 使用场景

### 适用场景

- ✅ 快慢车混合运营的城市轨道交通线路
- ✅ 需要优化发车间隔均衡性的场景
- ✅ 需要分析越行事件和优化建议的场景
- ✅ 需要与现有大小交路系统集成的场景

### 不适用场景

- ❌ 纯单一交路（建议使用src原有功能）
- ❌ 不考虑发车均衡性的场景
- ❌ 实时调度和动态调整（本版本为离线优化）

## 扩展方向

### 短期扩展（1-3个月）

1. **增加更多配置选项**
   - 自定义快车停站方案
   - 可配置的越行站选择
   - 更灵活的发车间隔约束

2. **性能优化**
   - 并行计算
   - 算法加速
   - 大规模问题求解

3. **输出增强**
   - 运行图可视化
   - 更详细的分析报告
   - 多种导出格式

### 中期扩展（3-6个月）

1. **组合运营模式**
   - 大小交路 + 快慢车组合
   - 多交路、多车型组合
   - 复杂的套跑模式

2. **多目标优化**
   - 均衡性 + 能耗
   - 均衡性 + 旅行时间
   - 帕累托前沿分析

3. **智能决策支持**
   - 参数推荐
   - 方案比较
   - 敏感性分析

### 长期扩展（6-12个月）

1. **实时调度支持**
   - 动态调整算法
   - 延误恢复策略
   - 在线优化

2. **机器学习集成**
   - 客流预测
   - 参数学习
   - 智能决策

3. **平台化**
   - Web界面
   - 云端部署
   - API服务

## 开发记录

### 2024-10-11 (Version 3.0.0)

- ✅ 创建express_local_V3目录结构
- ✅ 实现数据模型层（Train, TimetableEntry, OvertakingEvent, ExpressLocalTimetable）
- ✅ 实现算法层（ExpressLocalGenerator, HeadwayOptimizer, OvertakingDetector, TimetableBuilder）
- ✅ 实现输出层（ExcelExporter，复用src接口）
- ✅ 实现主程序（ExpressLocalSchedulerV3）
- ✅ 编写完整文档（README.md, PROJECT_SUMMARY.md）
- ✅ 提供示例代码（example_usage.py）

## 总结

快慢车运行图自动编制程序V3是一个**完全复用src接口、基于快慢车铺画规则、以发车时间均衡性为目标**的全新系统。它在保持与现有系统兼容的同时，提供了更科学的算法、更深入的分析和更清晰的代码结构。

### 核心价值

1. **实用性**: 完全复用现有接口，易于集成和使用
2. **科学性**: 基于实际铺画规则和优化理论
3. **智能化**: 提供越行分析和优化建议
4. **可维护性**: 清晰的模块化设计和完善的文档

---

<div align="center">

**快慢车运行图自动编制程序V3**  
*为城市轨道交通提供智能化的运行图编制解决方案*

Version 3.0.0 | 2024-10-11 | CRRC Team

</div>

