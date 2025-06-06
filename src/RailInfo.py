from typing import Dict, List, Optional
from dataclasses import dataclass
from Solution import Solution
from Station import Station
from Route import Route
from Path import Path
from Platform import Platform
from Turnback import Turnback
from CarInfo import CarInfo
from RouteSolution import RouteSolution
from Peak import Peak
from collections import deque
from queue import Queue
from Util import util
import sys
class RailInfo:
    """
    RailInfo类用于管理所有铁路信息
    负责:
    - 储存和管理车站、路径、线路、站台等核心结构
    - 计算列车运行时间(包括路径内部分段时间、全程时间等)
    - 管理列车的站台占用情况、冲突检测
    - 支持双向调度、交叉道岔(xroad)处理
    - 动态生成列车运行路径(Heuristic方法)
    
    支持路径扩展、路径连接、冲突检测、到发时间计算、偏移处理等操作。
    """
    
    def __init__(self, debug: bool = False):
        """初始化RailInfo对象"""
        self.debug = debug
        self.sl = Solution(debug)  #求解结果
        
        # 用于查询所有铁路组件的映射
        self.stationList: Dict[str, Station] = {}
        self.routeList: Dict[str, Route] = {}
        self.pathList: Dict[int, Path] = {}
        self.platformList: Dict[str, Platform] = {}
        self.turnbackList: Dict[str, Turnback] = {}
        self.path_search_by_dep: Dict[str, List[str]] = {}
        
        # 速度等级查询
        self.speedLevels_name: Dict[int, str] = {}
        self.speedLevels_spd: Dict[int, int] = {}
        
        # 站台到所属车站的映射
        self.platform_station_map: Dict[str, str] = {}
        
        # 用于站台冲突检测
        self.platform_occupation: Dict[str, List[int]] = {}
        self.platform_occupation_duration: Dict[str, List[int]] = {}
        self.platform_occupation_car: Dict[str, List[int]] = {}
        
        # 用于路径搜索
        self.foundPaths: Dict[str, Path] = {}
        self.foundPathsFull: Dict[str, Path] = {}
        
        # 运行中的车辆列表
        self.enroute_cars: List[List[CarInfo]] = [[] for _ in range(4)]
        self.depot_cars: List[Queue[CarInfo]] = []
        self.turn_back_cars: List[Queue[CarInfo]] = [deque() for _ in range(4)]
        
        # 最后发车记录
        self.last_sent: List[int] = [0, 0, 0, 0]  # up1, dn1, up2, dn2
        self.last_sent_car: List[Optional[CarInfo]] = [None] * 4
        self.last_sent_events: List[List[int]] = [[] for _ in range(4)]
        
        # 路线时长列表
        self.total_run_time: List[int] = []
        self.total_run_time_up: List[int] = []
        self.total_run_time_dn: List[int] = []
        self.unchanged_time_up: List[int] = []
        self.unchanged_time_dn: List[int] = []
        self.up_init_offset: List[int] = []
        self.dn_init_offset: List[int] = []
        
        # 最大停站时间差,用于全局安全检查
        self.max_dwell_diff: List[int] = [0] * 4
        
        # 冲突检查标志
        self.check_conflict: bool = True
        
        # 路径和运行时间的映射
        self.travel_time_map: Dict[str, int] = {}
        self.min_train_inter: int = 0
        self.min_turnback_inter: int = 0

    def find_path_by_start_end(self, start_plt: str, end_plt: str) -> Path:
            """
            根据起始站台和终点站台查找对应的路径
            
            Args:
                start_plt: 起始站台
                end_plt: 终点站台
                
            Returns:
                找到的路径对象，如果没有找到则返回None
            """
            query = f"{start_plt}_{end_plt}"
            
            # 检查我们是否之前已经找到过这个路径
            if query in self.foundPaths:
                return self.foundPaths[query]
            
            # 如果之前没有找到过这个路径，我们需要查找它
            for pid in self.pathList.keys():
                pth = self.pathList[pid]
                if pth.nodeList[0] != start_plt:
                    continue
                if pth.nodeList[-1] != end_plt:
                    continue
                
                # 如果这条路径从a开始到b结束，存储并返回
                self.foundPaths[query] = pth
                return self.pathList[pid]
            
            return None
            
    def reset_planning(self):
        """重置当前调度状态,清除之前发送的列车记录并重新初始化在途车辆列表"""
        self.sl = Solution(self.debug)
        self.last_sent = [0] * 4  # up1, dn1, up2, dn2
        self.enroute_cars = [[] for _ in range(4)]

    def initialize_depot_cars(self, us):
        """初始化车库中的车辆"""
        table_num = 0
        round_num = 0
        route_num = 0
        
        for i, n_train in enumerate(us.depot_trains):
            self.depot_cars.append(deque())
            for j in range(n_train):
                table_num += 1
                # round_num = table_num * 100
                round_num = table_num % 1000
                if round_num == 0:
                    round_num = 1000
                self.depot_cars[i].append(CarInfo(table_num, round_num, -1))
                
        self.turn_back_cars = [deque() for _ in range(4)]
        self.last_sent_car = [None] * 4
        self.last_sent_events = [[] for _ in range(4)]

    def setDirectionOffset(self):
        """根据两个方向的差异设置第一班车的上/下行时间偏移"""
        self.up_init_offset.clear()
        self.dn_init_offset.clear()
        
        for xroad in range(len(self.total_run_time)):
            if self.total_run_time_up[xroad] > self.total_run_time_dn[xroad]:
                self.up_init_offset.append(self.total_run_time_up[xroad] - self.total_run_time[xroad]//2)
                self.dn_init_offset.append(0)
                if self.debug:
                    print(f"Need to send first up time earlier: {self.up_init_offset[xroad]}")
            else:
                self.dn_init_offset.append(self.total_run_time_dn[xroad] - self.total_run_time[xroad]//2)
                self.up_init_offset.append(0)
                if self.debug:
                    print(f"Need to send first dn time earlier: {self.dn_init_offset[xroad]}")

    def setLastSentTime(self, time: int):
        """设置第一班上/下行车的最后发车时间"""
        self.last_sent[0] = time + self.up_init_offset[0]
        self.last_sent[1] = time + self.dn_init_offset[0]
        if len(self.up_init_offset) > 1:
            self.last_sent[2] = time + self.up_init_offset[1]
            self.last_sent[3] = time + self.dn_init_offset[1]
        else:
            self.last_sent[2] = time
            self.last_sent[3] = time

    def addTrainSolution(self, rs: RouteSolution):
        """将求解的值添加到一条运行线中"""
        c_info = rs.car_info
        rs.updateInfo(c_info.table_num, c_info.round_num, c_info.route_num)
        rs.car_info.id = len(self.sl.route_lists)
        self.sl.addTrainService(rs)

    def addStation(self, stt: Station):
        """添加车站到总车站列表"""
        self.stationList[stt.id] = stt

    def addRoute(self, id: str, name: str, up_route: str, down_route: str):
        """添加路线到总路线列表"""
        self.routeList[id] = Route(id, name, up_route, down_route)

    def addPath(self, pth: Path):
        """添加路径到总路径列表,同时更新映射"""
        self.pathList[pth.id] = pth
        if pth.dep_dest_code not in self.path_search_by_dep:
            self.path_search_by_dep[pth.dep_dest_code] = []
        self.path_search_by_dep[pth.dep_dest_code].append(pth.id)

    def addPerfLevel(self, id: str, name: str, spd: str):
        """添加速度等级"""
        tmp_id = int(id)
        self.speedLevels_name[tmp_id] = name
        self.speedLevels_spd[tmp_id] = int(spd)

    def addTravelInterval(self, start_id: str, end_id: str, perf_lv_ID_: str, run_time_: str):
        """添加给定路径段的行驶时间"""
        str_key = f"{start_id}_{end_id}_{perf_lv_ID_}"
        self.travel_time_map[str_key] = int(run_time_)

    def getTravelInterval(self, start_id: str, end_id: str, perf_lv_ID_: str) -> int:
        """获取给定路径段的行驶时间"""
        if int(perf_lv_ID_) < 0:
            perf_lv_ID_ = str(self.platformList[start_id].def_pl)
        str_key = f"{start_id}_{end_id}_{perf_lv_ID_}"
        # if self.debug:
        #     print(str_key)
            # 添加调试信息
        # print(f"尝试查找行驶时间数据: {str_key}")
        
        # 检查站台是否存在
        if start_id not in self.platformList:
            print(f"错误：起始站台 {start_id} 不存在于platformList中")
            return 60  # 使用默认值
        
        if end_id not in self.platformList:
            print(f"错误：终点站台 {end_id} 不存在于platformList中")
            return 60  # 使用默认值
        
        # 检查性能等级是否存在
        if int(perf_lv_ID_) not in self.speedLevels_name:
            print(f"错误：性能等级 {perf_lv_ID_} 不存在")

        # 添加错误处理
        if str_key not in self.travel_time_map:
            print(f"警告：未找到行驶时间数据 {str_key}，尝试使用默认性能等级")
            # 尝试使用默认性能等级
            for alt_level in self.speedLevels_name.keys():
                alt_key = f"{start_id}_{end_id}_{alt_level}"
                if alt_key in self.travel_time_map:
                    print(f"使用替代性能等级 {alt_level} 的行驶时间")
                    return self.travel_time_map[alt_key]
            
            # 如果仍然找不到，使用估计值
            # print(f"错误：无法找到从 {start_id} 到 {end_id} 的任何行驶时间数据，使用默认值60秒")
            # return 60  # 使用默认值，例如60秒

            # 如果仍然找不到，输出错误信息并终止程序
            print(f"严重错误：无法找到从 {start_id} 到 {end_id} 的任何行驶时间数据，程序终止！")
            print(f"调用堆栈跟踪：")
            import traceback
            traceback.print_stack()  # 打印调用堆栈，帮助定位问题
            sys.exit(1)  # 终止程序，返回错误码1
        return self.travel_time_map[str_key]

    def setConflict(self, mini_train_inter_: str, min_tb_inter: str):
        """设置最小列车间隔和折返间隔用于冲突检测"""
        self.min_train_inter = int(mini_train_inter_)
        self.min_turnback_inter = int(min_tb_inter)

    def generate_platform_staiton_map(self):
        """根据读取的数据生成站台-车站映射"""
        # print("generate_platform_staiton_map进入")
        for station in self.stationList.values():
            for platform in station.platformList:
                self.platform_station_map[platform.dest_code] = station.id
            for turnback in station.turnbackList:
                self.turnbackList[turnback.dest_code] = turnback
                # print("turnbackList添加数据")

    def generate_platform_occupation(self):
        """生成站台占用映射并初始化"""
        print("已加载的站台列表：")
        print(f"站台总数: {len(self.stationList)}")  # 添
        for station in self.stationList.values():
            # print(f"处理车站: {station.name}, 站台数量: {len(station.platformList)}")  # 添加这行来检查每个车站的站台数量
            for platform in station.platformList:
                # print(f"站台代码: {platform.dest_code}")
                self.platform_occupation[platform.dest_code] = []
                self.platform_occupation_duration[platform.dest_code] = []
                self.platform_occupation_car[platform.dest_code] = []
                self.platformList[platform.dest_code] = platform #写入赋值

    def compute_partial_time_threshold(self, route: str, spd_lvl: int, threshold: int, skip: bool) -> int:
        """计算列车应该出发的时间以在阈值内到达最后一个车站"""
        speed_level_ = spd_lvl
        if self.debug:
            print(f"Speed level: {speed_level_}    {self.speedLevels_name[speed_level_]}")
            
        total_time = 0
        path = self.pathList[route]
        
        for i in range(len(path.nodeList) - 1):
            current_platform = path.nodeList[i]
            stop_time = 0
            next_platform = path.nodeList[i + 1]
            travel_time = self.getTravelInterval(current_platform, next_platform, str(speed_level_))
            
            if total_time + travel_time > threshold:
                if not skip:
                    if total_time + travel_time - threshold < threshold - total_time:
                        total_time += travel_time
                break
                
            total_time += travel_time
            
            if self.debug:
                first_station_name = self.stationList[self.platform_station_map[current_platform]].name
                second_station_name = self.stationList[self.platform_station_map[next_platform]].name
                print(f"   from {first_station_name} to {second_station_name}   time: {travel_time}")
                
        if self.debug:
            print(f"  total time: {total_time}\n\n\n")
        return total_time

    def reset_time(self):
        """重置计算的行驶时间"""
        self.total_run_time.clear()
        self.total_run_time_up.clear()
        self.total_run_time_dn.clear()
        self.unchanged_time_up.clear()
        self.unchanged_time_dn.clear()

    def time_from_int_sec(self, time: int) -> str:
        """
        将时间戳(秒)转换为格式化的时间字符串 HH:MM:SS
        Args:
            time: 时间戳(秒)
        Returns:
            格式化的时间字符串
        """
        sec = time % 60
        mins = (time - (time % 60)) // 60
        hr = mins // 60
        mins = mins % 60
        return f"{hr}:{mins}:{sec}"

    def compute_full_length_time_turnback(self, pk: Peak, spd_lvl: int, stop: int):
        """计算不同峰期的全程时间,并根据不同情况更新所有时间
        这里total_run_time多加入了折返的时间"""
        self.reset_time()
        
        for xroad in range(len(pk.routes)):
            up_route = pk.routes[xroad].up_route
            dn_route = pk.routes[xroad].down_route
            
            self.total_run_time_up.append(self.compute_full_length_time_full(up_route, spd_lvl, stop) + pk.turnback_time_up_rt1)
            self.total_run_time_dn.append(self.compute_full_length_time_full(dn_route, spd_lvl, stop) + pk.turnback_time_dn_rt1)
            self.total_run_time.append(self.total_run_time_up[xroad] + self.total_run_time_dn[xroad])
            self.unchanged_time_up.append(self.compute_full_length_time_unchanged(up_route, spd_lvl, stop, 0))
            self.unchanged_time_dn.append(self.compute_full_length_time_unchanged(dn_route, spd_lvl, stop, 1))

    def compute_full_length_time(self, pk: Peak, spd_lvl: int, stop: int):
        """计算给定峰期的全程时间"""
        self.reset_time()
        
        for xroad in range(len(pk.routes)):
            up_route = pk.routes[xroad].up_route
            dn_route = pk.routes[xroad].down_route
            
            self.total_run_time_up.append(self.compute_full_length_time_full(up_route, spd_lvl, stop))
            self.total_run_time_dn.append(self.compute_full_length_time_full(dn_route, spd_lvl, stop))
            self.total_run_time.append(self.total_run_time_up[xroad] + self.total_run_time_dn[xroad])
            self.unchanged_time_up.append(self.compute_full_length_time_unchanged(up_route, spd_lvl, stop, 0))
            self.unchanged_time_dn.append(self.compute_full_length_time_unchanged(dn_route, spd_lvl, stop, 1))
            
            if self.debug:
                print(f"xroad {xroad} up time: {self.time_from_int_sec(self.total_run_time_up[xroad])}")
                print(f"xroad {xroad} dn time: {self.time_from_int_sec(self.total_run_time_dn[xroad])}")
                # print(f"xroad {1} up time: {self.time_from_int_sec(self.total_run_time_up[1])}")
                # print(f"xroad {1} dn time: {self.time_from_int_sec(self.total_run_time_dn[1])}")

    def compute_full_length_time_unchanged(self, route: str, spd_lvl: int, stop: int, direction: int) -> int:
        """计算上/下行方向运行时间
        只包含单向的运行时间"""
        speed_level_ = spd_lvl
        uc_time = 0
        path = self.pathList[route]
        
        for i in range(len(path.nodeList) - 1):
            current_platform = path.nodeList[i]
            stop_time = self.platformList[current_platform].def_dwell_time
            if stop == 0:
                stop_time = 0
                
            next_platform = path.nodeList[i + 1]
            elapsed_time = self.getTravelInterval(current_platform, next_platform, str(speed_level_))
            travel_time = stop_time + elapsed_time
            
            if (direction == 0 and i > 0) or (direction == 1 and i < len(path.nodeList) - 1):
                uc_time += travel_time
                
        return uc_time

    def compute_full_length_time_full(self, route: str, spd_lvl: int, stop: int) -> int:
        """计算上/下行方向运行时间
        参数：stop: 0表示不停站，没有停站时间：即运营时段开始前后出入库的车都采用跳停的方法，不停站"""
        speed_level_ = spd_lvl
        tt_time = 0
        path = self.pathList[route]
        
        for i in range(len(path.nodeList) - 1):
            current_platform = path.nodeList[i]
            if current_platform not in self.platformList:
                print(f"警告：未找到站台代码 {current_platform} 的配置信息")
                stop_time = 0  # 使用默认值
            else:
                stop_time = self.platformList[current_platform].def_dwell_time
            # stop_time = self.platformList[current_platform].def_dwell_time#从站台中取值默认停站时间
            if stop == 0 or i == 0:
                stop_time = 0
                
            next_platform = path.nodeList[i + 1]
            elapsed_time = self.getTravelInterval(current_platform, next_platform, str(speed_level_))#取值运行时间
            travel_time = stop_time + elapsed_time
            tt_time += travel_time
            
        return tt_time

    def get_minmax_def_dwell_all(self, pk: Peak):
        """计算此高峰期中所有经过的站台的最大停站时间最小值"""
        for xroad in range(len(pk.routes)):
            for dir in range(2):
                rt = pk.routes[xroad].up_route if dir == 0 else pk.routes[xroad].down_route
                self.max_dwell_diff[xroad * 2 + dir] = self.get_max_def_dwell(rt) - self.get_min_def_dwell(rt)

    def get_max_def_dwell(self, route: str) -> int:
        """获取默认停站时间的全局最大值"""
        max_t = 0
        path = self.pathList[route]
        
        for i in range(len(path.nodeList) - 1):
            current_platform = path.nodeList[i]
            stop_time = self.platformList[current_platform].def_dwell_time
            if max_t <= stop_time:
                max_t = stop_time
                
        return max_t

    def get_min_def_dwell(self, route: str) -> int:
        """获取默认停站时间的全局最小值"""
        min_t = 99999999
        path = self.pathList[route]
        
        for i in range(len(path.nodeList) - 1):
            current_platform = path.nodeList[i]
            stop_time = self.platformList[current_platform].def_dwell_time
            if min_t >= stop_time:
                min_t = stop_time
                
        return min_t

    def generateReqInfo(self):
        """生成映射的调用者"""
        self.generate_platform_staiton_map()#车站折返站台信息在这里添加
        self.generate_platform_occupation()

    def computePathDiff(self, path_id: str, path_id_small: str, speed_level: int) -> int:
        """计算来自不同交叉路的两条路径之间的时间差"""
        path = self.pathList[path_id]
        path_small = self.pathList[path_id_small]
        break_stt = path_small.nodeList[0]
        break_stt2 = path_small.nodeList[1]
        res = 0
        
        for i in range(len(path.nodeList) - 1):
            current_platform = path.nodeList[i]
            if current_platform == break_stt or current_platform == break_stt2:
                if current_platform == break_stt2:
                    # 需要减去被忽略的部分
                    res -= self.getTravelInterval(break_stt, break_stt2, str(speed_level))
                    res -= self.platformList[break_stt2].def_dwell_time
                break
                
            next_platform = path.nodeList[i + 1]
            travel_time_ = self.getTravelInterval(current_platform, next_platform, str(speed_level))
            stop_time_ = self.platformList[next_platform].def_dwell_time
            res += travel_time_ + stop_time_
            
            if self.debug:
                first_station_name = self.stationList[self.platform_station_map[current_platform]].name
                second_station_name = self.stationList[self.platform_station_map[next_platform]].name
                print(f"   from {first_station_name} to {second_station_name}   time: {travel_time_} Stop: {stop_time_}")
                
        if self.debug:
            print(f"   -- total time: {res}\n\n\n")
        return res

    def check_for_conflict(self, arr_time: int, dep_time: int, current_platform: str, 
                      path_id: str, cinfo: CarInfo) -> bool:
        """
        检查一个新的列车任务线是否与已有的站台占用时间产生冲突
        
        Args:
            arr_time: 列车计划到达时间
            dep_time: 列车计划离开时间
            current_platform: 当前站台
            path_id: 路径ID
            cinfo: 车辆信息对象
            
        Returns:
            bool: 是否存在冲突
        """
        # 获取当前站台的所有已有占用信息
        occupations = self.platform_occupation[current_platform]
        occupations_duration = self.platform_occupation_duration[current_platform]
        occupations_duration_by = self.platform_occupation_car[current_platform]
        
        # 检查是否有重叠
        found_conflict = False
        indx = -1
        
        # 检测两种冲突情况：
        # 1. 新列车的到达时间落在已有占用时间段内
        # 2. 新列车的离开时间落在已有占用时间段内
        for j in range(len(occupations)):
            if ((arr_time >= occupations[j] and arr_time <= occupations[j] + occupations_duration[j]) or
                (dep_time <= occupations[j] + occupations_duration[j] and dep_time >= occupations[j])):
                found_conflict = True
                indx = j
                break
        
        # 当发现冲突时，输出详细的冲突信息
        if found_conflict:
            print("!!!!!!!!!!   Found Potential Conflict   !!!!!!!!!!", file=sys.stderr)
            print(f"!!!!!!!!!!         Path: {path_id}, car round num: {cinfo.round_num} with {occupations_duration_by[indx]}   !!!!!!!!!!", 
                file=sys.stderr)
            print(f"!!!!!!!!!!         plan:{self.time_from_int_sec(arr_time)}~{self.time_from_int_sec(dep_time)}   !!!!!!!!!!", 
                file=sys.stderr)
            print(f"!!!!!!!!!!   occupation:{self.time_from_int_sec(occupations[indx])}~{self.time_from_int_sec(occupations[indx] + occupations_duration[indx])}   !!!!!!!!!!", 
                file=sys.stderr)
        
        return found_conflict

    def getHeuristicSolFromPath2(self, route_type, route_nums, path_id_, current_time, speed_level_, stop_time, time_early, cinfo, in_out):
        """
        根据给定的路径和其他信息生成新的列车运行方案
        
        Args:
            route_type: 路线类型，如果是"Replace"则替换路线，否则连接路线
            route_nums: 路线编号列表
            path_id_: 路径ID
            current_time: 当前时间
            speed_level_: 速度等级
            stop_time: 停站时间
            time_early: 提前时间
            cinfo: 车辆信息对象
            in_out: 进出标志，0表示进入车辆(添加到末尾)，1表示出站车辆(添加到开头)
            
        Returns:
            生成的列车运行方案(RouteSolution对象)
        """
        if route_type == "Replace":
            cinfo.route_num = int(route_nums[0])#如果是Replace，则路径编号取route_nums的第一个，即xml中如果是Replace：1196，会在excel表格中直接将路径编号替换为1196
            return self.getHeuristicSolFromPath1(route_nums[0], current_time, speed_level_, stop_time, time_early, cinfo)
        else:
            # "connect"连接类型，需要形成新的运行线，然后连接
            paths = []
            paths.append(path_id_)
            if in_out == 0:
                # 这是一个入库车辆，需要把新的路径编号添加到末尾
                for i in range(len(route_nums)):
                    paths.append(route_nums[i])
            else:
                # 这是一个出库车辆，需要把新的路径编号添加到前面
                for i in range(len(route_nums)):
                    paths.insert(0, route_nums[i])
            
            return self.get_heuristic_sol_from_path(paths, current_time, speed_level_, stop_time, time_early, cinfo)
            
    def getHeuristicSolFromPath1(self, path_id_, current_time, speed_level_, stop_time, time_early, cinfo):
        paths = []
        paths.append(path_id_)
        return self.get_heuristic_sol_from_path(paths, current_time, speed_level_, stop_time, time_early, cinfo)
    
    def get_heuristic_sol_from_path(self, paths: List[str], current_time: int, global_speed_level: int, 
                               stop_time: int, time_early: int, cinfo: CarInfo) -> RouteSolution:
        """
        根据给定的路径列表生成启发式解决方案：返回一个RouteSolution对象
        Args:
            paths: 路径ID列表
            current_time: 当前时间：用作发车时间
            global_speed_level: 全局速度等级
            stop_time: 停站时间
            time_early: 提前时间
            cinfo: 车辆信息对象
        Returns:
            路由解决方案对象
        """
        # 如果是第一辆车，忽略第一站的停站时间
        first_car = cinfo.implicit_round_num == 1
        rs = RouteSolution(current_time)

        path_id = paths[0]#取输入列表中的第一个参数作为路径编号
        cinfo.route_num = int(path_id)#确定路径编号
        total_time = 0
        stop_offset = 0  #stop_offset = 0即不进行整体偏移
        brand = [0.0] * 5  # 对应Java的float[] brand = new float[] { 0,0,0,0,0 }
        
        # 初始化
        path = self.pathList[path_id]
        init_station = path.dep_dest_code
        current_station = self.platform_station_map[init_station]#找到当前车站

        # 获取实际节点(站台目的地码）列表
        act_node_list = []
        for path_id in paths:
            if path_id not in self.pathList:
                print(f"错误：路径ID '{path_id}' 不存在于pathList中")
                # 可以返回一个默认值或抛出更明确的异常
                return None
            path = self.pathList[path_id]
            for node in path.nodeList:#node=一个站台码
                if not act_node_list or node != act_node_list[-1]:
                    act_node_list.append(node)

        if self.debug:
            print(f"车次路径编号:{ cinfo.route_num}")
            print(f"车次号:{ cinfo.round_num}")
            print(f"Current Station: {self.stationList[current_station].name}   id: {current_station}")
            print(f"       -- cur time: {self.time_from_int_sec(current_time)}")

        current_platform = ""
        # 处理除最后一个站点外的所有站点
        for i in range(len(act_node_list) - 1):
            speed_level = global_speed_level
            arr_time = current_time
            current_platform = act_node_list[i]
            
            if current_time >= time_early:
                stop_time = self.platformList[current_platform].def_dwell_time
                if stop_offset < 0:
                    stop_offset = self.platformList[current_platform].def_dwell_time
            else:
                stop_time = 0
                
            if i == 0 or (first_car and i == 0):
                stop_time = 0
                
            dep_time = current_time + stop_time

            # 检查站台是否被占用
            found_conflict = False
            if self.check_conflict:
                found_conflict = self.check_for_conflict(arr_time, dep_time, current_platform, path_id, cinfo)

            next_platform = act_node_list[i + 1]
            # 计算运行时间和速度等级
            if global_speed_level < 0:
                speed_level = self.platformList[current_platform].def_pl#采用默认速度等级
                
            elapsed_time = self.getTravelInterval(current_platform, next_platform, str(speed_level))#获取区间运行时间
            # stop_time = self.platformList[next_platform].def_dwell_time#获取默认停站时间
            # arr_time = dep_time
            brand[speed_level - 1] += elapsed_time
            current_time = dep_time + elapsed_time#这实际上就是计算列车到达下一站的时间
            total_time += elapsed_time + stop_time#- 累加总行程时间，包括区间运行时间和停站时间，这用于计算整个行程的总耗时
            
            rs.addStop(current_platform, stop_time, speed_level, arr_time, dep_time)

            if self.debug:
                stopped_time = arr_time + stop_time
                print(f"   Arrive time: {self.time_from_int_sec(arr_time)}({arr_time})")
                print(f"   Stop time: {stop_time}   Departure time: {self.time_from_int_sec(stopped_time)}({stopped_time})")
                first_station_name = self.stationList[self.platform_station_map[current_platform]].name
                second_station_name = self.stationList[self.platform_station_map[next_platform]].name
                print(f"   from {first_station_name} to {second_station_name}   time: {elapsed_time}")
                print(f"   Next arrival time: {self.time_from_int_sec(current_time)}({current_time})")
                print("   |")

        # 处理最后一个站点
        current_platform = act_node_list[-1]
        stop_time = self.platformList[current_platform].def_dwell_time
        speed_level = global_speed_level
        if global_speed_level < 0:
            speed_level = self.platformList[current_platform].def_pl
        # print(f"最后一个站点current_platform: {current_platform}")
        # print(f"最后一个站点stop_time: {stop_time}")
        # print(f"最后一个站点current_time: {current_time}")    
        rs.addStop(current_platform, stop_time, speed_level, current_time, current_time)
        rs.car_info = cinfo
        rs.offset_stop(stop_offset)

        return rs

    def compute_new_arrival(self, rs: 'RouteSolution', rs_oppo: 'RouteSolution', tar_end: str, level: int) -> int:
        """
        计算给定路线的新到达时间
        
        根据列车的交路类型(xroad)，计算从当前位置到目标站台的新到达时间。
        对于大交路(xroad=0)和小交路(xroad=1)有不同的处理逻辑。
        
        Args:
            rs: 当前列车运行方案
            rs_oppo: 对向列车运行方案
            tar_end: 目标站台
            level: 速度等级
            
        Returns:
            新的到达时间，如果无法计算则返回-1
        """
        # 获取起始站台，如果xroad=0（大交路）则使用最后一站，如果xroad=1（小交路）则使用倒数第二站
        rs_end = rs.stopped_platforms[len(rs.arr_time) - rs.xroad - 1]
        
        # 查找从起始站台到目标站台的路径
        new_path = self.find_path_by_start_end(rs_end, tar_end)
        if new_path is None:
            return -1
        
        # 计算新路径的全程运行时间
        new_travel_time = self.compute_full_length_time_full(new_path.id, level, 1)
        
        if rs.xroad == 1:
            # 小交路到大交路，返回模拟的小交路到达时间
            return self.compute_new_arrival_sb(rs, rs_end, tar_end, new_travel_time)
        elif rs.xroad == 0:
            # 大交路到小交路，返回模拟的小交路出发时间
            return self.compute_new_arrival_bs(rs, rs_oppo, rs_end, tar_end, new_travel_time)
        
        return -1

    def compute_new_arrival_sb(self, rs: 'RouteSolution', rs_end: str, tar_end: str, new_time: int) -> int:
        """
        计算小交路到大交路的新到达时间 (x->X)
        
        Args:
            rs: 当前列车运行方案
            rs_end: 起始站台
            tar_end: 目标站台
            new_time: 新路径的运行时间
            
        Returns:
            新的到达时间
        """
        # 使用倒数第二个出发时间作为起始时间
        start_time = rs.dep_time[len(rs.dep_time)- 2]
        return start_time + new_time

    def compute_new_arrival_bs(self, rs: 'RouteSolution', rs_oppo: 'RouteSolution', rs_end: str, tar_end: str, new_time: int) -> int:
        """
        计算大交路到小交路的新到达时间 (X->x)
        
        Args:
            rs: 当前列车运行方案
            rs_oppo: 对向列车运行方案
            rs_end: 起始站台
            tar_end: 目标站台
            new_time: 新路径的运行时间
            
        Returns:
            新的到达时间
        """
        # 使用第二个到达时间作为结束时间，然后减去新路径的运行时间
        end_time = rs.arr_time[1]
        return end_time - new_time

    def find_path_by_full_path(self, start_plt: str, end_plt: str, rs: 'RouteSolution') -> 'Path':
        """
        根据起始站台、终点站台和列车运行方案查找完整路径
        
        此方法首先检查是否已经找到过这条路径，如果找到过则直接返回。
        否则，遍历所有路径，查找起点和终点匹配，且中间停靠站台与给定列车运行方案相同的路径。
        
        Args:
            start_plt: 起始站台
            end_plt: 终点站台
            rs: 列车运行方案
            
        Returns:
            找到的路径，如果未找到则返回None
        """
        query = f"{start_plt}_{end_plt}"
        # 检查是否已经找到过这条路径
        if query in self.foundPaths:
            return self.foundPaths[query]
        
        # 如果之前没有找到过这条路径，需要查找
        for pid in self.pathList:
            pth = self.pathList[pid]
            if pth.nodeList[0] != start_plt:
                continue
            if pth.nodeList[len(pth.nodeList)-1] != end_plt:
                continue
            
            # 确保所有停靠站台都相同
            matching = True
            for j in range(1, len(rs.stopped_platforms) - 1):
                if pth.nodeList[j] != rs.stopped_platforms[j]:
                    matching = False
                    break
            
            if not matching:
                continue
            
            # 如果这条路线从a开始到b结束，存储并返回
            self.foundPaths[query] = pth
            return self.pathList[pid]
        
        return None

    def change_bs_path(self, rs: 'RouteSolution', rs_oppo: 'RouteSolution', tar_end: str, level: int, stop_prev: bool):
        """
        更改当前路径为新路径，并连接到相反方向的路径
        
        根据列车的交路类型(xroad)，有两种不同的处理逻辑：
        1. 小交路到大交路(xroad=1)：在rs的末尾添加新路径
        2. 大交路到小交路(xroad=0)：在rs_oppo的开头添加新路径
        
        Args:
            rs: 当前列车运行方案
            rs_oppo: 对向列车运行方案
            tar_end: 目标站台
            level: 速度等级
            stop_prev: 是否在前一站停车
        """
        rs_end = rs.stopped_platforms[len(rs.arr_time) - rs.xroad - 1]
        path = self.find_path_by_start_end(rs_end, tar_end)
        
        if self.debug:
            util.pf(f"Path id: {path.id}   {rs.xroad}->{rs_oppo.xroad}")
        
        if rs.xroad == 1:
            # 小交路到大交路，在rs的末尾添加
            # 步骤1：移除最后一站
            rs.arr_time.pop()
            rs.dep_time.pop()
            rs.stopped_platforms.pop()
            rs.stopped_time.pop()
            rs.performance_levels.pop()
            
            current_platform = rs.stopped_platforms[len(rs.stopped_platforms)-1]
            
            if self.debug:
                util.pf(f" OLD::: From {rs.stopped_platforms[0]} to {rs.stopped_platforms[len(rs.stopped_platforms) - 1]}")
                util.pf(f" NEW::: From {path.nodeList[0]} to {path.nodeList[len(path.nodeList) - 1]}")
            
            # 步骤2：向rs添加节点
            for i in range(len(path.nodeList)):
                next_platform = path.nodeList[i]
                if current_platform == next_platform:
                    continue
                
                rs.stopped_platforms.append(next_platform)
                
                if self.debug:
                    util.pf(f"   added plt: {next_platform}")
                
                last_dep_time = rs.dep_time[len(rs.dep_time)-1]
                t_time = self.getTravelInterval(current_platform, next_platform, str(level))
                
                arr_t = last_dep_time + t_time
                rs.arr_time.append(arr_t)
                
                plt = self.platformList[next_platform]
                dwell = plt.def_dwell_time
                if not stop_prev:
                    dwell = 0
                
                rs.dep_time.append(dwell + arr_t)
                rs.stopped_time.append(dwell)
                
                if level < 0:
                    rs.performance_levels.append(self.platformList[current_platform].def_pl)
                else:
                    rs.performance_levels.append(level)
                
                current_platform = next_platform
            
            # 为carinfo分配正确的到达时间
            rs.car_info.arr_time = rs.dep_time[len(rs.dep_time) - 1]
            
            # 分配正确的路径ID
            path_new = self.find_path_by_full_path(rs.stopped_platforms[0], rs.stopped_platforms[len(rs.stopped_platforms) - 1], rs)
            rs.car_info.route_num = int(path_new.id)
            
            # 修改了尾部，所以修改最后一位
            rs.side_notification += 1
            if rs.side_notification >= 3:
                rs.side_notification = 0
                rs.xroad = 0
        
        elif rs.xroad == 0:
            # 大交路到小交路，在rs_oppo的开头添加
            # 步骤1：移除第一站
            rs_oppo.arr_time.pop(0)
            rs_oppo.dep_time.pop(0)
            rs_oppo.stopped_platforms.pop(0)
            rs_oppo.stopped_time.pop(0)
            rs_oppo.performance_levels.pop(0)
            
            current_platform = rs_oppo.stopped_platforms[0]
            
            # 步骤2：向rs添加节点
            for i in range(len(path.nodeList)-1, -1, -1):
                prev_platform = path.nodeList[i]
                if current_platform == prev_platform:
                    continue
                
                rs_oppo.stopped_platforms.insert(0, prev_platform)
                
                last_arr_time = rs.arr_time[0]
                t_time = self.getTravelInterval(prev_platform, current_platform, str(level))
                det_t = last_arr_time - t_time
                
                rs.dep_time.insert(0, det_t)
                
                plt = self.platformList[prev_platform]
                dwell = plt.def_dwell_time
                if not stop_prev:
                    dwell = 0
                
                rs_oppo.arr_time.insert(0, det_t - dwell)
                rs_oppo.stopped_time.append(dwell)
                
                current_platform = prev_platform
                
                rs.performance_levels.insert(0, level)
            
            # 分配正确的路径ID
            if self.debug:
                util.pf(f"From {rs_oppo.stopped_platforms[0]} to {rs_oppo.stopped_platforms[len(rs_oppo.stopped_platforms) - 1]}")
            
            path_new = self.find_path_by_full_path(rs_oppo.stopped_platforms[0], rs_oppo.stopped_platforms[len(rs_oppo.stopped_platforms) - 1], rs_oppo)
            rs_oppo.car_info.route_num = int(path_new.id)
            
            # 修改了头部，所以修改第一位
            rs_oppo.side_notification += 2
            
            if rs_oppo.side_notification >= 3:
                rs_oppo.side_notification = 0
                rs_oppo.xroad = 0

    def compute_new_arrival_sb(self, rs: 'RouteSolution', rs_end: str, tar_end: str, new_time: int) -> int:
        """
        计算小交路到大交路的新到达时间 (x->X)
        
        Args:
            rs: 当前列车运行方案
            rs_end: 起始站台
            tar_end: 目标站台
            new_time: 新路径的运行时间
            
        Returns:
            新的到达时间
        """
        # 使用倒数第二个出发时间作为起始时间
        start_time = rs.dep_time[len(rs.dep_time) - 2]
        return start_time + new_time

    def compute_new_arrival_bs(self, rs: 'RouteSolution', rs_oppo: 'RouteSolution', rs_end: str, tar_end: str, new_time: int) -> int:
        """
        计算大交路到小交路的新到达时间 (X->x)
        
        Args:
            rs: 当前列车运行方案
            rs_oppo: 对向列车运行方案
            rs_end: 起始站台
            tar_end: 目标站台
            new_time: 新路径的运行时间
            
        Returns:
            新的到达时间
        """
        # 使用第二个到达时间作为结束时间，然后减去新路径的运行时间
        end_time = rs.arr_time[1]
        return end_time - new_time