"""
时刻表构建器

将列车信息和时刻构建成完整的时刻表
"""

from typing import List, Dict, Optional
import sys
import os

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
express_local_v3_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(express_local_v3_dir)
src_dir = os.path.join(project_root, 'src')

if project_root not in sys.path:
    sys.path.insert(0, project_root)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
if express_local_v3_dir not in sys.path:
    sys.path.insert(0, express_local_v3_dir)

# 导入src模块
from Station import Station
from Path import Path
from RailInfo import RailInfo
from Platform import Platform

# 导入models（使用绝对导入）
from models.train import Train, ExpressTrain, LocalTrain
from models.timetable_entry import TimetableEntry
from models.express_local_timetable import ExpressLocalTimetable


class TimetableBuilder:
    """
    时刻表构建器
    
    根据列车和线路信息，构建详细的时刻表
    """
    
    def __init__(self, rail_info: RailInfo):
        """
        初始化构建器
        
        Args:
            rail_info: 线路信息
        """
        self.rail_info = rail_info
        
        # 获取车站列表（按线路顺序）
        self.stations = self._get_ordered_stations()
    
    def _get_ordered_stations(self) -> List[Station]:
        """获取按线路顺序排列的车站列表"""
        stations = list(self.rail_info.stationList.values())
        # Station对象使用centerKp属性表示公里标
        stations.sort(key=lambda s: s.centerKp)
        return stations
    
    def build_timetable(self, timetable: ExpressLocalTimetable) -> ExpressLocalTimetable:
        """
        为时刻表中的所有列车构建详细时刻
        
        Args:
            timetable: 快慢车时刻表（只包含列车基本信息）
            
        Returns:
            完整的时刻表（包含所有时刻表条目）
        """
        # 为每列车构建时刻
        all_trains = timetable.express_trains + timetable.local_trains
        
        for train in all_trains:
            entries = self._build_train_schedule(train)
            for entry in entries:
                timetable.add_timetable_entry(entry)
        
        # 重建索引
        timetable._rebuild_indexes()
        
        return timetable
    
    def _build_train_schedule(self, train: Train) -> List[TimetableEntry]:
        """
        为单列车构建时刻表
        
        注意：应该根据路径的站台码序列(path.nodeList)生成时刻表，而不是根据车站列表。
        因为一个车站可能有多个站台（如折返站），路径可能经过同一车站的不同站台。
        
        Args:
            train: 列车对象
            
        Returns:
            时刻表条目列表
        """
        entries = []
        
        # 【关键修复】应该根据train的路径来生成时刻表
        # 但在这个阶段，我们还没有路径信息，所以先按车站生成
        # 后续在main.py中会根据path.nodeList调整
        
        # 确定该车经过的车站
        train_stations = self._get_train_stations(train)
        
        # 从起点开始，逐站计算时刻
        current_time = train.departure_time
        
        for i, station in enumerate(train_stations):
            # 判断是否停车
            is_stop = train.stops_at_station(station.id)
            is_skip = not is_stop
            
            # 计算到达时间
            if i == 0:
                # 起点站：到达时间=发车时间
                arrival_time = current_time
            else:
                # 中间站：到达时间=上一站发车时间+区间运行时间
                prev_station = train_stations[i-1]
                running_time = self._get_section_running_time(
                    prev_station, station, train
                )
                arrival_time = current_time + running_time
            
            # 计算停站时间和发车时间
            if is_stop:
                dwell_time = train.get_dwell_time(station.id)
            else:
                dwell_time = 0  # 跳停不停车
            
            departure_time = arrival_time + dwell_time
            
            # 获取正确的站台目的地码（根据列车方向选择站台）
            dest_code = self._get_platform_code(station, train.direction)
            
            # 创建时刻表条目
            entry = TimetableEntry(
                train_id=train.train_id,
                station_id=station.id,  # 使用车站ID
                station_name=station.name,
                arrival_time=arrival_time,
                departure_time=departure_time,
                dwell_time=dwell_time,
                is_stop=is_stop,
                is_skip=is_skip,
                platform_id=dest_code,  # 站台ID（内部引用）
                dest_code=dest_code  # 站台目的地码（用于输出）
            )
            
            entries.append(entry)
            
            # 更新当前时间为发车时间
            current_time = departure_time
        
        return entries
    
    def _get_train_stations(self, train: Train) -> List[Station]:
        """
        获取列车经过的车站列表
        
        Args:
            train: 列车对象
            
        Returns:
            车站列表（按列车行驶方向排序）
        """
        # 获取基础车站列表
        stations = self.stations.copy()
        
        # 如果是小交路，只走部分站
        if isinstance(train, LocalTrain) and train.is_short_route:
            # 走到折返站
            if train.turnback_station:
                turnback_idx = next(
                    (i for i, s in enumerate(stations) 
                     if s.id == train.turnback_station),
                    len(stations) // 2
                )
                stations = stations[:turnback_idx+1]
        
        # 【关键修复】如果是下行列车，车站顺序需要反转
        # self.stations是按公里标升序排列（上行方向）
        # 下行列车应该按公里标降序（反向行驶）
        if train.direction == "下行":
            stations = list(reversed(stations))
        
        return stations
    
    def _get_section_running_time(self, 
                                  from_station: Station,
                                  to_station: Station,
                                  train: Train) -> int:
        """
        获取区间运行时间
        
        Args:
            from_station: 起始车站
            to_station: 到达车站
            train: 列车对象
            
        Returns:
            区间运行时间（秒）
        """
        # 尝试从Path中获取实际的区间运行时间
        # 简化实现：使用固定值
        
        base_time = 120  # 基础区间运行时间（秒）
        
        # 快车运行速度更快
        if isinstance(train, ExpressTrain):
            return int(base_time / 1.2)
        
        return base_time
    
    def update_overtaking_entries(self,
                                  timetable: ExpressLocalTimetable) -> ExpressLocalTimetable:
        """
        根据越行事件更新时刻表条目
        
        Args:
            timetable: 时刻表（包含越行事件）
            
        Returns:
            更新后的时刻表
        """
        for event in timetable.overtaking_events:
            # 更新被越行慢车的时刻表条目
            local_entries = timetable.get_train_schedule(event.overtaken_train_id)
            
            for entry in local_entries:
                if entry.station_id == event.overtaking_station_id:
                    # 标记为越行
                    entry.is_overtaking = True
                    entry.overtaken_by = event.overtaking_train_id
                    entry.waiting_time = event.local_waiting_time - event.local_normal_dwell
                    
                    # 更新发车时间
                    entry.departure_time = event.local_departure_time
                    entry.dwell_time = event.local_waiting_time
                
                # 后续车站的时刻需要顺延
                if self._is_after_station(entry.station_id, event.overtaking_station_id):
                    time_delay = event.local_waiting_time - event.local_normal_dwell
                    entry.arrival_time += time_delay
                    entry.departure_time += time_delay
        
        return timetable
    
    def _is_after_station(self, station_id: str, reference_station_id: str) -> bool:
        """
        判断station_id是否在reference_station_id之后
        
        Args:
            station_id: 待判断车站ID
            reference_station_id: 参考车站ID
            
        Returns:
            True if station_id在reference_station_id之后
        """
        try:
            station_idx = next(i for i, s in enumerate(self.stations) if s.id == station_id)
            ref_idx = next(i for i, s in enumerate(self.stations) if s.id == reference_station_id)
            return station_idx > ref_idx
        except StopIteration:
            return False
    
    def _get_platform_code(self, station, direction: str) -> str:
        """
        根据车站和方向获取正确的站台目的地码
        
        Args:
            station: 车站对象
            direction: 方向（"上行"或"下行"）
            
        Returns:
            站台目的地码（destcode）
        """
        # 确定站台方向
        if direction == "上行":
            target_direction = Platform.Direction.LEFT
        else:  # 下行
            target_direction = Platform.Direction.RIGHT
        
        # 在车站的站台列表中查找匹配方向的正常站台（非虚拟、非折返）
        for platform in station.platformList:
            # 检查platform是否有dir属性
            if not hasattr(platform, 'dir'):
                continue
            # 优先选择正常站台
            if (platform.dir == target_direction and 
                not platform.is_virtual and
                platform.platform_type.value == "Normal"):
                return platform.dest_code
        
        # 如果没有找到正常站台，选择任何匹配方向的站台
        for platform in station.platformList:
            if hasattr(platform, 'dir') and platform.dir == target_direction:
                return platform.dest_code
        
        # 如果还没找到，返回第一个站台（兜底策略）
        if station.platformList:
            return station.platformList[0].dest_code
        
        # 如果车站没有站台，返回车站ID作为后备
        print(f"[WARNING] 车站{station.name}没有找到合适的站台，使用车站ID")
        return station.id

