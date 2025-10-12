"""
快慢车运行图生成器

基于快慢车铺画规则的核心算法：
1. 首先均匀铺画快车运行线
2. 然后根据均衡性及缩短额外停站待避时间要求，铺画慢车运行线
3. 在铺画每条慢车运行线时，在从上一同向列车出发时刻之后的均匀时间段内搜索旅行时间最短的运行线
"""

from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
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
from UserSetting import UserSetting

# 导入models（使用绝对导入）
from models.train import ExpressTrain, LocalTrain, TrainType
from models.express_local_timetable import ExpressLocalTimetable


@dataclass
class ExpressLocalConfig:
    """快慢车配置"""
    # 快慢车比例
    express_ratio: float = 0.5          # 快车比例（相对于总车数）
    
    # 发车间隔
    target_headway: int = 180           # 目标发车间隔（秒）
    min_headway: int = 120              # 最小发车间隔（秒）
    max_headway: int = 600              # 最大发车间隔（秒）
    
    # 快车停站方案
    express_stop_ratio: float = 0.6     # 快车停站比例
    express_skip_pattern: Optional[List[int]] = None  # 快车跳停模式（车站序号列表）
    
    # 越行参数
    min_overtaking_interval: int = 120  # 最小到通/通发间隔（秒）
    min_overtaking_dwell: int = 240     # 越行站最小停站时间（秒）
    
    # 运行时间参数
    base_running_time_per_section: int = 120  # 基础区间运行时间（秒）
    base_dwell_time: int = 40           # 基础停站时间（秒）
    express_speed_factor: float = 1.2   # 快车速度系数
    
    # 大小交路参数
    enable_short_route: bool = True     # 是否启用小交路
    short_route_ratio: float = 0.5      # 小交路比例（相对于慢车）


class ExpressLocalGenerator:
    """
    快慢车运行图生成器
    
    实现快慢车铺画的核心算法
    """
    
    def __init__(self, config: ExpressLocalConfig = None):
        """
        初始化生成器
        
        Args:
            config: 快慢车配置
        """
        self.config = config or ExpressLocalConfig()
        self.rail_info: Optional[RailInfo] = None
        self.user_setting: Optional[UserSetting] = None
    
    def generate(self, 
                 rail_info: RailInfo,
                 user_setting: UserSetting,
                 start_time: int,
                 end_time: int) -> ExpressLocalTimetable:
        """
        生成快慢车运行图
        
        Args:
            rail_info: 线路信息
            user_setting: 用户设置
            start_time: 开始时间（秒）
            end_time: 结束时间（秒）
            
        Returns:
            快慢车时刻表
        """
        self.rail_info = rail_info
        self.user_setting = user_setting
        
        # 创建时刻表对象
        timetable = ExpressLocalTimetable(
            timetable_id=f"express_local_{start_time}_{end_time}",
            timetable_name="快慢车运行图",
            start_time=start_time,
            end_time=end_time
        )
        
        # 获取车站列表
        stations = self._get_station_list()
        
        # 计算需要的列车数
        service_duration = end_time - start_time
        total_trains = self._calculate_total_trains(service_duration)
        express_count = int(total_trains * self.config.express_ratio)
        local_count = total_trains - express_count
        
        # 步骤1：均匀铺画快车
        express_trains = self._generate_express_trains(
            express_count, start_time, end_time, stations
        )
        for train in express_trains:
            timetable.add_train(train)
        
        # 步骤2：铺画慢车（考虑均衡性和旅行时间）
        local_trains = self._generate_local_trains(
            local_count, start_time, end_time, stations, express_trains
        )
        for train in local_trains:
            timetable.add_train(train)
        
        # 重建索引
        timetable._rebuild_indexes()
        
        return timetable
    
    def _get_station_list(self) -> List[Station]:
        """获取车站列表"""
        if self.rail_info is None:
            return []
        
        # 从rail_info获取车站列表
        stations = list(self.rail_info.stationList.values())
        # 按公里标排序（Station对象使用centerKp属性）
        stations.sort(key=lambda s: s.centerKp)
        
        return stations
    
    def _calculate_total_trains(self, service_duration: int) -> int:
        """
        计算需要的总列车数
        
        Args:
            service_duration: 服务时长（秒）
            
        Returns:
            总列车数
        """
        # 根据服务时长和发车间隔计算
        trains_needed = service_duration // self.config.target_headway
        
        # 至少需要2列车
        return max(2, trains_needed)
    
    def _generate_express_trains(self,
                                  count: int,
                                  start_time: int,
                                  end_time: int,
                                  stations: List[Station]) -> List[ExpressTrain]:
        """
        生成快车列表（均匀铺画）
        
        Args:
            count: 快车数量
            start_time: 开始时间
            end_time: 结束时间
            stations: 车站列表
            
        Returns:
            快车列表
        """
        express_trains = []
        
        if count == 0:
            return express_trains
        
        # 计算快车发车间隔（均匀分布）
        service_duration = end_time - start_time
        express_headway = service_duration / count if count > 0 else self.config.target_headway
        
        # 确定快车停站方案
        skip_stations = self._determine_express_skip_stations(stations)
        
        # 生成快车
        for i in range(count):
            train_id = f"E{i+1:03d}"
            departure_time = start_time + int(i * express_headway)
            
            # 根据编号确定方向：奇数上行，偶数下行
            direction = "上行" if (i % 2) == 0 else "下行"
            
            # 计算快车全程时间
            travel_time = self._calculate_express_travel_time(stations, skip_stations)
            arrival_time = departure_time + travel_time
            
            # 创建快车对象
            train = ExpressTrain(
                train_id=train_id,
                train_name=f"快车{i+1}",
                train_type=TrainType.EXPRESS,
                route_id="R001",  # 默认大交路
                direction=direction,
                stop_stations=[s.id for s in stations if s.id not in skip_stations],
                skip_stations=skip_stations,
                departure_time=departure_time,
                arrival_time=arrival_time,
                express_stop_ratio=self.config.express_stop_ratio
            )
            
            express_trains.append(train)
        
        return express_trains
    
    def _determine_express_skip_stations(self, stations: List[Station]) -> Set[str]:
        """
        确定快车跳停车站
        
        Args:
            stations: 车站列表
            
        Returns:
            跳停车站ID集合
        """
        skip_stations = set()
        
        # 如果指定了跳停模式，使用指定模式
        if self.config.express_skip_pattern:
            for idx in self.config.express_skip_pattern:
                if 0 <= idx < len(stations):
                    skip_stations.add(stations[idx].id)
            return skip_stations
        
        # 否则，根据停站比例自动确定
        # 始发站和终到站不跳停
        total_stations = len(stations)
        stop_count = int(total_stations * self.config.express_stop_ratio)
        skip_count = total_stations - stop_count
        
        # 从中间车站中选择跳停站（均匀分布）
        if skip_count > 0 and total_stations > 2:
            skip_interval = (total_stations - 2) / skip_count
            for i in range(skip_count):
                skip_idx = int(1 + i * skip_interval)
                if 0 < skip_idx < total_stations - 1:
                    skip_stations.add(stations[skip_idx].id)
        
        return skip_stations
    
    def _calculate_express_travel_time(self, 
                                       stations: List[Station],
                                       skip_stations: Set[str]) -> int:
        """
        计算快车全程旅行时间
        
        Args:
            stations: 车站列表
            skip_stations: 跳停车站集合
            
        Returns:
            旅行时间（秒）
        """
        total_time = 0
        
        for i in range(len(stations) - 1):
            # 区间运行时间（快车速度快）
            section_time = int(self.config.base_running_time_per_section / 
                             self.config.express_speed_factor)
            total_time += section_time
            
            # 停站时间
            station = stations[i]
            if station.id not in skip_stations:
                total_time += 30  # 快车停站30秒
        
        # 最后一站停站时间
        total_time += 30
        
        return total_time
    
    def _generate_local_trains(self,
                               count: int,
                               start_time: int,
                               end_time: int,
                               stations: List[Station],
                               express_trains: List[ExpressTrain]) -> List[LocalTrain]:
        """
        生成慢车列表（考虑均衡性和旅行时间最短）
        
        Args:
            count: 慢车数量
            start_time: 开始时间
            end_time: 结束时间
            stations: 车站列表
            express_trains: 已生成的快车列表
            
        Returns:
            慢车列表
        """
        local_trains = []
        
        if count == 0:
            return local_trains
        
        # 计算慢车发车间隔（目标均匀分布）
        service_duration = end_time - start_time
        target_local_headway = service_duration / count if count > 0 else self.config.target_headway
        
        # 确定大小交路分配
        small_route_count = 0
        if self.config.enable_short_route:
            small_route_count = int(count * self.config.short_route_ratio)
        large_route_count = count - small_route_count
        
        # 获取所有列车（快车+已生成的慢车）的发车时间，用于计算间隔
        all_departure_times = [train.departure_time for train in express_trains]
        
        # 生成慢车
        train_idx = 0
        current_time = start_time
        
        while train_idx < count and current_time < end_time:
            train_id = f"L{train_idx+1:03d}"
            
            # 判断是否为小交路
            is_short = train_idx < small_route_count
            
            # 在均匀时间段内搜索旅行时间最短的发车时刻
            best_departure_time = self._find_best_departure_time(
                current_time,
                target_local_headway,
                all_departure_times,
                express_trains,
                stations,
                is_short
            )
            
            # 根据编号确定方向：奇数上行，偶数下行
            direction = "上行" if (train_idx % 2) == 0 else "下行"
            
            # 计算慢车全程时间
            travel_time = self._calculate_local_travel_time(stations, is_short)
            arrival_time = best_departure_time + travel_time
            
            # 创建慢车对象
            train = LocalTrain(
                train_id=train_id,
                train_name=f"慢车{train_idx+1}{'(小)' if is_short else ''}",
                train_type=TrainType.LOCAL,
                route_id="R002" if is_short else "R001",
                direction=direction,
                stop_stations=[s.id for s in stations],
                skip_stations=set(),  # 慢车站站停
                departure_time=best_departure_time,
                arrival_time=arrival_time,
                is_short_route=is_short,
                turnback_station=stations[len(stations)//2].id if is_short else None
            )
            
            local_trains.append(train)
            all_departure_times.append(best_departure_time)
            
            # 更新时间和索引
            current_time = best_departure_time + target_local_headway
            train_idx += 1
        
        return local_trains
    
    def _find_best_departure_time(self,
                                   target_time: int,
                                   search_window: float,
                                   existing_departures: List[int],
                                   express_trains: List[ExpressTrain],
                                   stations: List[Station],
                                   is_short_route: bool) -> int:
        """
        在均匀时间段内搜索旅行时间最短的发车时刻
        
        这是实现"均衡发车+最短旅行时间"的关键方法
        
        Args:
            target_time: 目标发车时间（均匀分布）
            search_window: 搜索窗口（秒）
            existing_departures: 已有的发车时间列表
            express_trains: 快车列表
            stations: 车站列表
            is_short_route: 是否为小交路
            
        Returns:
            最佳发车时间
        """
        # 搜索窗口：目标时间前后各search_window/2
        search_start = int(target_time - search_window / 2)
        search_end = int(target_time + search_window / 2)
        
        # 搜索步长：10秒
        search_step = 10
        
        best_time = target_time
        best_score = float('inf')  # 越小越好
        
        for candidate_time in range(search_start, search_end, search_step):
            # 计算该时刻的得分
            # 得分 = 额外待避时间 + 间隔偏差惩罚
            
            # 1. 计算额外待避时间
            overtaking_delay = self._estimate_overtaking_delay(
                candidate_time, express_trains, stations, is_short_route
            )
            
            # 2. 计算与已有列车的间隔偏差
            headway_penalty = self._calculate_headway_penalty(
                candidate_time, existing_departures
            )
            
            # 综合得分
            score = overtaking_delay + headway_penalty * 0.5
            
            if score < best_score:
                best_score = score
                best_time = candidate_time
        
        return best_time
    
    def _estimate_overtaking_delay(self,
                                    departure_time: int,
                                    express_trains: List[ExpressTrain],
                                    stations: List[Station],
                                    is_short_route: bool) -> int:
        """
        估计慢车被越行的额外停站时间
        
        Args:
            departure_time: 慢车发车时间
            express_trains: 快车列表
            stations: 车站列表
            is_short_route: 是否为小交路
            
        Returns:
            估计的额外停站时间（秒）
        """
        # 简化实现：检查是否有快车会追上这列慢车
        total_delay = 0
        
        # 计算慢车的旅行时间
        local_travel_time = self._calculate_local_travel_time(stations, is_short_route)
        local_arrival_time = departure_time + local_travel_time
        
        for express in express_trains:
            # 检查是否会发生越行
            if express.departure_time > departure_time:
                # 快车在慢车后面出发
                # 计算快车是否会追上慢车
                time_diff = express.departure_time - departure_time
                
                # 如果快车在慢车到达终点前出发，且速度更快，可能会越行
                if time_diff < local_travel_time:
                    # 估计越行会增加240秒（4分钟）的待避时间
                    total_delay += 240
        
        return total_delay
    
    def _calculate_headway_penalty(self,
                                   candidate_time: int,
                                   existing_departures: List[int]) -> float:
        """
        计算发车间隔偏差惩罚
        
        Args:
            candidate_time: 候选发车时间
            existing_departures: 已有发车时间列表
            
        Returns:
            间隔偏差惩罚值
        """
        if not existing_departures:
            return 0.0
        
        # 找到最近的前后两列车
        sorted_departures = sorted(existing_departures)
        
        # 找到紧邻的前一列车和后一列车
        prev_time = None
        next_time = None
        
        for dep_time in sorted_departures:
            if dep_time < candidate_time:
                prev_time = dep_time
            elif dep_time > candidate_time:
                next_time = dep_time
                break
        
        penalty = 0.0
        
        # 与前车的间隔偏差
        if prev_time is not None:
            headway = candidate_time - prev_time
            if headway < self.config.min_headway:
                # 间隔过小，大惩罚
                penalty += (self.config.min_headway - headway) ** 2
            else:
                # 与目标间隔的偏差
                deviation = abs(headway - self.config.target_headway)
                penalty += deviation
        
        # 与后车的间隔偏差
        if next_time is not None:
            headway = next_time - candidate_time
            if headway < self.config.min_headway:
                # 间隔过小，大惩罚
                penalty += (self.config.min_headway - headway) ** 2
            else:
                # 与目标间隔的偏差
                deviation = abs(headway - self.config.target_headway)
                penalty += deviation
        
        return penalty
    
    def _calculate_local_travel_time(self,
                                     stations: List[Station],
                                     is_short_route: bool) -> int:
        """
        计算慢车旅行时间
        
        Args:
            stations: 车站列表
            is_short_route: 是否为小交路
            
        Returns:
            旅行时间（秒）
        """
        # 小交路只走一半
        station_count = len(stations) // 2 if is_short_route else len(stations)
        
        # 区间运行时间
        total_time = (station_count - 1) * self.config.base_running_time_per_section
        
        # 停站时间（慢车站站停）
        total_time += station_count * self.config.base_dwell_time
        
        return total_time

