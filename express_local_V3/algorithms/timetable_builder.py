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
    支持快车越行慢车的检测和处理
    """
    
    def __init__(self, rail_info: RailInfo, enable_overtaking: bool = True):
        """
        初始化构建器
        
        Args:
            rail_info: 线路信息
            enable_overtaking: 是否启用越行处理（默认True）
        """
        self.rail_info = rail_info
        self.enable_overtaking = enable_overtaking
        
        # 获取车站列表（按线路顺序）
        self.stations = self._get_ordered_stations()
        
        # 越行参数（严格按照md文档）
        self.min_tracking_interval = 120      # 最小追踪间隔（秒）
        self.min_arrival_pass_interval = 120  # 最小到通间隔（秒）
        self.min_pass_departure_interval = 120  # 最小通发间隔（秒）
        self.min_overtaking_dwell = 240       # 越行站最小停站时间（秒，4分钟）
        
        # 可越行的车站索引（每隔2站可以越行）
        self.overtaking_station_indices = set(range(2, len(self.stations), 2))
    
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
        
        # 【关键】如果启用越行处理，检测并处理越行
        if self.enable_overtaking:
            print("\n[越行] 开始检测快车越行慢车...")
            overtaking_count = self._detect_and_handle_overtaking(timetable)
            print(f"[越行] 检测完成，共处理 {overtaking_count} 次越行事件")
        
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
    
    def _detect_and_handle_overtaking(self, timetable: ExpressLocalTimetable) -> int:
        """
        检测并处理快车越行慢车
        
        这是从overtaking_demo.py验证过的核心算法
        
        Args:
            timetable: 时刻表
            
        Returns:
            处理的越行事件数量
        """
        overtaking_count = 0
        
        # 按方向分组处理
        for direction in ['上行', '下行']:
            # 获取该方向的快车和慢车
            express_trains = [t for t in timetable.express_trains if t.direction == direction]
            local_trains = [t for t in timetable.local_trains if t.direction == direction]
            
            # 检测每对快慢车
            for express in express_trains:
                for local in local_trains:
                    if self._check_and_handle_single_overtaking(express, local, timetable):
                        overtaking_count += 1
        
        return overtaking_count
    
    def _check_and_handle_single_overtaking(self,
                                           express: ExpressTrain,
                                           local: LocalTrain,
                                           timetable: ExpressLocalTimetable) -> bool:
        """
        检查并处理单个快慢车对的越行
        
        Args:
            express: 快车
            local: 慢车
            timetable: 时刻表
            
        Returns:
            是否发生了越行
        """
        # 前提：快车在慢车后面出发
        if express.departure_time <= local.departure_time:
            return False
        
        # 获取时刻表条目
        local_entries = timetable.get_train_schedule(local.train_id)
        express_entries = timetable.get_train_schedule(express.train_id)
        
        if not local_entries or not express_entries:
            return False
        
        # 查找越行点
        overtaking_station_idx = self._find_overtaking_point(local_entries, express_entries)
        
        if overtaking_station_idx is not None:
            # 应用越行处理
            self._apply_overtaking(local_entries, express_entries, overtaking_station_idx, local, express)
            
            print(f"  [越行] {express.train_name} 在站点{overtaking_station_idx+1} 越行 {local.train_name}")
            return True
        
        return False
    
    def _find_overtaking_point(self,
                               local_entries: List[TimetableEntry],
                               express_entries: List[TimetableEntry]) -> Optional[int]:
        """
        找到越行发生的位置（优化版）
        
        策略：
        1. 找到快车会追上慢车的第一个冲突点
        2. 从冲突点向前找最近的越行站
        3. 只有真正会发生冲突时才返回越行站
        
        Args:
            local_entries: 慢车时刻表条目
            express_entries: 快车时刻表条目
            
        Returns:
            越行站索引（在local_entries中的索引），如果不会越行则返回None
        """
        conflict_point = None
        
        # 逐站检查，找到第一个会发生冲突的站点
        for i, local_entry in enumerate(local_entries):
            # 跳过前几个站（太靠近起点不适合越行）
            if i < 2:
                continue
            
            # 查找快车在该站的条目
            express_entry = None
            for e in express_entries:
                if e.station_id == local_entry.station_id:
                    express_entry = e
                    break
            
            if express_entry is None:
                continue
            
            # 【优化】更精确的冲突判定
            # 快车到达时间必须早于慢车发车时间，才会真正追上
            if express_entry.arrival_time < local_entry.departure_time:
                # 计算间隔
                time_gap = local_entry.departure_time - express_entry.arrival_time
                
                # 如果间隔小于最小追踪间隔，确实会冲突
                if time_gap < self.min_tracking_interval:
                    conflict_point = i
                    break
        
        # 如果没有找到冲突点，不需要越行
        if conflict_point is None:
            return None
        
        # 【优化】从冲突点向前找合适的越行站
        # 策略：优先选择中间位置的越行站，而不是离冲突点最近的
        
        # 找出所有可用的越行站（在冲突点之前）
        available_overtaking_stations = []
        for j in range(2, conflict_point + 1):  # 从第3个站开始，到冲突点
            if j in self.overtaking_station_indices:
                available_overtaking_stations.append(j)
        
        if not available_overtaking_stations:
            # 没有合适的越行站
            return None
        
        # 【关键优化】选择中间位置的越行站
        # 如果有多个越行站可选，选择靠近中间的那个
        if len(available_overtaking_stations) == 1:
            return available_overtaking_stations[0]
        else:
            # 选择中间位置的越行站（让越行点更均衡）
            mid_index = len(available_overtaking_stations) // 2
            return available_overtaking_stations[mid_index]
    
    def _apply_overtaking(self,
                         local_entries: List[TimetableEntry],
                         express_entries: List[TimetableEntry],
                         overtaking_station_idx: int,
                         local_train: LocalTrain,
                         express_train: ExpressTrain):
        """
        应用越行处理（精确版 - 快车通过时间在慢车停留的正中间）
        
        【关键原则】：
        1. 到通间隔 = 120秒（慢车到达 -> 快车通过）
        2. 通发间隔 = 120秒（快车通过 -> 慢车发车）
        3. 总停站时间 = 到通间隔 + 通发间隔 = 240秒
        4. 快车通过时间 = 慢车到达时间 + 120秒（正好在中间）
        
        Args:
            local_entries: 慢车时刻表条目
            express_entries: 快车时刻表条目
            overtaking_station_idx: 越行站索引
            local_train: 慢车对象
            express_train: 快车对象
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
        
        # 保存原始时间
        original_departure = local_entry.departure_time
        original_arrival = local_entry.arrival_time
        original_dwell = local_entry.dwell_time
        
        # 【关键】快车通过时间（已确定，不能修改）
        express_pass_time = express_entry.arrival_time
        
        # 【核心原则】让快车通过时间位于慢车停留的正中间
        # 
        # 已知：
        #   - 慢车到达时间：A（已确定，由前一站决定）
        #   - 快车通过时间：E（已确定）
        #   - 到通间隔 = E - A（已固定，不能改）
        # 
        # 目标：让快车在中间
        #   - 通发间隔 = 到通间隔（这样快车就在正中间）
        #   - 慢车发车时间 = E + 到通间隔
        #   - 总停站时间 = 2 * 到通间隔
        
        # 计算实际的到通间隔
        actual_arrival_to_pass = express_pass_time - local_entry.arrival_time
        
        # 【关键】让通发间隔等于到通间隔，快车就在中间！
        ideal_pass_to_departure = actual_arrival_to_pass
        
        # 计算慢车发车时间
        new_local_departure = express_pass_time + ideal_pass_to_departure
        
        # 计算停站时间
        new_dwell_time = new_local_departure - local_entry.arrival_time
        # 应该等于 2 * 到通间隔
        
        # 验证：确保到通间隔和通发间隔都满足最小要求（120秒）
        if actual_arrival_to_pass < self.min_arrival_pass_interval:
            # 到通间隔不足，需要增加通发间隔来补偿
            ideal_pass_to_departure = self.min_pass_departure_interval
            new_local_departure = express_pass_time + ideal_pass_to_departure
            new_dwell_time = new_local_departure - local_entry.arrival_time
        
        if ideal_pass_to_departure < self.min_pass_departure_interval:
            # 通发间隔不足，调整到最小值
            new_local_departure = express_pass_time + self.min_pass_departure_interval
            new_dwell_time = new_local_departure - local_entry.arrival_time
        
        # 确保总停站时间至少240秒
        if new_dwell_time < self.min_overtaking_dwell:
            new_dwell_time = self.min_overtaking_dwell
            new_local_departure = local_entry.arrival_time + new_dwell_time
        
        # 【过滤】如果停站时间增加太少，不应用越行
        time_increase = new_dwell_time - original_dwell
        if time_increase < 60:
            return
        
        # 计算时间顺延量
        time_shift = new_local_departure - original_departure
        
        # 应用越行站的时间调整（只调整发车时间和停站时间，不调整到达时间）
        local_entry.departure_time = new_local_departure  # 调整发车时间
        local_entry.dwell_time = new_dwell_time          # 调整停站时间
        local_entry.is_overtaking = True
        local_entry.overtaken_by = express_train.train_id
        local_entry.waiting_time = time_shift
        
        # 顺延后续所有站点的时间
        for i in range(overtaking_station_idx + 1, len(local_entries)):
            local_entries[i].arrival_time += time_shift
            local_entries[i].departure_time += time_shift

