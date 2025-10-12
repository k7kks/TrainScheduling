# 快慢车运行图自动编制模型设计文档

**版本**：V3  
**日期**：2025-10-12  
**状态**：生产就绪

---

## 目录

1. [系统概述](#系统概述)
2. [核心设计理念](#核心设计理念)
3. [系统架构](#系统架构)
4. [数据模型](#数据模型)
5. [算法模型](#算法模型)
6. [运行流程](#运行流程)
7. [输入输出](#输入输出)
8. [使用方法](#使用方法)
9. [配置参数](#配置参数)
10. [扩展性设计](#扩展性设计)

---

## 系统概述

### 系统目标

基于**发车时间均衡性**的快慢车运行图自动编制系统，实现：
- 快车与慢车的混合编排
- 发车间隔优化（最小化方差）
- 越行事件的合理安排
- 大小交路的灵活组合

### 核心特点

1. **基于优化算法**：使用线性规划优化发车间隔
2. **复用现有框架**：兼容src文件夹的数据结构和输出接口
3. **模块化设计**：清晰的职责分离，易于扩展
4. **双层优化**：贪心算法+线性规划的两阶段优化

---

## 核心设计理念

### 1. 快慢车混跑模式

```
时间轴 ─────────────────────────────────────────────→
         E001    L001    L002    E002    L003    L004
         快车    慢车    慢车    快车    慢车    慢车
         ↓       ↓       ↓       ↓       ↓       ↓
站台A    停      停      停      停      停      停
站台B    跳      停      停      跳      停      停
站台C    停      停      停      停      停      停
站台D    跳      停      停      跳      停      停
站台E    停      停      停      停      停      停
```

**说明**：
- 快车：部分车站跳停，运行速度快
- 慢车：站站停，运行速度慢
- 越行：快车在特定车站超越慢车

### 2. 发车间隔优化目标

**目标函数**：最小化发车间隔方差

```python
minimize: Σ(headway_i - target_headway)²
```

**约束条件**：
- 最小发车间隔 ≥ 120秒
- 最大发车间隔 ≤ 600秒
- 快慢车比例符合配置
- 越行站停站时间 ≥ 240秒

### 3. 数据流架构

```
输入层（XML）
    ↓
数据读取层（DataReader）
    ↓
模型生成层（ExpressLocalGenerator）
    ↓
时刻表构建层（TimetableBuilder）
    ↓
优化调整层（HeadwayOptimizer）
    ↓
数据转换层（Solution转换）
    ↓
输出层（ExcelExporter）
```

---

## 系统架构

### 总体架构图

```
┌─────────────────────────────────────────────────────────┐
│                   Express Local V3                       │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌────────────┐  ┌────────────┐  ┌─────────────┐      │
│  │   Models   │  │ Algorithms │  │   Output    │      │
│  │  (数据模型) │  │  (算法层)   │  │  (输出层)    │      │
│  └────────────┘  └────────────┘  └─────────────┘      │
│         ↓               ↓                ↓              │
│  ┌──────────────────────────────────────────┐          │
│  │        Main (ExpressLocalSchedulerV3)     │          │
│  │           (主控制器和协调层)               │          │
│  └──────────────────────────────────────────┘          │
│                       ↓                                  │
│  ┌──────────────────────────────────────────┐          │
│  │          src/ (复用现有框架)              │          │
│  │  DataReader | RailInfo | Solution | ...  │          │
│  └──────────────────────────────────────────┘          │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### 核心模块

#### 1. Models（数据模型层）

**位置**：`express_local_V3/models/`

| 模块 | 职责 | 关键类 |
|------|------|--------|
| `train.py` | 列车模型定义 | Train, ExpressTrain, LocalTrain |
| `timetable_entry.py` | 时刻表条目 | TimetableEntry |
| `express_local_timetable.py` | 完整时刻表 | ExpressLocalTimetable |
| `overtaking_event.py` | 越行事件 | OvertakingEvent |

#### 2. Algorithms（算法层）

**位置**：`express_local_V3/algorithms/`

| 模块 | 职责 | 核心算法 |
|------|------|----------|
| `express_local_generator.py` | 快慢车生成 | 贪心算法 + 时间窗口搜索 |
| `timetable_builder.py` | 时刻表构建 | 逐站计算 + 站台码匹配 |
| `headway_optimizer.py` | 发车间隔优化 | 线性规划（PuLP + CBC） |
| `overtaking_detector.py` | 越行检测 | 时序分析 |

#### 3. Output（输出层）

**位置**：`express_local_V3/output/`

| 模块 | 职责 |
|------|------|
| `excel_exporter.py` | Excel文件导出（复用src格式） |

#### 4. Main（主控制器）

**位置**：`express_local_V3/main.py`

核心类：`ExpressLocalSchedulerV3`

---

## 数据模型

### 核心数据结构

#### 1. Train（列车基类）

```python
@dataclass
class Train:
    train_id: str                # 列车ID（如E001, L001）
    train_name: str             # 列车名称
    train_type: TrainType       # 列车类型（快车/慢车）
    route_id: str               # 所属交路ID
    direction: str              # 方向（上行/下行）
    
    stop_stations: List[str]    # 停靠车站列表
    skip_stations: Set[str]     # 跳停车站集合
    
    departure_time: int         # 发车时间（秒）
    arrival_time: int           # 到达时间（秒）
    
    prev_train_id: str          # 前序车次ID
    next_train_id: str          # 后续车次ID
```

**子类**：
- `ExpressTrain`：快车（支持跳停、越行能力）
- `LocalTrain`：慢车（站站停、可被越行、支持小交路）

#### 2. TimetableEntry（时刻表条目）

```python
@dataclass
class TimetableEntry:
    train_id: str               # 列车ID
    station_id: str             # 车站ID
    station_name: str           # 车站名称
    dest_code: str              # 站台目的地码（重要！）
    
    arrival_time: int           # 到达时间（秒）
    departure_time: int         # 发车时间（秒）
    dwell_time: int             # 停站时间（秒）
    
    is_stop: bool               # 是否停车
    is_skip: bool               # 是否跳停
    is_overtaking: bool         # 是否发生越行
    
    overtaken_by: str           # 被哪列车越行
    waiting_time: int           # 等待时间（待避）
```

**关键字段说明**：
- `station_id`：车站的唯一标识（如"11"）
- `dest_code`：站台目的地码，与XML文件中的Destcode对应（如"113"）
- `is_stop`：是否停车（快车可能跳停）
- `is_overtaking`：是否在此站被越行

#### 3. ExpressLocalTimetable（快慢车时刻表）

```python
class ExpressLocalTimetable:
    express_trains: List[ExpressTrain]    # 快车列表
    local_trains: List[LocalTrain]        # 慢车列表
    timetable_entries: List[TimetableEntry]  # 所有时刻表条目
    overtaking_events: List[OvertakingEvent]  # 越行事件
    
    # 索引结构（快速查询）
    _train_schedule_index: Dict[str, List[TimetableEntry]]
    _station_schedule_index: Dict[str, List[TimetableEntry]]
```

#### 4. OvertakingEvent（越行事件）

```python
@dataclass
class OvertakingEvent:
    event_id: str                      # 事件ID
    overtaking_train_id: str          # 越行车次
    overtaken_train_id: str           # 被越行车次
    overtaking_station_id: str        # 越行站ID
    overtaking_station_name: str      # 越行站名称
    
    local_arrival_time: int           # 慢车到达时间
    express_pass_time: int            # 快车通过时间
    local_departure_time: int         # 慢车发车时间
    
    arrival_to_pass_interval: int     # 到通间隔
    pass_to_departure_interval: int   # 通发间隔
    local_waiting_time: int           # 慢车等待时间
```

---

## 算法模型

### 1. 快慢车生成算法（ExpressLocalGenerator）

#### 1.1 快车生成

**算法**：基于目标停站比例的贪心选择

```python
def _generate_express_trains(service_duration, express_ratio):
    # 步骤1：计算快车数量
    total_trains = service_duration / target_headway
    express_count = int(total_trains * express_ratio)
    
    # 步骤2：确定快车停站方案
    skip_stations = _determine_express_skip_stations(stations)
    # 策略：
    # - 首末站必停
    # - 重要换乘站必停
    # - 其他站根据停站比例（如60%）选择
    
    # 步骤3：生成快车
    for i in range(express_count):
        train_id = f"E{i+1:03d}"
        direction = "上行" if (i % 2) == 0 else "下行"  # 交替上下行
        departure_time = start_time + i * express_headway
        
        train = ExpressTrain(
            train_id=train_id,
            direction=direction,
            skip_stations=skip_stations,
            departure_time=departure_time
        )
    
    return express_trains
```

#### 1.2 慢车生成

**算法**：时间窗口搜索 + 最小间隔约束

```python
def _generate_local_trains(express_trains, local_ratio):
    # 步骤1：计算慢车数量
    local_count = int(express_count / express_ratio * (1 - express_ratio))
    
    # 步骤2：生成慢车（时间窗口搜索）
    all_departure_times = [e.departure_time for e in express_trains]
    current_time = start_time
    
    for i in range(local_count):
        # 在时间窗口内搜索最优发车时间
        best_time = _find_best_departure_time(
            target_time=current_time,
            search_window=60,  # ±60秒
            existing_times=all_departure_times,
            min_headway=120    # 最小间隔120秒
        )
        
        direction = "上行" if (i % 2) == 0 else "下行"
        
        train = LocalTrain(
            train_id=f"L{i+1:03d}",
            direction=direction,
            stop_stations=all_stations,  # 站站停
            departure_time=best_time
        )
        
        all_departure_times.append(best_time)
        current_time += target_local_headway
    
    return local_trains
```

**时间窗口搜索算法**：

```python
def _find_best_departure_time(target, window, existing_times, min_headway):
    """
    在[target-window, target+window]范围内搜索最优发车时间
    目标：最小化与现有列车的间隔方差
    """
    best_time = target
    best_score = float('inf')
    
    for candidate in range(target - window, target + window + 1):
        # 检查最小间隔约束
        if not _check_min_headway(candidate, existing_times, min_headway):
            continue
        
        # 计算间隔方差
        score = _calculate_headway_variance(candidate, existing_times)
        
        if score < best_score:
            best_score = score
            best_time = candidate
    
    return best_time
```

### 2. 时刻表构建算法（TimetableBuilder）

**算法**：逐站累加计算

```python
def _build_train_schedule(train):
    entries = []
    current_time = train.departure_time
    stations = _get_train_stations(train)  # 根据交路获取车站列表
    
    for i, station in enumerate(stations):
        # 步骤1：判断是否停车
        is_stop = train.stops_at_station(station.id)
        
        # 步骤2：计算到达时间
        if i == 0:
            arrival_time = current_time  # 首站
        else:
            # 区间运行时间
            running_time = _get_section_running_time(
                stations[i-1], station, train
            )
            arrival_time = current_time + running_time
        
        # 步骤3：计算停站时间和发车时间
        if is_stop:
            dwell_time = train.get_dwell_time(station.id)
        else:
            dwell_time = 0  # 跳停
        
        departure_time = arrival_time + dwell_time
        
        # 步骤4：获取正确的站台目的地码
        dest_code = _get_platform_code(station, train.direction)
        # 核心逻辑：
        # - 根据train.direction确定方向（上行/下行）
        # - 从station.platformList中选择匹配方向的站台
        # - 返回该站台的dest_code
        
        # 步骤5：创建时刻表条目
        entry = TimetableEntry(
            train_id=train.train_id,
            station_id=station.id,
            station_name=station.name,
            dest_code=dest_code,  # 关键！
            arrival_time=arrival_time,
            departure_time=departure_time,
            dwell_time=dwell_time,
            is_stop=is_stop,
            is_skip=not is_stop
        )
        
        entries.append(entry)
        current_time = departure_time
    
    return entries
```

**站台目的地码获取算法**：

```python
def _get_platform_code(station, direction):
    """
    根据车站和列车方向获取正确的站台目的地码
    """
    # 确定站台方向
    if direction == "上行":
        target_direction = Platform.Direction.LEFT
    else:
        target_direction = Platform.Direction.RIGHT
    
    # 在车站的站台列表中查找匹配方向的站台
    for platform in station.platformList:
        if (platform.dir == target_direction and 
            not platform.is_virtual and
            platform.platform_type.value == "Normal"):
            return platform.dest_code  # 返回Destcode
    
    # 兜底策略
    for platform in station.platformList:
        if platform.dir == target_direction:
            return platform.dest_code
    
    # 最后的兜底
    return station.platformList[0].dest_code if station.platformList else station.id
```

### 3. 发车间隔优化算法（HeadwayOptimizer）

**算法**：线性规划优化

```python
def optimize_departure_times(trains, target_headway, min_headway, max_headway):
    """
    使用线性规划优化发车时间，最小化发车间隔方差
    """
    # 步骤1：建立优化模型
    prob = pulp.LpProblem("HeadwayOptimization", pulp.LpMinimize)
    
    # 步骤2：定义决策变量
    departure_vars = {}
    for train in trains:
        var = pulp.LpVariable(
            f"dep_{train.train_id}",
            lowBound=train.departure_time - time_window,
            upBound=train.departure_time + time_window,
            cat='Continuous'
        )
        departure_vars[train.train_id] = var
    
    # 步骤3：定义辅助变量（间隔偏差）
    headway_deviation_vars = []
    for i in range(len(trains) - 1):
        train1 = trains[i]
        train2 = trains[i+1]
        
        # 间隔 = 后车发车时间 - 前车发车时间
        headway = departure_vars[train2.train_id] - departure_vars[train1.train_id]
        
        # 偏差 = |间隔 - 目标间隔|
        deviation = pulp.LpVariable(f"dev_{i}", lowBound=0)
        
        # 约束：deviation ≥ headway - target_headway
        prob += deviation >= headway - target_headway
        # 约束：deviation ≥ target_headway - headway
        prob += deviation >= target_headway - headway
        
        headway_deviation_vars.append(deviation)
    
    # 步骤4：目标函数（最小化间隔偏差平方和）
    prob += pulp.lpSum([dev * dev for dev in headway_deviation_vars])
    
    # 步骤5：添加约束
    for i in range(len(trains) - 1):
        train1 = trains[i]
        train2 = trains[i+1]
        headway = departure_vars[train2.train_id] - departure_vars[train1.train_id]
        
        # 最小间隔约束
        prob += headway >= min_headway
        # 最大间隔约束
        prob += headway <= max_headway
    
    # 步骤6：求解
    status = prob.solve(pulp.PULP_CBC_CMD(msg=0))
    
    # 步骤7：更新发车时间
    if status == pulp.LpStatusOptimal:
        for train in trains:
            train.departure_time = int(departure_vars[train.train_id].varValue)
        return True
    else:
        return False
```

### 4. 越行检测算法（OvertakingDetector）

```python
def detect_overtaking_events(express_trains, local_trains, timetable):
    """
    检测快车越行慢车的事件
    """
    events = []
    
    for express in express_trains:
        for local in local_trains:
            # 只检测同方向列车
            if express.direction != local.direction:
                continue
            
            # 获取两车的时刻表
            express_schedule = timetable.get_train_schedule(express.train_id)
            local_schedule = timetable.get_train_schedule(local.train_id)
            
            # 逐站检查是否发生越行
            for i, station in enumerate(stations):
                express_entry = express_schedule[i]
                local_entry = local_schedule[i]
                
                # 检查越行条件
                if (local_entry.arrival_time < express_entry.arrival_time and
                    local_entry.departure_time > express_entry.departure_time):
                    # 慢车先到达，但晚发车 → 发生越行
                    
                    event = OvertakingEvent(
                        event_id=f"OT_{len(events)+1}",
                        overtaking_train_id=express.train_id,
                        overtaken_train_id=local.train_id,
                        overtaking_station_id=station.id,
                        local_arrival_time=local_entry.arrival_time,
                        express_pass_time=express_entry.departure_time,
                        local_departure_time=local_entry.departure_time,
                        local_waiting_time=local_entry.waiting_time
                    )
                    events.append(event)
    
    return events
```

---

## 运行流程

### 主流程图

```
开始
  ↓
1. 初始化ExpressLocalSchedulerV3
  ├─ 设置参数（快车比例、目标间隔等）
  └─ 创建算法模块实例
  ↓
2. read_data() - 读取输入数据
  ├─ 读取轨道信息XML（RailInfo）
  ├─ 读取用户设置XML（UserSetting）
  ├─ 初始化站台映射
  └─ 生成快车停站方案
  ↓
3. generate_express_local_timetable() - 生成运行图
  ├─ 3.1 ExpressLocalGenerator.generate()
  │   ├─ 生成快车列表
  │   ├─ 生成慢车列表
  │   └─ 创建ExpressLocalTimetable
  │
  ├─ 3.2 TimetableBuilder.build_timetable()
  │   ├─ 为每列车构建详细时刻表
  │   ├─ 计算到发时间
  │   └─ 获取站台目的地码
  │
  ├─ 3.3 HeadwayOptimizer.optimize() [可选]
  │   ├─ 建立线性规划模型
  │   ├─ 求解优化问题
  │   └─ 更新发车时间
  │
  └─ 3.4 OvertakingDetector.detect()
      ├─ 检测越行事件
      └─ 更新时刻表
  ↓
4. convert_timetable_to_solution() - 转换数据
  ├─ 将ExpressLocalTimetable转换为Solution
  ├─ 为每列车创建RouteSolution
  ├─ 根据列车属性获取正确路径ID
  └─ 设置方向、交路类型
  ↓
5. 输出结果
  ├─ ExcelExporter.export() - 导出Excel
  │   ├─ 列车时刻表
  │   ├─ 车站时刻表
  │   ├─ 交路统计
  │   ├─ 越行事件
  │   └─ 统计信息
  │
  └─ Solution.writeExcel() - 输出标准格式 [可选]
      ├─ 运行时间表
      ├─ 计划线数据
      └─ 任务线数据
  ↓
结束
```

### 详细步骤说明

#### 步骤1：初始化

```python
scheduler = ExpressLocalSchedulerV3(
    rail_info_file="data/input_data_new/RailwayInfo/Schedule-cs2.xml",
    user_setting_file="data/input_data_new/UserSettingInfoNew/cs2_real_28.xml",
    output_dir="data/output_data/results",
    express_ratio=0.5,        # 快车比例50%
    target_headway=180,       # 目标发车间隔3分钟
    speed_level=1,            # 运行等级
    default_dwell_time=30,    # 默认停站时间30秒
    express_stop_stations=None,  # 自动生成停站方案
    enable_short_route=True,  # 启用小交路
    short_route_ratio=0.5,    # 小交路比例50%
    debug=False
)
```

#### 步骤2：读取数据

```python
# 读取轨道信息
rail_info = DataReader.read_file(rail_info_file)
# 包含：
# - 车站列表（Station）
# - 站台列表（Platform，含dest_code）
# - 路径列表（Path，含站台序列）
# - 运行时间（PerformanceLevelBetweenStation）

# 读取用户设置
user_setting = DataReader.read_setting_file(user_setting_file)
# 包含：
# - 场段信息（Depot）
# - 峰期配置（Peak）
# - 交路配置（Route: up_route, down_route）
# - 列车数量和间隔
```

#### 步骤3：生成运行图

```python
# 3.1 生成快慢车
timetable = self.generator.generate(
    service_duration=12600,  # 服务时长（秒）
    start_time=23400,        # 开始时间
    stations=stations        # 车站列表
)

# 3.2 构建详细时刻表
timetable = self.builder.build_timetable(timetable)

# 3.3 优化发车间隔（可选）
if self.optimizer:
    optimized_timetable = self.optimizer.optimize(timetable)

# 3.4 检测越行
overtaking_events = self.detector.detect_overtaking(timetable)
```

#### 步骤4：转换为Solution

```python
solution = scheduler.convert_timetable_to_solution()

# 转换逻辑：
for train in all_trains:
    # 获取列车时刻表
    entries = timetable.get_train_schedule(train.train_id)
    
    # 根据列车属性获取正确的路径ID
    route_id = _get_route_id_for_train(train, peak)
    # 逻辑：
    # - train.direction == "上行" → peak.routes[xroad].up_route
    # - train.direction == "下行" → peak.routes[xroad].down_route
    
    # 创建RouteSolution
    rs = RouteSolution(
        initial_time_stamp=train.departure_time,
        table_num=table_num,
        round_num=round_num,
        route_num=int(route_id)  # 路径编号！
    )
    
    # 设置属性
    rs.dir = 0 if train.direction == "上行" else 1
    rs.xroad = 1 if train.is_short_route else 0
    
    # 添加所有站台（包括停站和跳站）
    # 快车和慢车的路径编号相同时，必须包含相同的所有站台目的地码
    # 快车跳站时，到站时间=离站时间（表示通过不停）
    for entry in entries:
        platform_code = entry.dest_code  # 使用dest_code！
        
        if entry.is_stop:
            # 正常停站
            rs.addStop(
                platform=platform_code,
                stop_time=entry.dwell_time,
                perf_level=speed_level,
                current_time=entry.arrival_time,
                dep_time=entry.departure_time
            )
        else:
            # 跳站：到站时间=离站时间，停站时间=0
            rs.addStop(
                platform=platform_code,
                stop_time=0,
                perf_level=speed_level,
                current_time=entry.arrival_time,
                dep_time=entry.arrival_time  # 跳站时，离站=到站
            )
    
    solution.addTrainService(rs)
```

#### 步骤5：输出结果

```python
# 方式1：使用ExcelExporter（推荐）
exporter = ExcelExporter()
output_file = exporter.export(
    timetable=timetable,
    output_path="output/express_local_timetable.xlsx",
    rail_info=rail_info,
    user_setting=user_setting
)

# 方式2：使用Solution.writeExcel（兼容原系统）
solution.writeExcel(
    file_name="output",
    rl=rail_info,
    csn_default="utf-8"
)
```

---

## 输入输出

### 输入文件

#### 1. 轨道信息文件（Schedule.xml）

**位置**：`data/input_data_new/RailwayInfo/Schedule-cs2.xml`

**关键内容**：
```xml
<RailwayInfo>
  <!-- 车站信息 -->
  <StationInfo>
    <Station>
      <Id>11</Id>
      <Name>梅溪湖西站</Name>
      <Platforms>
        <Platform>
          <Id>3</Id>
          <Name>梅溪湖西站上行站台</Name>
          <Direction>Left</Direction>
          <Destcode>113</Destcode>  <!-- 站台目的地码！-->
        </Platform>
        <Platform>
          <Id>4</Id>
          <Name>梅溪湖西站下行站台</Name>
          <Direction>Right</Direction>
          <Destcode>114</Destcode>
        </Platform>
      </Platforms>
    </Station>
  </StationInfo>
  
  <!-- 路径信息 -->
  <RouteInfo>
    <Paths>
      <Path>
        <Id>1086</Id>
        <Name>梅溪湖西站-光达站（上行）</Name>
        <Direction>Left</Direction>
        <DestcodesOfPath>
          <Destcode>113</Destcode>
          <Destcode>121</Destcode>
          <Destcode>131</Destcode>
          <!-- ... -->
        </DestcodesOfPath>
      </Path>
      <Path>
        <Id>1088</Id>
        <Name>光达站-梅溪湖西站（下行）</Name>
        <Direction>Right</Direction>
        <DestcodesOfPath>
          <Destcode>333</Destcode>
          <Destcode>321</Destcode>
          <!-- ... -->
        </DestcodesOfPath>
      </Path>
    </Paths>
  </RouteInfo>
  
  <!-- 运行时间 -->
  <PerformanceLevelInfo>
    <PerformanceLevelsBetweenStation>
      <PerformanceLevelBetweenStation>
        <StartDestcode>113</StartDestcode>
        <EndDestcode>121</EndDestcode>
        <RunTimeOfPerformanceLevel>
          <PerformanceLevelId>1</PerformanceLevelId>
          <RunTime>120</RunTime>  <!-- 秒 -->
        </RunTimeOfPerformanceLevel>
      </PerformanceLevelBetweenStation>
    </PerformanceLevelsBetweenStation>
  </PerformanceLevelInfo>
</RailwayInfo>
```

#### 2. 用户设置文件（Setting.xml）

**位置**：`data/input_data_new/UserSettingInfoNew/cs2_real_28.xml`

**关键内容**：
```xml
<Setting>
  <!-- 场段信息 -->
  <DepotsInfo>
    <Depot>
      <DepotId>60</DepotId>
      <TrainCapacity>32</TrainCapacity>
      <ParkingCapacity>32</ParkingCapacity>
    </Depot>
  </DepotsInfo>
  
  <!-- 峰期配置 -->
  <Peaks>
    <Peak>
      <StartTime>23400</StartTime>  <!-- 06:30:00 -->
      <EndTime>36000</EndTime>      <!-- 10:00:00 -->
      
      <!-- 大交路配置 -->
      <RouteCategory1>52</RouteCategory1>
      <UpRoute1>1086</UpRoute1>     <!-- 上行路径 -->
      <DownRoute1>1088</DownRoute1> <!-- 下行路径 -->
      
      <!-- 小交路配置（可选） -->
      <RouteCategory2>67</RouteCategory2>
      <UpRoute2>1xxx</UpRoute2>
      <DownRoute2>1xxx</DownRoute2>
      
      <!-- 列车配置 -->
      <TrainNumbers>24</TrainNumbers>
      <Interval>239</Interval>  <!-- 发车间隔（秒）-->
      <OperatingRate1>1</OperatingRate1>  <!-- 大交路开行比例 -->
      <OperatingRate2>0</OperatingRate2>  <!-- 小交路开行比例 -->
    </Peak>
  </Peaks>
</Setting>
```

### 输出文件

#### Excel文件结构

**文件**：`express_local_timetable.xlsx`

**工作表1：列车时刻表**
| 车次 | 车次名称 | 列车类型 | 交路ID | 方向 | 车站ID | 车站名称 | **站台目的地码** | 到达时间 | 发车时间 | 停站时间 | 是否停车 | 是否跳停 |
|------|----------|----------|--------|------|--------|----------|------------------|----------|----------|----------|----------|----------|
| E001 | 快车1 | 快车 | R001 | 上行 | 11 | 梅溪湖西站 | **113** | 06:30:00 | 06:30:30 | 30 | 是 | 否 |
| E001 | 快车1 | 快车 | R001 | 上行 | 12 | 麓谷路站 | **121** | 06:32:10 | 06:32:10 | 0 | 否 | 是 |

**工作表2：车站时刻表**
| 车站ID | 车站名称 | **站台目的地码** | 车次 | 列车类型 | 方向 | 到达时间 | 发车时间 |
|--------|----------|------------------|------|----------|------|----------|----------|
| 11 | 梅溪湖西站 | **113** | E001 | 快车 | 上行 | 06:30:00 | 06:30:30 |
| 11 | 梅溪湖西站 | **113** | L001 | 慢车 | 上行 | 06:32:00 | 06:32:40 |

**工作表3：交路统计**
| 交路ID | 快车数 | 慢车数 | 小交路数 | 大交路数 | 总列车数 |
|--------|--------|--------|----------|----------|----------|
| R001 | 12 | 30 | 0 | 42 | 42 |

**工作表4：越行事件**
| 事件ID | 越行车次 | 被越行车次 | 越行站 | 慢车到达时间 | 快车通过时间 | 慢车发车时间 | 慢车等待时间 |
|--------|----------|------------|--------|--------------|--------------|--------------|--------------|
| OT_001 | E002 | L004 | 望城坡站 | 06:45:00 | 06:46:30 | 06:49:00 | 240 |

**工作表5：统计信息**
| 统计项 | 数值 | 单位 |
|--------|------|------|
| 总列车数 | 42 | 列 |
| 快车数 | 12 | 列 |
| 慢车数 | 30 | 列 |
| 越行事件总数 | 9 | 次 |

---

## 使用方法

### 命令行方式

```bash
# 基本用法
cd express_local_V3
python main.py

# 指定配置文件
python main.py \
  --rail_info data/input_data_new/RailwayInfo/Schedule-cs2.xml \
  --user_setting data/input_data_new/UserSettingInfoNew/cs2_real_28.xml \
  --output_dir data/output_data/results \
  --express_ratio 0.5 \
  --target_headway 180
```

### Python API方式

```python
from express_local_V3.main import ExpressLocalSchedulerV3

# 创建调度器
scheduler = ExpressLocalSchedulerV3(
    rail_info_file="data/input_data_new/RailwayInfo/Schedule-cs2.xml",
    user_setting_file="data/input_data_new/UserSettingInfoNew/cs2_real_28.xml",
    output_dir="data/output_data/results",
    express_ratio=0.5,          # 快车比例
    target_headway=180,         # 目标发车间隔（秒）
    speed_level=1,              # 运行等级
    default_dwell_time=30,      # 默认停站时间（秒）
    express_stop_stations=None, # 快车停站列表（None=自动）
    enable_short_route=True,    # 是否启用小交路
    short_route_ratio=0.5,      # 小交路比例
    debug=False
)

# 运行完整流程
success = scheduler.run()

if success:
    print(f"运行图生成成功！")
    print(f"输出文件：{scheduler.output_dir}")
```

### 分步执行方式

```python
# 步骤1：读取数据
scheduler.read_data()

# 步骤2：生成运行图
scheduler.generate_express_local_timetable()

# 步骤3：转换数据格式
solution = scheduler.convert_timetable_to_solution()

# 步骤4：导出Excel
from express_local_V3.output.excel_exporter import ExcelExporter
exporter = ExcelExporter()
output_file = exporter.export(
    timetable=scheduler.timetable,
    output_path="output/timetable.xlsx",
    rail_info=scheduler.rail_info,
    user_setting=scheduler.user_setting
)

# 步骤5：输出标准格式（可选）
solution.writeExcel(
    file_name=scheduler.output_dir,
    rl=scheduler.rail_info,
    csn_default="utf-8"
)
```

---

## 配置参数

### 关键参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `express_ratio` | float | 0.5 | 快车比例（0-1） |
| `target_headway` | int | 180 | 目标发车间隔（秒） |
| `speed_level` | int | 1 | 运行等级（1-5） |
| `default_dwell_time` | int | 30 | 默认停站时间（秒） |
| `express_stop_stations` | List[str] | None | 快车停站列表（站台码）|
| `enable_short_route` | bool | True | 是否启用小交路 |
| `short_route_ratio` | float | 0.5 | 小交路比例（相对慢车）|

### 高级配置（ExpressLocalConfig）

```python
config = ExpressLocalConfig(
    express_ratio=0.5,              # 快车比例
    target_headway=180,             # 目标发车间隔（秒）
    min_headway=120,                # 最小发车间隔（秒）
    max_headway=600,                # 最大发车间隔（秒）
    express_stop_ratio=0.6,         # 快车停站比例
    express_skip_pattern=None,      # 快车跳站模式
    min_overtaking_interval=120,    # 最小越行间隔（秒）
    min_overtaking_dwell=240,       # 越行站最小停站时间（秒）
    base_running_time_per_section=120,  # 基础区间运行时间（秒）
    base_dwell_time=30,             # 基础停站时间（秒）
    express_speed_factor=1.2,       # 快车速度系数
    enable_short_route=True,        # 启用小交路
    short_route_ratio=0.5           # 小交路比例
)
```

---

## 扩展性设计

### 1. 插件化算法

系统支持替换核心算法模块：

```python
# 自定义发车间隔优化器
class CustomHeadwayOptimizer(HeadwayOptimizer):
    def optimize(self, timetable):
        # 自定义优化逻辑
        pass

# 使用自定义优化器
scheduler.optimizer = CustomHeadwayOptimizer(...)
```

### 2. 多种停站策略

```python
# 策略1：固定停站比例
express_stop_stations = auto_select_by_ratio(stations, 0.6)

# 策略2：基于客流的停站选择
express_stop_stations = select_by_passenger_flow(stations, flow_data)

# 策略3：手动指定
express_stop_stations = ['113', '141', '153', '201', '241', ...]
```

### 3. 自定义输出格式

```python
# 扩展ExcelExporter
class CustomExcelExporter(ExcelExporter):
    def _write_custom_sheet(self, timetable, writer):
        # 添加自定义工作表
        pass

# 使用
exporter = CustomExcelExporter()
exporter.export(...)
```

---

## 附录

### A. 术语表

| 术语 | 英文 | 说明 |
|------|------|------|
| 快车 | Express Train | 部分站点跳停的列车 |
| 慢车 | Local Train | 站站停的列车 |
| 大交路 | Long Route | 全程运行（首站→末站）|
| 小交路 | Short Route | 部分运行（首站→折返站）|
| 站台目的地码 | Destcode | 站台的唯一标识（如"113"）|
| 路径编号 | Route Number | 路径的唯一标识（如"1086"）|
| 越行 | Overtaking | 快车在特定车站超越慢车 |
| 发车间隔 | Headway | 相邻列车的发车时间差 |

### B. 文件结构

```
express_local_V3/
├── main.py                          # 主控制器
├── models/                          # 数据模型
│   ├── train.py                     # 列车模型
│   ├── timetable_entry.py           # 时刻表条目
│   ├── express_local_timetable.py   # 完整时刻表
│   └── overtaking_event.py          # 越行事件
├── algorithms/                      # 算法层
│   ├── express_local_generator.py   # 快慢车生成
│   ├── timetable_builder.py         # 时刻表构建
│   ├── headway_optimizer.py         # 发车间隔优化
│   └── overtaking_detector.py       # 越行检测
├── output/                          # 输出层
│   └── excel_exporter.py            # Excel导出
├── docs/                            # 文档
├── tests/                           # 测试
├── examples/                        # 示例
└── requirements.txt                 # 依赖
```

### C. 相关文档

1. [DESTCODE_FIX_SUMMARY.md](./DESTCODE_FIX_SUMMARY.md) - 站台目的地码修复
2. [ROUTE_NUM_FIX_SUMMARY.md](./ROUTE_NUM_FIX_SUMMARY.md) - 路径编号修复
3. [FIXES_VALIDATION_REPORT.md](./FIXES_VALIDATION_REPORT.md) - 修复验证报告
4. [README.md](./README.md) - 项目说明
5. [VERSION_HISTORY.md](./VERSION_HISTORY.md) - 版本历史

---

**文档版本**：1.0  
**最后更新**：2025-10-12  
**维护者**：AI Assistant (Claude Sonnet 4.5)

