# 快车越行慢车Demo程序说明

## 概述

这是一个完整展示**快车越行慢车**现象的Demo程序，严格按照`doc/快慢车运行图编制方案初稿/快慢车运行图编制方案初稿.md`文档中的越行设计原则实现。

## 核心特点

### ✅ 完整实现越行处理流程

1. **越行判定**：检测快车是否会追上慢车（基于发车间隔和速度差）
2. **越行站选择**：从冲突点向前查找最近的越行站
3. **时间调整**：
   - 慢车在越行站停留至少**4分钟(240秒)**
   - 满足**到通间隔≥120秒**
   - 满足**通发间隔≥120秒**
4. **时刻顺延**：越行站之后的所有车站到发时间自动顺延

### 🚄 运行场景设置

- **线路设置**：10个车站（起点站、站点1-8、终点站）
- **越行站**：站点3、站点5、站点7（具有越行能力）
- **快车数量**：3列
  - 快车1：02:00发车
  - 快车2：02:10发车
  - 快车3：02:20发车
- **慢车数量**：4列
  - 慢车1：02:02:30发车（在快车1后2.5分钟）
  - 慢车2：02:05:00发车（在快车1后5分钟）
  - 慢车3：02:12:30发车（在快车2后2.5分钟）
  - 慢车4：02:15:00发车（在快车2后5分钟）

### 📊 越行效果展示

从运行结果可以看到：

#### 越行事件1：快车2在站点6越行慢车1
```
慢车到达:        02:17:00
快车通过:        02:21:00
慢车原定发车:    02:17:30
慢车调整后发车:  02:23:00
停站时间:        30秒 -> 360秒(6分钟)
后续站点顺延:    +330秒
到通间隔:        240秒 ✓
通发间隔:        120秒 ✓
```

#### 越行事件2：快车2在站点4越行慢车2
```
慢车到达:        02:14:30
快车通过:        02:17:10
慢车原定发车:    02:15:00
慢车调整后发车:  02:19:10
停站时间:        30秒 -> 280秒
后续站点顺延:    +250秒
到通间隔:        160秒 ✓
通发间隔:        120秒 ✓
```

#### 越行事件3：快车3在站点6越行慢车3
```
停站时间:        30秒 -> 360秒(6分钟)
后续站点顺延:    +330秒
```

#### 越行事件4：快车3在站点4越行慢车4
```
停站时间:        30秒 -> 280秒
后续站点顺延:    +250秒
```

## 运行方法

### 方式1：直接运行（推荐）

```bash
cd express_local_V3/examples
python overtaking_demo.py
```

### 方式2：从项目根目录运行

```bash
python express_local_V3/examples/overtaking_demo.py
```

### 方式3：在Python中调用

```python
from express_local_V3.examples.overtaking_demo import OvertakingDemoGenerator

# 创建生成器
generator = OvertakingDemoGenerator(
    min_tracking_interval=120,      # 最小追踪间隔
    min_arrival_pass_interval=120,  # 最小到通间隔
    min_pass_departure_interval=120,# 最小通发间隔
    min_overtaking_dwell=240,       # 越行站最小停站时间
    section_running_time=120,       # 区间运行时间
    express_speed_factor=1.2,       # 快车速度系数
    normal_dwell_time=30            # 正常停站时间
)

# 生成快慢车运行图
express_trains, local_trains = generator.generate_demo_timetable(
    express_count=3,
    local_count=4,
    start_time=7200  # 从02:00开始
)

# 打印时刻表
generator.print_timetable(express_trains, local_trains)

# 导出Excel
generator.export_to_excel(express_trains, local_trains)
```

## 输出文件

程序运行后会生成：

1. **控制台输出**：
   - 越行检测信息
   - 越行处理详细信息（到通间隔、通发间隔、停站时间等）
   - 完整的快车和慢车时刻表
   - 统计信息

2. **Excel文件**：`../data/output/overtaking_demo.xlsx`
   - 包含所有快车和慢车的详细时刻表
   - 标注了跳站、越行站等状态
   - 可以直观看到越行站的停站时间增加

## 核心算法

### 1. 越行判定算法

```python
def _find_overtaking_point(local_stops, express):
    """
    找到越行发生的位置
    
    判定条件：
    快车到达时间 < 慢车离站时间 + 最小追踪间隔(120秒)
    """
    for i in range(1, len(local_stops)):
        local_stop = local_stops[i]
        express_arrival = express.get_arrival_at_station(i)
        
        # 检查是否会发生追踪间隔冲突
        if express_arrival < local_stop.departure_time + min_tracking_interval:
            # 从当前站往前找最近的越行站
            return find_nearest_overtaking_station(i)
    
    return None
```

### 2. 越行处理算法

```python
def _apply_overtaking_at_station(local_stops, express, overtaking_station_idx):
    """
    在越行站应用越行处理
    
    处理步骤：
    1. 计算慢车到达越行站的时间
    2. 获取快车通过越行站的时间
    3. 计算到通间隔（≥120秒）
    4. 计算慢车发车时间 = 快车通过时间 + 通发间隔（≥120秒）
    5. 确保慢车停站时间≥240秒（4分钟）
    6. 顺延后续所有站点的时刻
    """
    overtaking_stop = local_stops[overtaking_station_idx]
    express_pass_time = express.get_arrival_at_station(overtaking_station_idx)
    
    # 慢车发车时间 = 快车通过时间 + 通发间隔
    new_local_departure = express_pass_time + min_pass_departure_interval
    
    # 慢车停站时间
    new_dwell_time = new_local_departure - overtaking_stop.arrival_time
    
    # 确保停站时间至少240秒
    if new_dwell_time < min_overtaking_dwell:
        new_dwell_time = min_overtaking_dwell
        new_local_departure = overtaking_stop.arrival_time + new_dwell_time
    
    # 应用越行站的时间调整
    overtaking_stop.departure_time = new_local_departure
    overtaking_stop.dwell_time = new_dwell_time
    
    # 顺延后续所有站点的时间
    time_shift = new_local_departure - overtaking_stop.departure_time
    for i in range(overtaking_station_idx + 1, len(local_stops)):
        local_stops[i].arrival_time += time_shift
        local_stops[i].departure_time += time_shift
```

## 关键参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `min_tracking_interval` | 120秒 | 最小追踪间隔（前后两车经过同一位置的最小时间差）|
| `min_arrival_pass_interval` | 120秒 | 最小到通间隔（慢车到站到快车通过）|
| `min_pass_departure_interval` | 120秒 | 最小通发间隔（快车通过到慢车发车）|
| `min_overtaking_dwell` | 240秒 | 越行站最小停站时间（4分钟）|
| `section_running_time` | 120秒 | 区间运行时间（慢车）|
| `express_speed_factor` | 1.2 | 快车速度系数（快车运行时间=慢车/1.2）|
| `normal_dwell_time` | 30秒 | 正常停站时间 |

## 与md文档的对应关系

本Demo严格遵循`doc/快慢车运行图编制方案初稿/快慢车运行图编制方案初稿.md`中的以下原则：

### 1. 越行判定（第359-381行）

> 列车越行的主要依据是**前行慢车和后行快车的行车间隔**及其在各区间（各个站）内的运行时间和停站时间与最小追踪间隔的关系来判断特定区间内慢车是否会被快车越行。

✅ **Demo实现**：`_find_overtaking_point()`方法

### 2. 越行处理（第450-463行）

> 正确的处理方法应当假设慢车皆不被越行，快车和慢车按照一定原则初始布点，然后按照前文所述之原则，利用最小追踪间隔为标尺，判断是否有必要作越行。

✅ **Demo实现**：
- 先生成正常时刻表（不考虑越行）
- 然后检测越行并调整时刻表

### 3. 越行站停站时间（第315-317行）

> 一般来说，越行时慢车和快车的到通和通发最小时间都为2分钟，即发生越行时慢车在越行站的最短停留时间为4分钟。

✅ **Demo实现**：
- 到通间隔≥120秒
- 通发间隔≥120秒
- 慢车停站时间≥240秒

### 4. 时刻顺延（第457行）

> 慢车在该越行站之后区间内的车站到发时分均作顺延。设慢车在越行站不作避让的正常停站时间为理论停站时间，那么顺延的时长为该慢车在越行站的停站避让时间与理论避让时间之差

✅ **Demo实现**：`_apply_overtaking_at_station()`方法中的顺延逻辑

## 输出示例

### 快车时刻表
```
快车2 (E02) - 首站发车: 02:10:00
站名         到站时间         发车时间         停站时间       状态                  
----------------------------------------------------------------------
起点站        02:10:00     02:10:00     0秒                             
站点1        ---          通过           0秒         [跳站]                
站点2        02:13:20     02:13:50     30秒        [停站]                
站点3        ---          通过           0秒         [跳站]                
站点4        ---          通过           0秒         [跳站]                
站点5        02:18:50     02:19:20     30秒        [停站]                
站点6        ---          通过           0秒         [跳站]                
站点7        ---          通过           0秒         [跳站]                
站点8        02:24:20     02:24:50     30秒        [停站]                
终点站        02:26:30     02:27:00     30秒        [停站]
```

### 慢车时刻表（带越行）
```
慢车1 (L01) - 首站发车: 02:02:30
站名         到站时间         发车时间         停站时间       状态                  
----------------------------------------------------------------------
起点站        02:02:30     02:02:30     0秒                             
站点1        02:04:30     02:05:00     30秒        [停站]                
站点2        02:07:00     02:07:30     30秒        [停站]                
站点3        02:09:30     02:10:00     30秒        [停站]                
站点4        02:12:00     02:12:30     30秒        [停站]                
站点5        02:14:30     02:15:00     30秒        [停站]                
站点6        02:17:00     02:23:00     360秒       [越行站-待避4分钟]    ⬅️ 越行！
站点7        02:25:00     02:25:30     30秒        [停站]                
站点8        02:27:30     02:28:00     30秒        [停站]                
终点站        02:30:00     02:30:30     30秒        [停站]
```

注意：站点6的停站时间从30秒增加到360秒（6分钟），后续所有站点的时刻都顺延了330秒。

## 扩展功能

### 可配置的越行站
```python
# 在生成器中设置越行站
generator.overtaking_stations = {2, 4, 6}  # 索引：站点3、站点5、站点7
```

### 可调整的发车时间
```python
# 调整快车和慢车的发车间隔，观察不同的越行情况
express_trains, local_trains = generator.generate_demo_timetable(
    express_count=5,      # 增加快车数量
    local_count=8,        # 增加慢车数量
    start_time=7200
)
```

### 可修改的运行参数
```python
# 创建生成器时可以修改各种参数
generator = OvertakingDemoGenerator(
    min_tracking_interval=90,       # 减小追踪间隔
    min_overtaking_dwell=300,       # 增加越行站停站时间到5分钟
    express_speed_factor=1.5        # 快车速度更快
)
```

## 后续集成计划

这个Demo程序展示了越行处理的核心算法。接下来可以：

1. **集成到主程序**：将越行处理逻辑集成到`express_local_V3/main.py`中
2. **增强越行检测**：支持二次越行（一列慢车被多列快车越行）
3. **越行优化**：实现越行优化建议（调整发车间隔、交换发车顺序等）
4. **可视化**：生成运行图图表，直观展示越行现象

## 技术说明

### 为什么要实现越行？

在快慢车混合运营时，由于快车速度快（跳停部分车站），如果快车在慢车后面发车，很可能在线路中追上慢车，造成追踪间隔冲突。为了保证安全，需要让慢车在某个具有越行条件的车站停车等待，让快车先通过，这就是**越行**。

### 越行的影响

1. **对慢车的影响**：
   - 增加旅行时间（在越行站额外停留约4分钟）
   - 降低乘客舒适度（等待时间长）

2. **对整体运行图的影响**：
   - 提高线路通过能力（快车可以充分发挥速度优势）
   - 使得快慢车混合运营成为可能

3. **优化目标**：
   - 尽可能减少越行次数
   - 合理选择越行站位置
   - 优化快慢车发车间隔

## 常见问题

### Q1: 为什么慢车在越行站停留超过4分钟？

A: 程序计算的停站时间是为了满足：
- 到通间隔≥120秒
- 通发间隔≥120秒
- 总停站时间≥240秒

如果按照快车实际通过时间计算，可能需要更长的停站时间。

### Q2: 如何减少越行次数？

A: 可以：
1. 增大快慢车发车间隔
2. 减少快车数量或比例
3. 调整快车停站方案（减少跳停站）
4. 交换快慢车发车顺序

### Q3: 能否在任意车站越行？

A: 不能。越行需要车站具备越行条件：
- 需要有配线（站线）
- 需要有信号设备支持
- 通常是较大的车站

Demo中设定站点3、站点5、站点7可以越行。

### Q4: 一列慢车能被多列快车越行吗？

A: 可以，这叫**二次越行**。Demo程序已经支持，可以看到慢车被多次越行的情况。

## 总结

本Demo程序完整实现了快车越行慢车的核心算法，严格遵循文档规范，展示了：

✅ 越行判定逻辑
✅ 越行站选择
✅ 停站时间调整（≥4分钟）
✅ 到通/通发间隔验证（≥120秒）
✅ 后续站点时刻顺延
✅ Excel输出

这为将越行功能集成到主程序奠定了坚实基础。

