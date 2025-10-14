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
from models.path_station_index import PathStationIndex, build_path_station_index_from_path


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
        
        # 【NEW】构建PathStationIndex缓存（核心改造）
        self.path_station_indexes: Dict[str, PathStationIndex] = {}
        self._build_path_station_indexes()
        
        # 越行参数
        self.min_tracking_interval = 120      # 最小追踪间隔（秒）
        self.min_arrival_pass_interval = 60   # 最小到通间隔（秒）- 降低以产生更多越行
        self.min_pass_departure_interval = 60  # 最小通发间隔（秒）- 降低以产生更多越行
        self.min_overtaking_dwell = 120       # 越行站最小停站时间（秒）- 降低以产生更多越行
        
        # 【固定越行站】上行在金星路站，下行在人民东路站
        self.overtaking_station_name_up = "金星路站"      # 上行越行站
        self.overtaking_station_name_down = "人民东路站"  # 下行越行站
        
        # 查找这两个车站的ID（不是索引！）
        self.overtaking_station_id_up = None
        self.overtaking_station_id_down = None
        
        for station_id, station in rail_info.stationList.items():
            if self.overtaking_station_name_up in station.name:
                self.overtaking_station_id_up = station_id
                print(f"[越行站配置] 上行越行站: {station.name}（ID={station_id}）")
            elif self.overtaking_station_name_down in station.name:
                self.overtaking_station_id_down = station_id
                print(f"[越行站配置] 下行越行站: {station.name}（ID={station_id}）")
    
    def _get_ordered_stations(self) -> List[Station]:
        """获取按线路顺序排列的车站列表"""
        stations = list(self.rail_info.stationList.values())
        # Station对象使用centerKp属性表示公里标
        stations.sort(key=lambda s: s.centerKp)
        return stations
    
    def _build_path_station_indexes(self):
        """
        构建所有路径的PathStationIndex缓存
        
        核心目标：为每个route_id建立精确的path_index -> dest_code -> station映射
        """
        print(f"\n[PathStationIndex] 开始构建路径索引缓存...")
        
        for path_id, path in self.rail_info.pathList.items():
            # Path类使用id作为路径ID，path_route_id作为所属交路ID
            route_id = path.id  # 使用path.id作为唯一标识
            
            try:
                # 使用build_path_station_index_from_path函数构建索引
                index = build_path_station_index_from_path(path, self.rail_info)
                
                # 验证索引完整性
                is_valid, errors = index.validate()
                if not is_valid:
                    print(f"  [警告] 路径{route_id}的索引验证失败:")
                    for error in errors:
                        print(f"    - {error}")
                
                # 存储索引（使用route_id作为键）
                self.path_station_indexes[route_id] = index
                
                # 简要信息
                virtual_count = sum(1 for node in index.nodes if node.is_virtual)
                print(f"  [√] 路径{route_id}: {index.total_nodes}个节点 (虚拟节点={virtual_count})")
                
            except Exception as e:
                print(f"  [错误] 构建路径{route_id}的索引失败: {e}")
                continue
        
        print(f"[PathStationIndex] 完成！共构建{len(self.path_station_indexes)}个路径索引\n")
    
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
        为单列车构建时刻表【V3架构 - 基于PathStationIndex】
        
        【核心改造】：
        1. 使用train.route_id查找对应的PathStationIndex
        2. 按照PathStationIndex的path_index顺序生成时刻表
        3. 每个entry记录path_index，确保与path.nodeList精确对齐
        
        Args:
            train: 列车对象
            
        Returns:
            时刻表条目列表（按path_index顺序）
        """
        entries = []
        
        # 【关键】获取该列车路径的PathStationIndex
        path_index = self.path_station_indexes.get(train.route_id)
        
        if not path_index:
            # 如果没有找到PathStationIndex，回退到旧逻辑（兼容性）
            print(f"[警告] 列车{train.train_id}的路径{train.route_id}未找到PathStationIndex，回退到旧逻辑")
            return self._build_train_schedule_legacy(train)
        
        # 从起点开始，逐站计算时刻
        current_time = train.departure_time
        
        # 【核心改造】按PathStationIndex的节点顺序遍历
        for node in path_index.nodes:
            path_idx = node.path_index
            dest_code = node.dest_code
            station_id = node.station_id if node.station_id else dest_code  # 虚拟节点用dest_code
            station_name = node.station_name
            
            # 判断是否停车
            if node.is_virtual:
                # 虚拟节点（折返轨等）通常不停车
                is_stop = False
                is_skip = True
            else:
                is_stop = train.stops_at_station(station_id)
                is_skip = not is_stop
            
            # 计算到达时间
            if path_idx == 0:
                # 起点站：到达时间=发车时间
                arrival_time = current_time
            else:
                # 中间站：到达时间=上一站发车时间+区间运行时间
                prev_node = path_index.nodes[path_idx - 1]
                running_time = self._get_section_running_time_by_destcode(
                    prev_node.dest_code, dest_code, train
                )
                arrival_time = current_time + running_time
            
            # 计算停站时间和发车时间
            if is_stop:
                dwell_time = train.get_dwell_time(station_id)
            else:
                dwell_time = 0  # 跳停或虚拟节点不停车
            
            departure_time = arrival_time + dwell_time
            
            # 创建时刻表条目（包含path_index）
            entry = TimetableEntry(
                train_id=train.train_id,
                station_id=station_id,
                station_name=station_name,
                arrival_time=arrival_time,
                departure_time=departure_time,
                dwell_time=dwell_time,
                is_stop=is_stop,
                is_skip=is_skip,
                platform_id=dest_code,
                dest_code=dest_code,
                path_index=path_idx,  # 【NEW】记录path_index
                direction_hint=train.direction  # 【NEW】记录方向
            )
            
            entries.append(entry)
            
            # 更新当前时间为发车时间
            current_time = departure_time
        
        return entries
    
    def _build_train_schedule_legacy(self, train: Train) -> List[TimetableEntry]:
        """
        旧版时刻表构建逻辑（兼容性回退）
        
        用于当PathStationIndex不可用时的回退方案
        """
        entries = []
        train_stations = self._get_train_stations(train)
        current_time = train.departure_time
        
        for i, station in enumerate(train_stations):
            is_stop = train.stops_at_station(station.id)
            is_skip = not is_stop
            
            if i == 0:
                arrival_time = current_time
            else:
                prev_station = train_stations[i-1]
                running_time = self._get_section_running_time(
                    prev_station, station, train
                )
                arrival_time = current_time + running_time
            
            if is_stop:
                dwell_time = train.get_dwell_time(station.id)
            else:
                dwell_time = 0
            
            departure_time = arrival_time + dwell_time
            dest_code = self._get_platform_code(station, train.direction)
            
            entry = TimetableEntry(
                train_id=train.train_id,
                station_id=station.id,
                station_name=station.name,
                arrival_time=arrival_time,
                departure_time=departure_time,
                dwell_time=dwell_time,
                is_stop=is_stop,
                is_skip=is_skip,
                platform_id=dest_code,
                dest_code=dest_code,
                path_index=None,  # 旧逻辑没有path_index
                direction_hint=train.direction
            )
            
            entries.append(entry)
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
        获取区间运行时间（基于Station对象）
        
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
    
    def _get_section_running_time_by_destcode(self, 
                                               from_destcode: str,
                                               to_destcode: str,
                                               train: Train) -> int:
        """
        获取区间运行时间（基于dest_code）【V3新增】
        
        优先从rail_info的path中查询实际运行时间，
        如果查询失败则使用默认值
        
        Args:
            from_destcode: 起始站台目的地码
            to_destcode: 到达站台目的地码
            train: 列车对象
            
        Returns:
            区间运行时间（秒）
        """
        # TODO: 从rail_info查询实际的区间运行时间
        # 当前使用简化实现
        
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
        
        # 【修改】根据方向确定固定越行站ID
        direction = local.direction
        if direction == "上行":
            fixed_overtaking_station_id = self.overtaking_station_id_up
        else:
            fixed_overtaking_station_id = self.overtaking_station_id_down
        
        if fixed_overtaking_station_id is None:
            return False
        
        # 在local_entries中找到越行站的索引
        overtaking_entry_idx = None
        for i, entry in enumerate(local_entries):
            if entry.station_id == fixed_overtaking_station_id:
                overtaking_entry_idx = i
                break
        
        if overtaking_entry_idx is None:
            return False
        
        # 检查是否会在固定越行站之前发生冲突
        if self._should_overtake_at_station(local_entries, express_entries, overtaking_entry_idx):
            # 应用越行处理
            self._apply_overtaking(local_entries, express_entries, overtaking_entry_idx, local, express)
            
            station_name = local_entries[overtaking_entry_idx].station_name if overtaking_entry_idx < len(local_entries) else "未知站"
            print(f"  [越行] {express.train_name} 在{station_name} 越行 {local.train_name}")
            return True
        
        return False
    
    def _should_overtake_at_station(self,
                                   local_entries: List[TimetableEntry],
                                   express_entries: List[TimetableEntry],
                                   overtaking_idx: int) -> bool:
        """
        判断是否需要在指定站点越行
        
        Args:
            local_entries: 慢车时刻表条目
            express_entries: 快车时刻表条目
            overtaking_idx: 指定的越行站索引
            
        Returns:
            是否需要越行
        """
        # 【关键检查】确保在越行站，慢车到达时间早于快车通过时间
        if overtaking_idx >= len(local_entries):
            return False
        
        local_overtaking_entry = local_entries[overtaking_idx]
        
        # 查找快车在越行站的条目
        express_overtaking_entry = None
        for e in express_entries:
            if e.station_id == local_overtaking_entry.station_id:
                express_overtaking_entry = e
                break
        
        if express_overtaking_entry is None:
            return False
        
        # 【关键判定】慢车必须在快车通过之前到达越行站
        # 如果慢车到达晚于快车通过，说明需要调整
        arrival_to_pass_gap = express_overtaking_entry.arrival_time - local_overtaking_entry.arrival_time
        
        # 如果到通间隔为负数或太小，需要调整
        if arrival_to_pass_gap < self.min_arrival_pass_interval:
            # 需要调整：让慢车提前到达越行站，或者不越行
            # 这里选择：调整越行站前面所有站点的时间
            pass  # 继续检查冲突，决定是否越行
        
        # 检查在越行站或之前是否会发生冲突
        for i in range(min(overtaking_idx + 1, len(local_entries))):
            local_entry = local_entries[i]
            
            # 查找快车在该站的条目
            express_entry = None
            for e in express_entries:
                if e.station_id == local_entry.station_id:
                    express_entry = e
                    break
            
            if express_entry is None:
                continue
            
            # 检查是否会发生冲突
            if express_entry.arrival_time < local_entry.departure_time:
                time_gap = local_entry.departure_time - express_entry.arrival_time
                if time_gap < self.min_tracking_interval:
                    # 会发生冲突，需要在固定越行站越行
                    return True
        
        return False
    
    
    def _apply_overtaking(self,
                         local_entries: List[TimetableEntry],
                         express_entries: List[TimetableEntry],
                         overtaking_station_idx: int,
                         local_train: LocalTrain,
                         express_train: ExpressTrain):
        """
        应用越行处理【V3架构 - 基于path_index精确匹配】
        
        【核心改造】：
        1. 使用path_index而不是station_id匹配越行站
        2. 确保快慢车在同一path_index的entry上进行越行调整
        3. 避免因station_id vs dest_code混用导致的失配
        
        【关键原则】：
        1. 到通间隔 = 120秒（慢车到达 -> 快车通过）
        2. 通发间隔 = 120秒（快车通过 -> 慢车发车）
        3. 总停站时间 = 到通间隔 + 通发间隔 = 240秒
        4. 快车通过时间 = 慢车到达时间 + 120秒（正好在中间）
        
        Args:
            local_entries: 慢车时刻表条目
            express_entries: 快车时刻表条目
            overtaking_station_idx: 越行站在慢车entries中的索引
            local_train: 慢车对象
            express_train: 快车对象
        """
        # 获取越行站的条目
        local_entry = local_entries[overtaking_station_idx]
        
        # 【关键改造】通过path_index精确匹配快车的对应entry
        # 而不是使用station_id（因为虚拟节点的station_id可能是dest_code）
        express_entry = None
        
        if local_entry.path_index is not None:
            # 优先使用path_index匹配（精确）
            for e in express_entries:
                if e.path_index == local_entry.path_index:
                    express_entry = e
                    break
        else:
            # 回退到station_id匹配（兼容旧逻辑）
            for e in express_entries:
                if e.station_id == local_entry.station_id:
                    express_entry = e
                    break
        
        if express_entry is None:
            # 可能快车在该站跳停
            return
        
        # 保存原始时间
        original_departure = local_entry.departure_time
        original_arrival = local_entry.arrival_time
        original_dwell = local_entry.dwell_time
        
        # 快车通过时间（已确定）
        express_pass_time = express_entry.arrival_time
        
        # 【正确逻辑】不调整到达时间，只调整发车时间
        # 
        # 已知：
        #   慢车到达时间：A（不改！由前一站决定）
        #   快车通过时间：E（不改）
        #   到通间隔 = E - A（已固定）
        # 
        # 目标：让快车在中间
        #   通发间隔 = 到通间隔
        #   慢车发车 = E + 到通间隔
        #   总停站 = 2 * 到通间隔
        
        # 计算实际的到通间隔（慢车到达 -> 快车通过）
        actual_arrival_to_pass = express_pass_time - local_entry.arrival_time
        
        # 【绝对不调整到达时间！】只调整发车时间，确保站台码不会错
        
        # 【如果到通间隔为负数】说明慢车到达晚于快车通过，肯定不需要越行
        if actual_arrival_to_pass < 0:
            return
        
        # 如果到通间隔太小（<30秒），也不越行（太危险）
        if actual_arrival_to_pass < 30:
            return
        
        # 让通发间隔等于到通间隔（快车在中间）
        ideal_pass_to_departure = actual_arrival_to_pass
        
        # 确保通发间隔至少120秒
        if ideal_pass_to_departure < self.min_pass_departure_interval:
            ideal_pass_to_departure = self.min_pass_departure_interval
        
        # 计算慢车发车时间
        new_local_departure = express_pass_time + ideal_pass_to_departure
        
        # 计算停站时间
        new_dwell_time = new_local_departure - local_entry.arrival_time
        
        # 确保总停站时间至少240秒
        if new_dwell_time < self.min_overtaking_dwell:
            new_dwell_time = self.min_overtaking_dwell
            new_local_departure = local_entry.arrival_time + new_dwell_time
        
        # 【过滤】如果停站时间增加太少，不应用越行
        time_increase = new_dwell_time - original_dwell
        if time_increase < 60:
            return
        
        # 计算发车时间的调整量（用于顺延后续站点）
        departure_shift = new_local_departure - original_departure
        
        # 应用越行站的时间调整（不调整到达时间！只调整发车时间和停站时间）
        local_entry.departure_time = new_local_departure  # 调整发车时间
        local_entry.dwell_time = new_dwell_time          # 调整停站时间
        local_entry.is_overtaking = True
        local_entry.overtaken_by = express_train.train_id
        local_entry.waiting_time = departure_shift
        
        # 【验证】打印越行时间配置
        actual_arr_to_pass = express_pass_time - local_entry.arrival_time
        actual_pass_to_dep = new_local_departure - express_pass_time
        station_name = self.stations[overtaking_station_idx].name if overtaking_station_idx < len(self.stations) else f'站点{overtaking_station_idx+1}'
        print(f"    [时间验证] {local_train.train_name} 在{station_name}:")
        print(f"      慢车到{local_entry.arrival_time}秒, 快车过{express_pass_time}秒, 慢车发{new_local_departure}秒")
        print(f"      到通={actual_arr_to_pass}秒, 通发={actual_pass_to_dep}秒, 总停={new_dwell_time}秒")
        
        # 顺延后续所有站点的时间
        for i in range(overtaking_station_idx + 1, len(local_entries)):
            local_entries[i].arrival_time += departure_shift
            local_entries[i].departure_time += departure_shift

