"""
快慢车时刻表模型

整合所有时刻表相关信息的主模型
"""

from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

from .train import Train, ExpressTrain, LocalTrain, TrainType
from .timetable_entry import TimetableEntry
from .overtaking_event import OvertakingEvent


@dataclass
class ExpressLocalTimetable:
    """
    快慢车时刻表
    
    包含完整的快慢车运行图信息
    """
    timetable_id: str                   # 时刻表ID
    timetable_name: str                 # 时刻表名称
    
    # 时间范围（秒）
    start_time: int                     # 开始时间
    end_time: int                       # 结束时间
    
    # 列车集合
    express_trains: List[ExpressTrain] = field(default_factory=list)
    local_trains: List[LocalTrain] = field(default_factory=list)
    
    # 时刻表条目
    timetable_entries: List[TimetableEntry] = field(default_factory=list)
    
    # 越行事件
    overtaking_events: List[OvertakingEvent] = field(default_factory=list)
    
    # 索引结构（用于快速查询）
    _train_dict: Dict[str, Train] = field(default_factory=dict, init=False, repr=False)
    _entries_by_train: Dict[str, List[TimetableEntry]] = field(default_factory=lambda: defaultdict(list), 
                                                                init=False, repr=False)
    _entries_by_station: Dict[str, List[TimetableEntry]] = field(default_factory=lambda: defaultdict(list),
                                                                  init=False, repr=False)
    
    def __post_init__(self):
        """初始化后处理，构建索引"""
        self._rebuild_indexes()
    
    def _rebuild_indexes(self):
        """重建索引结构"""
        self._train_dict.clear()
        self._entries_by_train.clear()
        self._entries_by_station.clear()
        
        # 构建列车字典
        for train in self.express_trains + self.local_trains:
            self._train_dict[train.train_id] = train
        
        # 构建时刻表条目索引
        for entry in self.timetable_entries:
            self._entries_by_train[entry.train_id].append(entry)
            self._entries_by_station[entry.station_id].append(entry)
        
        # 按时间排序
        for entries in self._entries_by_train.values():
            entries.sort(key=lambda e: e.arrival_time)
        for entries in self._entries_by_station.values():
            entries.sort(key=lambda e: e.arrival_time)
    
    # === 添加方法 ===
    
    def add_train(self, train: Train):
        """添加列车"""
        if isinstance(train, ExpressTrain):
            self.express_trains.append(train)
        elif isinstance(train, LocalTrain):
            self.local_trains.append(train)
        self._train_dict[train.train_id] = train
    
    def add_timetable_entry(self, entry: TimetableEntry):
        """添加时刻表条目"""
        self.timetable_entries.append(entry)
        self._entries_by_train[entry.train_id].append(entry)
        self._entries_by_station[entry.station_id].append(entry)
    
    def add_overtaking_event(self, event: OvertakingEvent):
        """添加越行事件"""
        self.overtaking_events.append(event)
    
    # === 查询方法 ===
    
    def get_train(self, train_id: str) -> Optional[Train]:
        """获取列车"""
        return self._train_dict.get(train_id)
    
    def get_train_schedule(self, train_id: str) -> List[TimetableEntry]:
        """获取列车时刻表"""
        return self._entries_by_train.get(train_id, [])
    
    def get_station_schedule(self, station_id: str) -> List[TimetableEntry]:
        """获取车站时刻表"""
        return self._entries_by_station.get(station_id, [])
    
    def get_express_trains_at_time(self, time: int) -> List[ExpressTrain]:
        """获取指定时刻正在运行的快车"""
        result = []
        for train in self.express_trains:
            if train.departure_time <= time <= train.arrival_time:
                result.append(train)
        return result
    
    def get_local_trains_at_time(self, time: int) -> List[LocalTrain]:
        """获取指定时刻正在运行的慢车"""
        result = []
        for train in self.local_trains:
            if train.departure_time <= time <= train.arrival_time:
                result.append(train)
        return result
    
    # === 统计属性 ===
    
    @property
    def total_trains(self) -> int:
        """总列车数"""
        return len(self.express_trains) + len(self.local_trains)
    
    @property
    def express_trains_count(self) -> int:
        """快车数量"""
        return len(self.express_trains)
    
    @property
    def local_trains_count(self) -> int:
        """慢车数量"""
        return len(self.local_trains)
    
    @property
    def express_local_ratio(self) -> float:
        """快慢车比例"""
        if self.local_trains_count == 0:
            return float('inf')
        return self.express_trains_count / self.local_trains_count
    
    @property
    def service_duration(self) -> int:
        """服务时长（秒）"""
        return self.end_time - self.start_time
    
    @property
    def total_overtaking_events(self) -> int:
        """越行事件总数"""
        return len(self.overtaking_events)
    
    # === 分析方法 ===
    
    def calculate_average_headway(self, direction: str = "上行") -> float:
        """
        计算平均发车间隔
        
        Args:
            direction: 方向
            
        Returns:
            平均发车间隔（秒）
        """
        trains = [t for t in self.express_trains + self.local_trains 
                 if t.direction == direction and t.departure_time is not None]
        
        if len(trains) < 2:
            return 0.0
        
        trains.sort(key=lambda t: t.departure_time)
        headways = []
        
        for i in range(len(trains) - 1):
            headway = trains[i + 1].departure_time - trains[i].departure_time
            headways.append(headway)
        
        return sum(headways) / len(headways) if headways else 0.0
    
    def calculate_headway_variance(self, direction: str = "上行") -> float:
        """
        计算发车间隔方差（均衡性指标）
        
        Args:
            direction: 方向
            
        Returns:
            发车间隔方差
        """
        trains = [t for t in self.express_trains + self.local_trains 
                 if t.direction == direction and t.departure_time is not None]
        
        if len(trains) < 2:
            return 0.0
        
        trains.sort(key=lambda t: t.departure_time)
        headways = []
        
        for i in range(len(trains) - 1):
            headway = trains[i + 1].departure_time - trains[i].departure_time
            headways.append(headway)
        
        if not headways:
            return 0.0
        
        avg_headway = sum(headways) / len(headways)
        variance = sum((h - avg_headway) ** 2 for h in headways) / len(headways)
        
        return variance
    
    def get_overtaken_local_trains(self) -> List[LocalTrain]:
        """获取被越行的慢车列表"""
        overtaken_ids = {event.overtaken_train_id for event in self.overtaking_events}
        return [train for train in self.local_trains if train.train_id in overtaken_ids]
    
    def get_train_headways(self, direction: str = "上行") -> List[Tuple[str, str, int]]:
        """
        获取列车发车间隔列表
        
        Args:
            direction: 方向
            
        Returns:
            列表，每项为 (前车ID, 后车ID, 间隔秒数)
        """
        trains = [t for t in self.express_trains + self.local_trains 
                 if t.direction == direction and t.departure_time is not None]
        
        trains.sort(key=lambda t: t.departure_time)
        headways = []
        
        for i in range(len(trains) - 1):
            headway = trains[i + 1].departure_time - trains[i].departure_time
            headways.append((trains[i].train_id, trains[i + 1].train_id, headway))
        
        return headways
    
    def validate_timetable(self) -> List[str]:
        """
        验证时刻表的有效性
        
        Returns:
            问题列表，空列表表示无问题
        """
        issues = []
        
        # 1. 检查是否有列车
        if self.total_trains == 0:
            issues.append("时刻表中没有列车")
        
        # 2. 检查时间范围
        if self.start_time >= self.end_time:
            issues.append(f"时间范围无效：开始时间({self.start_time}) >= 结束时间({self.end_time})")
        
        # 3. 检查列车时刻
        for train in self.express_trains + self.local_trains:
            if train.departure_time is None or train.arrival_time is None:
                issues.append(f"列车{train.train_id}缺少发车或到达时间")
            elif train.departure_time >= train.arrival_time:
                issues.append(f"列车{train.train_id}发车时间({train.departure_time}) >= 到达时间({train.arrival_time})")
        
        # 4. 检查发车间隔（最小追踪间隔）
        min_headway = 120  # 最小追踪间隔120秒
        for direction in ["上行", "下行"]:
            headways = self.get_train_headways(direction)
            for prev_id, next_id, headway in headways:
                if headway < min_headway:
                    issues.append(f"{direction}列车{prev_id}和{next_id}间隔过小({headway}秒 < {min_headway}秒)")
        
        # 5. 检查越行事件
        for event in self.overtaking_events:
            if not event.is_valid_overtaking:
                issues.append(f"越行事件{event.event_id}不满足安全间隔要求")
        
        return issues
    
    def __repr__(self) -> str:
        return (f"ExpressLocalTimetable({self.timetable_name}: "
                f"{self.express_trains_count}快车 + {self.local_trains_count}慢车, "
                f"{self.total_overtaking_events}次越行)")

