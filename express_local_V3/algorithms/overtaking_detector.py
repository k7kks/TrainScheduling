"""
越行检测器

检测快车是否会越行慢车，并判定越行的必然性
"""

from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
import sys
import os

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
express_local_v3_dir = os.path.dirname(current_dir)
if express_local_v3_dir not in sys.path:
    sys.path.insert(0, express_local_v3_dir)

# 导入models（使用绝对导入）
from models.express_local_timetable import ExpressLocalTimetable
from models.train import ExpressTrain, LocalTrain
from models.overtaking_event import OvertakingEvent, OvertakingType


@dataclass
class OvertakingDetectionConfig:
    """越行检测配置"""
    min_tracking_interval: int = 120        # 最小追踪间隔（秒）
    min_arrival_pass_interval: int = 120    # 最小到通间隔（秒）
    min_pass_departure_interval: int = 120  # 最小通发间隔（秒）
    min_overtaking_dwell: int = 240         # 越行站最小停站时间（秒）
    
    # 运行时间参数（用于估算）
    section_running_time: int = 120         # 区间运行时间（秒）
    express_speed_factor: float = 1.2       # 快车速度系数


class OvertakingDetector:
    """
    越行检测器
    
    主要功能：
    1. 检测快车是否会追上慢车
    2. 判断是否需要越行
    3. 确定越行发生的位置
    4. 分析越行是否可避免
    """
    
    def __init__(self, config: OvertakingDetectionConfig = None):
        """
        初始化越行检测器
        
        Args:
            config: 越行检测配置
        """
        self.config = config or OvertakingDetectionConfig()
    
    def detect_all_overtaking_events(self,
                                     timetable: ExpressLocalTimetable,
                                     station_list: List[str]) -> List[OvertakingEvent]:
        """
        检测所有越行事件
        
        Args:
            timetable: 快慢车时刻表
            station_list: 车站ID列表（按线路顺序）
            
        Returns:
            越行事件列表
        """
        events = []
        
        # 遍历所有快车
        for express in timetable.express_trains:
            # 遍历所有慢车
            for local in timetable.local_trains:
                # 检查这对快慢车是否会发生越行
                event = self._check_overtaking_pair(express, local, station_list)
                if event is not None:
                    events.append(event)
        
        return events
    
    def _check_overtaking_pair(self,
                               express: ExpressTrain,
                               local: LocalTrain,
                               station_list: List[str]) -> Optional[OvertakingEvent]:
        """
        检查一对快慢车是否会发生越行
        
        Args:
            express: 快车
            local: 慢车
            station_list: 车站ID列表
            
        Returns:
            越行事件（如果发生越行），否则返回None
        """
        # 前提条件：快车在慢车后面出发
        if express.departure_time <= local.departure_time:
            return None
        
        # 计算快慢车的发车间隔
        initial_headway = express.departure_time - local.departure_time
        
        # 判定条件：检查快车是否会在线路中追上慢车
        # 沿线路逐站检查
        for i, station_id in enumerate(station_list):
            # 估算慢车和快车到达该站的时间
            local_arrival = self._estimate_arrival_time(local, station_id, i)
            express_arrival = self._estimate_arrival_time(express, station_id, i)
            
            # 如果快车到达时间 < 慢车到达时间 + 最小追踪间隔，则会发生冲突
            if express_arrival < local_arrival + self.config.min_tracking_interval:
                # 需要在该站或之前的某站进行越行
                overtaking_station = self._find_overtaking_station(
                    station_list, i, local, express
                )
                
                if overtaking_station:
                    # 创建越行事件
                    event = self._create_overtaking_event(
                        express, local, overtaking_station, station_list
                    )
                    return event
        
        # 没有发生越行
        return None
    
    def _estimate_arrival_time(self,
                               train,
                               station_id: str,
                               station_index: int) -> int:
        """
        估算列车到达指定车站的时间
        
        Args:
            train: 列车对象
            station_id: 车站ID
            station_index: 车站在线路中的序号
            
        Returns:
            估计到达时间（秒）
        """
        if train.departure_time is None:
            return 0
        
        # 计算从起点到该站的累计时间
        # 区间运行时间 × 站数 + 停站时间 × 停站次数
        
        # 区间运行时间
        section_time = self.config.section_running_time
        if isinstance(train, ExpressTrain):
            section_time = int(section_time / self.config.express_speed_factor)
        
        running_time = station_index * section_time
        
        # 停站时间
        dwell_time = 0
        for i in range(station_index):
            if train.stops_at_station(f"S{i+1:02d}"):  # 简化：假设车站ID格式为S01, S02, ...
                dwell_time += train.get_dwell_time(f"S{i+1:02d}")
        
        return train.departure_time + running_time + dwell_time
    
    def _find_overtaking_station(self,
                                 station_list: List[str],
                                 conflict_index: int,
                                 local: LocalTrain,
                                 express: ExpressTrain) -> Optional[str]:
        """
        找到合适的越行站
        
        Args:
            station_list: 车站列表
            conflict_index: 冲突发生的车站序号
            local: 慢车
            express: 快车
            
        Returns:
            越行站ID（如果找到），否则返回None
        """
        # 从冲突点向前查找，找到离冲突点最近的越行站
        # 简化实现：假设所有车站都可以越行
        # 实际应该检查车站是否有越行条件（配线等）
        
        # 从冲突站往前找
        for i in range(conflict_index, -1, -1):
            station_id = station_list[i]
            
            # 检查该站是否可以越行（简化：都可以）
            # 实际应该从RailInfo中获取车站信息，检查是否有越行配线
            
            return station_id
        
        return None
    
    def _create_overtaking_event(self,
                                 express: ExpressTrain,
                                 local: LocalTrain,
                                 overtaking_station: str,
                                 station_list: List[str]) -> OvertakingEvent:
        """
        创建越行事件对象
        
        Args:
            express: 快车
            local: 慢车
            overtaking_station: 越行站ID
            station_list: 车站列表
            
        Returns:
            越行事件
        """
        # 获取越行站序号
        station_index = station_list.index(overtaking_station)
        
        # 估算慢车到达和发车时间
        local_arrival = self._estimate_arrival_time(local, overtaking_station, station_index)
        
        # 慢车在越行站的停站时间（包含待避）
        local_dwell = max(
            local.get_dwell_time(overtaking_station),
            self.config.min_overtaking_dwell
        )
        local_departure = local_arrival + local_dwell
        
        # 估算快车通过时间
        express_pass = self._estimate_arrival_time(express, overtaking_station, station_index)
        
        # 计算间隔
        arrival_to_pass = express_pass - local_arrival
        pass_to_departure = local_departure - express_pass
        
        # 创建事件
        event = OvertakingEvent(
            event_id=f"OVT_{express.train_id}_{local.train_id}",
            overtaking_train_id=express.train_id,
            overtaken_train_id=local.train_id,
            overtaking_station_id=overtaking_station,
            overtaking_station_name=f"车站{station_index+1}",
            direction=local.direction,
            local_arrival_time=local_arrival,
            local_departure_time=local_departure,
            express_pass_time=express_pass,
            arrival_to_pass_interval=arrival_to_pass,
            pass_to_departure_interval=pass_to_departure,
            overtaking_type=OvertakingType.SINGLE,
            local_waiting_time=local_dwell,
            local_normal_dwell=local.get_dwell_time(overtaking_station)
        )
        
        # 分析是否可以避免越行
        self._analyze_overtaking_avoidability(event, express, local)
        
        return event
    
    def _analyze_overtaking_avoidability(self,
                                         event: OvertakingEvent,
                                         express: ExpressTrain,
                                         local: LocalTrain):
        """
        分析越行是否可以避免
        
        更新event的is_avoidable, can_adjust_headway, can_swap_order等字段
        
        Args:
            event: 越行事件
            express: 快车
            local: 慢车
        """
        # 计算快慢车的初始发车间隔
        initial_headway = express.departure_time - local.departure_time
        
        # 判定1：如果发车间隔足够大（大于全程旅行时间差），可能不会越行
        if express.get_travel_time() > 0 and local.get_travel_time() > 0:
            travel_time_diff = local.get_travel_time() - express.get_travel_time()
            
            if initial_headway > travel_time_diff:
                event.is_avoidable = True
                event.can_adjust_headway = True
                event.optimization_suggestion = "增大发车间隔可以避免越行"
                return
        
        # 判定2：如果慢车是小交路，快车是大交路，可以交换顺序
        if local.is_short_route and not express.is_short_route:
            event.is_avoidable = True
            event.can_swap_order = True
            event.optimization_suggestion = "快车大交路追踪慢车小交路可以避免越行"
            return
        
        # 判定3：如果间隔可以适当调整，可能避免越行
        if initial_headway > self.config.min_tracking_interval:
            event.is_avoidable = True
            event.can_adjust_headway = True
            event.optimization_suggestion = "适当调整发车间隔可能避免越行"
            return
        
        # 否则，越行不可避免
        event.is_avoidable = False
        event.optimization_suggestion = "越行不可避免，建议保持现状"
    
    def detect_double_overtaking(self,
                                events: List[OvertakingEvent]) -> List[OvertakingEvent]:
        """
        检测二次越行（一列慢车被两列快车越行）
        
        Args:
            events: 越行事件列表
            
        Returns:
            二次越行事件列表
        """
        # 按被越行的慢车分组
        overtaken_groups = {}
        for event in events:
            local_id = event.overtaken_train_id
            if local_id not in overtaken_groups:
                overtaken_groups[local_id] = []
            overtaken_groups[local_id].append(event)
        
        # 找出被越行2次或以上的慢车
        double_overtaking_events = []
        for local_id, event_list in overtaken_groups.items():
            if len(event_list) >= 2:
                # 标记为二次越行
                for event in event_list:
                    event.overtaking_type = OvertakingType.DOUBLE
                    double_overtaking_events.append(event)
        
        return double_overtaking_events

