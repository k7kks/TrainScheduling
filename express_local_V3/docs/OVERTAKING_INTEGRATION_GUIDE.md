# 越行功能集成指南

## 概述

本文档说明如何将越行Demo程序（`examples/overtaking_demo.py`）中的越行处理逻辑集成到主程序（`main.py`）中。

## 当前状态

### 已完成

✅ **越行Demo程序**（`examples/overtaking_demo.py`）
- 完整实现了越行判定和处理算法
- 展示了4次越行事件
- 生成Excel和图表输出

✅ **越行检测器**（`algorithms/overtaking_detector.py`）
- 已有基本的越行检测逻辑
- 需要完善和集成

✅ **核心算法验证**
- 到通间隔≥120秒 ✓
- 通发间隔≥120秒 ✓
- 越行站停站时间≥240秒 ✓
- 后续站点时刻顺延 ✓

### 待完成

⬜ 将越行处理集成到`algorithms/timetable_builder.py`
⬜ 在`main.py`中启用越行处理
⬜ 在Excel输出中标注越行事件
⬜ 支持越行优化建议

## 集成步骤

### 步骤1：增强TimetableBuilder

修改 `algorithms/timetable_builder.py`，添加越行处理方法：

```python
class TimetableBuilder:
    """时刻表构建器"""
    
    def __init__(self, rail_info: RailInfo, enable_overtaking: bool = True):
        """
        初始化时刻表构建器
        
        Args:
            rail_info: 线路信息
            enable_overtaking: 是否启用越行处理
        """
        self.rail_info = rail_info
        self.enable_overtaking = enable_overtaking
        
        # 越行参数
        self.min_tracking_interval = 120
        self.min_arrival_pass_interval = 120
        self.min_pass_departure_interval = 120
        self.min_overtaking_dwell = 240
    
    def build_timetable(self, timetable: ExpressLocalTimetable) -> ExpressLocalTimetable:
        """
        构建详细时刻表
        
        Args:
            timetable: 快慢车时刻表
            
        Returns:
            构建完成的时刻表
        """
        # 1. 为每列车生成基本时刻表条目
        for train in timetable.all_trains:
            entries = self._generate_entries_for_train(train)
            timetable.add_entries(train.train_id, entries)
        
        # 2. 如果启用越行处理，检测并处理越行
        if self.enable_overtaking:
            self._detect_and_handle_overtaking(timetable)
        
        return timetable
    
    def _detect_and_handle_overtaking(self, timetable: ExpressLocalTimetable):
        """
        检测并处理越行
        
        这是集成越行功能的关键方法
        
        Args:
            timetable: 快慢车时刻表
        """
        # 按方向分组
        for direction in ['上行', '下行']:
            # 获取该方向的快车和慢车
            express_trains = [t for t in timetable.express_trains if t.direction == direction]
            local_trains = [t for t in timetable.local_trains if t.direction == direction]
            
            # 检测每对快慢车是否会发生越行
            for express in express_trains:
                for local in local_trains:
                    self._check_and_handle_single_overtaking(
                        express, local, timetable
                    )
    
    def _check_and_handle_single_overtaking(self,
                                           express: ExpressTrain,
                                           local: LocalTrain,
                                           timetable: ExpressLocalTimetable):
        """
        检查并处理单个快慢车对的越行
        
        Args:
            express: 快车
            local: 慢车
            timetable: 时刻表
        """
        # 前提：快车在慢车后面出发
        if express.departure_time <= local.departure_time:
            return
        
        # 获取慢车和快车的时刻表条目
        local_entries = timetable.get_entries(local.train_id)
        express_entries = timetable.get_entries(express.train_id)
        
        # 查找越行点
        overtaking_station_idx = self._find_overtaking_point(
            local_entries, express_entries
        )
        
        if overtaking_station_idx is not None:
            # 应用越行处理
            self._apply_overtaking(
                local_entries, express_entries, overtaking_station_idx, timetable
            )
            
            # 记录越行事件
            self._record_overtaking_event(
                express, local, overtaking_station_idx, timetable
            )
    
    def _find_overtaking_point(self,
                               local_entries: List[TimetableEntry],
                               express_entries: List[TimetableEntry]) -> Optional[int]:
        """
        找到越行发生的位置
        
        Args:
            local_entries: 慢车时刻表条目
            express_entries: 快车时刻表条目
            
        Returns:
            越行站索引，如果不会越行则返回None
        """
        # 逐站检查
        for i in range(len(local_entries)):
            local_entry = local_entries[i]
            
            # 查找快车在该站的条目
            express_entry = None
            for e in express_entries:
                if e.station_id == local_entry.station_id:
                    express_entry = e
                    break
            
            if express_entry is None:
                continue
            
            # 检查是否会发生追踪间隔冲突
            if express_entry.arrival_time < local_entry.departure_time + self.min_tracking_interval:
                # 会发生冲突，从当前站往前找最近的越行站
                overtaking_station_idx = self._find_nearest_overtaking_station(i)
                return overtaking_station_idx
        
        return None
    
    def _find_nearest_overtaking_station(self, conflict_idx: int) -> Optional[int]:
        """
        从冲突点向前查找最近的越行站
        
        Args:
            conflict_idx: 冲突站索引
            
        Returns:
            越行站索引
        """
        # 从rail_info中获取越行站信息
        # 简化实现：假设部分车站可以越行
        for i in range(conflict_idx, -1, -1):
            # 检查该站是否可以越行
            # 这里需要从rail_info.stationList中获取车站信息
            # 检查车站是否有越行配线
            
            # 简化：假设每隔2站可以越行
            if i % 2 == 0:
                return i
        
        return conflict_idx
    
    def _apply_overtaking(self,
                         local_entries: List[TimetableEntry],
                         express_entries: List[TimetableEntry],
                         overtaking_station_idx: int,
                         timetable: ExpressLocalTimetable):
        """
        应用越行处理
        
        这是从overtaking_demo.py移植过来的核心算法
        
        Args:
            local_entries: 慢车时刻表条目
            express_entries: 快车时刻表条目
            overtaking_station_idx: 越行站索引
            timetable: 时刻表
        """
        # 获取越行站的条目
        local_entry = local_entries[overtaking_station_idx]
        
        # 查找快车在越行站的条目
        express_entry = None
        for e in express_entries:
            if e.station_id == local_entry.station_id:
                express_entry = e
                break
        
        if express_entry is None:
            return
        
        # 计算新的停站时间
        express_pass_time = express_entry.arrival_time
        arrival_to_pass = express_pass_time - local_entry.arrival_time
        
        # 慢车发车时间 = 快车通过时间 + 通发间隔
        new_local_departure = express_pass_time + self.min_pass_departure_interval
        
        # 慢车停站时间
        new_dwell_time = new_local_departure - local_entry.arrival_time
        
        # 确保停站时间至少240秒
        if new_dwell_time < self.min_overtaking_dwell:
            new_dwell_time = self.min_overtaking_dwell
            new_local_departure = local_entry.arrival_time + new_dwell_time
        
        # 计算时间顺延量
        time_shift = new_local_departure - local_entry.departure_time
        
        # 应用越行站的时间调整
        local_entry.departure_time = new_local_departure
        local_entry.dwell_time = new_dwell_time
        local_entry.is_overtaking_station = True
        
        # 顺延后续所有站点的时间
        for i in range(overtaking_station_idx + 1, len(local_entries)):
            local_entries[i].arrival_time += time_shift
            local_entries[i].departure_time += time_shift
    
    def _record_overtaking_event(self,
                                 express: ExpressTrain,
                                 local: LocalTrain,
                                 overtaking_station_idx: int,
                                 timetable: ExpressLocalTimetable):
        """
        记录越行事件
        
        Args:
            express: 快车
            local: 慢车
            overtaking_station_idx: 越行站索引
            timetable: 时刻表
        """
        from models.overtaking_event import OvertakingEvent, OvertakingType
        
        # 创建越行事件对象
        event = OvertakingEvent(
            event_id=f"OVT_{express.train_id}_{local.train_id}",
            overtaking_train_id=express.train_id,
            overtaken_train_id=local.train_id,
            overtaking_station_id=f"S{overtaking_station_idx:02d}",
            overtaking_station_name=f"车站{overtaking_station_idx}",
            direction=local.direction,
            overtaking_type=OvertakingType.SINGLE
        )
        
        # 添加到时刻表
        timetable.add_overtaking_event(event)
```

### 步骤2：修改Main.py

在 `main.py` 中启用越行处理：

```python
class ExpressLocalSchedulerV3:
    def __init__(self, ..., enable_overtaking: bool = True):
        """
        Args:
            ...
            enable_overtaking: 是否启用越行处理
        """
        self.enable_overtaking = enable_overtaking
    
    def _initialize_algorithms(self):
        """初始化算法模块"""
        # ...
        
        # 创建时刻表构建器（启用越行处理）
        self.builder = TimetableBuilder(
            self.rail_info,
            enable_overtaking=self.enable_overtaking
        )
```

### 步骤3：增强Excel输出

修改 `Solution.writeExcel()` 或创建新的输出方法，在Excel中标注越行事件：

```python
def _patch_express_flag(self):
    """
    为每个RouteSolution动态修改输出方法
    使其返回正确的快车标志位和越行标志位
    """
    for rs in self.solution.route_lists:
        is_express = getattr(rs, 'is_express', False)
        is_overtaking_at_station = {}  # 记录在哪些站发生了越行
        
        # 检查该车次是否有越行事件
        for event in self.timetable.overtaking_events:
            if event.overtaken_train_id == rs.car_info.table_num:
                # 这是被越行的慢车
                is_overtaking_at_station[event.overtaking_station_id] = True
        
        # ... 修改输出格式，增加越行标志列
```

### 步骤4：添加越行统计

在程序结束时输出越行统计信息：

```python
def run(self) -> bool:
    """执行完整的调度流程"""
    # ...
    
    # 统计越行事件
    overtaking_events = self.timetable.overtaking_events
    
    print("\n" + "="*60)
    print(f"[越行统计]")
    print(f"  总越行事件: {len(overtaking_events)}次")
    
    # 按车站统计
    station_counts = {}
    for event in overtaking_events:
        station_id = event.overtaking_station_id
        station_counts[station_id] = station_counts.get(station_id, 0) + 1
    
    print(f"  越行站分布:")
    for station_id, count in sorted(station_counts.items()):
        print(f"    {station_id}: {count}次")
    
    # 被越行次数最多的慢车
    overtaken_counts = {}
    for event in overtaking_events:
        train_id = event.overtaken_train_id
        overtaken_counts[train_id] = overtaken_counts.get(train_id, 0) + 1
    
    if overtaken_counts:
        max_overtaken = max(overtaken_counts.items(), key=lambda x: x[1])
        print(f"  被越行最多的慢车: {max_overtaken[0]} ({max_overtaken[1]}次)")
    
    print("="*60)
    
    return True
```

## 测试计划

### 单元测试

创建 `tests/test_overtaking.py`：

```python
"""越行功能单元测试"""

import unittest
from algorithms.timetable_builder import TimetableBuilder
from models.train import ExpressTrain, LocalTrain
from models.express_local_timetable import ExpressLocalTimetable

class TestOvertaking(unittest.TestCase):
    """越行功能测试"""
    
    def setUp(self):
        """设置测试环境"""
        # 创建测试用的线路信息
        self.rail_info = create_test_rail_info()
        self.builder = TimetableBuilder(self.rail_info, enable_overtaking=True)
    
    def test_overtaking_detection(self):
        """测试越行检测"""
        # 创建会发生越行的快慢车
        express = create_test_express_train(departure_time=600)
        local = create_test_local_train(departure_time=150)
        
        timetable = ExpressLocalTimetable()
        timetable.add_train(express)
        timetable.add_train(local)
        
        # 构建时刻表（应该检测到越行）
        timetable = self.builder.build_timetable(timetable)
        
        # 验证：应该有越行事件
        self.assertGreater(len(timetable.overtaking_events), 0)
    
    def test_overtaking_dwell_time(self):
        """测试越行站停站时间"""
        # ... 测试越行站停站时间≥240秒
    
    def test_overtaking_intervals(self):
        """测试到通/通发间隔"""
        # ... 测试到通间隔≥120秒，通发间隔≥120秒
    
    def test_time_propagation(self):
        """测试时刻顺延"""
        # ... 测试越行后后续站点时刻是否正确顺延

if __name__ == '__main__':
    unittest.main()
```

### 集成测试

创建 `tests/test_integration_overtaking.py`：

```python
"""越行功能集成测试"""

def test_full_workflow_with_overtaking():
    """测试完整的快慢车运行图生成（含越行）"""
    
    # 1. 创建调度器（启用越行）
    scheduler = ExpressLocalSchedulerV3(
        rail_info_file="...",
        user_setting_file="...",
        enable_overtaking=True
    )
    
    # 2. 读取数据
    assert scheduler.read_data()
    
    # 3. 生成运行图
    assert scheduler.generate_express_local_timetable()
    
    # 4. 验证越行事件
    overtaking_events = scheduler.timetable.overtaking_events
    assert len(overtaking_events) > 0
    
    # 5. 验证越行站停站时间
    for event in overtaking_events:
        assert event.local_waiting_time >= 240
    
    # 6. 输出Excel
    assert scheduler.write_output()
```

## 参数配置

在 `ExpressLocalConfig` 中添加越行相关参数：

```python
@dataclass
class ExpressLocalConfig:
    """快慢车配置"""
    # ... 现有参数
    
    # 越行参数
    enable_overtaking: bool = True              # 是否启用越行处理
    min_tracking_interval: int = 120            # 最小追踪间隔（秒）
    min_arrival_pass_interval: int = 120        # 最小到通间隔（秒）
    min_pass_departure_interval: int = 120      # 最小通发间隔（秒）
    min_overtaking_dwell: int = 240             # 越行站最小停站时间（秒）
    
    # 越行站配置
    overtaking_stations: Optional[List[str]] = None  # 可越行的车站ID列表
    auto_detect_overtaking_stations: bool = True     # 是否自动检测越行站
```

## 越行优化建议

根据越行事件的分析，可以提供优化建议：

```python
def analyze_overtaking_avoidability(timetable: ExpressLocalTimetable):
    """
    分析越行是否可以避免
    
    Args:
        timetable: 时刻表
        
    Returns:
        优化建议列表
    """
    suggestions = []
    
    for event in timetable.overtaking_events:
        # 分析该越行是否可以通过调整发车间隔避免
        if can_avoid_by_headway_adjustment(event):
            suggestions.append({
                'event': event,
                'method': '调整发车间隔',
                'detail': f'将快车{event.overtaking_train_id}的发车时间推迟{calc_delay(event)}秒'
            })
        
        # 分析是否可以通过交换发车顺序避免
        if can_avoid_by_swap_order(event):
            suggestions.append({
                'event': event,
                'method': '交换发车顺序',
                'detail': f'让快车{event.overtaking_train_id}在慢车{event.overtaken_train_id}之前发车'
            })
    
    return suggestions
```

## Excel输出格式

在Excel输出中增加越行相关列：

| 车次 | 车站 | 到站时间 | 发车时间 | 停站时间 | **是否越行站** | **越行快车** | **待避时间** |
|------|------|----------|----------|----------|----------------|--------------|--------------|
| L01  | 站点6 | 02:17:00 | 02:23:00 | 360秒    | **是**         | **E02**      | **330秒**    |

## 可视化输出

增强可视化功能，在运行图中标注越行点：

```python
def visualize_timetable_with_overtaking(timetable: ExpressLocalTimetable,
                                       output_file: str):
    """
    可视化运行图（标注越行点）
    
    Args:
        timetable: 时刻表
        output_file: 输出文件路径
    """
    # 生成运行图图表
    # 用绿色圆圈标注越行点
    # 用红色虚线标注快车越行慢车的位置
```

## 性能优化

对于大规模运行图，越行检测可能比较耗时，可以优化：

1. **并行处理**：对不同方向的列车并行检测越行
2. **提前终止**：如果发车间隔足够大，可以提前判定不会越行
3. **缓存**：缓存已经计算过的越行判定结果

## 注意事项

1. **越行站选择**：
   - 需要从rail_info中获取车站信息，判断是否有越行配线
   - 优先选择离冲突点最近的越行站
   - 考虑越行站的通过能力

2. **二次越行**：
   - 需要检测一列慢车是否会被多列快车越行
   - 需要累计越行站的停站时间
   - 需要处理时刻顺延的叠加效应

3. **边界情况**：
   - 首站和末站不应作为越行站
   - 小交路慢车的折返站附近需要特殊处理
   - 出入库列车的越行处理

4. **性能考虑**：
   - 对于100+列车的大规模运行图，越行检测可能需要1-2秒
   - 需要优化算法，避免重复计算

## 后续工作

1. **越行优化算法**：
   - 实现越行优化建议
   - 自动调整发车间隔以减少越行
   - 自动交换发车顺序以避免越行

2. **越行站选择优化**：
   - 考虑越行站的位置、设备等因素
   - 优化越行站的选择策略

3. **多目标优化**：
   - 在均衡性和越行次数之间平衡
   - 考虑乘客旅行时间的影响

4. **实时调整**：
   - 支持运营过程中的实时越行调整
   - 处理延误情况下的越行重新安排

## 总结

越行功能是快慢车运行图编制的关键功能。通过以上集成步骤，可以将越行Demo中验证的核心算法集成到主程序中，实现完整的快慢车运行图自动编制功能，包括：

✅ 越行自动检测
✅ 越行时刻自动调整
✅ 越行事件记录和统计
✅ 越行可视化展示
✅ 越行优化建议

这将大大提升程序的实用性和智能化水平。

