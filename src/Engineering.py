from typing import List, Dict, Optional
from enum import Enum
import sys
import math
import pandas as pd
import time as sys_time
import os
from DataReader import DataReader
from PhaseTime import PhaseTime
from Platform import PlatformType
from PhaseTime import PHASETYPE
from UserSetting import UserSetting
from RailInfo import RailInfo
from RouteSolution import RouteSolution
from CarInfo import CarInfo
from Util import util
from ConflictPair import ConflictPair
from IntervalRecorder import IntervalRecorder
from DepotRoutesInfo import DepotRoutesInfo
from Pulp import *
import matplotlib.pyplot as plt

class Params:
    def __init__(self):
        self.peaks = []
        self.depot_routes = []
        self.depotsInfo = []


class Engineering:
    """
    Engineering类是列车调度系统的接口类：
    1、负责数据输入的读取。
    2、负责Excel时刻表文件的输出（调用其他类）。
    """

    # 用于快速检索的辅助值
    IN_INDX: int = 0  # 进站索引
    OUT_INDX: int = 1  # 出站索引
    UP_INDX: int = 0  # 上行索引
    DOWN_INDX: int = 1  # 下行索引

    def __init__(self, debug: bool,
                 ftar: str,
                 ftar_setting: str):
        """
        构造函数
        Args:
            debug: 是否开启调试模式
            ftar: 轨道参数信息文件路径
            ftar_setting: 用户参数设置文件路径
        """

        # 是否输出调试信息的标志
        self.debug: bool = debug
        self.amount_delta: int = 0.01
        # 读入文件的数据对象
        self.us: UserSetting  # 用户设置
        self.rl: RailInfo  # 铁路信息

        # 默认性能等级速度
        self.level: int = -1
        # 已发送车辆计数器
        self.cont_n_sent: int = 0

        # 计划完成标志
        self.planning_done: bool = False
        self.require_reopt: bool = False

        # 用于识别交叉路的最后车辆计数器
        self.last_c_up: int = 0    # 上行最后车辆
        self.last_c_dn: int = 0    # 下行最后车辆
        # 新生成阶段的列表
        self.Phases: List[PhaseTime] = []
        # 进出站车辆可能冲突的列表
        self.cpr_out: List[ConflictPair] = []  # 出站冲突
        self.cpr_in: List[ConflictPair] = []  # 进站冲突

        # 进出站车辆修改映射
        self.modified_out: Dict[int, List[int]] = {}
        self.modified_in: Dict[int, List[int]] = {}

        # 需要修改的路线列表
        self.to_modify_init: List[RouteSolution] = []
        self.to_modify_init_amnt: List[int] = []

        # 全局安全停站时间差
        self.global_dwell_diff: List[int] = []

        # 当前找到的最佳间隔记录器
        self.besst_ir: Optional[IntervalRecorder] = None
        self.vehicle_pool = set()  # 可用车辆池
        self.active_vehicles = set()  # 当前在线车辆
        self.max_vehicle_id = 0  # 最大车辆编号
        self.round_counter = 1  # 全局车次号计数器
        # 使用DataReader读取设置文件
        dr = DataReader(debug)
        self.rl = dr.read_file(ftar)  # 读取轨道信息文件
        self.us = dr.read_setting_file(ftar_setting)  # 读取峰期信息文件
        self.rl.generateReqInfo()  # 完成站台占用的信息关系写入
        self.rl.initialize_depot_cars(self.us)

    def get_available_vehicle_id(self):
        """
        获取可用的车辆编号
        优先使用回收的车辆编号，否则分配新编号
        车辆编号限制在1到最大车辆数范围内（根据用户设置动态确定）
        """
        # 动态获取最大车辆数（所有峰期中的最大train_num值）
        max_vehicles = max(peak.train_num for peak in self.us.peaks) if self.us.peaks else 45
        
        if self.vehicle_pool:
            vehicle_id = self.vehicle_pool.pop()
        else:
            self.max_vehicle_id += 1
            # 如果超过最大值，采用循环分配策略
            if self.max_vehicle_id > max_vehicles:
                # 循环使用车辆编号，从1开始重新分配
                for i in range(1, max_vehicles + 1):
                    if i not in self.active_vehicles:
                        vehicle_id = i
                        break
                else:
                    # 如果所有车辆都在使用，强制使用循环编号（允许重复）
                    vehicle_id = ((self.max_vehicle_id - 1) % max_vehicles) + 1
                    print(f"警告：车辆资源不足，重复使用车辆编号 {vehicle_id}")
            else:
                vehicle_id = self.max_vehicle_id
        
        self.active_vehicles.add(vehicle_id)
        return vehicle_id
    
    def release_vehicle_id(self, vehicle_id):
        """
        释放车辆编号，使其可以被重新使用
        """
        if vehicle_id in self.active_vehicles:
            self.active_vehicles.remove(vehicle_id)
            self.vehicle_pool.add(vehicle_id)

    def get_next_round_num(self):
        """
        获取下一个车次号
        """
        round_num = self.round_counter
        self.round_counter += 1
        if self.round_counter > 999:
            self.round_counter = 1
        return round_num

    def update_inout_time(self, spd_lvl: int) -> None:
        """
        根据指定的速度等级更新所有车库进出站路线的运行时间
        Args:
            spd_lvl: 用于计算运行时间的性能/速度等级
        """
        # print("打印depot_routes_infos内容1：")
        # self.print_depot_routes_infos()
        
        for xroad in range(len(self.us.depot_routes_infos)):
            dpi = self.us.depot_routes_infos[xroad]
            for inout in range(2):
                for dir in range(2):
                    # 遍历所有列车
                    for i in range(len(dpi.routes[inout][dir])):
                        travel_time = self.rl.compute_full_length_time_full(
                            dpi.routes[inout][dir][i], spd_lvl, 0)
                        dpi.routes_time[inout][dir][i] = travel_time

    def load_routes_2_dim(self, rss: List[List[RouteSolution]]) -> None:
        """
        将计划列表中的所有路线加载到实际解决方案类中
        Args:
            rss: 解决方案的二维列表 [方向][路线]
        """
        # 加载上行方向的路线
        for rs in rss[0]:
            if rs is None:
                continue
            self.rl.addTrainSolution(rs)

        # 加载下行方向的路线
        for rs in rss[1]:
            if rs is None:
                continue
            self.rl.addTrainSolution(rs)

    def load_routes_3_dim(self, rss):
        """
        从计划列表加载所有路线到实际解决方案类中
        
        Args:
            rss: 包含RouteSolution对象的三维列表
        """
        # 打印rss三维列表的每个维度规模
        print("=== rss三维列表的维度规模 ===")
        print("=== rss三维列表中RouteSolution对象统计 ===")
        total_routes = 0
        valid_routes = 0
        print(f"第一维度(阶段数量): {len(rss)}")
        for phase_idx in range(len(rss)):
            print(f"  阶段[{phase_idx}]的方向数量: {len(rss[phase_idx])}")
            for dir_idx in range(len(rss[phase_idx])):
                dir_name = "上行" if dir_idx == 0 else "下行"
                print(f"    方向[{dir_idx}]({dir_name})的路线数量: {len(rss[phase_idx][dir_idx])}")
                for route_idx in range(len(rss[phase_idx][dir_idx])):
                    total_routes += 1
                    if rss[phase_idx][dir_idx][route_idx] is not None:
                        valid_routes += 1
        print(f"RouteSolution对象总数: {total_routes}")
        print(f"有效RouteSolution对象数: {valid_routes}")
        print("=========================")
        
        for phase_idx in range(len(rss)):
            for rs in rss[phase_idx][0]: #上行数据
                if rs is None:
                    continue
                self.rl.addTrainSolution(rs) 
            for rs in rss[phase_idx][1]:#下行数据
                if rs is None:
                    continue
                self.rl.addTrainSolution(rs)

    def connect(self) -> None:
        """
        连接时刻表中所有相连的列车
        通过修改它们的列车编号（表号）使它们被视为同一列车
        """
        connected = {}  # 使用dict替代Java的Hashtable
        for r_idx in range(len(self.rl.sl.route_lists)):
            rs = self.rl.sl.route_lists[r_idx]
            # 这个车辆需要连接（非入库车）
            if rs.next_ptr is not None and rs.car_info.table_num not in connected:
                try:
                    self.connect_routes(rs, connected)
                except Exception as e:
                    util.pf(util.ANSI_RED + f"连接路线时出错: {e}")
                    util.pf(util.ANSI_YELLOW + f"rs.car_info.table_num = {rs.car_info.table_num}")
                    util.pf(util.ANSI_YELLOW + f"connected = {connected}")

    def connect_routes(self, rs: RouteSolution, connected: Dict[int, int]) -> int:
        """
        连接列车并记录它们的车次编号(如果之前未记录)
        Args:
            rs: 路由解决方案对象
            connected: 已连接的列车编号字典 {车次编号: 车轮数}
        Returns:
            列车编号(tbm)
        """
        # util.pf(f"调用 connect_routes: rs.car_info.table_num = {rs.car_info.table_num}")
        tbm = -1
        if rs.next_ptr is not None:
            # 如果连接的路线已经连接,需要跟随该路线,无需继续探索
            if rs.next_ptr.car_info.table_num in connected:
                # tbm = rs.car_info.table_num = rs.next_ptr.car_info.table_num
                rs.car_info.table_num = rs.next_ptr.car_info.table_num
                tbm = rs.next_ptr.car_info.table_num
                rs.car_info.round_num = connected[rs.next_ptr.car_info.table_num]
                # 更新每个车次编号的表号
                connected[rs.car_info.table_num] = rs.car_info.round_num + 1
                # util.pf(f"已连接路线: tbm = {tbm}, 类型 = {type(tbm)}")
            else:
                tbm = self.connect_routes(rs.next_ptr, connected)
                # util.pf(f"递归调用返回: tbm = {tbm}, 类型 = {type(tbm)}")
                
                # 确保 tbm 是整数
                if not isinstance(tbm, int):
                    util.pf(util.ANSI_YELLOW + f"警告: tbm 不是整数类型，而是 {type(tbm)}")
                    if hasattr(tbm, 'table_num'):
                        tbm = tbm.table_num
                        util.pf(f"已转换 tbm 为 {tbm}")
                    else:
                        util.pf(util.ANSI_RED + f"错误: tbm 对象没有 table_num 属性")
                        tbm = -1
                
                if tbm < 0:
                    util.pf(util.ANSI_RED + "ERROR:: connecting error")
                    sys.exit(1)
                rs.car_info.table_num = tbm
                # 确保tbm在connected字典中存在
                if tbm not in connected:
                    util.pf(util.ANSI_YELLOW + f"警告: tbm={tbm} 不在connected字典中")
                    util.pf(util.ANSI_YELLOW + f"connected字典内容: {connected}")
                    connected[tbm] = 0
                rs.car_info.round_num = connected[tbm]
                connected[rs.car_info.table_num] = rs.car_info.round_num + 1
        else:
            tbm = rs.car_info.table_num
            connected[rs.car_info.table_num] = rs.car_info.round_num + 1
            # util.pf(f"无下一路线: tbm = {tbm}, 类型 = {type(tbm)}")
        
        # 确保返回整数
        result = tbm if isinstance(tbm, int) else tbm.table_num
        # util.pf(f"connect_routes 返回: {result}, 类型 = {type(result)}")
        return result


    def set_init_last_c(self):
        """
        恢复基于第一个高峰期的列车计数器，为初始阶段做准备
        需要为初始车辆预留空间
        """
        # 从第一个阶段获取高峰期信息
        pk = self.Phases[0].pk
        
        # 从用户设置中获取总车辆数
        n_cars = self.us.peaks[0].train_num
        
        # 计算上行列车数（总车辆数的一半）
        up_car = n_cars // 2
        
        # 计算下行列车数（总车辆数减去上行列车数）
        dn_car = n_cars - up_car
        
        # 更新类的成员变量
        self.last_c_dn = dn_car  # 下行列车数
        self.last_c_up = up_car  # 上行列车数

    def generate_phase1_optimized(self, level: int, p_idx_offset: int, res: List[List[List[RouteSolution]]]) -> List[List[List[RouteSolution]]]:
        """
        优化版本：使车次数与优化模型完全一致
        根据多阶段信息生成列车运行线，确保车次数与优化模型匹配
        
        Args:
            level: 速度等级
            p_idx_offset: 阶段索引偏移量  
            res: 结果列表
        Returns:
            调度结果列表
        """
        self.set_init_last_c()
        last_deter_interval_up = -1
        last_deter_interval_dn = -1
        
        # 预计算每个阶段的目标车次数（与优化模型一致）
        target_trips_per_phase = self.calculate_target_trips_per_phase()
        
        for p_idx in range(1, len(self.Phases)):
            pt = self.Phases[p_idx]
            phase_res = []
            local_interval = pt.interval
            
            if pt.p_type != PHASETYPE.STABLE:
                last_deter_interval_up = local_interval
            elif last_deter_interval_up > 0:
                local_interval = last_deter_interval_up
            
            # 获取该阶段的目标车次数
            phase_target = target_trips_per_phase.get(p_idx, {})
            target_up_large = phase_target.get('up_large', 0)
            target_up_small = phase_target.get('up_small', 0)
            target_dn_large = phase_target.get('dn_large', 0)
            target_dn_small = phase_target.get('dn_small', 0)
            
            # 生成上行方向（精确控制车次数）
            up_res = self.generate_direction_with_target_count(
                pt, level, 0, target_up_large, target_up_small, p_idx + p_idx_offset
            )
            phase_res.append(up_res)
            
            # 生成下行方向（精确控制车次数）
            dn_res = self.generate_direction_with_target_count(
                pt, level, 1, target_dn_large, target_dn_small, p_idx + p_idx_offset
            )
            phase_res.append(dn_res)
            
            res.append(phase_res)
        
        return res

    def calculate_target_trips_per_phase(self) -> dict:
        """
        计算每个阶段的目标车次数，与优化模型逻辑完全一致
        
        Returns:
            字典，键为阶段索引，值为该阶段各交路类型的目标车次数
        """
        target_trips = {}
        
        for p_idx in range(1, len(self.Phases)):
            pt = self.Phases[p_idx]
            pk = pt.pk
            
            # 使用与优化模型相同的计算逻辑
            peak_duration = pt.t_e - pt.t_s  # 峰期时长（秒）
            route_interval = pt.interval  # 共线间隔（秒）
            
            # 与优化模型完全一致的计算方式
            actual_full_trains = int(np.round(peak_duration / route_interval)) + 1
            
            # 根据开行比例分配大小交路车次
            if pk.op_rate1 == -1 and pk.op_rate2 == -1:
                # 只有大交路
                large_trains = actual_full_trains
                small_trains = 0
            else:
                # 有大小交路
                total_rate = pk.op_rate1 + pk.op_rate2
                large_trains = int(actual_full_trains * pk.op_rate1 / total_rate)
                small_trains = actual_full_trains - large_trains
            
            # 上下行分配（与优化模型一致）
            target_trips[p_idx] = {
                'up_large': int(np.ceil(large_trains / 2)),
                'dn_large': int(np.floor(large_trains / 2)),
                'up_small': int(np.ceil(small_trains / 2)),
                'dn_small': int(np.floor(small_trains / 2))
            }
        
        return target_trips

    def generate_direction_with_target_count(self, pt: PhaseTime, level: int, direction: int, 
                                        target_large: int, target_small: int, phase_idx: int) -> List[RouteSolution]:
        """
        按目标车次数精确生成指定方向的列车
        
        Args:
            pt: 阶段时间信息
            level: 速度等级
            direction: 方向（0=上行，1=下行）
            target_large: 大交路目标车次数
            target_small: 小交路目标车次数
            phase_idx: 阶段索引
        Returns:
            该方向的列车列表
        """
        result = []
        pk = pt.pk
        period = pk.op_rate1 + pk.op_rate2
        
        # 计算总目标车次数
        total_target = target_large + target_small
        if total_target == 0:
            return result
        
        # 计算平均间隔，确保在时间窗口内均匀分布
        time_window = pt.t_e - pt.t_s
        if total_target > 1:
            avg_interval = time_window / (total_target - 1)
        else:
            avg_interval = pt.interval
        
        # 生成车次序列（按开行比例）
        trip_sequence = self.generate_trip_sequence(target_large, target_small, pk.op_rate1, pk.op_rate2)
        
        # 按序列生成列车
        for i, xroad in enumerate(trip_sequence):
            # 计算发车时刻
            if total_target == 1:
                dep_time = pt.t_s + time_window // 2  # 单车次放在中间
            else:
                dep_time = pt.t_s + int(i * avg_interval)
            
            # 确保不超出时间窗口
            if dep_time >= pt.t_e:
                break
                
            # 创建列车
            self.cont_n_sent += 1
            dummy = CarInfo(self.cont_n_sent, 1 + 100 * self.cont_n_sent, -1)
            # vehicle_id = self.get_available_vehicle_id()
            # round_num = self.get_next_round_num()  # 获取车次号
            # dummy = CarInfo(vehicle_id, round_num, -1)
            # 选择路径
            if direction == 0:  # 上行
                route = pk.routes[xroad].up_route
            else:  # 下行
                route = pk.routes[xroad].down_route
            
            # 调整小交路发车时间
            local_time = dep_time
            if xroad == 1 and len(pk.routes) > 1:
                if direction == 0:
                    local_time = self.get_act_send_time(dep_time, pk.routes[0].up_route, route, level)
                else:
                    local_time = self.get_act_send_time(dep_time, pk.routes[0].down_route, route, level)
            
            # 生成运行方案
            rs = self.rl.getHeuristicSolFromPath1(route, local_time, level, 30, self.us.first_car, dummy)
            rs.dir = direction
            rs.xroad = xroad
            rs.phase = phase_idx
            result.append(rs)
            
            # 更新最后发车时间
            self.rl.last_sent[direction] = local_time
        
        return result

    def generate_trip_sequence(self, target_large: int, target_small: int, op_rate1: int, op_rate2: int) -> List[int]:
        """
        生成车次序列，按开行比例分布大小交路
        
        Args:
            target_large: 大交路车次数
            target_small: 小交路车次数
            op_rate1: 大交路开行比例
            op_rate2: 小交路开行比例
        Returns:
            车次序列，0表示大交路，1表示小交路
        """
        if target_small == 0:
            return [0] * target_large
        
        if target_large == 0:
            return [1] * target_small
        
        # 按比例交替排列
        sequence = []
        large_count = 0
        small_count = 0
        
        total_target = target_large + target_small
        for i in range(total_target):
            # 根据比例决定当前车次类型
            if op_rate1 > 0 and op_rate2 > 0:
                cycle_pos = i % (op_rate1 + op_rate2)
                if cycle_pos < op_rate1 and large_count < target_large:
                    sequence.append(0)
                    large_count += 1
                elif small_count < target_small:
                    sequence.append(1)
                    small_count += 1
                elif large_count < target_large:
                    sequence.append(0)
                    large_count += 1
            else:
                # 处理特殊情况
                if large_count < target_large:
                    sequence.append(0)
                    large_count += 1
                else:
                    sequence.append(1)
                    small_count += 1
        
        return sequence

    def generate_initial_phase1_optimized(self, res1: List[List[List[RouteSolution]]], level: int) -> List[List[List[RouteSolution]]]:
        """
        优化版本：使初始出库车次数与优化模型匹配
        根据计算的间隔生成首班车之前的车辆，确保车次数与优化模型一致
        
        Args:
            res1: 存储调度结果的三维列表
            level: 速度等级
        Returns:
            更新后的调度结果列表
        """
        pt = self.Phases[0]
        phase_res = []
        
        # 获取优化模型中的初始车次数
        target_initial_trips = self.get_optimization_initial_trips()
        
        # 计算发车间隔（与优化模型保持一致）
        n_cars = self.us.peaks[0].train_num
        interval = self.rl.total_run_time[0] // n_cars
        
        # 生成上行初始车次
        up_car = target_initial_trips['up_large'] + target_initial_trips['up_small']
        up_res = self.generate_initial_direction(
            pt, level, 0, up_car, target_initial_trips['up_large'], 
            target_initial_trips['up_small'], interval
        )
        phase_res.append(up_res)
        
        # 生成下行初始车次
        dn_car = target_initial_trips['dn_large'] + target_initial_trips['dn_small']
        dn_res = self.generate_initial_direction(
            pt, level, 1, dn_car, target_initial_trips['dn_large'], 
            target_initial_trips['dn_small'], interval
        )
        phase_res.append(dn_res)
        
        # 更新计数器
        self.last_c_up = up_car
        self.last_c_dn = dn_car
        
        # 插入结果并更新阶段
        res1.insert(0, phase_res)
        
        # 创建初始阶段
        pt_init = PhaseTime(0, self.Phases[0].t_s, n_cars, interval, 
                        PHASETYPE.STABLE, pt.pk,
                        self.us.predict_Interval_up[0], 
                        self.us.predict_Interval_dn[0])
        self.Phases.insert(0, pt_init)
        
        # 更新后续阶段编号
        for i in range(1, len(res1)):
            for dir in range(2):
                for idx in range(len(res1[i][dir])):
                    res1[i][dir][idx].phase += 1
        
        # 调整时间范围
        if res1[0][0] and res1[0][1]:
            self.Phases[0].t_s = min(res1[0][0][0].arr_time[0], res1[0][1][0].arr_time[0])
        
        return res1

    def generate_initial_direction(self, pt, level: int, direction: int, total_cars: int, 
                                large_route_cars: int, small_route_cars: int, interval: int) -> List[RouteSolution]:
        """
        生成指定方向的初始车次
        
        Args:
            pt: 阶段时间信息
            level: 速度等级
            direction: 运行方向 (0: 上行, 1: 下行)
            total_cars: 该方向总车辆数
            large_route_cars: 大交路车辆数
            small_route_cars: 小交路车辆数
            interval: 发车间隔
        
        Returns:
            该方向的运行方案列表
        """
        direction_res = []
        t_ptr = pt.t_s - interval  # 从第一个阶段开始时间往前推
        pk = pt.pk  # 获取峰期信息
        
        # 生成车次计数器（倒序）
        c_indx = total_cars - 1
        
        for i in range(total_cars):
            xroad = 0  # 默认使用大交路
            local_time = round(t_ptr)
            self.cont_n_sent += 1
            dummy = CarInfo(self.cont_n_sent, 1 + 100 * self.cont_n_sent, -1)
            # vehicle_id = self.get_available_vehicle_id()
            # round_num = self.get_next_round_num()  # 获取车次号
            # dummy = CarInfo(vehicle_id, round_num, -1)
            # 根据方向选择路线
            if direction == 0:  # 上行
                route = pk.routes[0].up_route
            else:  # 下行
                route = pk.routes[0].down_route
            
            # 判断是否使用小交路
            # 根据车次索引和大小交路配置决定使用哪种交路
            if len(pk.routes) > 1:
                # 计算当前车次应该使用的交路类型
                # 前 large_route_cars 个车次使用大交路，后面使用小交路
                if i >= large_route_cars:
                    if direction == 0:  # 上行
                        local_time = self.get_act_send_time(local_time, route, pk.routes[1].up_route, level)
                        route = pk.routes[1].up_route
                    else:  # 下行
                        local_time = self.get_act_send_time(local_time, route, pk.routes[1].down_route, level)
                        route = pk.routes[1].down_route
                    xroad = 1
            
            # 生成运行方案
            rs = self.rl.getHeuristicSolFromPath1(route, local_time, level, 30, 0, dummy)
            rs.dir = direction
            rs.xroad = xroad
            rs.phase = 0
            
            # 倒序添加到结果列表
            direction_res.insert(0, rs)
            c_indx -= 1
            t_ptr -= interval
        
        return direction_res
    def get_optimization_initial_trips(self) -> dict:
        """
        获取优化模型中的初始车次数配置
        
        Returns:
            初始车次数字典
        """
        # 这里需要根据优化模型的具体逻辑来计算
        # 假设优化模型中初始车次数为58（根据你的描述）
        total_initial = 58
        
        # 按大小交路和上下行分配
        pk = self.Phases[0].pk if self.Phases else self.us.peaks[0]
        
        if pk.op_rate1 == -1 and pk.op_rate2 == -1:
            # 只有大交路
            large_total = total_initial
            small_total = 0
        else:
            # 按比例分配
            total_rate = pk.op_rate1 + pk.op_rate2
            large_total = int(total_initial * pk.op_rate1 / total_rate)
            small_total = total_initial - large_total
        
        return {
            'up_large': int(np.ceil(large_total / 2)),
            'dn_large': int(np.floor(large_total / 2)),
            'up_small': int(np.ceil(small_total / 2)),
            'dn_small': int(np.floor(small_total / 2))
        }

    def compute_unified_intervals(self) -> None:
        """
        统一间隔计算方法，确保与优化模型一致
        """
        for i, phase in enumerate(self.Phases):
            if i == 0:  # 跳过初始阶段
                continue
                
            pk = phase.pk
            
            # 使用与优化模型相同的间隔计算逻辑
            # 这里需要根据你的优化模型具体实现来调整
            peak_duration = phase.t_e - phase.t_s
            target_trains = pk.train_num
            
            # 统一的间隔计算公式
            unified_interval = peak_duration / target_trains
            
            # 更新阶段间隔
            phase.interval = unified_interval
            
            print(f"阶段{i}统一间隔: {unified_interval}秒")
        
    def is_normal_service_train(self, rs: RouteSolution) -> bool:
        """
        判断是否为正常折返车次（排除出入库车次）
        
        Args:
            rs: RouteSolution对象
            
        Returns:
            bool: True表示正常折返车次，False表示出入库车次
        """
        if rs is None:
            return False
        
        # 排除条件1：运营开始前的出库车次（generate_initial_phase1生成）
        # 这些车次通常在第一个阶段且没有前序车次
        if rs.phase == 0 and rs.prev_ptr is None:
            return False
        
        # 排除条件2：phase_inout阶段添加的出入库车次
        # 入库车次：没有后续车次的末车
        # 出库车次：没有前序车次的首车（但不是第一阶段的）
        if rs.next_ptr is None and rs.phase > 0:  # 入库车次
            return False
        if rs.prev_ptr is None and rs.phase > 0:  # 出库车次（非初始阶段）
            return False
        
        # 排除条件3：可能的车库相关路径特征
        # 可以通过路径信息或其他特征进一步识别
        # 这部分需要根据实际的车库路径配置来判断
        return True        

    def extract_normal_service_trips_from_schedule(self, res_schedule):
        """
        从优化模型结果中提取正常折返车次
        
        Args:
            res_schedule: 优化模型结果 (4, v_num)
            
        Returns:
            正常折返车次的时刻数据
        """
        normal_trips = []
        
        for route in range(4):  # 4种交路类型
            # 跳过初始出库车次，从 initial_trip_num[route] 开始
            start_idx = self.params.initial_trip_num[route]
            
            for trip_idx in range(start_idx, res_schedule.shape[1]):
                if not np.isnan(res_schedule[route, trip_idx]):
                    normal_trips.append({
                        'route_type': route,
                        'trip_index': trip_idx - start_idx,  # 正常折返车次内的索引
                        'departure_time': res_schedule[route, trip_idx]
                    })
        
        return normal_trips        

    def generate_phase1(self, level: int, p_idx_offset: int, res: List[List[List[RouteSolution]]]) -> List[List[List[RouteSolution]]]:
        """
        根据多阶段信息生成列车运行线
        * 此方法根据 compute_new_phases 生成的各个调度阶段 (Phases) 来安排后续的列车。
        * 它遍历除初始阶段(即运营开始前时段）外的所有阶段，
        * 根据每个阶段的起止时间、列车数、发车间隔以及大小交路运营比例 (pk.op_rate1, pk.op_rate2)，
        * 生成上行 (UP_INDX) 和下行 (DOWN_INDX) 的列车运行方案 (RouteSolution)。
        * 对于小交路列车，会通过 get_act_send_time 调整其实际发车时间，以匹配大交路。
        * 最终，这些方案会被添加到结果列表 (res) 中，并返回。
        Args:
            level: 速度等级
            p_idx_offset: 阶段索引偏移量
            res: 结果列表
        Returns:
            调度结果列表
        """
        self.set_init_last_c()#初始化上下行列车计数器
        # 设置上下行方向的间隔记录  
        last_deter_interval_up = -1
        last_deter_interval_dn = -1
        # print(f"len(self.Phases):{len(self.Phases)}")#阶段数：在之前的函数中已经创立
        #函数从第二个阶段开始遍历（索引从1开始），因为第一个阶段是初始阶段。
        #初始阶段=运营开始前出库时段
        for p_idx in range(1, len(self.Phases)):
            pt = self.Phases[p_idx]
            phase_res = []
            local_interval = pt.interval
            #根据阶段类型调整发车间隔
            if pt.p_type != PHASETYPE.STABLE:
                last_deter_interval_up = local_interval
            elif last_deter_interval_up > 0:
                local_interval = last_deter_interval_up

            # 生成上行方向
            t_ptr = max(pt.t_s, self.rl.last_sent[0] + local_interval)
            pt.offset_up = int(round(t_ptr)) - pt.t_s
            pk = pt.pk
            period = pk.op_rate1 + pk.op_rate2
            c_indx = self.last_c_up
            
            up_res = []
            total_sent = 0
            
            while t_ptr < pt.t_e:
                xroad = 0
                local_time = int(round(t_ptr))
                self.cont_n_sent += 1
                dummy = CarInfo(self.cont_n_sent, 1 + 100 * self.cont_n_sent, -1)
                # vehicle_id = self.get_available_vehicle_id()
                # round_num = self.get_next_round_num()  # 获取车次号
                # dummy = CarInfo(vehicle_id, round_num, -1)
                route = pk.routes[0].up_route
                
                if c_indx % period >= pk.op_rate1 and len(pk.routes) > 1:  # 添加长度检查
                    local_time = self.get_act_send_time(local_time, route, pk.routes[1].up_route, level)
                    route = pk.routes[1].up_route
                    xroad = 1
                    
                rs = self.rl.getHeuristicSolFromPath1(route, local_time, level, 30, self.us.first_car, dummy)
                rs.dir = 0
                total_sent += 1
                rs.xroad = xroad
                rs.phase = p_idx + p_idx_offset
                up_res.append(rs)
                self.rl.last_sent[0] = int(round(t_ptr))
                c_indx += 1
                self.last_c_up = c_indx
                t_ptr += local_interval
                
            phase_res.append(up_res)

            # 生成下行方向
            t_ptr = max(pt.t_s, self.rl.last_sent[1] + local_interval)
            pt.offset_dn = int(round(t_ptr)) - pt.t_s
            c_indx = self.last_c_dn
            dn_res = []
            
            while t_ptr < pt.t_e:
                xroad = 0
                local_time = int(round(t_ptr))
                self.cont_n_sent += 1
                dummy = CarInfo(self.cont_n_sent, 1 + 100 * self.cont_n_sent, -1)
                # vehicle_id = self.get_available_vehicle_id()
                # round_num = self.get_next_round_num()  # 获取车次号
                # dummy = CarInfo(vehicle_id, round_num, -1)
                route = pk.routes[0].down_route
                
                if c_indx % period >= pk.op_rate1 and len(pk.routes) > 1:  # 添加长度检查
                    local_time = self.get_act_send_time(local_time, route, pk.routes[1].down_route, level)
                    route = pk.routes[1].down_route
                    xroad = 1
                    
                rs = self.rl.getHeuristicSolFromPath1(route, local_time, level, 30, self.us.first_car, dummy)
                rs.dir = 1
                total_sent += 1
                rs.xroad = xroad
                rs.phase = p_idx + p_idx_offset
                dn_res.append(rs)
                self.rl.last_sent[1] = int(round(t_ptr))
                c_indx += 1
                self.last_c_dn = c_indx
                t_ptr += local_interval
                
            phase_res.append(dn_res)
            # 将上下行方案添加到阶段结果中    
            res.append(phase_res)
            
            self.last_c_dn = self.last_c_dn % period
            self.last_c_up = self.last_c_dn % period
        return res
    
    def get_act_send_time(self, t: int, route_large: str, route_small: str, level: int) -> int:
        """
        计算小交路列车的实际发车时间
        
        Args:
            t: 原始发车时间
            route_large: 大交路路线
            route_small: 小交路路线
            level: 速度等级
            
        Returns:
            调整后的实际发车时间
        """
        diff_interval = self.rl.computePathDiff(route_large, route_small, level)
        return t + diff_interval

    def compute_new_phases(self) -> None:
        """根据读取的高峰期数据计算是否需要加减车
        /**
        * 根据读取的高峰期数据生成调度阶段：重新划分平峰、高峰时段和过渡时段
        * 此方法基于用户设置 (us.peaks) 中的高峰期数据，生成调度阶段 (PhaseTime)。
        * 它会分析相邻高峰期之间的列车数量变化，自动插入"加车阶段"(ADDCAR)、"减车阶段"(REDUCECAR)或"预减车阶段"(PREREDUCE)，以平滑过渡。
        * 平稳运行的时段则定义为"稳定阶段"(STABLE)。这些阶段信息存储在 Phases 列表中。
        */
        """
        last_end = 0
        for i in range(len(self.us.peaks)):
            pk = self.us.peaks[i]
            interval = self.us.predict_Interval[i]  #各阶段的发车间隔数据来自于这里
            print("PhaseTime中的interval=" + str(interval))
            total_time = max(self.rl.total_run_time_up[0], 
                            self.rl.total_run_time_dn[0])
            
            # 计算时间关键点
            t_s = max(pk.start_time, last_end)
            t_e = pk.end_time

            # 1. 检查是否需要添加减车阶段
            if i > 0:
                last_train_num = self.us.peaks[i - 1].train_num
                if last_train_num > pk.train_num:#如果上一个峰期列车数大于当前峰期列车数
                    # 需要添加减车阶段
                    tmp_s = t_s
                    tmp_e = t_s + total_time
                    pt = PhaseTime(tmp_s, tmp_e, pk.train_num, interval,
                                PHASETYPE.REDUCECAR, pk,
                                self.us.predict_Interval_up[i],
                                self.us.predict_Interval_dn[i])
                    self.Phases.append(pt)
                    t_s = tmp_e

            # 2. 检查是否需要添加加车阶段
            add_phase = None
            pre_red_phase = None
            if i < len(self.us.peaks) - 1:
                next_train_num = self.us.peaks[i + 1].train_num
                if next_train_num > pk.train_num:#如果下一个峰期列车数大于当前峰期列车数  
                    tmp_s = t_e - total_time
                    tmp_e = t_e
                    if t_e - total_time > t_s:
                        t_e -= total_time
                    else:
                        t_e = t_s
                        tmp_s = t_s
                        tmp_e = t_e + total_time

                    add_phase = PhaseTime(tmp_s, tmp_e, next_train_num,
                                        self.us.predict_Interval[i+1],
                                        PHASETYPE.ADDCAR,
                                        self.us.peaks[i+1],
                                        self.us.predict_Interval_up[i+1],
                                        self.us.predict_Interval_dn[i+1])
                    last_end = tmp_e

                # 检查是否需要添加预减车阶段
                if t_s < t_e and next_train_num < pk.train_num:
                    tmp_s = max(t_s, t_e - total_time // 2)
                    pre_red_phase = PhaseTime(tmp_s, t_e, pk.train_num,
                                            interval,
                                            PHASETYPE.PREREDUCE,
                                            pk,
                                            self.us.predict_Interval_up[i],
                                            self.us.predict_Interval_dn[i])
                    t_e = tmp_s

            # 添加稳定阶段:在t_s和t_e之间的时间段
            if t_s < t_e:
                pt = PhaseTime(t_s, t_e, pk.train_num, interval,
                            PHASETYPE.STABLE, pk,
                            self.us.predict_Interval_up[i],
                            self.us.predict_Interval_dn[i])
                self.Phases.append(pt)

            # 添加加车阶段
            if add_phase is not None:
                self.Phases.append(add_phase)

            # 添加预减车阶段
            if pre_red_phase is not None:
                self.Phases.append(pre_red_phase)

        # 初始化最佳间隔记录为非空
        if self.besst_ir is None:
            self.besst_ir = IntervalRecorder(len(self.Phases))

    # /**
    #  * 阶段0：生成调度阶段，并准备阶段1
    #  * 重新划分平峰、高峰时段和过渡时段：调用prepare_phase1、compute_new_phases
    #  */
    def phase0(self) -> None:
        """
        阶段0：生成调度阶段，并准备阶段1
        """
        self.level = self.prepare_phase1()
        self.compute_new_phases()
        # print("PhaseTime中的self.Phases=" + str(self.Phases))

    def prepare_phase1(self) -> int:
        """
        阶段1：准备调度阶段
        准备生成调度阶段所需的重要信息
        Returns:
            速度等级
        """
        # 获取第一个高峰期
        pk = self.us.peaks[0]
        for ptk in self.us.peaks:
            if ptk.op_rate2 != 0:
                pk = ptk
                break

        # 获取最后一个峰期的结束时间
        last_time = self.us.peaks[-1].end_time
        self.us.setLastCarTime(util.ps(last_time))#设置末班车时间

        #获取该峰期的速度等级
        self.level = int(pk.op_lvl)

        # 检查加车是否可行
        # 首先需要计算每个高峰期的间隔
        self.rl.compute_full_length_time(pk, self.level, 1)

        # 计算安全停站时间供后续使用
        self.rl.get_minmax_def_dwell_all(pk)
        self.global_dwell_diff = self.rl.max_dwell_diff

        # 计算每个高峰期发车间隔：这里它自己计算更新了间隔，而不是从xml中读取的，所以是深圳和我们自己的车次数不一致的原因
        if len(self.rl.total_run_time_up) > 1:
            t_delta = self.rl.total_run_time_up[0] - self.rl.total_run_time_up[1]
            self.us.update_interval_delta(
                self.rl.total_run_time_up[0], 
                self.rl.total_run_time_dn[0], 
                t_delta
            )
        else:
            self.us.update_interval(self.rl.total_run_time[0], 0)#offset设置为0

        self.update_inout_time(self.level)
        print(f"更新后的总上行运行时间={self.rl.total_run_time_up[0]}")
        print(f"更新后的总下行运行时间={self.rl.total_run_time_dn[0]}")
        print(f"更新后的predict_Interval_up={self.us.predict_Interval_up[0]}")
        print(f"更新后的predict_Interval_dn={self.us.predict_Interval_dn[0]}")
        # 打印所有峰期的间隔
        print("所有峰期的间隔值:")
        for i, peak in enumerate(self.us.peaks):
            print(f"峰期[{i}].interval = {self.us.peaks[i].interval}")
        # 或者简单地：
        for i in range(len(self.us.peaks)):
            print(f"predict_Interval[{i}] = {self.us.predict_Interval[i]}")
        print(f"peaks[0].interval = {self.us.peaks[0].interval}")
        print(f"peaks[0].interval_up = {self.us.peaks[0].interval_up}")
        print(f"peaks[0].interval_dn = {self.us.peaks[0].interval_dn}")

        return self.level

    def generate_initial_phase1(self, res1: List[List[List[RouteSolution]]], level: int) -> List[List[List[RouteSolution]]]:
        """
        /**
        * 根据计算的间隔生成首班车之前的车辆
        * 此方法负责生成首班车发车之前的列车运行计划。
        * 它根据第一个调度阶段的信息，反向推算并安排初始运行的列车，确保在第一个高峰期开始前有足够的列车在线运营。
        * 生成的初始列车运行方案 (RouteSolution) 会被添加到结果列表的开头。
        */
        Args:
            res1: 存储调度结果的三维列表
            level: 速度等级
            
        Returns:
            更新后的调度结果列表
        """
        # 1. 初始化阶段
        pt = self.Phases[0]  # 获取第一个调度阶段的时间信息
        phase_res = []  # 创建存储调度结果的列表
        n_cars = self.us.peaks[0].train_num  # 获取总车辆数
        interval = self.rl.total_run_time[0] // self.us.peaks[0].train_num  #计算发车间隔（上下行总运行时间/车辆数）=周转时间间隔
        #使用读取的xml中的共线间隔时间
        # interval = self.us.peaks[0].interval
        # print(f"初始化阶段interval={interval}")
        
        # 2. 车辆分配计算
        t_ptr = pt.t_s - interval  # 设置时间指针（从第一个阶段开始时间往前推）
        pk = pt.pk  # 获取峰期信息
        period = pk.op_rate1 + pk.op_rate2  # 计算大小交路总开行比例，用于后续分配
        up_car = n_cars // 2 - 1  # 计算上行车辆数
        dn_car = n_cars - up_car - 1  # 计算下行车辆数
        self.last_c_up = up_car
        self.last_c_dn = dn_car
        
        # 3. 上行方向车辆生成
        c_indx = up_car - 1
        up_res = []
        for i in range(up_car):
            # // 生成车辆信息
            # // 判断使用大小交路
            # // 生成运行方案
            # // 倒序添加到结果列表
            xroad = 0
            local_time = round(t_ptr)
            self.cont_n_sent += 1
            dummy = CarInfo(self.cont_n_sent, 1 + 100 * self.cont_n_sent, -1)
            # vehicle_id = self.get_available_vehicle_id()
            # round_num = self.get_next_round_num()  # 获取车次号
            # dummy = CarInfo(vehicle_id, round_num, -1)
            route = pk.routes[0].up_route
            
            if c_indx % period >= pk.op_rate1 and len(pk.routes) > 1:  # 添加长度检查
                local_time = self.get_act_send_time(local_time, route, pk.routes[1].up_route, level)
                route = pk.routes[1].up_route
                xroad = 1
                
            rs = self.rl.getHeuristicSolFromPath1(route, local_time, level, 30, 0, dummy)
            rs.dir = 0
            rs.xroad = xroad
            rs.phase = 0
            up_res.insert(0, rs)  # 倒序添加
            c_indx -= 1
            t_ptr -= interval
        
        phase_res.append(up_res)
        
        # 4. 下行方向车辆生成
        # - 与上行方向类似的处理流程
        # - 使用下行路线信息
        # - 生成下行方向的运行方案
        t_ptr = pt.t_s - interval
        c_indx = dn_car - 1
        dn_res = []
        for i in range(dn_car):
            xroad = 0
            local_time = round(t_ptr)
            self.cont_n_sent += 1
            dummy = CarInfo(self.cont_n_sent, 1 + 100 * self.cont_n_sent, -1)
            # vehicle_id = self.get_available_vehicle_id()
            # round_num = self.get_next_round_num()  # 获取车次号
            # dummy = CarInfo(vehicle_id, round_num, -1)
            route = pk.routes[0].down_route
            
            if c_indx % period >= pk.op_rate1 and len(pk.routes) > 1:  # 添加长度检查
                local_time = self.get_act_send_time(local_time, route, pk.routes[1].down_route, level)
                route = pk.routes[1].down_route
                xroad = 1
                
            rs = self.rl.getHeuristicSolFromPath1(route, local_time, level, 30, 0, dummy)
            rs.dir = 1
            rs.xroad = xroad
            rs.phase = 0
            dn_res.insert(0, rs)
            c_indx -= 1
            t_ptr -= interval
            
        phase_res.append(dn_res)
        
        # 5. 结果整理和阶段调整
        res1.insert(0, phase_res)
        self.last_c_dn = self.last_c_dn % period
        self.last_c_up = self.last_c_dn % period
        # - 将生成的方案添加到结果列表
        # - 创建并添加初始阶段
        # - 更新后续阶段的编号
        pt_init = PhaseTime(0, self.Phases[0].t_s, n_cars, interval, 
                        PHASETYPE.STABLE, pk,
                        self.us.predict_Interval_up[0], 
                        self.us.predict_Interval_dn[0])
        self.Phases.insert(0, pt_init)
        
        # 更新后续阶段的编号
        for i in range(1, len(res1)):
            for dir in range(2):
                for idx in range(len(res1[i][dir])):
                    res1[i][dir][idx].phase += 1
        
        # 6. 时间范围调整
        # - 根据实际生成的车辆到达时间调整初始阶段的开始时间
        # - 取上下行首车到达时间的较早值
        # 这个函数的主要目的是确保在第一个调度阶段开始前，已经有足够的列车在运行，以保证系统的平稳运行。
        # 它通过逆向计算的方式，合理安排首班车之前的车辆运行计划。
        self.Phases[0].t_s = res1[0][0][0].arr_time[0]
        self.Phases[0].t_s = min(res1[0][1][0].arr_time[0], self.Phases[0].t_s)
        
        return res1

    def phase1_optimized(self) -> List[List[List[RouteSolution]]]:
        """
        阶段1：生成初始时刻表:依据当前发车间隔发车
        Returns:
            三维列表，包含所有调度方案:
            - 第一维: 调度阶段
            - 第二维: 上下行方向
            - 第三维: 具体的运行线
        """
        # 创建存储调度结果的三维列表
        phase1_res: List[List[List[RouteSolution]]] = []
        # 生成首班车之前的车辆调度方案
        phase1_res = self.generate_initial_phase1_optimized(phase1_res, self.level)

        # 生成后续阶段的调度方案
        phase1_res = self.generate_phase1_optimized(self.level, 0, phase1_res)

        return phase1_res

    def phase1(self) -> List[List[List[RouteSolution]]]:
        """
        阶段1：生成初始时刻表:依据当前发车间隔发车
        Returns:
            三维列表，包含所有调度方案:
            - 第一维: 调度阶段
            - 第二维: 上下行方向
            - 第三维: 具体的运行线
        """
        # 创建存储调度结果的三维列表
        phase1_res: List[List[List[RouteSolution]]] = []
        # 生成首班车之前的车辆调度方案
        phase1_res = self.generate_initial_phase1(phase1_res, self.level)
        print("生成首班车之前的车辆调度方案:")
        self.print_phase3_res(phase1_res)
        # 生成后续阶段的调度方案
        phase1_res = self.generate_phase1(self.level, 0, phase1_res)
        print("生成后续阶段的调度方案:")
        self.print_phase3_res(phase1_res)
        return phase1_res

    def phase2_revert(self, phase_info: List[List[RouteSolution]]) -> List[List[List[RouteSolution]]]:
        """
        将处理完毕的包含所有列车的列表再转换回按阶段划分的格式。
        即：将所有列车按阶段重新划分，方便后续处理。
        将List<List<RouteSolution>>转换为List<List<List<RouteSolution>>>
        
        Args:
            phase_info: 包含所有列车的列表，按方向划分
            
        Returns:
            按阶段划分的列车列表
        """
        res = []
        for t_index in range(len(self.Phases)):
            res.append([])
            for dir in range(2):
                res[t_index].append([])
                for rs in phase_info[dir]:
                    if rs.phase == t_index:
                        res[t_index][dir].append(rs)
        
        return res

    def fix_phase2(self, window_stat: List[List[RouteSolution]], fix_side: int, shift_amount: int, 
              shift_times: int, t_s: int, t_e: int, first_interval: float) -> List[List[RouteSolution]]:
        """
        fix_phase2: 这是峰期内核心的调整函数。它并不直接按固定单位平移固定时长，而是尝试一系列的平移。
        它通过遍历所有可能的平移次数，计算每次平移后的车次连接情况，并记录最小违规数。
        最终返回最小违规数对应的平移量。
        
        选择折返冲突最少的运行计划: fix_phase2 通过多次调用 shift_side 来平移可变一侧的列车，
        并在每次平移后调用 phase2_connect 计算连接后的总冲突（这里体现为总的折返时间差 violation）。
        它会记录并最终采用那个使得 violation 最小的平移方案。
        
        Args:
            window_stat: 窗口状态列表
            fix_side: 固定的方向
            shift_amount: 移动量
            shift_times: 移动次数
            t_s: 开始时间
            t_e: 结束时间
            first_interval: 第一个间隔
            
        Returns:
            调整后的窗口状态列表
        """
        min_violation = int(1e+20)
        shift_tar = -1
        # 上行和下行
        ori_flex = window_stat[1-fix_side]
        flexi_side = []
        # test_start_time = sys_time.time() * 1000
        for rs_tmp in ori_flex:
            flexi_side.append(rs_tmp.clone())
        # test_end_time = sys_time.time() * 1000
        # print(f"fix_phase2中clone的时间为{test_end_time - test_start_time}")

        # test_start_time1 = sys_time.time() * 1000
        for i in range(shift_times):
            flexi_side = self.shift_side(flexi_side, shift_amount, t_s, t_e, first_interval)
            window_stat[1-fix_side] = flexi_side
            
            # violation = self.phase2_connect(window_stat)
            violation = self.phase2_connect_ultra_optimized(window_stat)
            if min_violation > violation:
                min_violation = violation
                shift_tar = (i + 1) * shift_amount
        # test_end_time1 = sys_time.time() * 1000
        # print(f"fix_phase2中100次for循环的时间为{test_end_time1 - test_start_time1}")


        # 恢复
        if self.debug:
            util.pf("Shifted: " + util.ps(shift_tar))
        # test_start_time3 = sys_time.time() * 1000
        ori_flex = self.shift_side(ori_flex, shift_tar, t_s, t_e, first_interval)
        # test_end_time3 = sys_time.time() * 1000
        # print(f"fix_phase2中shift_side的时间为{test_end_time3 - test_start_time3}")
        window_stat[1-fix_side] = ori_flex
        self.phase2_disconnect(window_stat)
        # self.debug = True
        # test_start_time2 = sys_time.time() * 1000
        # self.phase2_connect(window_stat)
        self.phase2_connect_ultra_optimized(window_stat)
        # test_end_time2 = sys_time.time() * 1000
        # print(f"fix_phase2中phase2_connect的时间为{test_end_time2 - test_start_time2}")

        # self.debug = False
        return window_stat

    def phase2_disconnect(self, window_stat: List[List['RouteSolution']]) -> None:
        """
        阶段2：断开所有列车的连接（通过折返）以进行进一步修改
        在连接前，断开所有列车原有的前后连接关系 (next_ptr = None, prev_ptr = None)。
        
        Args:
            window_stat: 包含上下行列车的列表
        """
        for dir in range(2):
            for i in range(len(window_stat[dir])):
                window_stat[dir][i].next_ptr = None
                window_stat[dir][i].prev_ptr = None

    def phase2_connect(self, window_stat: List[List['RouteSolution']]) -> int:
        """
        阶段2：尝试在当前峰期的窗口内（通常是所有列车）连接列车
        
        此方法遍历一个方向的每辆列车，然后在相反方向寻找最佳的接续列车。
        选择标准是折返时间（到达与出发时间差）的绝对值最小。连接时会考虑列车的交路类型 (xroad) 是否一致。
        
        Args:
            window_stat: 包含上下行列车的列表
            
        Returns:
            违反约束的总量（折返时间差的总和）
        """
        vio = 0
        # test_sort_time = sys_time.time() * 1000
        window_stat = self.sort_window_optimized(window_stat)
        # test_sort_time_end = sys_time.time() * 1000 
        # print(f"phase2_connect中sort_window_optimized的时间为{test_sort_time_end - test_sort_time}")
        # 连接每条路线
        for dir in range(2):
            for rs in window_stat[dir]:
                if rs.next_ptr is not None:
                    continue
                arr_time = rs.dep_time[len(rs.dep_time) - 1]
                # 寻找最佳匹配
                rs_t = None
                vio_ = 999999999
                
                for i in range(len(window_stat[1 - dir])):
                    # 检查这个列车是否可以连接
                    rs_o = window_stat[1 - dir][i]
                    if rs_o.xroad != rs.xroad:
                        continue
                    
                    dep_time = rs_o.arr_time[0]
                    
                    if dep_time < arr_time - 100:
                        continue
                    
                    if rs_o.prev_ptr is not None:
                        if dep_time > arr_time:
                            break
                        else:
                            continue
                    # 可能的连接，计算违反约束的量
                    distance = abs(dep_time - arr_time)
                    if distance < vio_:
                        vio_ = distance
                        rs_t = rs_o
                
                if rs_t is not None:
                    rs_t.prev_ptr = rs
                    rs.next_ptr = rs_t
                
                vio += vio_
        
        return vio

    def phase2_connect_ultra_optimized(self, window_stat: List[List['RouteSolution']]) -> int:
        """
        阶段2：尝试在当前峰期的窗口内（通常是所有列车）连接列车 - 超级优化版本
        
        使用更激进的优化策略，包括二分搜索和更精细的索引管理
        
        Args:
            window_stat: 包含上下行列车的列表
            
        Returns:
            违反约束的总量（折返时间差的总和）
        """
        import bisect
        
        vio = 0
        
        # 先排序窗口
        window_stat = self.sort_window_optimized(window_stat)
        
        # 为每个方向的每个xroad建立时间索引
        time_indexed_trains = [{}, {}]
        
        for dir in range(2):
            for i, rs in enumerate(window_stat[dir]):
                if rs.xroad not in time_indexed_trains[dir]:
                    time_indexed_trains[dir][rs.xroad] = []
                
                # 存储 (到达时间, 索引, 列车对象)
                time_indexed_trains[dir][rs.xroad].append((
                    rs.arr_time[0], i, rs
                ))
            
            # 按时间排序每个xroad的列车
            for xroad in time_indexed_trains[dir]:
                time_indexed_trains[dir][xroad].sort(key=lambda x: x[0])
        
        # 连接每条路线
        for dir in range(2):
            oppo_dir = 1 - dir
            
            for rs in window_stat[dir]:
                if rs.next_ptr is not None:
                    continue
                    
                arr_time = rs.dep_time[len(rs.dep_time) - 1]
                
                # 只在相同xroad的列车中搜索
                if rs.xroad not in time_indexed_trains[oppo_dir]:
                    continue
                    
                candidates = time_indexed_trains[oppo_dir][rs.xroad]
                
                # 使用二分搜索找到合适的时间范围
                min_time = arr_time - 100
                start_idx = bisect.bisect_left(candidates, (min_time, 0, None))
                
                # 寻找最佳匹配
                rs_t = None
                vio_ = 999999999
                
                for i in range(start_idx, len(candidates)):
                    dep_time, _, rs_o = candidates[i]
                    
                    # 检查是否已被连接
                    if rs_o.prev_ptr is not None:
                        if dep_time > arr_time:
                            break
                        continue
                    
                    # 计算违反约束的量
                    distance = abs(dep_time - arr_time)
                    if distance < vio_:
                        vio_ = distance
                        rs_t = rs_o
                
                # 建立连接
                if rs_t is not None:
                    rs_t.prev_ptr = rs
                    rs.next_ptr = rs_t
                    vio += vio_
        
        return vio

    def phase2_connect_optimized(self, window_stat: List[List['RouteSolution']]) -> int:
        """
        阶段2：尝试在当前峰期的窗口内连接列车（优化加速版本）
        
        优化点：
        1. 预先按xroad分组相反方向的列车，减少搜索范围
        2. 对每组列车按到达时间排序，使用二分查找加速匹配
        3. 时间复杂度从O(n²)优化为O(n log n)
        
        Args:
            window_stat: 包含上下行列车的列表
            
        Returns:
            违反约束的总量（折返时间差的总和）
        """
        vio = 0
        window_stat = self.sort_window_optimized(window_stat)
        
        # 预先按xroad分组相反方向的列车
        oppo_by_xroad = {}
        for dir in range(2):
            oppo_dir = 1 - dir
            oppo_by_xroad[dir] = {}
            for rs_o in window_stat[oppo_dir]:
                if rs_o.xroad not in oppo_by_xroad[dir]:
                    oppo_by_xroad[dir][rs_o.xroad] = []
                # 只考虑未被连接的列车
                if rs_o.prev_ptr is None:
                    oppo_by_xroad[dir][rs_o.xroad].append(rs_o)
        
        # 对每组列车按到达时间排序（用于二分查找）
        for dir in oppo_by_xroad:
            for xroad in oppo_by_xroad[dir]:
                oppo_by_xroad[dir][xroad].sort(key=lambda rs: rs.arr_time[0])
        
        # 连接每条路线
        for dir in range(2):
            for rs in window_stat[dir]:
                if rs.next_ptr is not None:
                    continue
                    
                arr_time = rs.dep_time[-1]  # 当前列车的出发时间
                
                # 只考虑相同xroad的候选列车
                if rs.xroad not in oppo_by_xroad[dir]:
                    continue
                    
                candidates = oppo_by_xroad[dir][rs.xroad]
                rs_t = None
                min_vio = float('inf')
                
                # 使用二分查找找到第一个可能的候选列车
                low = 0
                high = len(candidates) - 1
                first_candidate_idx = -1
                
                while low <= high:
                    mid = (low + high) // 2
                    rs_o = candidates[mid]
                    dep_time = rs_o.arr_time[0]
                    
                    if dep_time >= arr_time - 100:  # 满足时间条件
                        first_candidate_idx = mid
                        high = mid - 1
                    else:
                        low = mid + 1
                
                # 线性遍历候选列车（数量通常很少）
                if first_candidate_idx != -1:
                    for i in range(first_candidate_idx, len(candidates)):
                        rs_o = candidates[i]
                        dep_time = rs_o.arr_time[0]
                        
                        # 时间超出范围，提前终止
                        if dep_time > arr_time:
                            break
                            
                        # 计算时间差
                        distance = abs(dep_time - arr_time)
                        if distance < min_vio:
                            min_vio = distance
                            rs_t = rs_o
                
                # 连接最佳匹配
                if rs_t is not None:
                    rs_t.prev_ptr = rs
                    rs.next_ptr = rs_t
                    # 从候选列表移除已连接的列车
                    candidates.remove(rs_t)
                    vio += min_vio
                
        return vio

    def shift_route(self, rs: 'RouteSolution', shift_amount: int) -> 'RouteSolution':
        """
        阶段2：允许违反约束，在同一时间段（阶段）内连接车辆
        
        此方法用于平移一个列车的所有到发时间，保持停站时长不变。
        
        Args:
            rs: 需要平移的列车运行方案
            shift_amount: 平移的时间量（秒）
            
        Returns:
            平移后的列车运行方案
        """
        # 将传入的平移量赋值给局部变量
        s_am = shift_amount
        
        # 1. 更改所有时间，除了停站时间（实际是更改所有到发时间，停站时长不变）
        for i in range(len(rs.arr_time)):
            # 获取当前停站的原始到达时间
            ori_val = rs.arr_time[i]
            # 将当前停站的到达时间更新为：原始到达时间 + 平移量
            rs.arr_time[i] = ori_val + s_am
            
            # 获取当前停站的原始出发时间
            ori_val = rs.dep_time[i]
            # 将当前停站的出发时间更新为：原始出发时间 + 平移量
            rs.dep_time[i] = ori_val + s_am
         # 添加空值检查
        if rs.car_info.arr_time is None:
            print("空值警告：rs.car_info.arr_time is None，设置为0")
            rs.car_info.arr_time = 0  # 或者其他合适的默认值
        # 更新车次信息中的最终到达时间（通常指该路径段的终点到达时间）
        rs.car_info.arr_time = rs.car_info.arr_time + s_am
        
        # 返回被修改后的车次对象
        return rs

    def shift_side(self, side_stat: List['RouteSolution'], shift_amount: int, 
                t_s: int, t_e: int, first_interval: float) -> List['RouteSolution']:
        """
        移动单侧所有列车
        
        此辅助函数负责将指定方向的所有列车的发车时间进行整体平移。
        平移时会考虑时段的边界，检查列车发车时间是否超出时段边界，并进行相应的调整。
        
        Args:
            side_stat: 需要平移的列车列表
            shift_amount: 平移的时间量（秒）
            t_s: 时段开始时间
            t_e: 时段结束时间
            first_interval: 首班车间隔
            
        Returns:
            平移后的列车列表
        """
        res = []
        t_ = t_e - t_s
        
        for rs in side_stat:
            s_am = shift_amount
            # 如果平移后超出时段结束时间，则减去时段长度（循环回到开始）
            if rs.arr_time[0] + s_am > t_e:
                s_am -= t_
            
            # 平移列车
            tmp = self.shift_route(rs, s_am)
            
            # 按照到达时间顺序插入结果列表
            if len(res) > 0 and tmp.arr_time[0] < res[len(res) - 1].arr_time[0]:
                # 如果新列车比最后一个列车早，则插入到开头
                res.insert(0, tmp)
            else:
                # 否则添加到末尾
                res.append(tmp)
        
        return res

    def print_phase1_res_details(self, phase1_res):
        """
        打印 phase1_res 的详细内容
        
        Args:
            phase1_res: 三维列表，包含各个阶段的上下行列车调度方案
        """
        print("========== phase1_res 详细内容 ==========")
        for phase in range(len(phase1_res)):
            print(f"阶段 #{phase}:")
            phase_data = phase1_res[phase]
            
            for dir in range(len(phase_data)):
                direction = "上行" if dir == 0 else "下行"
                print(f"  方向: {direction} (共 {len(phase_data[dir])} 个列车)")
                
                dir_solutions = phase_data[dir]
                for i in range(len(dir_solutions)):
                    rs = dir_solutions[i]
                    print(f"    列车 #{i}:")
                    print(f"      交路类型: {'大交路' if rs.xroad == 0 else '小交路'}")
                    print(f"      阶段: {rs.phase}")
                    print(f"      到达时间: {rs.arr_time}")
                    print(f"      出发时间: {rs.dep_time}")
                    
                    # 打印 CarInfo 对象详细信息
                    car_info = rs.car_info
                    if car_info is not None:
                        print("      车辆信息:")
                        print(f"        ID: {car_info.id}")
                        print(f"        表号: {car_info.table_num}")
                        print(f"        路线编号: {car_info.route_num}")
                        print(f"        车次号: {car_info.round_num}")
                        print(f"        到达时间: {car_info.arr_time}")
                        # print(f"        车库ID: {car_info.getDepotId()}")
                    
                    print(f"      停靠站台数: {len(rs.stopped_platforms)}")
                    # 如果需要打印所有站台，可以取消下面的注释
                    # print(f"      停靠站台: {rs.stopped_platforms}")
                    print()
                print("    --------------------------------")
            print("  ================================")
        print("========== 打印结束 ==========")

    def phase2(self, phase1_res: List[List[List[RouteSolution]]], fix_side: int, shift_amount: int, shift_times: int) -> List[List[List[RouteSolution]]]:
        """
        阶段二：连接峰期内车次，并尽量满足车底接续
        
        代码对应: phase2 (包含 phase2_convert, phase2_disconnect, fix_phase2, shift_side, phase2_connect, sort_window, phase2_revert)

        对每个时段，固定特定方向: phase2 方法接受一个 fix_side 参数，
        用于确定在调整时哪个方向的列车时刻是固定的，另一个方向的列车时刻则进行调整
        
        Args:
            phase1_res: 阶段一生成的调度方案
            fix_side: 固定的方向
            shift_amount: 移动量
            shift_times: 移动次数
            
        Returns:
            调整后的调度方案
        """
        # self.print_phase1_res_details(phase1_res)
        all_stat = self.phase2_convert(phase1_res)
        # 准备数据
        te = self.Phases[-1].t_e
        latest_time = -1
        last_interval = self.Phases[-1].interval
        
        for dir in range(2):
            for rs in all_stat[dir]:
                if rs.arr_time[0] + last_interval > latest_time:
                    latest_time = rs.arr_time[0] + last_interval
        
        # 找到最佳移动并安排车辆
        te = int(round(latest_time)) + 1
        # test_start_time = sys_time.time() * 1000
        all_stat = self.fix_phase2(all_stat, fix_side, shift_amount, shift_times, 
                                self.Phases[0].t_s, te, self.Phases[0].interval)
        # test_end_time = sys_time.time() * 1000
        # print(f"fix_phase2 耗时: {test_end_time - test_start_time} ms")
        # 转换为所需格式
        phase1_res = self.phase2_revert(all_stat)
        
        return phase1_res

    def phase2_convert(self, phase_info: List[List[List[RouteSolution]]]) -> List[List[RouteSolution]]:
        """
        将按阶段划分的列车时刻表 (List[List[List[RouteSolution]]]) 合并为一个包含所有列车的列表 (List[List[RouteSolution]])，
        方便统一处理。
        
        Args:
            phase_info: 按阶段划分的列车时刻表
            
        Returns:
            包含所有列车的列表，按方向划分
        """
        all_stat = []
        for dir in range(2):
            all_stat.append([])
            for t_index in range(len(phase_info)):
                for rs_tmp in phase_info[t_index][dir]:
                    all_stat[dir].append(rs_tmp.clone())
        
        return all_stat

    def find_next_rs_tail(self, xroad: int, idx: int, rss: List[RouteSolution]) -> Optional[RouteSolution]:
        """
        查找具有相同尾部交路(xroad)的下一个路线解决方案
        
        Args:
            xroad: 要匹配的交路类型
            idx: 当前路线解决方案的索引
            rss: 路线解决方案列表
            
        Returns:
            找到的下一个具有相同尾部交路的路线解决方案，如果没有找到则返回None
        """
        rs = None
        offset = 1
        while idx + offset < len(rss):
            if rss[idx + offset].getTailXroad() == xroad:
                rs = rss[idx + offset]
                break
            offset += 1
        return rs

    def find_last_connect_prev_oppo(self, oppo_stat: List[RouteSolution], rs: RouteSolution) -> int:
        """
        查找在指定列车到达之前，对方方向上最后一个已连接的列车
        
        此函数查找在当前列车到达之前，对方方向上最后一个已有前序连接的列车，
        用于确保连接的合理性，避免跳过中间可能存在的更优连接。
        
        Args:
            oppo_stat: 对方方向的列车列表
            rs: 当前正在处理的列车
            
        Returns:
            找到的对方列车的始发时间，如果没有找到则返回0
        """
        # 获取当前列车的最终到达时间
        arr_t = rs.arr_time[len(rs.arr_time) - 1]
        rs_oppo = None
        
        # 遍历对方方向的所有列车
        for i in range(len(oppo_stat)):
            # 如果对方列车的始发时间早于当前列车的到达时间
            if oppo_stat[i].arr_time[0] < arr_t:
                # 如果对方列车已有前序连接，记录该列车
                if oppo_stat[i].prev_ptr is not None:
                    rs_oppo = oppo_stat[i]
                continue
            else:
                break
        
        # 如果没有找到符合条件的对方列车，返回0
        if rs_oppo is None:
            return 0
        
        # 返回找到的对方列车的始发时间
        return rs_oppo.arr_time[0]      

    def phase3_connect(self, window_stat: List[List[RouteSolution]], next_stat: List[List[RouteSolution]]) -> List[List[RouteSolution]]:
        """
        尝试连接不同峰期之间的列车。
        
        此方法遍历当前阶段(window_stat)中尚未连接下一列车的车次，
        然后在下一阶段的相反方向(next_stat.get(1-dir))寻找可以接续的列车。
        连接条件包括：交路类型(xroad)相同，对方列车尚未有前序连接，
        且时间上基本吻合，并考虑中间不应有已连接的车阻挡。
        
        Args:
            window_stat: 当前峰期（阶段）的列车运行方案列表 (第一个List代表方向，第二个List代表该方向的列车)
            next_stat: 下一个峰期（阶段）的列车运行方案列表
            
        Returns:
            修改后的当前阶段列车运行方案列表(window_stat)，其中部分列车的next_ptr可能已被设置
        """
        # 遍历方向：0代表上行(UP_INDX)，1代表下行(DOWN_INDX)
        for dir in range(2):
            # 遍历当前阶段、当前方向(dir)的所有列车(RouteSolution)
            for i in range(len(window_stat[dir])):
                # 如果当前列车window_stat[dir][i]还没有后续连接的列车(next_ptr == None)
                # 这意味着它可能是当前阶段在该方向的末端列车之一，或者其后续列车在下一个阶段
                if window_stat[dir][i].next_ptr is None:
                    # 获取当前列车在本路径段的最终出发时间（即最后一个停站的出发时间）
                    arr_time = window_stat[dir][i].dep_time[len(window_stat[dir][i].dep_time) - 1]
                    
                    # 标记是否已找到连接
                    found = False
                    # 遍历下一个阶段(next_stat)的相反方向(1-dir)的所有列车，尝试寻找匹配
                    for j in range(len(next_stat[1-dir])):
                        rs = window_stat[dir][i]  # 当前正在尝试连接的源列车
                        # --- 开始检查连接条件 ---
                        if (
                            # 条件1: 交路类型(xroad)必须相同
                            next_stat[1-dir][j].xroad == window_stat[dir][i].xroad and
                            # 条件2: 下一阶段的候选列车(next_stat[1-dir][j])必须没有前序连接(prev_ptr==None)，
                            #        即它是一个始发列车或其前序在更早的阶段。
                            next_stat[1-dir][j].prev_ptr is None and
                            # 条件3: 下一阶段候选列车的始发时间(arr_time[0])必须晚于
                            #        一个由find_last_connect_prev_oppo计算出的时间。
                            #        find_last_connect_prev_oppo的作用是找到在rs列车到达之前，
                            #        对方线路(next_stat[1-dir])上最后一个已连接的前序列车的发车时间。
                            #        这个条件的目的是确保我们不会跳过中间可能存在的更优连接，
                            #        或者避免连接到一个其前方本应有其他车先连接的列车。
                            next_stat[1-dir][j].arr_time[0] > self.find_last_connect_prev_oppo(next_stat[1-dir], window_stat[dir][i])
                            # 注释：暗示不应有已连接的列车位于两者之间
                        ):
                            # --- 进一步检查，防止连接交叉/重叠 ---
                            condition2 = True  # 默认第二个条件为真
                            # 如果当前源列车(rs)不是其所在方向(window_stat[dir])的最后一辆车
                            if i < len(window_stat[dir]) - 1:
                                # 尝试找到源列车(rs)同方向、同交路类型(rs.xroad)的下一辆车(rs_next_car)
                                rs_next_car = self.find_next_rs_tail(rs.xroad, i, window_stat[dir])
                                # 如果找到了这样的rs_next_car，并且它已经有了后续连接(rs_next_car.next_ptr!=None)
                                if rs_next_car is not None and rs_next_car.next_ptr is not None:
                                    rs_next_next = rs_next_car.next_ptr  # rs_next_car的下一辆车，在相反方向
                                    # 检查时间是否重叠，以避免连接导致线路交叉
                                    # this_arr: 当前源列车rs的终到时间
                                    # oppo_dep: 正在考虑连接的下一阶段目标列车next_stat[1-dir][j]的始发时间
                                    # next_arr: 源列车同方向的下一班车rs_next_car的终到时间
                                    # next_oppo_dep: rs_next_car连接的对方列车rs_next_next的始发时间
                                    this_arr = window_stat[dir][i].dep_time[len(window_stat[dir][i].dep_time) - 1]
                                    oppo_dep = next_stat[1-dir][j].arr_time[0]
                                    next_arr = rs_next_car.dep_time[len(rs_next_car.dep_time) - 1]
                                    next_oppo_dep = rs_next_next.arr_time[0]
                                    # 如果rs的到达时间 <= rs_next_car的到达时间， 且rs_next_next的出发时间 <= 目标列车的出发时间
                                    # 这构成了一种潜在的连接交叉或不合理的连接顺序，例如：
                                    # rs (dir 0) -----> oppo_dep (dir 1)
                                    # rs_next_car (dir 0) --> next_oppo_dep (dir 1)
                                    # 如果this_arr <= next_arr且next_oppo_dep <= oppo_dep,
                                    # 意味着我们尝试将rs连接到一个比rs_next_car的配对接车还要晚的车，
                                    # 或者rs_next_car本身就比rs晚到但其配对车反而早发。
                                    if this_arr <= next_arr and next_oppo_dep <= oppo_dep:
                                        # overlapped
                                        condition2 = False  # 标记为不满足条件
                            
                            # 如果所有连接条件都满足
                            if condition2:
                                # 建立连接
                                window_stat[dir][i].next_ptr = next_stat[1-dir][j]  # 设置源车的next_ptr
                                next_stat[1-dir][j].prev_ptr = window_stat[dir][i]  # 设置目标车的prev_ptr
                                if self.debug:
                                    util.pf(util.ANSI_CYAN_BACKGROUND + "Phase3 connect " + 
                                        str(window_stat[dir][i].car_info.round_num) + " --> " + 
                                        str(next_stat[1-dir][j].car_info.round_num))
                                found = True  # 标记已找到连接
                                break  # 找到后即跳出内层循环，为当前源列车寻找下一个连接（如果需要）或处理下一个源列车
                    
                    # 如果遍历完下一阶段所有可能的配对列车后仍未找到连接
                    if not found and self.debug:
                        util.pf("Direction " + util.ps(dir) + ": Path not connected: " + 
                            util.timeFromIntSec(window_stat[dir][i].arr_time[0]) + " ~ " + 
                            util.timeFromIntSec(window_stat[dir][i].dep_time[len(window_stat[dir][i].dep_time) - 1]))
        
        return window_stat  # 返回修改后的window_stat

    def phase3(self, phase2_res: List[List[List[RouteSolution]]]) -> List[List[List[RouteSolution]]]:
        """
        阶段三：根据现有排班，连接多个峰期间车次
        
        代码对应: phase3 (主要调用 phase3_connect 和 connnect_xxroad)
        将相邻时段组成集合 (隐式): phase3 方法通过迭代 phase2_res (按阶段划分的列车列表) 来处理相邻时段。
        phase3_connect 会接收当前时段 (window_stat) 和下一时段 (next_stat) 的列车。
        
        Args:
            phase2_res: 阶段二处理后的列车运行方案列表
            
        Returns:
            处理后的列车运行方案列表
        """
        # Connect inter-phase trains
        for t_index in range(len(phase2_res) - 1):
            window_stat = phase2_res[t_index]
            next_stat = phase2_res[t_index + 1]
            self.phase3_connect(window_stat, next_stat)
        
        # Connect inter-xroad cars
        tmp = self.phase5_convert(phase2_res)
        tmp = self.connnect_xxroad(tmp)
        self.require_reopt = False
        
        # restore the order of the trains
        tmp = self.sort_window_optimized(tmp)
        phase2_res = []
        phase2_res.append(tmp)
        
        return phase2_res

    def get_act_send_time_rev(self, rs: 'RouteSolution', dir: int) -> int:
        """
        获取给定列车的等效大交路发车时间
        
        对于大交路列车，直接返回其到达时间；
        对于小交路列车，需要减去大小交路之间的运行时间差，以获得等效的大交路发车时间。
        这个方法主要用于列车排序和连接时的时间比较。
        
        Args:
            rs: 列车运行方案
            dir: 运行方向（0表示上行，1表示下行）
            
        Returns:
            等效的大交路发车时间
        """
        if rs.xroad == 0 or rs.phase < 0:
            # 大交路，直接返回第一个到达时间
            return rs.arr_time[0]
        else:
            # 小交路，需要减去差值
            pk = self.Phases[rs.phase].pk
            route_large = pk.routes[0].up_route
            route_small = pk.routes[1].up_route
            if dir == 1:
                route_large = pk.routes[0].down_route
                route_small = pk.routes[1].down_route
            
            diff = self.rl.computePathDiff(route_large, route_small, self.level)
            return rs.arr_time[0] - diff

    def sort_window(self, window_stat: List[List['RouteSolution']]) -> List[List['RouteSolution']]:
        """
        在连接前，根据列车的实际发车时间（通过 get_act_send_time_rev 计算，考虑了大小交路的时间差异）对窗口内的列车进行排序。
        
        Args:
            window_stat: 包含上下行列车的列表
            
        Returns:
            排序后的列车列表
        """
        res = []
        for dir in range(2):
            res.append([])
            for i in range(len(window_stat[dir])):
                pos = max(0, len(res[dir]))
                while pos > 0 and self.get_act_send_time_rev(res[dir][pos-1], dir) > self.get_act_send_time_rev(window_stat[dir][i], dir):
                    pos -= 1
                res[dir].insert(pos, window_stat[dir][i])
        return res

    def sort_window_optimized(self, window_stat):
        res = []
        for dir in range(2):
            # 使用Python内置排序，比插入排序快
            res.append(sorted(window_stat[dir], 
                            key=lambda rs: self.get_act_send_time_rev(rs, dir)))
        return res

    def phase5_convert(self, phase4_res: List[List[List[RouteSolution]]]) -> List[List[RouteSolution]]:
        """
        将按阶段和方向组织的三维列表转换为按方向组织的二维列表
        
        就是把所有阶段合并成一个阶段。
        在转换过程中，它会根据列车的实际发车时间（考虑大小交路差异）对每个方向的列车进行排序。
        这个函数通常用于准备数据，以便进行后续的全局性操作，如优化或连接。
        
        Args:
            phase4_res: 一个三维列表，结构为 List<阶段<方向<RouteSolution>>>，代表经过第四阶段处理后的列车运行方案
            
        Returns:
            一个二维列表，结构为 List<方向<RouteSolution>>，其中每个方向的 RouteSolution 按实际发车时间排序
        """
        # 初始化结果列表，用于存放按方向组织的列车
        res = []
        # 为上行方向(通常索引为0)初始化一个空的RouteSolution列表
        res.append([])
        # 为下行方向(通常索引为1)初始化一个空的RouteSolution列表
        res.append([])
        
        # 遍历phase4_res中的每一个"阶段"
        for t in range(len(phase4_res)):
            # 遍历当前阶段的两个方向(0: 上行, 1: 下行)
            for dir in range(2):
                # 遍历当前阶段、当前方向的所有列车(RouteSolution)
                for rs in phase4_res[t][dir]:
                    # 初始插入位置为当前方向结果列表的末尾
                    insert_pos = len(res[dir])
                    # 获取当前列车的原始发车时间(这行在Java中被注释掉了)
                    # tt = rs.arr_time[0]
                    
                    # 循环查找正确的插入位置：
                    # 当插入位置大于0(即结果列表中已有元素)并且
                    # 结果列表中前一个元素的"实际反向计算的发车时间"
                    # 大于当前待插入列车的"实际反向计算的发车时间"时，
                    # 将插入位置向前移动一位。
                    while (insert_pos > 0 and 
                        self.get_act_send_time_rev(res[dir][insert_pos - 1], dir) > 
                        self.get_act_send_time_rev(rs, dir)):
                        insert_pos -= 1  # 将插入点向前移动
                    
                    # 在找到的正确位置插入当前列车rs
                    res[dir].insert(insert_pos, rs)
        
        # 返回整合并排序后的二维列表
        return res
        
    def checkNextNonConnected(self, tmp: List[List[RouteSolution]], 
                            rs_oppo: RouteSolution,
                            dir: int, j_start: int, tar_end: str) -> bool:
        """
        检查是否存在更好的列车连接选择
        
        此方法检查在当前列车之后是否存在更适合连接到目标列车的其他列车。
        如果找到更好的选择，则返回False，表示应该跳过当前连接。
        
        Args:
            tmp: 按方向组织的列车列表
            rs_oppo: 对方方向的候选连接列车
            dir: 当前方向索引
            j_start: 当前列车在列表中的索引
            tar_end: 目标折返站
            
        Returns:
            如果当前连接是最佳选择则返回True，否则返回False
        """
        rs_check = None
        # 在当前列车之后寻找第一个未连接且交路类型与目标列车不同的列车
        for j in range(j_start + 1, len(tmp[dir])):
            rs_test = tmp[dir][j]
            if rs_test.next_ptr is None and rs_test.xroad != rs_oppo.xroad:
                rs_check = rs_test
                break
        
        if rs_check is None:
            # 没有找到后续可能的冲突列车，可以使用当前连接
            return True
        
        # 否则，需要检查找到的列车是否应该优先连接到目标列车
        if self.checkNonConnected(rs_check, rs_oppo, tar_end, None):
            # 如果找到了更好的选择，跳过当前连接
            return False
        
        return True    

    def checkNonConnected(self, rs: RouteSolution, rs_oppo: RouteSolution, tar_end: str, rs_next: Optional[RouteSolution]) -> bool:
        """
        检查当前列车是否可以连接到对方方向的列车
        
        此方法检查两个不同交路类型的列车是否可以在折返站连接。
        连接条件包括：交路类型不同、对方列车尚未有前序连接、
        折返时间在合理范围内、中间没有其他列车阻挡等。
        
        Args:
            rs: 当前列车
            rs_oppo: 对方方向的候选连接列车
            tar_end: 目标折返站
            rs_next: 当前列车同方向的下一列车（用于检查是否有列车阻挡）
            
        Returns:
            如果可以连接则返回True，否则返回False
        """
        arr_time = rs.arr_time[len(rs.arr_time) - 1]
        
        # 只考虑不同交路类型的列车
        if rs_oppo.xroad == rs.xroad:
            return False
        
        # 对方列车不应该已经有前序连接
        if rs_oppo.prev_ptr is not None:
            return False
        
        # 计算关键时间点
        act_time = self.rl.compute_new_arrival(rs, rs_oppo, tar_end, self.level)
        if act_time < 0:
            return False
        
        if rs.xroad == 0:
            # 大交路 -> 小交路，使用小交路的实际出发时间(act_time)
            tb = self.rl.turnbackList[rs.stopped_platforms[len(rs.stopped_platforms) - 1]]
            min_tb_time = tb.min_tb_time
            max_tb_time = tb.max_tb_time
            
            # 检查折返时间是否在合理范围内
            if not (arr_time <= act_time - min_tb_time and  # 到达时间必须早于对方实际出发时间减去最小折返时间（确保有足够的折返时间）
                    arr_time >= act_time - max_tb_time):    # 到达时间必须晚于对方实际出发时间减去最大折返时间（确保折返时间不会过长）
                return False
            
            # 检查中间是否有列车阻挡
            if rs_next is not None:
                next_arr_time = rs_next.dep_time[len(rs_next.dep_time) - 1]
                if next_arr_time >= arr_time and next_arr_time <= act_time:
                    return False
        else:
            # 小交路 -> 大交路，使用小交路的实际到达时间(act_time)
            tb = self.rl.turnbackList[rs_oppo.stopped_platforms[0]]
            min_tb_time = tb.min_tb_time
            max_tb_time = tb.max_tb_time
            oppo_dep_time = rs_oppo.arr_time[0]
            
            # 检查时间
            if not (oppo_dep_time >= act_time + min_tb_time and  # 对方出发时间必须晚于当前实际到达时间加上最小折返时间（确保有足够的折返时间）
                    oppo_dep_time <= act_time + max_tb_time):    # 对方出发时间必须早于当前实际到达时间加上最大折返时间（确保折返时间不会过长）
                # 对方列车比当前列车早
                return False
            
            # 检查中间是否有列车阻挡
            if rs_next is not None:
                next_arr_time = rs_next.dep_time[len(rs_next.dep_time) - 1]
                if next_arr_time >= act_time and next_arr_time <= oppo_dep_time:
                    return False
        
        return True

    def connnect_xxroad(self, tmp: List[List[RouteSolution]]) -> List[List[RouteSolution]]:
        """
        连接不同交路类型（大交路与小交路）但在同一物理位置可以折返的列车
        
        此方法在所有列车中（通过phase5_convert合并）尝试连接不同交路类型（大交路与小交路，xroad 不同）
        但在同一物理位置可以折返的列车。即：实现大小交路混跑（存在共折返站的情况下）。
        它会通过 rl.changeBSPath 调整小交路列车的路径（虚拟地延长或缩短）以匹配大交路的折返点，
        并检查时间是否允许连接。如果进行了此类连接，会设置 require_reopt = True，因为路径的改变可能需要后续优化。
        
        Args:
            tmp: 一个二维列表，其中第一维代表列车运行方向（上行/下行），第二维包含该方向上所有的 RouteSolution 对象
                此列表通常是经过 phase5_convert 函数处理后的结果
                
        Returns:
            处理后的列车运行方案列表
        """
        # 函数首先遍历两个行车方向 (dir = 0 代表上行, dir = 1 代表下行)
        for dir in range(2):
            for j in range(len(tmp[dir])):
                # 每个方向内，它遍历该方向的每一列车 rs (使用索引 j)
                rs = tmp[dir][j]
                if rs.next_ptr is not None:
                    # 如果当前列车 rs 已经有了一个后续连接，意味着它已经参与了某个折返，则跳过此列车
                    continue
                
                # 寻找同向下一个大交路列车
                rs_next = None
                for k in range(j+1, len(tmp[dir])):
                    # 尝试在 rs 之后（同一方向）找到第一个 xroad == 0 （通常代表大交路或主线）的列车
                    if tmp[dir][k].xroad == 0:
                        rs_next = tmp[dir][k]
                        break
                
                # 寻找反向潜在连接列车 (rs_oppo)
                for i in range(len(tmp[1-dir])):
                    rs_oppo = tmp[1-dir][i]
                    if rs_oppo.prev_ptr is not None:
                        continue
                    if rs_oppo.xroad == rs.xroad:
                        continue
                    
                    # 确定目标折返站 (tar_end)
                    tar_end = ""
                    # 根据 rs 和 rs_oppo 的交路类型，确定它们可能共同折返的目标站点
                        # 添加空值检查
                    if rs_oppo.car_info.route_num is None:
                        # 处理空值情况，例如跳过当前迭代或设置默认值
                        print("空值警告：rs_oppo.car_info.route_num is None")
                        continue  # 或者其他适当的处理方式
                    if rs.xroad == 1:
                        tar_end = self.rl.pathList[util.ps(rs_oppo.car_info.route_num)].nodeList[0]
                    else:
                        tar_end = self.rl.pathList[util.ps(rs_oppo.car_info.route_num)].nodeList[1]
                    
                    # 连接可行性验证
                    if not self.checkNonConnected(rs, rs_oppo, tar_end, rs_next):
                        continue
                    
                    # 检查是否存在更优选择
                    if not self.checkNextNonConnected(tmp, rs_oppo, dir, j, tar_end):
                        continue
                    
                    # 如果以上所有检查都通过，则认为 rs 和 rs_oppo 可以进行跨交路连接
                    rs.next_ptr = rs_oppo
                    rs_oppo.prev_ptr = rs
                    
                    # 调用 RailInfo 类中的 changeBSPath 方法修改列车路径信息
                    self.rl.change_bs_path(rs, rs_oppo, tar_end, self.level, False)
                    self.require_reopt = True
                    break
        
        return tmp

    def reset_planning(self):
        """Reset the planning status for re-planning"""
        self.cont_n_sent = 0
        self.Phases.pop(0)  # Python中使用pop(0)替代Java的remove(0)
        self.rl.reset_planning()

    def initialize_params(self):
        """
        初始化参数结构体，从XML数据中提取所有必要的参数信息
        
        该函数负责：
        1. 初始化基础参数结构体
        2. 提取站点信息和车库信息
        3. 解析大小交路的起终点站
        4. 提取路径目的地码和运行时间
        5. 处理出入库路径信息
        6. 建立各种映射关系
        
        Returns:
            Params: 初始化完成的参数对象
        """
        # 初始化参数结构体
        params = Params()
        # 初始化站点相关变量
        params.large_start_station = None  # 大交路起点
        params.large_end_station = None  # 大交路终点
        params.small_start_station = None  # 小交路起点
        params.small_end_station = None  # 小交路终点

        params.peaks = self.us.peaks  # 峰期参数信息
        params.depot_routes = self.us.depot_routes_infos  # 出入库路径信息
        # 动态添加车库信息，根据depot_ids中的元素数量
        if len(self.us.depot_ids) > 0:
            for i in range(len(self.us.depot_ids)):
                # 确保对应的数组有足够的元素
                if i < len(self.us.depot_trains) and i < len(self.us.depot_caps):
                    params.depotsInfo.append({
                        'id': self.us.depot_ids[i],
                        'usable': self.us.depot_trains[i],  # 可用车辆数
                        'parking': self.us.depot_caps[i]  # 可用停车位
                    })
                else:
                    print(f"警告：车库{self.us.depot_ids[i]}缺少对应的车辆数或停车位信息")
        else:
            print("警告：未读取到任何车库信息")
        # 从self.rl中提取数据
        params.all_station_names = []  # 存储所有车站+停车场+车辆段
        params.station_names = []  # 存储正线车站
        params.DestcodesOfAllBackTurnback = []  # 所有站后折返的站台目的地码

        for station_node in self.rl.stationList.values():
            station_name = station_node.name  # 直接访问Station对象的name属性
            if station_name:
                params.all_station_names.append(station_name)
                # 只有不包含"车辆段"和停车场的才算正线站台
                if '车辆段' not in station_name and '停车场' not in station_name:
                    params.station_names.append(station_name)

            # 解析调头信息
            if hasattr(station_node, 'turnbackList'):
                if station_node.turnbackList:
                    for turnback in station_node.turnbackList:
                        turnback_name = turnback.name
                        tb_dest_code = turnback.dest_code

                        # 检查turnback_name是否包含特定关键字
                        if any(keyword in turnback_name for keyword in ["存车线", "折返线", "站后"]):
                            params.DestcodesOfAllBackTurnback.append(tb_dest_code)

        # 提取车辆段和停车场的位置
        params.depot_location = []
        for i, station_name in enumerate(params.all_station_names, 1):  # 从1开始计数
            if '车辆段' in station_name or '停车场' in station_name:
                params.depot_location.append(i)
        
        #### 提取大小交路的起终点站位置
        if params.peaks:  # 确保有峰期数据
            for p_id in range(len(params.peaks)):
                first_peak = params.peaks[p_id]  # 只取第一个峰期：这样取值不对，因为有些峰期（尤其是第一个峰期）可能不开行小交路
                # 获取大交路和小交路的路径类别ID
                route_category1 = first_peak.route_cat1_
                route_category2 = first_peak.route_cat2_
                print(f"大交路路径类别ID：{route_category1}")
                print(f"小交路路径类别ID：{route_category2}")
                
                # 在XML2中查找对应的Route节点
                for route_id_str, route in self.rl.routeList.items():
                    current_route_id = int(route_id_str)  # 获取当前路由的ID
                    if current_route_id == int(route_category1):  # 大交路ID匹配成功
                        # 获取站点名称
                        # 获取Route节点下的直接子节点Name
                        large_start_end_name = route.name
                        print(f"大交路名称：{large_start_end_name}")
                        # 获取起终点站名称
                        station_names = large_start_end_name.split('--')
                        if len(station_names) >= 2:
                            start_name = station_names[0].strip()
                            large_start_name = start_name
                            end_name = station_names[1].strip()
                            large_end_name = end_name
                            # 在station_names中查找索引位置
                            if params.large_start_station is None and start_name in params.station_names:
                                params.large_start_station = params.station_names.index(start_name) + 1
                            if params.large_end_station is None and end_name in params.station_names:
                                params.large_end_station = params.station_names.index(end_name) + 1

                    elif current_route_id == int(route_category2):  # 小交路
                        # 获取站点名称
                        # 获取Route节点下的直接子节点Name
                        small_start_end_name = route.name
                        # 获取起终点站名称
                        station_names = small_start_end_name.split('--')
                        if len(station_names) >= 2:
                            start_name = station_names[0].strip()
                            end_name = station_names[1].strip()
                            # 在station_names中查找索引位置
                            if params.small_start_station is None and start_name in params.station_names:
                                params.small_start_station = params.station_names.index(start_name) + 1
                            if params.small_end_station is None and end_name in params.station_names:
                                params.small_end_station = params.station_names.index(end_name) + 1

        # 反转站台顺序
        params.station_names.reverse()
        
        # 提取折返路径单元对应的完整目的地码
        params.DestcodesOfPath = []
        params.all_path_run_times = []  # 所有站台的运行时间:只有25个（因为只提取了大小交路上下行所有路径单元对应的相邻目的地码之间的运行时间）
        
        if params.peaks:  # 确保有峰期数据
            first_peak = params.peaks[0]  # 只取第一个峰期
            # 添加第一条交路的上下行路径
            path_ids = []
            path_ids.extend([first_peak.routes[0].get_path(0), first_peak.routes[0].get_path(1)])
            # 如果存在第二条交路，则添加其上下行路径
            if len(first_peak.routes) > 1:
                path_ids.extend([first_peak.routes[1].get_path(0), first_peak.routes[1].get_path(1)])
            
            for path_id in path_ids:  # 大小交路上下行 ：一共四条Path
                # 在XML中查找对应的Path节点
                # 在pathList中查找对应的Path对象
                if str(path_id) in self.rl.pathList:
                    path_obj = self.rl.pathList[str(path_id)]
                    # 提取该路径的所有目的地码
                    destcodes = path_obj.nodeList  # 直接使用Path对象的nodeList属性
                    params.DestcodesOfPath.append(destcodes)

        # 创建路径ID到Path节点的映射
        path_id_map = {}
        for path_id in self.rl.pathList:
            path = self.rl.pathList[path_id]  # 获取实际的Path对象
            path_id_map[str(path_id)] = path  # 使用path_id作为键

        # 创建目的地码对之间运行时间的映射
        run_time_map = self.rl.travel_time_map
        
        # 提取出入库路径的目的地码序列和运行时间
        params.DestcodesOfDepotPath = []
        params.all_depot_run_times = []
        params.all_depotPath_run_time_cost = []  # 存储每个路径单元的总运行时长
        params.isBackTurnbackStation = [0] * len(params.station_names)
        
        # 新增8种类型的时间成本变量
        params.categorized_depot_time_cost = {}
        
        # 新增分类后的目的地码序列变量
        params.categorized_depot_destcodes = {
            'large': {
                'up': {'in': [], 'out': []},
                'down': {'in': [], 'out': []}
            },
            'small': {
                'up': {'in': [], 'out': []},
                'down': {'in': [], 'out': []}
            }
        }
        
        # 使用优化后的查找逻辑：存放所有出入库路径的站台码和运行时间
        for depot_route in params.depot_routes:
            route_category = 'large' if depot_route.routes[0][0] == params.peaks[0].route_cat1_ else 'small'
            direction = depot_route.direction.lower()  # 转换为小写
            in_out = 'in' if depot_route.inOrOut == 'In' else 'Out'
            
            for route_detail in depot_route.routes:
                if route_detail and hasattr(route_detail, 'route_ids') and route_detail.used:
                    # 该组路径的所有目的地码和运行时间
                    group_destcodes = []
                    group_run_times = []

                    # 处理该组内的所有路径ID
                    for route_id in route_detail['route_ids']:
                        path = path_id_map.get(str(route_id))
                        if path:
                            # 提取目的地码
                            # 直接使用Path对象的nodeList属性获取目的地码
                            current_destcodes = path.nodeList
                            if current_destcodes:
                                # 如果是该组的第一个路径，直接添加
                                if not group_destcodes:
                                    group_destcodes.extend(current_destcodes)
                                else:
                                    # 如果不是第一个路径，只添加除第一个之外的目的地码（避免重复）
                                    group_destcodes.extend(current_destcodes[1:])

                    # 只有当收集到目的地码时才处理
                    if group_destcodes:
                        params.DestcodesOfDepotPath.append(group_destcodes)
                        # 将目的地码序列添加到对应类别中
                        params.categorized_depot_destcodes[route_category][direction][in_out].append(group_destcodes)
                        
                        # 计算整组路径的运行时间
                        group_run_times = []
                        for i in range(len(group_destcodes) - 1):
                            start_code = group_destcodes[i]
                            end_code = group_destcodes[i + 1]
                            perf_lv_ID_ = params.peaks[0].op_lvl
                            if int(perf_lv_ID_) < 0:
                                perf_lv_ID_ = str(self.rl.platformList[start_code].def_pl)
                            print(f"默认性能等级：{perf_lv_ID_}")
                            # 构造正确的键格式
                            key = f"{start_code}_{end_code}_{perf_lv_ID_}"  # 使用默认性能等级5
                            run_time = run_time_map.get(key, 120)  # 如果找不到使用默认值120
                            group_run_times.append(run_time)

                        # 将整组的运行时间添加到结果中
                        params.all_depot_run_times.append(group_run_times)
                        # 计算该组路径的总运行时长
                        total_run_time = sum(group_run_times)
                        params.all_depotPath_run_time_cost.append(total_run_time)
                        
                        # 根据入库/出库类型选择对应的站台码
                        target_destcode = group_destcodes[-1] if in_out == 'in' else group_destcodes[0]
                        # 检查是否已存在相同key的记录，如果存在则保留最小值
                        key = (route_category, direction, in_out, target_destcode)
                        if key not in params.categorized_depot_time_cost or total_run_time < params.categorized_depot_time_cost[key]:
                            params.categorized_depot_time_cost[key] = total_run_time

        # 打印各类型的目的地码序列（用于调试）
        print("\n各类型出入库路径的目的地码序列:")
        for category in ['large', 'small']:
            for direction in ['up', 'down']:
                for io in ['in', 'out']:
                    destcodes = params.categorized_depot_destcodes[category][direction][io]
                    print(f"{category}交路 {direction}行 {io}库路径数量: {len(destcodes)}")
        
        # 创建目的地码到站台索引的映射
        destcode_to_station = {}
        # 新增：创建目的地码到车场ID的映射
        params.destcode_to_depot = {}  # 使用字典存储目的地码和车场ID的对应关系
        
        for i, station in enumerate(params.station_names):
            for station_node in self.rl.stationList.values():
                if station_node.name == station:  # 直接使用Station对象的name属性
                    # 遍历站台列表
                    for platform in station_node.platformList:  # 直接使用platformList属性
                        destcode = platform.dest_code  # 直接使用Platform对象的属性
                        depot_id = platform.depot_id  # 获取车场的depot_id属性
                        if destcode is not None:
                            destcode_to_station[destcode] = i
                            if depot_id and depot_id.strip():  # 检查depot_id是否为空或只包含空白字符
                                try:
                                    params.destcode_to_depot[destcode] = int(depot_id)
                                except ValueError:
                                    print(f"警告：站台 {destcode} 的车场ID '{depot_id}' 无效，已跳过")
        
        print("destcode_to_depot的值:", params.destcode_to_depot)
        
        # 遍历所有路径的目的地码
        for path_destcodes in params.DestcodesOfPath:
            # 遍历每个路径中的目的地码
            for destcode in path_destcodes:
                # 如果该目的地码在站后折返目的地码列表中
                if destcode in params.DestcodesOfAllBackTurnback:
                    # 找到对应的站台索引
                    if destcode in destcode_to_station:
                        station_index = destcode_to_station[destcode]
                        # 将对应站台标记为站后折返站（1）
                        params.isBackTurnbackStation[station_index] = 1
        
        params.isBackTurnbackStation.reverse()  # 为了匹配站台顺序，反转
        
        # 保持XML文件中的站台顺序
        # 初始化结构体数组（按station_names顺序存储）
        params.dest_codes = []  # 只包含正线站台的目的地码和方向
        for station_name in params.station_names:
            params.dest_codes.append({
                'station': station_name,
                'up': None,
                'down': None
            })
        
        params.stop_times = {'up': [], 'down': []}  # 修改为字典结构存储双向数据
        # def_dwell_time 停站时间需要从PlatformLists中取值
        params.dest_codes = [{}for _ in range(len(params.station_names))]  # 初始化dest_codes列表
        
        # 遍历所有正线站台
        for i, station_name in enumerate(params.station_names):  # 这里实际上只取了25个正线站台
            for station_node in self.rl.stationList.values():
                if station_node.name == station_name:
                    # 遍历该站的所有站台
                    for platform in station_node.platformList:
                        # 判断方向
                        if '上行站台' in platform.name:
                            direction = 'up'
                        elif '下行站台' in platform.name:
                            direction = 'down'
                        else:
                            continue  # 如果不包含这几个字就跳过

                        # 提取目的地码
                        if platform.dest_code:
                            params.dest_codes[i][direction] = platform.dest_code

                        # 添加停站时间
                        if platform.def_dwell_time:  # 假设Platform对象有dwell_time属性
                            params.stop_times[direction].append(platform.def_dwell_time)

                    break  # 找到对应站点后跳出内层循环

        params.run_times = {
            'up': [],
            'down': []
        }
        
        if params.peaks:  # 确保有峰期数据
            first_peak = params.peaks[0]  # 只取第一个峰期
            # 获取上下行路径ID:这里同时统计了大小交路的上下行路径ID
            up_path_ids = [first_peak.routes[0].get_path(0)]  # 大交路上行路径
            down_path_ids = [first_peak.routes[0].get_path(1)]  # 大交路下行路径

            # 处理上行路径
            for path_id in up_path_ids:
                if str(path_id) in self.rl.pathList:
                    path_obj = self.rl.pathList[str(path_id)]
                    destcodes = path_obj.nodeList
                    # 计算运行时间:只取正线站台：站后折返线的那一个站台码不取,所以上行时第一个区段的时间不取
                    print("len of up destcodes:", len(destcodes))
                    print(f"up destcodes:{destcodes}")
                    start_code = destcodes[1]
                    if start_code in self.rl.platformList:
                        platform = self.rl.platformList[start_code]
                        station_id = self.rl.platform_station_map.get(start_code)
                        if station_id and station_id in self.rl.stationList:
                            station = self.rl.stationList[station_id]
                            if station.name != large_start_name:
                                print(f"站台{start_code}所属站点{station.name}不是大交路起点站{large_start_name}，逆序runtimes")
                                for i in range(1, len(destcodes) - 1):
                                    start_code = destcodes[i]
                                    end_code = destcodes[i + 1]
                                    perf_lv_ID_ = params.peaks[0].op_lvl
                                    if int(perf_lv_ID_) < 0:
                                        perf_lv_ID_ = str(self.rl.platformList[start_code].def_pl)
                                    # 构造正确的键格式
                                    key = f"{start_code}_{end_code}_{perf_lv_ID_}"
                                    run_time = run_time_map.get(key, 120)  # 如果找不到使用默认值120
                                    params.run_times['up'].append(run_time)
                                params.run_times['up'].reverse()  # 逆序
                            else:
                                for i in range(1, len(destcodes) - 1):
                                    start_code = destcodes[i]
                                    end_code = destcodes[i + 1]
                                    perf_lv_ID_ = params.peaks[0].op_lvl
                                    if int(perf_lv_ID_) < 0:
                                        perf_lv_ID_ = str(self.rl.platformList[start_code].def_pl)
                                    # 构造正确的键格式
                                    key = f"{start_code}_{end_code}_{perf_lv_ID_}"
                                    run_time = run_time_map.get(key, 120)  # 如果找不到使用默认值120
                                    params.run_times['up'].append(run_time)

            # 处理下行路径
            for path_id in down_path_ids:
                if str(path_id) in self.rl.pathList:
                    path_obj = self.rl.pathList[str(path_id)]
                    destcodes = path_obj.nodeList
                    # 计算运行时间:只取正线站台：站后折返线的那一个站台码不取,所以下行时最后一个区段的时间不取
                    print("len of down destcodes:", len(destcodes))
                    print(f"down destcodes:{destcodes}")
                    start_code = destcodes[1]
                    if start_code in self.rl.platformList:
                        platform = self.rl.platformList[start_code]
                        station_id = self.rl.platform_station_map.get(start_code)
                        if station_id and station_id in self.rl.stationList:
                            station = self.rl.stationList[station_id]
                            if station.name != large_end_name:
                                print(f"站台{start_code}所属站点{station.name}不是大交路终点站{large_end_name}，逆序runtimes")
                                for i in range(1, len(destcodes) - 1):
                                    start_code = destcodes[i]
                                    end_code = destcodes[i + 1]
                                    perf_lv_ID_ = params.peaks[0].op_lvl
                                    if int(perf_lv_ID_) < 0:
                                        perf_lv_ID_ = str(self.rl.platformList[start_code].def_pl)
                                    # 构造正确的键格式
                                    key = f"{start_code}_{end_code}_{perf_lv_ID_}"
                                    run_time = run_time_map.get(key, 120)  # 如果找不到使用默认值120
                                    params.run_times['down'].append(run_time)
                                params.run_times['down'].reverse()  # 逆序
                            else:
                                for i in range(1, len(destcodes) - 1):
                                    start_code = destcodes[i]
                                    end_code = destcodes[i + 1]
                                    perf_lv_ID_ = params.peaks[0].op_lvl
                                    if int(perf_lv_ID_) < 0:
                                        perf_lv_ID_ = str(self.rl.platformList[start_code].def_pl)
                                    # 构造正确的键格式
                                    key = f"{start_code}_{end_code}_{perf_lv_ID_}"
                                    run_time = run_time_map.get(key, 120)  # 如果找不到使用默认值120
                                    params.run_times['down'].append(run_time)
        
        # 其他运行参数
        params.min_headway = 120  # 最小追踪间隔（秒）
        params.min_turnback_time = 120  # 最小折返时间（秒）
        params.max_turnback_time = 1800  # 最大折返时间（秒）
        params.min_shared_interval = 120  # 共线区段最小间隔（秒）
        # 替换为列表形式存储各峰期列车数
        params.N1 = [peak.train_num1 for peak in params.peaks]  # 各峰期交路1列车数列表
        params.N2 = [peak.train_num2 for peak in params.peaks]  # 各峰期交路2列车数列表
        params.OperaRate1 = [peak.op_rate1 for peak in params.peaks]  # 各峰期交路1开行比例列表
        params.OperaRate2 = [peak.op_rate2 for peak in params.peaks]  # 各峰期交路2开行比例列表
        # 获取每个峰期的发车间隔
        params.RouteInterval = [peak.interval for peak in params.peaks]
        params.t = [peak.start_time for peak in params.peaks]  # 所有峰期的开始时间
        if params.peaks:  # 添加最后一个峰期的结束时间
            params.t.append(params.peaks[-1].end_time)
        # 计算每个峰期的持续时间（秒）
        params.f1_real = []
        params.f2_real = []
        for i in range(len(params.peaks)):
            # 获取峰期开始和结束时间
            start = params.t[i]
            end = params.t[i + 1] if i < len(params.peaks) - 1 else params.t[-1]
            peak_duration = end - start

            # 根据共线发车间隔计算实际车次数
            actual_full_trains = int(np.round(peak_duration / params.RouteInterval[i])) + 1#总发车车次数
            # 当 OperaRate1 和 OperaRate2 都为 -1 时，所有车次都由大交路发出
            if params.OperaRate1[i] == -1 and params.OperaRate2[i] == -1:
                params.f1_real.append(actual_full_trains)
                params.f2_real.append(0)
            else:
                # 根据开行比例来计算大小交路车次数
                total_rate = params.OperaRate1[i] + params.OperaRate2[i]
                f1_count = int(actual_full_trains * params.OperaRate1[i] / total_rate)
                f2_count = actual_full_trains - f1_count
                params.f1_real.append(f1_count)
                params.f2_real.append(f2_count)
        params.min_dep_arr_delta = 120#发到间隔
        params.n_r = 4
        params.m = 1
        params.n = 1
        # 折返站定义
        params.major_turnback_stations = [params.large_start_station, params.large_end_station]  # 大交路折返站
        params.minor_turnback_stations = [params.small_start_station, params.small_end_station]  # 小交路折返站
        params.period_num = len(params.t) - 1
        params.trip_num1 = sum(params.f1_real)
        params.trip_num2 = sum(params.f2_real)
        params.rcd = [[0] * (params.trip_num2 + params.trip_num1) for _ in range(2)]
        for i in range(len(params.rcd[0])):
            if i % 2 == 1:
                params.rcd[0][i] = 2
            params.rcd[1][i] = -params.rcd[0][i] + 3
        rcd_idx = 0
        for i in range(params.period_num):
            tot_trip_num_p = params.f1_real[i] + params.f2_real[i]
            a, b = params.OperaRate1[i], params.OperaRate2[i]
            if a != -1:
                c = tot_trip_num_p / (a + b)
                c1 = math.ceil(c)
                c2 = math.floor(c)
                if c1 * (a + b) - tot_trip_num_p < tot_trip_num_p - c2 * (a + b):
                    k = c1
                else:
                    k = c2
                params.f1_real[i] = k * params.OperaRate1[i]
                params.f2_real[i] = k * params.OperaRate2[i]
                for j in range(k):
                    for k1 in range(params.OperaRate1[i]):
                        params.rcd[0][rcd_idx] = 0
                        rcd_idx += 1
                    for k2 in range(params.OperaRate2[i]):
                        params.rcd[0][rcd_idx] = 2
                        rcd_idx += 1
            else:
                if params.f1_real[i] != 0:
                    for k1 in range(params.f1_real[i]):
                        params.rcd[0][rcd_idx] = 0
                        rcd_idx += 1
                else:
                    for k1 in range(params.f2_real[i]):
                        params.rcd[0][rcd_idx] = 2
                        rcd_idx += 1


        for i in range(len(params.rcd[0])):
            params.rcd[1][i] = params.rcd[0][i] + 1

        params.trip_num1 = sum(params.f1_real)
        params.trip_num2 = sum(params.f2_real)
        params.v_num = max(params.trip_num2, params.trip_num1)
        params.f_tag = [[0] * params.v_num for _ in range(params.n_r)]
        params.f_accumulated = [[0] * (params.period_num + 1) for _ in range(params.n_r)]
        params.the_pre_variable = [[-1] * params.v_num for _ in range(params.n_r)]
        params.the_aft_variable = [[-1] * params.v_num for _ in range(params.n_r)]
        params.rcd[0] = params.rcd[0][:params.trip_num2 + params.trip_num1]
        params.rcd[1] = params.rcd[1][:params.trip_num2 + params.trip_num1]


        params.f1_accumulated = [0]
        # 根据 f1_real 累加生成剩余的 f1_accumulated 元素
        for i in range(len(params.f1_real)):
            next_value = params.f1_accumulated[-1] + params.f1_real[i]
            params.f1_accumulated.append(next_value)

        params.f2_accumulated = [0]
        # 根据 f2_real 累加生成剩余的 f2_accumulated 元素
        for i in range(len(params.f2_real)):
            next_value = params.f2_accumulated[-1] + params.f2_real[i]
            params.f2_accumulated.append(next_value)

        params.same_arrive_delta = 30
        # 根据是否存在小交路来设置交路起终点站
        if params.small_start_station is not None and params.small_end_station is not None:
            params.jiaolu_start = [params.large_start_station, params.small_start_station]
            params.jiaolu_end = [params.large_end_station, params.small_end_station]
        else:
            # 只有大交路时
            params.jiaolu_start = [params.large_start_station]
            params.jiaolu_end = [params.large_end_station]
        print("params.small_start_station的值:", params.small_start_station)
        print("params.small_end_station的值:", params.small_end_station)
        print("params.large_start_station的值:", params.large_start_station)
        print("params.large_end_station的值:", params.large_end_station)
        params.depot_id = [0, 25]
        params.key_stations = [18]

        print("params.all_depot_run_times的值:")
        print(params.all_depot_run_times)
        print("params.run_times的值:")
        print(params.run_times)
        print("params.run_times的内容:")
        print(f"上行运行时间列表长度: {len(params.run_times['up'])}")
        print(f"下行运行时间列表长度: {len(params.run_times['down'])}")
        print("params.stop_times的值:")
        print(params.stop_times)
        # 矩阵数据：运行时间和停站时间
        if not params.run_times['down']:
            print("警告：下行运行时间列表为空")
        params.downward_running_time_origin = np.array(params.run_times['down'], dtype=int)
        # print(f'下行运行时间原始数据xml: {params.downward_running_time_origin.tolist()}, 数组形状: {params.downward_running_time_origin.shape}')
        params.downward_stopping_time_origin = np.array(params.stop_times['down'][1:-1], dtype=int)  # 去掉首尾站台时间
        # print(f'下行停站时间原始数据xml: {params.downward_stopping_time_origin.tolist()}, 数组形状: {params.downward_stopping_time_origin.shape}')
        # 上行数据 
        params.upward_running_time_origin = np.array(params.run_times['up'][::-1], dtype=int)
        # print(f'上行运行时间原始数据xml: {params.upward_running_time_origin.tolist()}, 数组形状: {params.upward_running_time_origin.shape}')
        params.upward_stopping_time_origin = np.array(params.stop_times['up'][1:-1], dtype=int)
        # print(f'上行运行时间原始数据xml: {params.upward_stopping_time_origin.tolist()}, 数组形状: {params.upward_stopping_time_origin.shape}')

        params.downward_running_time = np.concatenate(([0], params.downward_running_time_origin, [0]))
        params.upward_running_time = np.concatenate(([0], params.upward_running_time_origin, [0]))
        params.downward_stopping_time = np.concatenate(([0], params.downward_stopping_time_origin, [0]))
        params.upward_stopping_time = np.concatenate(([0], params.upward_stopping_time_origin, [0]))
        # 从i出发到达j的旅行时间
        params.travel_time_matrix = np.zeros(
            (2, len(params.upward_running_time) + 1, len(params.upward_running_time) + 1))
        # 从i出发到达j的停站时间，包括站台i和站台j
        params.stop_time_matrix = np.zeros(
            (2, len(params.upward_running_time) + 1, len(params.upward_running_time) + 1))

        # 上行
        for i in range(len(params.upward_running_time)):
            for j in range(i + 1, len(params.upward_running_time) + 1):
                travel_time = np.sum(
                    params.upward_running_time[len(params.upward_running_time) - j:len(params.upward_running_time) - i])
                params.travel_time_matrix[0, i, j] = travel_time

        for i in range(1, len(params.downward_running_time) + 1):
            for j in range(i):
                travel_time = np.sum(params.downward_running_time[
                                     len(params.downward_running_time) - i:len(params.downward_running_time) - j])
                params.travel_time_matrix[1, i, j] = travel_time

        for i in range(1, len(params.upward_stopping_time) + 1):
            for j in range(i, len(params.upward_stopping_time) + 1):
                stop_time = np.sum(params.upward_stopping_time[
                                   len(params.upward_stopping_time) - j:len(params.upward_stopping_time) - i + 1])
                params.stop_time_matrix[0, i, j] = stop_time
            params.stop_time_matrix[0, 0, i] = params.stop_time_matrix[0, 1, i]
            params.stop_time_matrix[0, i, len(params.upward_running_time)] = params.stop_time_matrix[
                0, i, len(params.upward_running_time) - 1]

        for i in range(1, len(params.downward_stopping_time) + 1):
            for j in range(1, i + 1):
                stop_time = np.sum(params.downward_stopping_time[
                                   len(params.downward_stopping_time) - i:len(params.downward_stopping_time) + 1 - j])
                params.stop_time_matrix[1, i, j] = stop_time
            params.stop_time_matrix[1, len(params.downward_running_time), i] = params.stop_time_matrix[
                1, len(params.downward_running_time) - 1, i]
            params.stop_time_matrix[1, i, 0] = params.stop_time_matrix[1, i, 1]

        for i in range(1, len(params.downward_stopping_time)):
            params.stop_time_matrix[1, len(params.downward_running_time), i] = params.stop_time_matrix[
                1, len(params.downward_running_time) - 1, i]
            params.stop_time_matrix[1, i, 0] = params.stop_time_matrix[1, i, 1]

        params.stop_time_matrix[1, params.jiaolu_end[0], 0] = params.stop_time_matrix[1, params.jiaolu_end[0], 1]
        params.stop_time_matrix[0, 0, params.jiaolu_end[0]] = params.stop_time_matrix[0, 1, params.jiaolu_end[0]]
        # 添加参数打印params内容
        print("\nparams对象内容：")
        print(f"对象类型: {type(params)}")
        print("对象属性列表:")
        for attr in vars(params):
            value = getattr(params, attr)
            # 处理numpy数组的显示
            if isinstance(value, np.ndarray):
                print(f"  {attr}: numpy数组 {value.shape} {value.dtype}")
            else:
                print(f"  {attr}: {repr(value)[:2000]}")  # 限制输出长度
                
        params.up_time1 = params.travel_time_matrix[0, params.jiaolu_start[0], params.jiaolu_end[0]] + \
                          params.stop_time_matrix[0, params.jiaolu_start[0] + 1, params.jiaolu_end[0] - 1]
        params.down_time1 = params.travel_time_matrix[1, params.jiaolu_end[0], params.jiaolu_start[0]] + \
                            params.stop_time_matrix[1, params.jiaolu_end[0] - 1, params.jiaolu_start[0] + 1]
        # 只有在存在第二条交路时才计算up_time2和down_time2
        if len(params.jiaolu_start) > 1:
            params.up_time2 = params.travel_time_matrix[0, params.jiaolu_start[1], params.jiaolu_end[1]] + \
                              params.stop_time_matrix[0, params.jiaolu_start[1] + 1, params.jiaolu_end[1] - 1]
            params.down_time2 = params.travel_time_matrix[1, params.jiaolu_end[1], params.jiaolu_start[1]] + \
                                params.stop_time_matrix[1, params.jiaolu_end[1] - 1, params.jiaolu_start[1] + 1]
        else:
            # 如果只有一条交路，将第二条交路的运行时间设置为0或与第一条交路相同
            params.up_time2 = 0
            params.down_time2 = 0
        # 其他运行参数配置
        # 根据是否存在小交路来设置共线区段
        if params.small_start_station is not None and params.small_end_station is not None:
            params.shared_stations = list(range(params.small_start_station, params.small_end_station + 1))  # 共线区段车站范围
            target_station = params.small_end_station  # 共线区段关键车站
            # 计算从始发站到目标车站的总运行+停站时间
            stations_to_target = params.major_turnback_stations[1] - target_station  # station_P到station_M共13个区间
            total_run_time = np.sum(params.downward_running_time[:stations_to_target])
            total_stop_time = np.sum(params.downward_stopping_time[:stations_to_target])  # 最后一站无停站
            major_to_station_M_time = total_run_time + total_stop_time  # 大交路下行到达station_M站的发车时间
            params.major_to_station_M_time = major_to_station_M_time
        else:
            # 如果只有大交路，则共线区段为空列表
            params.shared_stations = []  # 预计算大交路下行到达车站station_M的运行参数

        return params

    @staticmethod
    def draw_lines(lines, colors=None, linewidth=1, title="Multilines Plot", xlabel="X", ylabel="Y"):
        """
        绘制多条折线图的函数

        参数:
            lines (list): 输入的多条折线列表，每条折线由点列表组成，例如 [[(0,0), (1,1)], [(2,3), (4,5)]]
            colors (list): 可选，每条折线的颜色列表（默认为系统自动配色）
            linewidth (int): 线条宽度（默认为1）
            title (str): 图表标题（默认为"Multilines Plot"）
            xlabel/ylabel (str): 坐标轴标签（默认为"X"和"Y"）
        """
        plt.figure(figsize=(8, 6))

        # 遍历每条折线并绘图
        for idx, line in enumerate(lines):
            if len(line) == 0:
                continue  # 跳过空列表

            y, x = zip(*line)  # 解包坐标点
            color = colors[idx] if (colors and idx < len(colors)) else None

            plt.plot(
                x,
                y,
                marker='o' if len(line) == 1 else '',  # 单点时显示标记
                linestyle='-' if len(line) > 1 else '',  # 多点时连线
                linewidth=linewidth,
                color=color,
                label=f"Line {idx + 1}"
            )

        plt.title(title)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.grid(True)
        plt.legend()

    def get_temp_res(self,params,res_schedule):
        temp_res = []
        mt = 100
        vis = [[0] * params.v_num for _ in range(params.n_r)]
        # 添加上行的
        for i in range(params.n_r):
            if i <= 1:
                mt = abs(mt)
                for j in range(params.trip_num[i]):
                    if vis[i][j] == 0:
                        r = i
                        vis[i][j] = 1
                        if i == 1:
                            path = [(mt * params.jiaolu_end[0], res_schedule[i][j]),
                                    (mt * params.jiaolu_start[0], res_schedule[i][j] + params.down_time1)]
                        else:
                            path = [(mt * params.jiaolu_start[0], res_schedule[i][j]),
                                    (mt * params.jiaolu_end[0], res_schedule[i][j] + params.up_time1)]
                        while 1:
                            if params.the_aft_variable[r][j] != -1:
                                if r == 0:
                                    path.append(
                                        (mt * params.jiaolu_end[0], res_schedule[1 - r][params.the_aft_variable[r][j]]))
                                    path.append((mt * params.jiaolu_start[0], res_schedule[1 - r][
                                        params.the_aft_variable[r][j]] + params.down_time1))
                                else:
                                    path.append((mt * params.jiaolu_start[0],
                                                    res_schedule[1 - r][params.the_aft_variable[r][j]]))
                                    path.append((mt * params.jiaolu_end[0],
                                                    res_schedule[1 - r][params.the_aft_variable[r][j]] + params.up_time1))
                                vis[1 - r][params.the_aft_variable[r][j]] = 1
                                j = params.the_aft_variable[r][j]
                                r = 1 - r
                            else:
                                break
                        temp_res.append(path)
            else:
                mt = abs(mt)
                for j in range(params.trip_num[i]):
                    if vis[i][j] == 0:
                        r = i
                        vis[i][j] = 1
                        if i == 3:
                            path = [(mt * params.jiaolu_end[1], res_schedule[i][j]),
                                    (mt * params.jiaolu_start[1], res_schedule[i][j] + params.down_time2)]
                        else:
                            path = [(mt * params.jiaolu_start[1], res_schedule[i][j]),
                                    (mt * params.jiaolu_end[1], res_schedule[i][j] + params.up_time2)]
                        while 1:
                            if params.the_aft_variable[r][j] != -1:
                                if r == 2:
                                    path.append(
                                        (mt * params.jiaolu_end[1], res_schedule[5 - r][params.the_aft_variable[r][j]]))
                                    path.append((mt * params.jiaolu_start[1], res_schedule[5 - r][
                                        params.the_aft_variable[r][j]] + params.down_time2))
                                else:
                                    path.append((mt * params.jiaolu_start[1],
                                                    res_schedule[5 - r][params.the_aft_variable[r][j]]))
                                    path.append(
                                        (mt * params.jiaolu_end[1],
                                            res_schedule[5 - r][params.the_aft_variable[r][j]] + params.up_time2))
                                vis[5 - r][params.the_aft_variable[r][j]] = 1
                                j = params.the_aft_variable[r][j]
                                r = 5 - r
                            else:
                                break
                        temp_res.append(path)
                    # 添加下行的
        return temp_res

    def run_alg(self):
        p1_time = 0
        p2_time = 0
        p3_time = 0
        ## 运行第0阶段：Phase0
        self.phase0()  
        do_re = True
        while True:
            # If time limit is met, we use the best one so far
            if p2_time + p1_time + p3_time > 17000:
                # restore to the best and break
                do_re = False
                if self.debug:
                    util.pf(util.ANSI_RED + f"TLE, use the best one so far, score: {self.besst_ir.computeScore()}   {len(self.besst_ir.intervals)} {len(self.Phases)}")
                for i in range(len(self.Phases)):
                    val = self.besst_ir.intervals[i + 1]
                    if val > 0:
                        self.Phases[i].interval = val
                    if self.debug:
                        util.pf(util.ANSI_RED + f"   Interval: {val}")

            # Phase1
            millis1 = sys_time.time() * 1000  # 转换为毫秒
            phase_res = self.phase1()
            # phase_res = self.phase1_optimized()
            if self.debug:
                util.pf("Phase 1 done...\n")

            phase1_time = sys_time.time() * 1000
            p1_time += phase1_time - millis1  # 经过的毫秒数
            # print(f"Phase 1 time: {phase1_time - millis1} ms")
            # Phase2
            # print("阶段2前")
            # self.print_phase3_res(phase_res)
            shift_times = 100
            phase_res = self.phase2(phase_res, 0, 5, shift_times)
            if self.debug:
                util.pf("Phase 2 done...\n")

            phase2_time = sys_time.time() * 1000
            p2_time += phase2_time - phase1_time  # 经过的毫秒数
            # print(f"Phase 2 time: {phase2_time - phase1_time} ms")
            # Phase3
            # print("阶段3前")
            # self.print_phase3_res(phase_res)
            phase_res = self.phase3(phase_res)
            self.count_cars_all(phase_res, do_re)
            # print("阶段3后")
            # self.print_phase3_res(phase_res)
            # check if we have finished the process
            if not do_re:
                self.planning_done = True
            if self.debug:
                util.pf("Phase 3 done...\n")

            phase3_time = sys_time.time() * 1000
            p3_time += phase3_time - phase2_time  # 经过的毫秒数
            # print(f"Phase 3 time: {phase3_time - phase2_time} ms")
            if self.planning_done:
                break
            else:
                if self.debug:
                    util.pf("No-matching car number found, redo")
                self.reset_planning()

        # print("=====================检查阶段前=====================")
        # self.print_phase3_res(phase_res)
        #==============检查阶段===================
        # 移除早期车辆
        phase_res = self.removeEarlyCars(phase_res)
        # 检查车库车辆数目，并根据需求进行车辆调运
        dimb = self.check_depot_cars(phase_res)
        # 检查是否存在车辆不足的情况
        if dimb is None or dimb.ins_cars <= 0:
            # 检查是否存在不平衡
            if self.imb_amnt > 0:
                if self.debug:
                    util.pf(util.ANSI_YELLOW_BACKGROUND + "处理车库不平衡")
                self.handle_imb(phase_res)
            else:
                if self.debug:
                    util.pf("当前车库状态良好")
        else:
            # 需要先解决车辆不足问题
            phase_res = self.handle_insufficent(dimb, phase_res)
        # print("=====================检查阶段后=====================")
        # self.print_phase3_res(phase_res)
        ##出入库阶段
        # print("=====================出入库阶段前=====================")
        # self.print_phase3_res(phase_res)

        ######出入库阶段前就把正常折返车次的到发时刻全部替换了

        phase_res = self.phase_inout(phase_res) #只用这一个函数就把所有线全部画成出入库线了
        self.load_routes_3_dim(phase_res)#将结果加载到rl中，方便后续的时刻表文件生成
        self.connect()

        return 
        ######### 基于规则生成运行图的部分完毕############

        params = self.initialize_params()# 把这套代码的输入全部整到params里面
        ######传入算法模型进行求解
        a = TrainScheduler(params)  
        res_schedule, divide_res = a.solve_smart()  # 返回的是大小交路上下行的发车时刻，里面如果有nan是因为小交路的发车比大交路少
        # # 画图
        # temp_res = self.get_temp_res(params,res_schedule)
        # temp_res2 = self.get_temp_res(params,divide_res)
        # self.draw_lines(temp_res2, None, 1, "raw")
        # self.draw_lines(temp_res, None, 1, "optimized")
        # plt.show()

        print(f"res_schedule的内容: {res_schedule}")
        print(f"a.params.trip_num: {a.params.trip_num}")

        # """
        #    # 第一种思路：根据res_schedule来创建最终的解，需要加上出入库阶段
        # """
        # 新的实现：
        print("应用优化模型的调度方案...")
        new_phase_res = self.apply_optimized_schedule(res_schedule, params)
        # new_phase_res = self.phase_inout(new_phase_res)
        # 重新加载数据用于生成时刻表
        self.load_routes_3_dim(new_phase_res)
        self.connect()
        # """
        #     #第二种思路： 根据res_schedule修改phase_res，必须保证车次数一致
        # """
        # # 使用新函数更新phase_res中的到发时刻
        # # self.update_routes_from_schedule(phase_res, res_schedule)
        # # 方案1：硬改
        # # self.update_routes_from_schedule_improved(phase_res, res_schedule)
        # #方案2：使得规则算法生成与优化模型一样的车次
        # self.update_routes_with_intelligent_matching(phase_res, res_schedule)
        # #修改完成后重新load一次
        # # self.load_routes_3_dim(phase_res)

    def write_excel(self, dir: str, csn: str) -> None:
        """
        写入Excel文件
        Args:
            dir: 输出目录
            csn: 自定义名称
        """
        import os
        if not os.path.exists(dir):
            os.makedirs(dir)

        self.rl.sl.renumb_routes()#重新编号路线。
        # self.rl.sl.renumb_routes_new()#重新编号路线。
        self.rl.sl.writeExcel(dir, self.rl, csn)  # 调用Solution中的writeExcel方法输出结果
        util.pf(util.ANSI_RED + " write_excel DONE........")

    def xls_to_xlsx(self, source_file, target_file):
        try:
            # 获取当前脚本的绝对路径
            script_dir = os.path.dirname(os.path.abspath(__file__))

            # 构建完整的源文件和目标文件路径
            source_path = os.path.join(script_dir, source_file)
            target_path = os.path.join(script_dir, target_file)

            # 读取原始xls文件中的所有sheet页
            excel_file = pd.ExcelFile(source_path)
            sheet_names = excel_file.sheet_names

            # 创建ExcelWriter对象
            with pd.ExcelWriter(target_path, engine='openpyxl') as writer:
                # 遍历所有sheet页并保持原有名称
                for sheet_name in sheet_names:
                    # 读取当前sheet页的数据
                    df = pd.read_excel(source_path, sheet_name=sheet_name, dtype=str)

                    # 写入数据，保持原有sheet名称
                    df.to_excel(writer, sheet_name=sheet_name, index=False)

                    # 获取当前工作表
                    worksheet = writer.sheets[sheet_name]

                    # 调整列宽以匹配原始文件
                    for idx, col in enumerate(df.columns):
                        max_length = max(df[col].astype(str).apply(len).max(), len(str(col)))
                        worksheet.column_dimensions[chr(65 + idx)].width = max_length + 2

            print(f"转换完成，已将{source_path}转换为{target_path}")
            print(f"保存的sheet页: {', '.join(sheet_names)}")
        except Exception as e:
            print(f"转换过程中发生错误: {str(e)}")

    def convert_to_xlsx(self, dir: str) -> None:
        """
        将xls文件转换为xlsx格式
        Args:
            dir: 包含xls文件的目录
        """
        input_path = os.path.join(dir, "result.xls")
        output_path = os.path.join(dir, "result.xlsx")
        xls_file = input_path
        xlsx_file = output_path

        # 确保文件存在
        script_dir = os.path.dirname(os.path.abspath(__file__))
        full_xls_path = os.path.join(script_dir, xls_file)

        if not os.path.exists(full_xls_path):
            print(f"错误：找不到源文件 {full_xls_path}")
        else:
            # 调用函数进行转换
            self.xls_to_xlsx(xls_file, xlsx_file)

    def create_route_solutions_from_schedule(self, res_schedule, params):
        """
        根据优化模型的发车时刻res_schedule创建完整的RouteSolution列表
        
        Args:
            res_schedule: 优化模型返回的4×v_num发车时刻矩阵
            params: 优化模型参数对象
        
        Returns:
            route_solutions: 按phase_res格式组织的RouteSolution列表
        """
        import pandas as pd
        
        # 创建结果存储结构，模拟phase_res的格式
        route_solutions = []
        
        # 获取基础信息
        pk = self.Phases[0].pk  # 获取峰期信息
        level = self.level  # 速度等级
        
        # 处理每个交路类型和方向
        route_configs = [
            {'route_idx': 0, 'direction': 0, 'route_type': 0, 'name': '大交路上行'},  # 大交路上行
            {'route_idx': 1, 'direction': 1, 'route_type': 0, 'name': '大交路下行'},  # 大交路下行
            {'route_idx': 2, 'direction': 0, 'route_type': 1, 'name': '小交路上行'},  # 小交路上行
            {'route_idx': 3, 'direction': 1, 'route_type': 1, 'name': '小交路下行'}   # 小交路下行
        ]
        
        # 按阶段组织数据
        phase_solutions = []
        
        # 创建一个阶段的解（可以根据需要扩展为多阶段）
        current_phase = [[], []]  # [上行列表, 下行列表]
        
        car_counter = 1  # 车次编号计数器
        
        for config in route_configs:
            route_idx = config['route_idx']
            direction = config['direction']
            route_type = config['route_type']
            
            # 获取该交路方向的发车时刻
            schedule_times = res_schedule[route_idx, :]
            
            # 过滤掉NaN值
            valid_times = [t for t in schedule_times if not pd.isna(t)]
            
            print(f"处理{config['name']}: {len(valid_times)}个有效车次")
            
            # 为每个有效发车时刻创建RouteSolution
            for i, dep_time in enumerate(valid_times):
                # 创建车辆信息
                # 创建车辆信息 - 使用车辆管理方法
                vehicle_id = self.get_available_vehicle_id()  # 获取可用车辆编号（1-45范围内）
                round_num = self.get_next_round_num()  # 获取唯一车次号
                car_info = CarInfo(vehicle_id, round_num, route_type)  # 创建CarInfo对象    
                
                # 选择路线
                if direction == 0:  # 上行
                    route = pk.routes[route_type].up_route
                else:  # 下行
                    route = pk.routes[route_type].down_route
                
                # 生成完整的运行方案
                rs = self.rl.getHeuristicSolFromPath1(
                    route, 
                    int(dep_time), 
                    level, 
                    30,  # 停站时间 默认为30秒对吗？
                    0,   # 阶段
                    car_info
                )
                
                # 设置RouteSolution属性
                rs.dir = direction
                rs.xroad = route_type
                rs.phase = 0  # 假设都在第0阶段
                
                # 添加到对应方向的列表
                current_phase[direction].append(rs)
        
        # 按发车时间排序
        for direction in range(2):
            current_phase[direction].sort(key=lambda x: x.dep_time[0] if x.dep_time else 0)
        # 修改：传递params参数给折返连接函数
        self.establish_turnaround_connections(current_phase, params)
        phase_solutions.append(current_phase)
        
        return phase_solutions

    def establish_turnaround_connections(self, phase_data, params):
        """
        基于优化模型结果建立折返连接关系
        正确使用 the_aft_variable 和 the_pre_variable 建立完整的双向连接
        
        Args:
            phase_data: 阶段数据，格式为 [上行RouteSolution列表, 下行RouteSolution列表]
            params: 优化模型参数对象
        """
        # 创建车次索引映射：(交路类型, 方向, 车次索引) -> RouteSolution对象
        trip_to_route = {}
        
        # 处理上行和下行的RouteSolution对象
        for direction in range(len(phase_data)):
            route_list = phase_data[direction]
            for trip_idx, route in enumerate(route_list):
                # 根据交路类型和方向确定在params中的索引
                if route.xroad == 0:  # 大交路
                    if direction == 0:  # 上行
                        param_direction = 0
                    else:  # 下行
                        param_direction = 1
                else:  # 小交路
                    if direction == 0:  # 上行
                        param_direction = 2
                    else:  # 下行
                        param_direction = 3
                
                # 为RouteSolution对象添加必要属性
                route.trip_index = trip_idx
                route.param_direction = param_direction
                trip_to_route[(param_direction, trip_idx)] = route
        
        connected_count = 0
        
        # 使用 the_aft_variable 建立后向连接
        for param_dir in range(params.n_r):
            for trip_idx in range(len(params.the_aft_variable[param_dir])):
                if params.the_aft_variable[param_dir][trip_idx] != -1:
                    current_route = trip_to_route.get((param_dir, trip_idx))
                    next_trip_idx = params.the_aft_variable[param_dir][trip_idx]
                    
                    # 确定下一个车次的方向
                    if param_dir <= 1:  # 大交路
                        next_param_dir = 1 - param_dir
                    else:  # 小交路
                        next_param_dir = 5 - param_dir
                    
                    next_route = trip_to_route.get((next_param_dir, next_trip_idx))
                    
                    if current_route and next_route:
                        current_route.next_ptr = next_route
                        next_route.prev_ptr = current_route
                        connected_count += 1
                        if self.debug:
                            print(f"建立连接: {param_dir}[{trip_idx}] -> {next_param_dir}[{next_trip_idx}]")
        
        # 使用 the_pre_variable 进行验证和补充
        for param_dir in range(params.n_r):
            for trip_idx in range(len(params.the_pre_variable[param_dir])):
                if params.the_pre_variable[param_dir][trip_idx] != -1:
                    current_route = trip_to_route.get((param_dir, trip_idx))
                    prev_trip_idx = params.the_pre_variable[param_dir][trip_idx]
                    
                    # 确定前一个车次的方向
                    if param_dir <= 1:  # 大交路
                        prev_param_dir = 1 - param_dir
                    else:  # 小交路
                        prev_param_dir = 5 - param_dir
                    
                    prev_route = trip_to_route.get((prev_param_dir, prev_trip_idx))
                    
                    if current_route and prev_route:
                        # 验证连接的一致性
                        if current_route.prev_ptr is None:
                            current_route.prev_ptr = prev_route
                            if self.debug:
                                print(f"补充前向连接: {prev_param_dir}[{prev_trip_idx}] -> {param_dir}[{trip_idx}]")
                        if prev_route.next_ptr is None:
                            prev_route.next_ptr = current_route
                            if self.debug:
                                print(f"补充后向连接: {prev_param_dir}[{prev_trip_idx}] -> {param_dir}[{trip_idx}]")
        
        print(f"建立了 {connected_count} 个折返连接")
        
        # 统计连接情况
        total_routes = sum(len(phase_data[d]) for d in range(len(phase_data)))
        null_next_count = 0
        null_prev_count = 0
        
        for direction in range(len(phase_data)):
            for route in phase_data[direction]:
                if route.next_ptr is None:
                    null_next_count += 1
                if route.prev_ptr is None:
                    null_prev_count += 1
        
        print(f"连接统计: 总车次 {total_routes}, next_ptr为空 {null_next_count}, prev_ptr为空 {null_prev_count}")
        
        return phase_data
        
    def apply_optimized_schedule(self, res_schedule, params):
        """
        应用优化模型的调度方案，替换原有的phase_res
        
        Args:
            phase_res: 原始规则算法生成的解
            res_schedule: 优化模型返回的发车时刻矩阵
            params: 优化模型参数
        
        Returns:
            更新后的phase_res
        """
        print("开始根据优化模型结果创建完整的运行方案...")
        # 清空现有的route_lists，避免时刻表文件中与新生成的车次重复
        self.rl.sl.route_lists.clear()
        # 从res_schedule创建新的RouteSolution列表
        optimized_solutions = self.create_route_solutions_from_schedule(res_schedule, params)
        
        # 直接使用优化后的解，不保留原有的phase_res
        new_phase_res = optimized_solutions
        
        print(f"优化后的解包含 {len(new_phase_res)} 个阶段")
        total_trips = 0
        for i, phase in enumerate(new_phase_res):
            up_count = len(phase[0]) if len(phase) > 0 else 0
            down_count = len(phase[1]) if len(phase) > 1 else 0
            total_trips += up_count + down_count
            print(f"阶段 {i}: 上行 {up_count} 车次, 下行 {down_count} 车次")
        
        print(f"总车次数: {total_trips}")
        
        return new_phase_res

    def has_initial_phase(self, phase):
        """
        判断是否为初始出库阶段
        
        Args:
            phase: 阶段数据
        
        Returns:
            bool: 是否为初始出库阶段
        """
        # 简单判断：如果阶段中的车次都标记为phase=0且时间较早，则认为是初始阶段
        if len(phase) < 2:
            return False
        
        for direction in range(2):
            if len(phase[direction]) > 0:
                # 检查第一个车次的phase属性
                first_rs = phase[direction][0]
                if hasattr(first_rs, 'phase') and first_rs.phase == 0:
                    return True
        
        return False
    def update_routes_2_dim(self, rss: List[List[RouteSolution]]) -> None:
        """
        更新计划列表中的路线时刻表，而不是添加新的路线
        主要用于修改现有RouteSolution对象的到发时刻
        
        Args:
            rss: 解决方案的二维列表 [方向][路线]，包含更新后的时刻数据
        """
        updated_count = 0
        skipped_count = 0
        
        # 用于快速查找已有对象的字典 {(dir, table_num): index}
        existing_routes = {}
        for i, rs in enumerate(self.rl.sl.route_lists):
            key = (rs.dir, rs.car_info.table_num)
            existing_routes[key] = i
            
        # 更新上行方向的路线
        for rs in rss[0]:
            if rs is None:
                continue
                
            key = (rs.dir, rs.car_info.table_num)
            if key in existing_routes:
                # 找到匹配的路线，更新其到发时刻
                idx = existing_routes[key]
                existing_rs = self.rl.sl.route_lists[idx]
                
                # 更新到发时刻
                existing_rs.arr_time = rs.arr_time.copy() if rs.arr_time else existing_rs.arr_time
                existing_rs.dep_time = rs.dep_time.copy() if rs.dep_time else existing_rs.dep_time
                
                # 可选：更新其他需要同步的字段
                if rs.stopped_platforms:
                    existing_rs.stopped_platforms = rs.stopped_platforms.copy()
                if rs.performance_levels:
                    existing_rs.performance_levels = rs.performance_levels.copy()
                if rs.stopped_time:
                    existing_rs.stopped_time = rs.stopped_time.copy()
                    
                updated_count += 1
            else:
                # 没有找到匹配的路线，跳过或可选择添加
                skipped_count += 1
                
        # 更新下行方向的路线（同上）
        for rs in rss[1]:
            if rs is None:
                continue
                
            key = (rs.dir, rs.car_info.table_num)
            if key in existing_routes:
                idx = existing_routes[key]
                existing_rs = self.rl.sl.route_lists[idx]
                
                existing_rs.arr_time = rs.arr_time.copy() if rs.arr_time else existing_rs.arr_time
                existing_rs.dep_time = rs.dep_time.copy() if rs.dep_time else existing_rs.dep_time
                
                if rs.stopped_platforms:
                    existing_rs.stopped_platforms = rs.stopped_platforms.copy()
                if rs.performance_levels:
                    existing_rs.performance_levels = rs.performance_levels.copy()
                if rs.stopped_time:
                    existing_rs.stopped_time = rs.stopped_time.copy()
                    
                updated_count += 1
            else:
                skipped_count += 1
                
        print(f"已更新 {updated_count} 条路线，跳过 {skipped_count} 条路线")

    def update_routes_3_dim(self, rss: List[List[List[RouteSolution]]]) -> None:
        """
        更新三维RouteSolution数据的到发时刻，而不是添加新的路线
        
        Args:
            rss: 三维列表结构 [阶段][方向][路线]，包含更新后的时刻数据
        """
        updated_count = 0
        skipped_count = 0
        
        # 创建用于快速查找的字典 {(phase, dir, table_num): index}
        existing_routes = {}
        for i, rs in enumerate(self.rl.sl.route_lists):
            key = (rs.phase, rs.dir, rs.car_info.table_num)
            existing_routes[key] = i
            
        # 遍历所有阶段
        for phase_idx in range(len(rss)):
            # 处理上行方向
            for rs in rss[phase_idx][0]:
                if rs is None:
                    continue
                    
                key = (rs.phase, rs.dir, rs.car_info.table_num)
                if key in existing_routes:
                    # 找到匹配的路线，更新其到发时刻
                    idx = existing_routes[key]
                    existing_rs = self.rl.sl.route_lists[idx]
                    
                    # 更新到发时刻
                    existing_rs.arr_time = rs.arr_time.copy() if rs.arr_time else existing_rs.arr_time
                    existing_rs.dep_time = rs.dep_time.copy() if rs.dep_time else existing_rs.dep_time
                    
                    # 更新其他相关字段
                    if rs.stopped_platforms:
                        existing_rs.stopped_platforms = rs.stopped_platforms.copy()
                    if rs.performance_levels:
                        existing_rs.performance_levels = rs.performance_levels.copy()
                    if rs.stopped_time:
                        existing_rs.stopped_time = rs.stopped_time.copy()
                    if hasattr(rs, 'xroad') and hasattr(existing_rs, 'xroad'):
                        existing_rs.xroad = rs.xroad
                        
                    updated_count += 1
                else:
                    # 没有找到匹配的路线，跳过
                    skipped_count += 1
                    
            # 处理下行方向
            for rs in rss[phase_idx][1]:
                if rs is None:
                    continue
                    
                key = (rs.phase, rs.dir, rs.car_info.table_num)
                if key in existing_routes:
                    idx = existing_routes[key]
                    existing_rs = self.rl.sl.route_lists[idx]
                    
                    existing_rs.arr_time = rs.arr_time.copy() if rs.arr_time else existing_rs.arr_time
                    existing_rs.dep_time = rs.dep_time.copy() if rs.dep_time else existing_rs.dep_time
                    
                    if rs.stopped_platforms:
                        existing_rs.stopped_platforms = rs.stopped_platforms.copy()
                    if rs.performance_levels:
                        existing_rs.performance_levels = rs.performance_levels.copy()
                    if rs.stopped_time:
                        existing_rs.stopped_time = rs.stopped_time.copy()
                    if hasattr(rs, 'xroad') and hasattr(existing_rs, 'xroad'):
                        existing_rs.xroad = rs.xroad
                        
                    updated_count += 1
                else:
                    skipped_count += 1
                    
        print(f"已更新 {updated_count} 条路线，跳过 {skipped_count} 条路线")
        
    def update_routes_from_schedule(self, phase_res: List[List[List[RouteSolution]]], res_schedule) -> None:
        """
        根据res_schedule修改phase_res中的到发时刻
        
        Args:
            phase_res: 三维列表 [阶段][方向][路线]，包含要更新的RouteSolution对象
            res_schedule: 算法求解结果，二维数据(r*q)
                r=4: 分别代表大小交路上下行 [大交路上行, 大交路下行, 小交路上行, 小交路下行]
                q: 代表每种类型的列车数量
        """
        self.print_phase3_res(phase_res)
        if res_schedule is None:
            print("警告：res_schedule为空，无法更新到发时刻")
            return
            
        updated_count = 0
        skipped_count = 0
        
        # 获取res_schedule的有效数据数量
        valid_count = 0
        if hasattr(res_schedule, 'shape'):
            # numpy数组情况
            valid_count = np.sum(~np.isnan(res_schedule))
            row_count, col_count = res_schedule.shape  # 比如：4行108列
            print(f"res_schedule形状: {res_schedule.shape}, 有效数据数量: {valid_count}")
        else:
            print(f"警告：无法识别的res_schedule类型: {type(res_schedule)}")
            return
        
        # 重新设计匹配逻辑：按phase_res的实际结构进行匹配
        # 首先收集所有正常折返列车（排除出入库车次）
        normal_trains = [[] for _ in range(4)]  # [大交路上行, 大交路下行, 小交路上行, 小交路下行]
        
        # 遍历phase_res，收集所有正常折返列车
        for phase_idx in range(len(phase_res)):
            for dir_idx in range(2):  # 0=上行, 1=下行
                for rs in phase_res[phase_idx][dir_idx]:
                    if rs is None:
                        continue
                        
                    # 判断是否为正常折返列车（非出入库车次）
                    # 出入库车次通常在phase_inout阶段添加，或者有特殊标识
                    # 这里假设正常折返列车有完整的停站序列和时刻表
                    if (hasattr(rs, 'dep_time') and rs.dep_time is not None and 
                        len(rs.dep_time) > 1 and hasattr(rs, 'xroad')):
                        
                        # 根据phase_res的结构确定交路类型
                        # dir_idx已经表示了方向：0=上行，1=下行
                        # rs.xroad表示交路类型：0=大交路，1=小交路
                        
                        route_type = -1
                        if rs.xroad == 0 and dir_idx == 0:  # 大交路上行
                            route_type = 0
                        elif rs.xroad == 0 and dir_idx == 1:  # 大交路下行
                            route_type = 1
                        elif rs.xroad == 1 and dir_idx == 0:  # 小交路上行
                            route_type = 2
                        elif rs.xroad == 1 and dir_idx == 1:  # 小交路下行
                            route_type = 3
                        
                        if route_type >= 0:
                            normal_trains[route_type].append((phase_idx, dir_idx, rs))
        
        # 打印各交路类型的匹配路线数量
        route_type_names = ["大交路上行", "大交路下行", "小交路上行", "小交路下行"]
        for i, trains in enumerate(normal_trains):
            print(f"{route_type_names[i]}匹配到 {len(trains)} 条正常折返路线")
        
        # 按发车时间对每种交路类型的列车进行排序
        for route_type in range(4):
            normal_trains[route_type].sort(key=lambda x: x[2].dep_time[0] if x[2].dep_time else 0)
        
        # 遍历res_schedule，更新各交路类型的时刻
        for row_idx in range(min(row_count, 4)):  # 确保不超过4种交路类型
            trains = normal_trains[row_idx]
            if not trains:
                continue
                
            # 获取该交路类型的所有有效车次数据
            valid_schedule_count = 0
            for col_idx in range(col_count):
                if not np.isnan(res_schedule[row_idx, col_idx]):
                    valid_schedule_count += 1
            
            print(f"{route_type_names[row_idx]}: res_schedule中有{valid_schedule_count}个有效时刻，phase_res中有{len(trains)}条路线")
            
            # 按顺序匹配：res_schedule的列索引对应排序后的列车
            schedule_idx = 0
            for col_idx in range(col_count):
                # 检查是否是有效数据且还有未匹配的列车
                if (not np.isnan(res_schedule[row_idx, col_idx]) and 
                    schedule_idx < len(trains)):
                    
                    # 获取对应的RouteSolution对象
                    phase_idx, dir_idx, rs = trains[schedule_idx]
                    
                    # 获取时刻值并取整
                    time_value = int(round(res_schedule[row_idx, col_idx]))
                    
                    # 更新到发车时刻（整条运行线）
                    if rs.dep_time is None:
                        rs.dep_time = [time_value]
                    else:
                        # 计算时间差值
                        time_diff = time_value - rs.dep_time[0]
                        # 如果有时间差，则整体平移运行线
                        if time_diff != 0:
                            # 平移所有到发时刻
                            for i in range(len(rs.dep_time)):
                                rs.dep_time[i] += time_diff
                            # 如果存在到达时刻数据，也需要平移
                            if rs.arr_time is not None:
                                for i in range(len(rs.arr_time)):
                                    rs.arr_time[i] += time_diff
                    
                    updated_count += 1
                    schedule_idx += 1
                elif not np.isnan(res_schedule[row_idx, col_idx]):
                    # 有有效数据但没有对应的列车
                    skipped_count += 1
        
        print(f"已根据res_schedule更新 {updated_count} 条路线，跳过 {skipped_count} 条路线")

    # def update_routes_from_schedule(self, phase_res: List[List[List[RouteSolution]]], res_schedule) -> None:
    #     """
    #     根据res_schedule修改phase1_res中的到发时刻
        
    #     Args:
    #         phase_res: 三维列表 [阶段][方向][路线]，包含要更新的RouteSolution对象
    #         res_schedule: 算法求解结果，二维数据(r*q)
    #             r=4: 分别代表大小交路上下行 [大交路上行, 大交路下行, 小交路上行, 小交路下行]
    #             q: 代表每种类型的列车数量
    #     """
    #     self.print_phase3_res(phase_res)
    #     if res_schedule is None:
    #         print("警告：res_schedule为空，无法更新到发时刻")
    #         return
            
    #     updated_count = 0
    #     skipped_count = 0
        
    #     # 获取res_schedule的有效数据数量
    #     valid_count = 0
    #     if hasattr(res_schedule, 'shape'):
    #         # numpy数组情况
    #         valid_count = np.sum(~np.isnan(res_schedule))
    #         row_count, col_count = res_schedule.shape#比如：4行108列
    #         print(f"res_schedule形状: {res_schedule.shape}, 有效数据数量: {valid_count}")
    #     else:
    #         print(f"警告：无法识别的res_schedule类型: {type(res_schedule)}")
    #         return
        
    #     #按这个顺序组织更新有问题，不匹配
    #     # 创建交路类型到方向的映射
    #     # 假设 res_schedule 的行索引对应为：
    #     # 0: 大交路上行
    #     # 1: 大交路下行
    #     # 2: 小交路上行
    #     # 3: 小交路下行
    #     route_type_mapping = {
    #         0: {'dir': 0, 'xroad': 0},  # 大交路上行
    #         1: {'dir': 1, 'xroad': 0},  # 大交路下行
    #         2: {'dir': 0, 'xroad': 1},  # 小交路上行
    #         3: {'dir': 1, 'xroad': 1}   # 小交路下行
    #     }
        
    #     # 为每种交路类型(大小交路上下行)创建匹配的RouteSolution对象列表
    #     matching_routes = [[] for _ in range(row_count)]
        
    #     # 遍历phase_res，将RouteSolution对象按照交路类型和方向分类
    #     for phase_idx in range(len(phase_res)):
    #         for dir_idx in range(2):  # 上下行
    #             for rs in phase_res[phase_idx][dir_idx]:
    #                 if rs is None:
    #                     continue
    #                 # 确定该rs属于哪个交路类型
    #                 # 遍历所有RouteSolution对象，根据其xroad和dir属性将其分类到对应的交路类型
    #                 #由于phase_res中很多值没有rs.dir属性，很多值rs.dir=-1，所以这样划分有问题
    #                 route_type = -1
    #                 if hasattr(rs, 'xroad') and hasattr(rs, 'dir'):
    #                     if rs.xroad == 0 and rs.dir == 0:  # 大交路上行
    #                         route_type = 0
    #                     elif rs.xroad == 0 and rs.dir == 1:  # 大交路下行
    #                         route_type = 1
    #                     elif rs.xroad == 1 and rs.dir == 0:  # 小交路上行
    #                         route_type = 2
    #                     elif rs.xroad == 1 and rs.dir == 1:  # 小交路下行
    #                         route_type = 3
                    
    #                 if route_type >= 0 and route_type < row_count:
    #                     matching_routes[route_type].append((phase_idx, dir_idx, rs))#这里把原始基于规则的结果phase_res分类存到matching_routes中
        
    #     # 打印各交路类型的匹配路线数量
    #     for i, routes in enumerate(matching_routes):
    #         route_type_name = ["大交路上行", "大交路下行", "小交路上行", "小交路下行"][i]
    #         print(f"{route_type_name}匹配到 {len(routes)} 条路线")
        
    #     # 遍历res_schedule，更新各交路类型的时刻
    #     for row_idx in range(row_count):#遍历0-3："大交路上行", "大交路下行", "小交路上行", "小交路下行"
    #         routes = matching_routes[row_idx]
    #         if not routes:
    #             continue
                
    #         # 获取该交路类型的所有有效车次数据
    #         for col_idx in range(col_count):
    #             # 检查是否是有效数据
    #             if col_idx < len(routes) and col_idx < col_count and not np.isnan(res_schedule[row_idx, col_idx]):
    #                 # 获取对应的RouteSolution对象
    #                 phase_idx, dir_idx, rs = routes[col_idx]
                    
    #                 # 获取时刻值并取整
    #                 time_value = int(round(res_schedule[row_idx, col_idx]))
                    
    #                 # 更新到发车时刻（整条线），
    #                 # 但是rs代表的是一条完整运行线，dep_time是一个列表
    #                 # 简单的直接替换始发站的值不行，需要根据始发站的差值(time_value和rs.dep_time[0])整体平移这根运行线
    #                 if rs.dep_time is None:
    #                     rs.dep_time = [time_value]
    #                 else:
    #                     # 计算时间差值
    #                     time_diff = time_value - rs.dep_time[0]
    #                     # 如果有时间差，则整体平移运行线
    #                     if time_diff != 0:
    #                         # 平移所有到发时刻
    #                         for i in range(len(rs.dep_time)):
    #                             rs.dep_time[i] += time_diff
    #                         # 如果存在到达时刻数据，也需要平移
    #                         if rs.arr_time is not None:
    #                             for i in range(len(rs.arr_time)):
    #                                 rs.arr_time[i] += time_diff
                    
    #                 updated_count += 1
    #             else:
    #                 skipped_count += 1
        
    #     print(f"已根据res_schedule更新 {updated_count} 条路线，跳过 {skipped_count} 条路线")

    def comput_send_time_replace(self, replace_road: str, original_road: str, end_time: int, 
                            level: int, xroad: int, rs: RouteSolution) -> int:
        """
        计算替换路径时的新发车时间
        
        这个辅助函数用于计算当路径被替换时，列车的新发车时间。
        它通过查找原始路径和新路径的交汇点，然后从该点向前推算时间。
        
        Args:
            replace_road: 替换路径ID
            original_road: 原始路径ID
            end_time: 结束时间
            level: 速度等级
            xroad: 交路索引
            rs: 原始运行方案
            
        Returns:
            计算得到的新发车时间
        """
        ori_path = self.rl.pathList[original_road]
        new_path = self.rl.pathList[replace_road]
        
        # 首先找到碰撞站点
        exit_stop = ""
        exit_indx = -1
        for i in range(len(new_path.nodeList)):
            if new_path.nodeList[i] in ori_path.nodeList:
                exit_stop = new_path.nodeList[i]
                exit_indx = i
                break
        
        old_dep = 0
        cur_plt = ""
        for i in range(len(rs.stopped_platforms)):
            if exit_stop == rs.stopped_platforms[i]:
                old_dep = rs.arr_time[i]
                cur_plt = rs.stopped_platforms[i]
                break
        
        for i in range(exit_indx - 1, -1, -1):
            tar_plt = new_path.nodeList[i]
            tar_platform = self.rl.platformList[tar_plt]
            travel_time = self.rl.getTravelInterval(tar_plt, cur_plt, util.ps(level))
            old_dep -= travel_time
            
            # 检查是否需要停站
            if old_dep - tar_platform.def_dwell_time < self.us.first_car:
                # 需要减少停站
                old_dep = min(self.us.first_car, old_dep)
            elif i != 0:
                # 停站
                old_dep -= tar_platform.def_dwell_time
            
            cur_plt = tar_plt
        
        return old_dep    

    def compute_send_time(self, connect_road: List[str], end_time: int, level: int, stop: bool) -> int:
        """
        计算保持结束时间不变的情况下，列车的实际发车时间
        
        Args:
            connect_road: 连接路径列表
            end_time: 结束时间
            level: 速度等级
            stop: 是否停站
            
        Returns:
            计算得到的发车时间
        """
        elapsed_time = 0
        
        for rd in connect_road:
            new_path = self.rl.pathList[rd]
            for i in range(len(new_path.nodeList) - 1):
                elapsed_time += self.rl.getTravelInterval(
                    new_path.nodeList[i], 
                    new_path.nodeList[i + 1], 
                    util.ps(level)
                )
                if stop:
                    elapsed_time += self.rl.platformList[new_path.nodeList[i]].def_dwell_time
            
            final_plat = self.rl.platformList[new_path.nodeList[-1]]
            if final_plat.platform_type == PlatformType.TURNBACK:
                tb = self.rl.turnbackList[final_plat.dest_code]
                elapsed_time += tb.min_tb_time
        
        return end_time - elapsed_time

    def restore_dwell_out(self, rs_new: RouteSolution, rs_ori: RouteSolution) -> RouteSolution:
        """
        对于每辆出站车辆，如果是替换类型，我们需要同步它们的停站时间
        
        Args:
            rs_new: 新的运行方案
            rs_ori: 原始运行方案
            
        Returns:
            同步停站时间后的运行方案
        """
        # 我们需要同步停站时间
        # 1. 找到两条路径的汇合点
        tar_idx_new = -1
        tar_idx_ori = -1
        for i in range(len(rs_new.arr_time)):
            for j in range(len(rs_ori.arr_time)):
                if rs_new.stopped_platforms[i] == rs_ori.stopped_platforms[j]:
                    tar_idx_new = i
                    tar_idx_ori = j
                    break
            if tar_idx_new > 0:
                break
        
        # 如果没有找到任何交叉点，直接返回
        if tar_idx_new < 0:
            return rs_new
        
        # 否则，同步停站时间
        # 当我们仍然有交叉节点时，我们直接从原始rs复制粘贴arr/dep时间
        while (tar_idx_new < len(rs_new.arr_time) and 
            tar_idx_ori < len(rs_ori.arr_time) and 
            rs_new.stopped_platforms[tar_idx_new] == rs_ori.stopped_platforms[tar_idx_ori]):
            rs_new.arr_time[tar_idx_new] = rs_ori.arr_time[tar_idx_ori]
            rs_new.dep_time[tar_idx_new] = rs_ori.dep_time[tar_idx_ori]
            tar_idx_new += 1
            tar_idx_ori += 1
        
        return rs_new

    def resend_car_at_time(self, rdy_car: CarInfo, send_time: int, xroad: int, up_down: int, 
                        peak_idx: int, level: int, in_out: int, rs_ori: RouteSolution) -> RouteSolution:
        """
        根据给定的列车计划，使用不同的路线重新发送列车，同时保持发送时间不变
        
        Args:
            rdy_car: 准备发送的车辆信息
            send_time: 发送时间
            xroad: 交路索引
            up_down: 上行/下行方向 (0=上行, 1=下行)
            peak_idx: 峰期索引
            level: 速度等级
            in_out: 进出站标志 (0=进站, 1=出站, -1=无操作)
            rs_ori: 原始运行方案
            
        Returns:
            新生成的运行方案
        """
        # print("====================resend_car_at_time过程中打印数据=============")  
        self.rl.check_conflict = False
        
        route = util.ps(rs_ori.car_info.route_num)
        rdy_car.route_num = int(route)
        dealing_road = 2 * xroad + up_down
        
        # 根据不同情况生成运行方案
        if in_out < 0:
            rs = self.rl.getHeuristicSolFromPath1(route, send_time, level, 30, 0, rdy_car)
        else:
            if self.debug:
                util.pf("in out: " + util.ps(in_out) + "  up_down: " + util.ps(up_down))
            
            deopt_route_type = self.us.depot_routes_infos[xroad].routeType[in_out][up_down]
            deopt_route_route = self.us.depot_routes_infos[xroad].routes[in_out][up_down]
            rs = self.rl.getHeuristicSolFromPath2(deopt_route_type, deopt_route_route, route, 
                                            send_time, level, 30, self.us.first_car, rdy_car, in_out)
            
            # 由于停站时间可能不同，我们需要同步
            # 首先需要找到汇合点
            if in_out == 1:
                # 这是出站车辆
                rs = self.restore_dwell_out(rs, rs_ori)
        
        # 设置终点站和到达时间
        terminal_station = self.rl.pathList[route].nodeList[-1]
        rdy_car.target_platform = terminal_station
        arr_time_of_car1 = rs.dep_time[-1]
        rdy_car.arr_time = arr_time_of_car1
        rs.car_info = rdy_car
        
        # 调试信息输出
        if self.debug:
            util.pf(util.ANSI_GREEN + util.ps(rs.car_info.route_num))
            util.pf(util.ANSI_BLUE + "Sent car with transistor " + util.ps(rdy_car.round_num) + 
                " at " + util.timeFromIntSec(send_time) + " for direction " + util.ps(dealing_road))
        
        self.rl.check_conflict = True
        rs.xroad = xroad
        
        return rs

    def compute_send_time_in_replace(self, rs: RouteSolution, level: int) -> int:
        """
        计算入库替换时的发送时间
        
        Args:
            rs: 运行方案
            level: 速度等级
            
        Returns:
            计算得到的发送时间
        """
        return rs.arr_time[0]
    
    def compute_send_time_in_connect(self, rs: RouteSolution) -> int:
        """
        根据给定的列车计划，计算连接到新路径时的发送时间
        
        Args:
            rs: 运行方案
            
        Returns:
            计算得到的发送时间
        """
        base_time = rs.dep_time[-1]
        
        # 检查是否需要折返时间
        final_plat = self.rl.platformList[rs.stopped_platforms[-1]]
        if final_plat.platform_type == PlatformType.TURNBACK:
            tb = self.rl.turnbackList[final_plat.dest_code]
            base_time += tb.min_tb_time
        
        return base_time

    def handle_in(self, speed_level_: int, stop_time: int, time_early: int, cinfo: CarInfo, 
             direction: int, peak_idx: int, xroad: int, rs: RouteSolution) -> List[RouteSolution]:
        """
        处理列车入库（进入车库）的逻辑
        
        这个方法会根据车库设置 (us.depot_infos) 中定义的出入库类型（"Replace" 或 "Connect"）和路径，
        以及从 phase_reopt_inout 获取的调整量 (modified_in, modified_out)，来生成或修改 RouteSolution。
        "Replace" 类型：通常意味着出/入库路径会部分替换主线路径，原有的主线列车 RouteSolution 会被修改。
        "Connect" 类型：通常意味着会生成新的 RouteSolution 代表出入库的独立运行段，并将其与主线列车连接起来。
        
        Args:
            speed_level_: 速度等级
            stop_time: 停站时间
            time_early: 提前时间
            cinfo: 车辆信息对象
            direction: 方向（上行/下行）
            peak_idx: 峰期索引
            xroad: 交路索引
            rs: 原始运行方案
            
        Returns:
            生成的运行方案列表
        """
        # 如果是替换类型，需要重新发送；否则只需要发送更多
        rs_cn = rs.car_info.round_num
        in_out = 0
        deopt_route_type = self.us.depot_routes_infos[xroad].routeType[in_out][direction]
        deopt_route_route = list(self.us.depot_routes_infos[xroad].routes[in_out][direction])
        
        tmp_rs = None
        res = []
        
        # 根据不同类型处理
        # Replace类型：简单地更改RouteSolution
        if deopt_route_type == "Replace":
            new_send_time = self.compute_send_time_in_replace(rs, speed_level_)#返回替换情况下的新发车时间
            # print("===== resend_car_at_time 输入参数 =====")
            # print(f"cinfo: {vars(cinfo)}")
            # print(f"new_send_time: {new_send_time}")
            # print(f"rs.xroad: {rs.xroad}")
            # print(f"direction: {direction}")
            # print(f"peak_idx: {peak_idx}")
            # print(f"speed_level_: {speed_level_}")
            # print(f"in_out: {in_out}")
            # print(f"rs: {vars(rs)}")
            # print("=================================")         
            # print("====================handle_in处理入库车时调用resend_car_at_time=============")       
            tmp_rs = self.resend_car_at_time(cinfo, new_send_time, rs.xroad, direction, 
                                            peak_idx, speed_level_, in_out, rs)
            # print("===== 调试信息 =====")
            # print(f"tmp_rs类型: {type(tmp_rs)}")
            # print(f"tmp_rs内容: {vars(tmp_rs)}")
            # print(f"tmp_rs.car_info类型: {type(tmp_rs.car_info)}")
            # print(f"tmp_rs.car_info内容: {vars(tmp_rs.car_info)}")
            # print(f"tmp_rs.car_info.helper_indx: {tmp_rs.car_info.helper_indx}")
            # print("===================")

            next_arrival_car = tmp_rs.car_info
            self.rl.depot_cars[next_arrival_car.helper_indx].append(tmp_rs.car_info)
            res.append(tmp_rs)
        else:
            # 否则为Connect类型
            res.append(rs)
            rs_ptr = rs
            quant = 1
            send_time = cinfo.arr_time
            # cinfo1 = CarInfo(cinfo)
            cinfo1 = CarInfo.from_car_info(cinfo)
            # if self.debug:
            if True:
                util.pf(util.ANSI_BLUE_BACKGROUND + " n connect rounds: " + 
                    util.ps(len(deopt_route_route)) + "      -----  " + util.ps(cinfo1.round_num))
            
            while len(deopt_route_route) > 0:
                send_time = self.compute_send_time_in_connect(rs_ptr)#返回连接情况下的新发车时间
                
                if rs_cn in self.modified_in:
                    # 已经修改过
                    sz = len(deopt_route_route)
                    modified_in_this = self.modified_in[rs_cn]
                    for k in range(len(modified_in_this) - sz, len(modified_in_this)):
                        send_time -= modified_in_this[k]
                        # if self.debug:
                        if True:
                            util.pf(util.ANSI_RED + "Modified route: " + str(rs_cn) + 
                                " out rt with time: " + str(modified_in_this[k]))
                
                cinfo1.modify_round(quant)
                quant += 1
                tar_route = deopt_route_route[0]
                deopt_route_route.pop(0)
                tmp_rs = self.rl.getHeuristicSolFromPath1(tar_route, send_time, speed_level_, 
                                                        stop_time, 28*3600, cinfo1)
                tmp_rs.car_info.route_num = int(tar_route)
                # self.rl.addRoute(tmp_rs)
                # cinfo1 = CarInfo(cinfo1)
                cinfo1 = CarInfo.from_car_info(cinfo)
                res.append(tmp_rs)
                rs_ptr = tmp_rs
            
            # cinfo2 = CarInfo(cinfo)
            cinfo2 = CarInfo.from_car_info(cinfo)

            cinfo2.modify_round(quant-1)
            helper_indx = 0 if cinfo2.helper_indx is None else cinfo2.helper_indx
            if helper_indx is not None and 0 <= helper_indx < len(self.rl.depot_cars):
                self.rl.depot_cars[helper_indx].append(cinfo2)
            else:
                print(f"警告: 车库索引 {helper_indx} 超出范围，最大索引为 {len(self.rl.depot_cars)-1 if len(self.rl.depot_cars) > 0 else '无'}")
                # 可以选择使用默认索引或跳过此操作
        
        return res

    def print_depot_routes_infos(self):
        """
        打印用户设置中的所有车库路线信息
        """
        print("========== depot_routes_infos 详细内容 ==========")
        print(f"车库路线信息总数: {len(self.us.depot_routes_infos)}")
        
        for idx, depot_info in enumerate(self.us.depot_routes_infos):
            print(f"\n=== 车库路线 {idx} ===")
            
            # 打印路线类型信息
            print("路线类型 (routeType):")
            for in_out in range(2):
                in_out_str = "出库" if in_out == 0 else "入库"
                print(f"  {in_out_str}:")
                for dir in range(2):
                    dir_str = "上行" if dir == 0 else "下行"
                    print(f"    {dir_str}: {depot_info.routeType[in_out][dir]}")
            
            # 打印路线信息
            print("\n路线 (routes):")
            for in_out in range(2):
                in_out_str = "出库" if in_out == 0 else "入库"
                print(f"  {in_out_str}:")
                for dir in range(2):
                    dir_str = "上行" if dir == 0 else "下行"
                    print(f"    {dir_str}: {depot_info.routes[in_out][dir]}")
            
            # 打印路线时间信息
            print("\n路线时间 (routes_time):")
            for in_out in range(2):
                in_out_str = "出库" if in_out == 0 else "入库"
                print(f"  {in_out_str}:")
                for dir in range(2):
                    dir_str = "上行" if dir == 0 else "下行"
                    print(f"    {dir_str}: {depot_info.routes_time[in_out][dir]}")
        
        print("\n========== depot_routes_infos 打印完成 ==========")

    def handle_out(self, path_id_: str, current_time: int, speed_level_: int, stop_time: int, 
                time_early: int, cinfo: CarInfo, direction: int, xroad: int, 
                rs: RouteSolution) -> List[RouteSolution]:
        """
        处理列车从车库出发的逻辑
        
        Args:
            path_id_: 路径ID
            current_time: 当前时间
            speed_level_: 速度等级
            stop_time: 停站时间
            time_early: 提前时间
            cinfo: 车辆信息对象
            direction: 方向（上行/下行）
            xroad: 交路索引
            rs: 原始运行方案
            
        Returns:
            生成的运行方案列表
        """
        rs_cn = rs.car_info.round_num
        res = []
        in_out = 1 #定义为出库
        # print("打印depot_routes_infos内容：")
        # self.print_depot_routes_infos()
        deopt_route_type = self.us.depot_routes_infos[xroad].routeType[in_out][direction]
        deopt_route_route = list(self.us.depot_routes_infos[xroad].routes[in_out][direction])
        # print(f"direction={direction}")
        # print(f"deopt_route_type={deopt_route_type}")
        # print(f"deopt_route_route={deopt_route_route}")
        
        # 对于替换类型，我们直接重新发送这辆车并返回，如果是Replace就是直接把这趟车的发车时间往前改，比如-30
        if deopt_route_type == "Replace":
            self.rl.check_conflict = False
            cinfo.route_num = int(deopt_route_route[0])
            new_send_time = self.comput_send_time_replace(deopt_route_route[0], path_id_, 
                                                        current_time, speed_level_, xroad, rs)
            # print("=====出库处理中： resend_car_at_time 输入参数 =====")
            # print(f"cinfo: {vars(cinfo)}")
            # print(f"new_send_time: {new_send_time}")
            # print(f"rs.xroad: {rs.xroad}")
            # print(f"direction: {direction}")
            # print(f"speed_level_: {speed_level_}")
            # print(f"in_out: {in_out}")
            # print(f"rs: {vars(rs)}")
            # print("=================================")    
            # print("====================handle_out处理出库车时调用resend_car_at_time=============")                                               
            rs_new = self.resend_car_at_time(cinfo, new_send_time, rs.xroad, direction, 
                                            0, speed_level_, in_out, rs)
            # print("===== resend_car_at_time的返回结果 =====")
            # print(f"rs_new类型: {type(rs_new)}")
            # print(f"rs_new内容: {vars(rs_new)}")
            # print(f"rs_new.car_info类型: {type(rs_new.car_info)}")
            # print(f"rs_new.car_info内容: {vars(rs_new.car_info)}")
            # print(f"rs_new.car_info.helper_indx: {rs_new.car_info.helper_indx}")
            print("===================")
            # 由于停站时间可能不同，我们需要同步
            # 首先需要找到汇合点
            res.append(rs_new)
            self.rl.check_conflict = True
            return res
        
        # 连接类型("Connect") ：
        # // - 添加一个 null 作为占位符
        # // - 循环处理每段出库路线
        # // - 计算每段路线的发车时间( compute_send_time )
        # // - 应用时间修改(如果 modified_out 中有相应修改)
        # // - 为每段路线创建新的 RouteSolution 并添加到结果列表
        act_start = rs.arr_time[0]
        res.append(None)  #这里添加空值是否正确？
        quant = 0
        while deopt_route_route:
            # print("deopt_route_route有值，成功进入while循环")
            quant += 1
            # cinfo1 = CarInfo(cinfo)  #对象克隆
            cinfo1 = CarInfo.from_car_info(cinfo)
            cinfo1.modify_round(quant)
            send_time = self.compute_send_time(deopt_route_route, act_start, speed_level_, False)
            # 如果我们已经修改了时间，需要更改它
            if rs_cn in self.modified_out:
                # 我们已经修改过它
                modified_out_this = self.modified_out[rs_cn]
                for k in range(len(modified_out_this)):
                    send_time -= modified_out_this[k]
                    if self.debug:
                        util.pf(util.ANSI_RED + "Modified route: " + str(rs_cn) + 
                            " out rt with time: " + str(modified_out_this[k]))
            
            tar_route = deopt_route_route[0]
            deopt_route_route.pop(0)
            tmp_rs = self.rl.getHeuristicSolFromPath1(tar_route, send_time, speed_level_, 
                                                    stop_time, 28*3600, cinfo1)
            tmp_rs.car_info.route_num = int(tar_route)
            # self.rl.addRoute(tmp_rs)
            res.append(tmp_rs)
        
        return res

    def combine_rs(self, rs: RouteSolution, rs_new: RouteSolution) -> RouteSolution:
        """
        合并两个路线方案
        这个方法用于处理收集和发送车辆的情况，如果两个路线方案共享相同的终点，则直接返回新的路线方案
        
        Args:
            rs: 原始路线方案
            rs_new: 新的路线方案
            
        Returns:
            合并后的路线方案
        """
        n_rs = len(rs.stopped_platforms)
        # 添加空值检查
        if rs_new is None:
            # 可以返回原始的rss或者进行其他处理
            print("报错：combine_rs函数的输入参数rs_new is None,故返回空值")
            return rs_new
        n_rsnew = len(rs_new.stopped_platforms)
        
        # 如果两个路线方案共享相同的终点，直接返回新的路线方案
        if rs.stopped_platforms[n_rs-1] == rs_new.stopped_platforms[n_rsnew-1]:
            # 这两个共享相同的终点，直接替换
            return rs_new
        
        rsn_ptr = 0
        rs_ptr = 0
        
        # 寻找汇合点
        for rsn_ptr in range(n_rsnew):
            found = False
            for rs_ptr in range(n_rs):
                # 找到汇合点
                if rs.stopped_platforms[rs_ptr] == rs_new.stopped_platforms[rsn_ptr]:
                    found = True
                    break
            if found:
                break
        
        # 移除不相交的停靠站
        for i in range(rs_ptr):
            rs.stopped_platforms.pop(0)
            rs.arr_time.pop(0)
            rs.dep_time.pop(0)
            rs.performance_levels.pop(0)
        
        # 添加原始方案中没有的新停靠站
        for i in range(rsn_ptr - 1, -1, -1):
            rs.stopped_platforms.insert(0, rs_new.stopped_platforms[i])
            rs.arr_time.insert(0, rs_new.arr_time[i])
            rs.dep_time.insert(0, rs_new.dep_time[i])
            rs.performance_levels.insert(0, rs_new.performance_levels[i])
        
        # 更新路线信息
        start_plt = rs.stopped_platforms[0]
        end_plt = rs.stopped_platforms[-1]
        pth = self.rl.find_path_by_start_end(start_plt, end_plt)
        rs.car_info.route_num = int(pth.id)
        
        return rs
    # 打印 rss 列表的详细内容
    def print_handle_in_results(self, rss):
        """
        打印handle_out函数返回的rss列表详细内容
        
        Args:
            rss: 包含RouteSolution对象的列表
        """
        print("========== handle_in 返回的 rss 列表详细内容 ==========")
        print(f"rss 列表大小: {len(rss)}")
        for j in range(len(rss)):
            rs = rss[j]
            print(f"列车 #{j}:")
            print(f"  交路类型: {'大交路' if rs.xroad == 0 else '小交路'}")
            print(f"  方向: {'上行' if rs.dir == 0 else '下行'}")
            print(f"  阶段: {rs.phase}")
            print(f"  到达时间列表: {rs.arr_time}")
            print(f"  出发时间列表: {rs.dep_time}")
            
            # 打印 CarInfo 对象详细信息
            car_info = rs.car_info
            if car_info is not None:
                print("  车辆信息:")
                print(f"    ID: {car_info.id}")
                print(f"    表号: {car_info.table_num}")
                print(f"    路线编号: {car_info.route_num}")
                print(f"    车次号: {car_info.round_num}")
                print(f"    到达时间: {car_info.arr_time}")
            
            print(f"  停靠站台数: {len(rs.stopped_platforms)}")
            print(f"  辅助标记: {rs.auxilary}")
            print(f"  前置指针: {'null' if rs.prev_ptr is None else '非null'}")
            print(f"  后置指针: {'null' if rs.next_ptr is None else '非null'}")
            print()
        print("========== 打印结束 ==========")  

    def print_connect_results(self, rss):
        """
        打印handle_out函数返回的rss列表详细内容
        
        Args:
            rss: 包含RouteSolution对象的列表
        """
        print("========== 递归调用connect_routes的 输入参数详细内容 ==========")
        print(f"rss 列表大小: {len(rss)}")
        for i, rs in enumerate(rss):
            print(f"列车 #{i}:")
            if rs is None:
                print("  [空值占位符]")
                continue
            print(f"  交路类型: {'大交路' if rs.xroad == 0 else '小交路'}")
            print(f"  方向: {'上行' if rs.dir == 0 else '下行'}")
            print(f"  阶段: {rs.phase}")
            print(f"  到达时间列表: {rs.arr_time}")
            print(f"  出发时间列表: {rs.dep_time}")
            
            # 打印 CarInfo 对象详细信息
            car_info = rs.car_info
            if car_info is not None:
                print("  车辆信息:")
                print(f"    ID: {car_info.id}")
                print(f"    表号: {car_info.table_num}")
                print(f"    路线编号: {car_info.route_num}")
                print(f"    车次号: {car_info.round_num}")
                print(f"    到达时间: {car_info.arr_time}")
            
            print(f"  停靠站台数: {len(rs.stopped_platforms)}")
            print(f"  辅助标记: {rs.auxilary}")
            print(f"  前置指针: {'null' if rs.prev_ptr is None else '非null'}")
            print(f"  后置指针: {'null' if rs.next_ptr is None else '非null'}")
            print()
        print("========== 打印结束 ==========")        
      
    # 打印 rss 列表的详细内容
    def print_handle_out_results(self, rss):
        """
        打印handle_out函数返回的rss列表详细内容
        
        Args:
            rss: 包含RouteSolution对象的列表
        """
        print("========== handle_out 返回的 rss 列表详细内容 ==========")
        print(f"rss 列表大小: {len(rss)}")
        for i, rs in enumerate(rss):
            print(f"列车 #{i}:")
            if rs is None:
                print("  [空值占位符]")
                continue
            print(f"  交路类型: {'大交路' if rs.xroad == 0 else '小交路'}")
            print(f"  方向: {'上行' if rs.dir == 0 else '下行'}")
            print(f"  阶段: {rs.phase}")
            print(f"  到达时间列表: {rs.arr_time}")
            print(f"  出发时间列表: {rs.dep_time}")
            
            # 打印 CarInfo 对象详细信息
            car_info = rs.car_info
            if car_info is not None:
                print("  车辆信息:")
                print(f"    ID: {car_info.id}")
                print(f"    表号: {car_info.table_num}")
                print(f"    路线编号: {car_info.route_num}")
                print(f"    车次号: {car_info.round_num}")
                print(f"    到达时间: {car_info.arr_time}")
            
            print(f"  停靠站台数: {len(rs.stopped_platforms)}")
            print(f"  辅助标记: {rs.auxilary}")
            print(f"  前置指针: {'null' if rs.prev_ptr is None else '非null'}")
            print(f"  后置指针: {'null' if rs.next_ptr is None else '非null'}")
            print()
        print("========== 打印结束 ==========")        

    def print_phase3_res(self, phase3_res: List[List[List[RouteSolution]]]) -> None:
        """
        打印phase3_res的详细内容，包括所有阶段、方向和列车信息
        
        Args:
            phase3_res: 第三阶段生成的列车运行方案
        """
        print("========== phase3_res 详细内容 ==========")
        print(f"阶段总数: {len(phase3_res)}")
        # 添加计数器
        total_rs_count = 0
        valid_rs_count = 0
        null_next_ptr_count = 0  # 统计next_ptr为null的数量
        null_prev_ptr_count = 0  # 统计prev_ptr为null的数量
        # 遍历所有阶段
        for phase_idx, phase in enumerate(phase3_res):
            print(f"\n=== 阶段 {phase_idx} ===")
            phase_rs_count = 0
            # 遍历方向（上行/下行）
            for dir_idx, direction in enumerate(phase):
                dir_name = "上行" if dir_idx == 0 else "下行"
                print(f"\n--- {dir_name}方向 (共{len(direction)}辆列车) ---")
                total_rs_count += len(direction)
                # 遍历该方向的所有列车
                for train_idx, rs in enumerate(direction):
                    # print(f"\n列车 #{train_idx}:")
                    if rs is None:
                        print("  [空值]")
                        continue
                    valid_rs_count += 1
                    phase_rs_count += 1
                    # 统计next_ptr为null的情况
                    if not hasattr(rs, 'next_ptr') or rs.next_ptr is None:
                        null_next_ptr_count += 1
                    # 统计prev_ptr为null的情况
                    if not hasattr(rs, 'prev_ptr') or rs.prev_ptr is None:
                        null_prev_ptr_count += 1
                    # # 打印基本属性
                    # print(f"  阶段: {rs.phase}")
                    # print(f"  phase3_res中rs.dir: {rs.dir}")
                    # print(f"  方向: {dir_idx} ({'上行' if rs.dir == 0 else '下行' if rs.dir == 1 else '未设置'})")
                    # print(f"  交路类型: {'大交路' if rs.xroad == 0 else '小交路' if rs.xroad == 1 else '未设置'}")
                    
                    # # 打印车辆信息
                    # if rs.car_info is not None:
                    #     print(f"  车辆信息:")
                    #     print(f"    车次编号: {rs.car_info.table_num}")
                    #     print(f"    车轮编号: {rs.car_info.round_num}")
                    #     print(f"    路线编号: {rs.car_info.route_num}")
                    #     print(f"    ID: {rs.car_info.id if hasattr(rs.car_info, 'id') else 'N/A'}")
                    # else:
                    #     print(f"  车辆信息: None")
                    
                    # # 打印时间和站台信息
                    # if hasattr(rs, 'arr_time') and rs.arr_time:
                    #     print(f"  到站时间: {[util.timeFromIntSec(t) if t is not None else 'None' for t in rs.arr_time]}")
                    # if hasattr(rs, 'dep_time') and rs.dep_time:
                    #     print(f"  发车时间: {[util.timeFromIntSec(t) if t is not None else 'None' for t in rs.dep_time]}")
                    # if hasattr(rs, 'stopped_time') and rs.stopped_time:
                    #     print(f"  停站时间: {rs.stopped_time}")
                    # if hasattr(rs, 'stopped_platforms') and rs.stopped_platforms:
                    #     print(f"  停靠站台: {rs.stopped_platforms}")
                    # if hasattr(rs, 'performance_levels') and rs.performance_levels:
                    #     print(f"  性能等级: {rs.performance_levels}")
                    
                    # # 打印前后车信息
                    # if hasattr(rs, 'prev_ptr'):
                    #     print(f"  前序车: {rs.prev_ptr.car_info.round_num if rs.prev_ptr and hasattr(rs.prev_ptr, 'car_info') else 'None'}")
                    # if hasattr(rs, 'next_ptr'):
                    #     print(f"  后续车: {rs.next_ptr.car_info.round_num if rs.next_ptr and hasattr(rs.next_ptr, 'car_info') else 'None'}")
            print(f"本阶段有效RouteSolution对象数量: {phase_rs_count}")
            print("\n========== RouteSolution对象统计 ==========")
        print(f"总计划列车数量: {total_rs_count}")
        print(f"有效RouteSolution对象数量: {valid_rs_count}")
        print(f"空值(None)数量: {total_rs_count - valid_rs_count}")
        print("\n========== 指针统计 ==========")
        print(f"next_ptr为null的数量: {null_next_ptr_count}")
        print(f"prev_ptr为null的数量: {null_prev_ptr_count}")
        print("\n========== phase3_res 打印完成 ==========")

    def print_window_stat_null_pointers(self,window_stat):
        print("\n=== window_stat 空指针统计 ===")
        if window_stat is None:
            print("window_stat 为空值")
            return
            
        null_next_count = 0
        null_prev_count = 0
        null_rs_count = 0
        
        for rs in window_stat:
            if rs is None:
                null_rs_count += 1
                continue
                
            if rs.next_ptr is None:
                null_next_count += 1
            if rs.prev_ptr is None:
                null_prev_count += 1
        
        print(f"RouteSolution 为空的数量: {null_rs_count}")
        print(f"next_ptr 为空的数量: {null_next_count}")
        print(f"prev_ptr 为空的数量: {null_prev_count}")

    def phase_inout(self, phase3_res: List[List[List[RouteSolution]]]) -> List[List[List[RouteSolution]]]:
        """
        这是实际添加或修改出入库路径的核心方法。它遍历所有列车：
        对于没有后序连接的列车（末车），调用 handle_in 处理入库。
        对于没有前序连接的列车（首车），调用 handle_out 处理出库。
        
        Args:
            phase3_res: 第三阶段生成的列车运行方案
            
        Returns:
            添加了出入库路径的列车运行线结果
        """
        # 打印phase3_res的详细内容
        # self.print_phase3_res(phase3_res)
        # 遍历所有车辆
        for t_index in range(len(phase3_res)):#阶段遍历
            for dir in range(2):#方向遍历
                to_add = []  #待加入的车次（新的出入库线）
                window_stat = phase3_res[t_index][dir]
                self.print_window_stat_null_pointers(window_stat)
                # print(f"window_stat的长度={len(window_stat)}")
                # # # 修复phase3_res中的dir属性
                # # for i in range(len(window_stat)):
                # #     if window_stat[i] is not None and window_stat[i].dir != dir:
                # #         # 修复dir属性
                # #         print(f"修复列车 #{i} 的dir属性，从 {window_stat[i].dir} 改为 {dir}")
                # #         window_stat[i].dir = dir

                # # # 打印window_stat的详细内容
                # print(f"===== window_stat[{dir}][{t_index}] 详细内容 =====")
                # for i, rs in enumerate(window_stat):
                #     print(f"列车 #{i}:")
                #     if rs is None:
                #         print("window_stat中有  [空值]")
                #         continue
                    
                #     # 打印RouteSolution的基本属性
                #     print(f"  阶段: {rs.phase}")
                #     print(f"  方向: {'上行' if rs.dir == 0 else '下行'}")
                #     print(f"  rs.dir: {rs.dir}")
                #     print(f"  交路类型: {'大交路' if rs.xroad == 0 else '小交路'}")
                    
                #     # 打印CarInfo的详细信息
                #     if rs.car_info is not None:
                #         print(f"  车辆信息:")
                #         print(f"    车次编号: {rs.car_info.table_num}")
                #         print(f"    车轮编号: {rs.car_info.round_num}")
                #         print(f"    路线编号: {rs.car_info.route_num}")
                #         print(f"    ID: {rs.car_info.id if hasattr(rs.car_info, 'id') else 'N/A'}")
                #     else:
                #         print(f"  车辆信息: None")
                    
                #     # 打印时间和站台信息
                #     if hasattr(rs, 'arr_time') and rs.arr_time:
                #         print(f"  到站时间: {[util.timeFromIntSec(t) if t is not None else 'None' for t in rs.arr_time]}")
                #     if hasattr(rs, 'dep_time') and rs.dep_time:
                #         print(f"  发车时间: {[util.timeFromIntSec(t) if t is not None else 'None' for t in rs.dep_time]}")
                #     if hasattr(rs, 'stopped_time') and rs.stopped_time:
                #         print(f"  停站时间: {rs.stopped_time}")
                #     if hasattr(rs, 'stopped_platforms') and rs.stopped_platforms:
                #         print(f"  停靠站台: {rs.stopped_platforms}")
                #     if hasattr(rs, 'performance_levels') and rs.performance_levels:
                #         print(f"  性能等级: {rs.performance_levels}")
                    
                #     # 打印前后车信息
                #     print(f"  前序车: {rs.prev_ptr.car_info.round_num if rs.prev_ptr and rs.prev_ptr.car_info else 'None'}")
                #     print(f"  后续车: {rs.next_ptr.car_info.round_num if rs.next_ptr and rs.next_ptr.car_info else 'None'}")
                # print("================================")
                
                i = 0
                print(f"len(window_stat) = {len(window_stat)}")
                while i < len(window_stat): #单个阶段内单方向遍历  循环次数来自于这里
                    if window_stat[i] is None:
                        i += 1
                        continue

                    # 处理没有后序连接的列车（末车）- 需要入库
                    if window_stat[i].next_ptr is None:
                        # 打印 handle_in 函数的所有输入参数
                        # print("===== handle_in 函数输入参数 =====")
                        # print(f"speed_level: {self.level}")
                        # print(f"stop_time: {30}")
                        # print(f"time_early: {0}")
                        # print(f"car_info: {window_stat[i].car_info}")
                        # if window_stat[i].car_info is not None:
                        #     print(f"  car_info.table_num: {window_stat[i].car_info.table_num}")
                        #     print(f"  car_info.route_num: {window_stat[i].car_info.route_num}")
                        #     print(f"  car_info.round_num: {window_stat[i].car_info.round_num}")
                        # print(f"direction: {dir}")
                        # print(f"peak_idx: {0}")
                        # print(f"xroad: {window_stat[i].xroad}")
                        # print(f"rs: {window_stat[i]}")
                        # if window_stat[i] is not None:
                        #     print(f"  rs.phase: {window_stat[i].phase}")
                        #     print(f"  rs.dir: {window_stat[i].dir}")
                        #     print(f"  rs.xroad: {window_stat[i].xroad}")
                        #     if hasattr(window_stat[i], 'stopped_platforms') and window_stat[i].stopped_platforms:
                        #         print(f"  rs.stopped_platforms: {window_stat[i].stopped_platforms}")
                        #     if hasattr(window_stat[i], 'arr_time') and window_stat[i].arr_time:
                        #         print(f"  rs.arr_time: {window_stat[i].arr_time}")
                        #     if hasattr(window_stat[i], 'dep_time') and window_stat[i].dep_time:
                        #         print(f"  rs.dep_time: {window_stat[i].dep_time}")
                        #     print(f"  前置指针: {'null' if window_stat[i].prev_ptr is None else '非null'}")
                        #     print(f"  后置指针: {'null' if window_stat[i].next_ptr is None else '非null'}")
                        # print("================================")
                        
                        rss = self.handle_in(self.level, 30, 0, window_stat[i].car_info, 
                                            dir, 0, window_stat[i].xroad, window_stat[i])
                        # self.print_handle_in_results(rss)
                        if len(rss) == 1:
                            # 替换Replace
                            rss[0].prev_ptr = window_stat[i].prev_ptr
                            if window_stat[i].prev_ptr is not None:
                                window_stat[i].prev_ptr.next_ptr = rss[0]
                            window_stat[i] = rss[0]
                        else:
                            # 连接Connect
                            print(f"入库的rss.size ={len(rss)} ")
                            rs_ptr = window_stat[i]
                            for r_idx in range(1, len(rss)):
                                rs_ptr.next_ptr = rss[r_idx]
                                rss[r_idx].prev_ptr = rs_ptr
                                to_add.append(rss[r_idx])
                                rs_ptr = rss[r_idx]
                    
                    # 处理没有前序连接的列车（首车）- 需要出库
                    if window_stat[i].prev_ptr is None:
                        ori_rs = window_stat[i]
                        route = util.ps(ori_rs.car_info.route_num)
                        # 打印 handle_out 函数的所有输入参数
                        # print("===== handle_out 函数输入参数 =====")
                        # print(f"route: {route}")
                        # print(f"current_time: {ori_rs.arr_time[0]}")
                        # print(f"speed_level: {self.level}")
                        # print(f"stop_time: {30}")
                        # print(f"time_early: {0}")
                        # print(f"car_info: {ori_rs.car_info}")
                        # if ori_rs.car_info is not None:
                        #     print(f"  car_info.table_num: {ori_rs.car_info.table_num}")
                        #     print(f"  car_info.route_num: {ori_rs.car_info.route_num}")
                        #     print(f"  car_info.round_num: {ori_rs.car_info.round_num}")
                        # print(f"direction: {dir}")
                        # print(f"xroad: {ori_rs.xroad}")
                        # print(f"rs: {ori_rs}")
                        # if ori_rs is not None:
                        #     print(f"  rs.phase: {ori_rs.phase}")
                        #     print(f"  rs.dir: {ori_rs.dir}")
                        #     print(f"  rs.xroad: {ori_rs.xroad}")
                        #     if hasattr(ori_rs, 'stopped_platforms') and ori_rs.stopped_platforms:
                        #         print(f"  rs.stopped_platforms: {ori_rs.stopped_platforms}")
                        #     if hasattr(ori_rs, 'arr_time') and ori_rs.arr_time:
                        #         print(f"  rs.arr_time: {ori_rs.arr_time}")
                        #     if hasattr(ori_rs, 'dep_time') and ori_rs.dep_time:
                        #         print(f"  rs.dep_time: {ori_rs.dep_time}")
                        #     if hasattr(ori_rs, 'stopped_time') and ori_rs.stopped_time:
                        #         print(f"  rs.stopped_time: {ori_rs.stopped_time}")
                        # print("================================")
                        
                        rss = self.handle_out(route, ori_rs.arr_time[0], self.level, 30, 0, 
                                            ori_rs.car_info, dir, ori_rs.xroad, ori_rs)
                        # self.print_handle_out_results(rss)
                        if len(rss) == 1:
                            # 替换Replace
                            rss[0] = self.combine_rs(window_stat[i], rss[0])
                            rss[0].next_ptr = window_stat[i].next_ptr
                            window_stat[i] = rss[0]
                        else:
                            # 连接Connect
                            print(f"出库的rss.size ={len(rss)} ")
                            rs_ptr = rss[1]
                            to_add.append(rs_ptr)
                            for r_idx in range(2, len(rss)):
                                rs_ptr.next_ptr = rss[r_idx]
                                rss[r_idx].prev_ptr = rs_ptr
                                to_add.append(rss[r_idx])
                                rs_ptr = rss[r_idx]
                            rs_ptr.next_ptr = window_stat[i]
                            window_stat[i].prev_ptr = rs_ptr
                    
                    i += 1
                
                # 更新结果
                phase3_res[t_index][dir] = window_stat
                print(f"to_add的规模：{len(to_add)}")
                for rs in to_add:
                    phase3_res[t_index][dir].append(rs)
        
        return phase3_res

    def count_cars_all(self, phase2_res: List[List[List[RouteSolution]]], modify: bool) -> None:
        """
        检查阶段：检查当前初步运行图是否满足要求
        
        此方法遍历所有非稳定 (STABLE) 的调度阶段 (PhaseTime)。
        代码对应: count_cars_all (调用 count_cars_addred 和 count_cars_prereduce), check_depot_cars, 
        handle_insufficent, handle_imb (在 run_alg 的循环和后续阶段中调用)
        
        Args:
            phase2_res: 阶段二处理后的列车运行方案列表
            modify: 是否修改运行方案
        """
        self.planning_done = True
        ir = IntervalRecorder(len(self.Phases))
        ir.setScore()
        
        for pidx in range(len(self.Phases) - 1):
            pt = self.Phases[pidx]
            # 我们不关心稳定阶段，只要加/减车阶段正确，整体就是正确的
            if pt.p_type == PHASETYPE.STABLE:
                continue
            
            if pt.p_type == PHASETYPE.PREREDUCE:
                self.count_cars_prereduce(phase2_res, modify, ir, pidx, pt)
            else:
                self.count_cars_addred(phase2_res, modify, ir, pidx, pt)
        
        if self.debug:
            util.pf(f"{ir.computeScore()}  {self.besst_ir.computeScore()}")
        
        if ir.computeScore() < self.besst_ir.computeScore():
            self.besst_ir = ir
            # 可能需要恢复所有记录
            for pt in self.Phases:
                pt.tested_int = set()
                pt.tested_int.add(pt.interval)

    def count_cars_prereduce(self, phase2_res: List[List[List[RouteSolution]]], modify: bool, ir: 'IntervalRecorder', pidx: int, pt: 'PhaseTime') -> None:
        """
        count_cars_prereduce: 这个方法分别针对预减车阶段。
        它会在该阶段的关键时间点（通常是阶段结束加上一个发车间隔）统计正在运行的列车数量 (n_found)。
        如果找到的列车数 (n_found) 与阶段要求的列车数 (pt.n_cars) 不符（过多或过少），会将 planning_done 标记为 false，
        并调整该阶段的发车间隔 (pt.interval)。
        run_alg中的循环会根据 planning_done 的状态决定是否从 phase1 重新开始。
        这里会记录一个 besst_ir (IntervalRecorder) 来保存历史尝试中效果最好的间隔组合。
        
        Args:
            phase2_res: 阶段二处理后的列车运行方案列表
            modify: 是否修改运行方案
            ir: 间隔记录器
            pidx: 阶段索引
            pt: 阶段时间对象
        """
        trimmed = False
        connected = set()
        
        ir.setInterval(pidx, pt.interval)
            
        if self.debug: 
            util.pf(util.ANSI_GREEN + " Checking #cars for " + str(pt))
        
        n_found = 0
        for dir in range(2):
            local_found = 0
            critical_time = pt.t_e + pt.offset_up + int(round(pt.interval))
            if dir == 1:
                critical_time = pt.t_e + pt.offset_dn + int(round(pt.interval))
            
            if self.debug: 
                util.pf(util.ANSI_YELLOW + "      critical time: " + util.timeFromIntSec(critical_time))
            
            for rs in phase2_res[0][dir]:
                if rs.car_info.round_num in connected:
                    continue
                
                dep_time = rs.arr_time[0]
                arr_time = rs.dep_time[len(rs.dep_time) - 1]
                
                if dep_time <= critical_time and arr_time >= critical_time:
                    connected.add(rs.car_info.round_num)
                    if rs.prev_ptr is not None: 
                        connected.add(rs.prev_ptr.car_info.round_num)
                    if rs.next_ptr is not None: 
                        connected.add(rs.next_ptr.car_info.round_num)
                    n_found += 1
                    local_found += 1
                    continue

                if rs.next_ptr is not None:
                    rs_n = rs.next_ptr
                    dep_timen = rs_n.arr_time[0]
                    arr_timen = rs_n.dep_time[len(rs_n.dep_time) - 1]

                    if arr_time <= critical_time and dep_timen >= critical_time:
                        connected.add(rs.car_info.round_num)
                        if rs.prev_ptr is not None: 
                            connected.add(rs.prev_ptr.car_info.round_num)
                        if rs.next_ptr is not None: 
                            connected.add(rs.next_ptr.car_info.round_num)
                        n_found += 1
                        local_found += 1
        
        color = util.ANSI_WHITE_BACKGROUND
        
        # 检查车辆数量
        if n_found < pt.n_cars:
            ir.insuff_cars_prered += pt.n_cars - n_found
            if self.debug:
                color = util.ANSI_RED_BACKGROUND
                util.pf(color + "     found #cars: " + str(n_found) + "/" + str(pt.n_cars) + "    not enough car, reduce interval")
            
            if modify:
                pt.interval -= self.amount_delta
                trimmed = True
            
            self.planning_done = False
        
        elif n_found > pt.n_cars:
            ir.redund_cars_prered += n_found - pt.n_cars
            if self.debug:
                color = util.ANSI_GREEN_BACKGROUND
                util.pf(color + "     found #cars: " + str(n_found) + "/" + str(pt.n_cars) + "    too many car, increase interval")
            
            if modify:
                pt.interval += self.amount_delta
                trimmed = True
            
            self.planning_done = False
        
        else:
            pt.interval += self.amount_delta
            if self.debug: 
                util.pf(color + "     found #cars: " + str(n_found) + "/" + str(pt.n_cars))

    def count_cars_addred(self, phase2_res: List[List[List[RouteSolution]]], modify: bool, ir: 'IntervalRecorder', pidx: int, pt: 'PhaseTime') -> None:
        """
        这个方法针对加减车阶段。它会在该阶段的关键时间点（通常是阶段结束加上一个发车间隔）统计正在运行的列车数量 (n_found)。
        
        Args:
            phase2_res: 阶段二处理后的列车运行方案列表
            modify: 是否修改运行方案
            ir: 间隔记录器
            pidx: 阶段索引
            pt: 阶段时间对象
        """
        trimmed = False
        connected = set()
        
        ir.setInterval(pidx, pt.interval)
            
        if self.debug: 
            util.pf(util.ANSI_GREEN + " Checking #cars for " + str(pt))
        
        n_found = 0
        for dir in range(2):
            local_found = 0
            critical_time = pt.t_e + pt.offset_up + int(round(pt.interval))
            if dir == 1:
                critical_time = pt.t_e + pt.offset_dn + int(round(pt.interval))
            
            if self.debug: 
                util.pf(util.ANSI_YELLOW + "      critical time: " + util.timeFromIntSec(critical_time))
            
            for rs in phase2_res[0][dir]:
                if rs.car_info.round_num in connected:
                    continue
                
                dep_time = rs.arr_time[0]
                arr_time = rs.dep_time[len(rs.dep_time) - 1]
                
                if dep_time <= critical_time and arr_time >= critical_time:
                    connected.add(rs.car_info.round_num)
                    if rs.prev_ptr is not None: 
                        connected.add(rs.prev_ptr.car_info.round_num)
                    if rs.next_ptr is not None: 
                        connected.add(rs.next_ptr.car_info.round_num)
                    n_found += 1
                    local_found += 1
                    continue

                if rs.next_ptr is not None:
                    rs_n = rs.next_ptr
                    dep_timen = rs_n.arr_time[0]
                    arr_timen = rs_n.dep_time[len(rs_n.dep_time) - 1]

                    if arr_time <= critical_time and dep_timen >= critical_time:
                        connected.add(rs.car_info.round_num)
                        if rs.prev_ptr is not None: 
                            connected.add(rs.prev_ptr.car_info.round_num)
                        if rs.next_ptr is not None: 
                            connected.add(rs.next_ptr.car_info.round_num)
                        n_found += 1
                        local_found += 1
        
        color = util.ANSI_WHITE_BACKGROUND
        
        # 检查车辆数量是否足够
        if n_found < pt.n_cars:
            ir.insuff_cars += pt.n_cars - n_found
            if self.debug:
                color = util.ANSI_RED_BACKGROUND
                util.pf(color + "     found #cars: " + str(n_found) + "/" + str(pt.n_cars) + "    not enough car, reduce interval")
            
            if modify:
                while pt.interval in pt.tested_int:
                    pt.interval -= self.amount_delta
                    trimmed = True
            
            pt.tested_int.add(pt.interval)
            self.planning_done = False
        
        elif n_found > pt.n_cars:
            ir.redund_cars += n_found - pt.n_cars
            if self.debug:
                color = util.ANSI_GREEN_BACKGROUND
                util.pf(color + "     found #cars: " + str(n_found) + "/" + str(pt.n_cars) + "    too many car, increase interval")
            
            if modify:
                while pt.interval in pt.tested_int:
                    pt.interval += self.amount_delta
                    trimmed = True
            
            pt.tested_int.add(pt.interval)
            self.planning_done = False
        
        else:
            if self.debug: 
                util.pf(color + "     found #cars: " + str(n_found) + "/" + str(pt.n_cars))
        
        connected = set()
        # 检查结束时间
        if pidx < len(self.Phases) - 2:
            pt_next = self.Phases[pidx + 1]
            if pt_next.p_type == PHASETYPE.STABLE:
                # 如果下一个阶段是预减车阶段，则不需要执行此操作
                n_found = 0
                for dir in range(2):
                    critical_time = pt_next.t_e
                    if self.debug: 
                        util.pf(util.ANSI_YELLOW + "      critical time: " + util.timeFromIntSec(critical_time))
                    
                    for rs in phase2_res[0][dir]:
                        if rs.car_info.round_num in connected:
                            continue
                        
                        dep_time = rs.arr_time[0]
                        arr_time = rs.dep_time[len(rs.dep_time) - 1]
                        
                        if dep_time <= critical_time and arr_time >= critical_time:
                            connected.add(rs.car_info.round_num)
                            if rs.prev_ptr is not None: 
                                connected.add(rs.prev_ptr.car_info.round_num)
                            if rs.next_ptr is not None: 
                                connected.add(rs.next_ptr.car_info.round_num)
                            n_found += 1
                            continue

                        if rs.next_ptr is not None:
                            rs_n = rs.next_ptr
                            dep_timen = rs_n.arr_time[0]
                            arr_timen = rs_n.dep_time[len(rs_n.dep_time) - 1]

                            if arr_time < critical_time and dep_timen > critical_time:
                                connected.add(rs.car_info.round_num)
                                if rs.prev_ptr is not None: 
                                    connected.add(rs.prev_ptr.car_info.round_num)
                                if rs.next_ptr is not None: 
                                    connected.add(rs.next_ptr.car_info.round_num)
                                n_found += 1
                
                color = util.ANSI_WHITE_BACKGROUND

                # 检查是否有足够的车辆
                if n_found < pt.n_cars:
                    ir.insuff_cars_end += pt.n_cars - n_found
                    if self.debug:
                        color = util.ANSI_RED_BACKGROUND
                        util.pf(color + "     found #cars: " + str(n_found) + "/" + str(pt.n_cars) + "    not enough car, reduce interval" + str(trimmed))
                    
                    if not trimmed and modify:
                        while pt.interval in pt.tested_int:
                            pt.interval -= self.amount_delta
                        
                        pt.tested_int.add(pt.interval)
                    
                    self.planning_done = False
                
                elif n_found > pt.n_cars:
                    ir.redund_cars_end += n_found - pt.n_cars
                    if self.debug:
                        color = util.ANSI_GREEN_BACKGROUND
                        util.pf(color + "     found #cars: " + str(n_found) + "/" + str(pt.n_cars) + "    too many car, increase interval" + str(trimmed))
                    
                    if not trimmed and modify:
                        while pt.interval in pt.tested_int:
                            pt.interval += self.amount_delta
                        
                        pt.tested_int.add(pt.interval)
                    
                    self.planning_done = False
                
                else:
                    if self.debug: 
                        util.pf(color + "     found #cars: " + str(n_found) + "/" + str(pt.n_cars))

    def removeEarlyCars(self, pres):
        """
        移除早期车辆
        
        Args:
            pres: 包含车辆调度方案的嵌套列表
            
        Returns:
            处理后的车辆调度方案
        """
        res = []
        for t in range(len(pres)):
            time_frame = []
            for dir in range(2):
                direction_frame = []
                for i in range(len(pres[t][dir])):
                    rs = pres[t][dir][i]
                    if not rs.auxilary == "aux" and rs.dep_time[len(rs.dep_time) - 1] < self.us.first_car:
                        if rs.next_ptr is not None:
                            rs.next_ptr.prev_ptr = None
                        continue
                    direction_frame.append(rs)
                time_frame.append(direction_frame)
            res.append(time_frame)
        print("已执行该removeEarlyCars函数")
        return res
    

    imb_amnt = 0
    imb_dir = -1
    def check_depot_cars(self, phase_res):
        """
        检查车库车辆数目，判断是否需要进行车辆调运
        
        Args:
            phase_res: 包含车辆调度方案的嵌套列表
            
        Returns:
            DepotImbalance对象，表示车库不平衡情况
        """
        print("已执行该check_depot_cars函数")
        depot_cars = []
        init_depot_cars = []
        depot_caps = []
        
        for dir in range(2):
            t_cap = self.us.depot_caps[dir]
            t_ava = self.us.depot_trains[dir]
            depot_cars.append(t_ava)
            depot_caps.append(t_cap)
            init_depot_cars.append(t_ava)
            
        # 存储进出站车辆的时间和车辆信息
        inout_cars = []
        
        for dir in range(2):
            for t in range(len(phase_res)):
                rt_list = phase_res[t][dir]
                for rs in rt_list:
                    rs.dir = dir
                    
                    if rs.prev_ptr is None or self.is_ignored(rs.prev_ptr):
                        # 出站车辆
                        inout_cars.append(TimeRSPair(rs.arr_time[0], rs))
                    
                    if rs.next_ptr is None:
                        # 入站车辆
                        inout_cars.append(TimeRSPair(rs.dep_time[len(rs.dep_time) - 1], rs))
        
        max_insuff = 0  # 最大不足数量
        insuff_dir = -1  # 不足方向
        max_redund = 0   # 最大冗余数量
        redund_dir = -1  # 冗余方向
        
        if self.debug:
            util.pf(util.ANSI_GREEN_BACKGROUND + "Depot stat at beginning: " + 
                        str(depot_cars[0]) + "/" + str(depot_caps[0]) + "     " + 
                        str(depot_cars[1]) + "/" + str(depot_caps[1]))
        
        # 按时间排序
        inout_cars.sort(key=lambda x: x.time)
        
        for tpair in inout_cars:
            etime = tpair.time
            rs = tpair.rs
            
            # 出站车辆
            if rs.arr_time[0] == etime:
                tmp = depot_cars[rs.dir] - 1
                depot_cars[rs.dir] = tmp
                color1 = util.ANSI_GREEN
                color2 = util.ANSI_GREEN
                
                if depot_cars[0] < 0:
                    max_insuff = max(max_insuff, abs(depot_cars[0]))
                    insuff_dir = 0
                    color1 = util.ANSI_RED
                
                if depot_cars[0] > depot_caps[0]:
                    max_redund = max(max_redund, depot_cars[0] - depot_caps[0])
                    redund_dir = 0
                    color1 = util.ANSI_YELLOW
                
                if depot_cars[1] < 0:
                    max_insuff = max(max_insuff, abs(depot_cars[1]))
                    insuff_dir = 1
                    color2 = util.ANSI_RED
                
                if depot_cars[1] > depot_caps[1]:
                    max_redund = max(max_redund, depot_cars[1] - depot_caps[1])
                    redund_dir = 1
                    color1 = util.ANSI_YELLOW
                
                if self.debug:
                    util.pf(util.ANSI_GREEN + "   Out car at " + 
                                util.timeFromIntSec(rs.arr_time[0]) + 
                                " (dir" + str(rs.dir) + ")  Depot Stat: " + 
                                color1 + str(depot_cars[0]) + "/" + str(depot_caps[0]) + 
                                "     " + color2 + str(depot_cars[1]) + "/" + str(depot_caps[1]))
            else:
                # 入站车辆
                tmp = depot_cars[1 - rs.dir] + 1
                depot_cars[1 - rs.dir] = tmp
                color1 = util.ANSI_GREEN
                color2 = util.ANSI_GREEN
                
                if depot_cars[0] < 0:
                    max_insuff = max(max_insuff, abs(depot_cars[0]))
                    insuff_dir = 0
                    color1 = util.ANSI_RED
                
                if depot_cars[0] > depot_caps[0]:
                    max_redund = max(max_redund, depot_cars[0] - depot_caps[0])
                    redund_dir = 0
                    color1 = util.ANSI_YELLOW
                
                if depot_cars[1] < 0:
                    max_insuff = max(max_insuff, abs(depot_cars[1]))
                    insuff_dir = 1
                    color2 = util.ANSI_RED
                
                if depot_cars[1] > depot_caps[1]:
                    max_redund = max(max_redund, depot_cars[1] - depot_caps[1])
                    redund_dir = 1
                    color1 = util.ANSI_YELLOW
                
                if self.debug:
                    util.pf(util.ANSI_GREEN + "   In car at " + 
                                util.timeFromIntSec(rs.dep_time[len(rs.dep_time) - 1]) + 
                                " (dir" + str(rs.dir) + ")  Depot Stat: " + 
                                color1 + str(depot_cars[0]) + "/" + str(depot_caps[0]) + 
                                "     " + color2 + str(depot_cars[1]) + "/" + str(depot_caps[1]))
        
        # 检查车库不平衡情况
        if init_depot_cars[0] != depot_cars[0]:
            self.imb_amnt = abs(init_depot_cars[0] - depot_cars[0])
            if init_depot_cars[0] > depot_cars[0]:
                # 0号方向起始车库缺少车辆
                self.imb_dir = 0
            else:
                # 1号方向起始车库缺少车辆
                self.imb_dir = 1
        
        if insuff_dir == -1:
            return None
        
        max_redund = self.us.depot_trains[insuff_dir] - depot_cars[insuff_dir]
        redund_dir = insuff_dir
        
        if self.debug:
            util.pf(util.ANSI_BLUE + "(Early) Need to transfer " + 
                        str(max_insuff) + " cars from dir" + str(1 - insuff_dir) + 
                        " to dir" + str(insuff_dir))
            util.pf(util.ANSI_BLUE_BACKGROUND + "(Late) Need to transfer " + 
                        str(max_redund) + " cars from dir" + str(1 - redund_dir) + 
                        " to dir" + str(redund_dir))
        
        return DepotImbalance(max_insuff, insuff_dir, max_redund, redund_dir)
    
    def handle_imb(self, phase_res):
        """
        处理车库不平衡情况
        
        Args:
            phase_res: 包含车辆调度方案的嵌套列表
            
        Returns:
            处理后的车辆调度方案
        """
        print("已执行该handle_imb函数")
        send_dir = (1 - self.imb_dir)
        check_dir = self.imb_dir
        
        util.pf(util.ANSI_CYAN + "  need to send " + str(self.imb_amnt) + 
                    " cars to depot " + str(self.imb_dir) + "  with path dir " + str(send_dir))
        
        self.debug = True
        
        # 需要发送车辆回去
        rss_last = phase_res[0][check_dir]
        # 找到起始位置
        starting_last_car = 0
        
        # 找到第一辆在末班车之后且没有后续连接的车
        for i in range(len(rss_last)):
            starting_last_car = i
            rs = rss_last[i]
            if rs.dep_time[len(rs.dep_time) - 1] >= self.us.last_car and rs.next_ptr is None:
                break
        
        finder = 0
        pk_idx = 0
        pk = self.us.peaks[pk_idx]
        
        if self.us.n_xroads > 1:
            while pk.op_rate2 < 0:
                pk_idx += 1
                pk = self.us.peaks[pk_idx]
        
        for i in range(self.imb_amnt):
            # 找到要连接的车
            rs = rss_last[starting_last_car + finder]
            while rs.next_ptr is not None:
                finder += 1
                rs = rss_last[starting_last_car + finder]
            
            xroad = rs.xroad
            sent_t = -1
            
            send_route = pk.getRoute(rs.xroad, send_dir)
            
            if xroad != 0:
                route = pk.routes[0].up_route
                routeX = pk.routes[1].up_route
                if send_dir == 1:
                    route = pk.routes[0].down_route
                    routeX = pk.routes[1].down_route
                sent_t = self.get_act_send_time(int(round(sent_t)), route, routeX, self.level)
            
            self.cont_n_sent += 1
            dummy = CarInfo(self.cont_n_sent, 1 + 100 * self.cont_n_sent, -1)
            # vehicle_id = self.get_available_vehicle_id()
            # round_num = self.get_next_round_num()  # 获取车次号
            # dummy = CarInfo(vehicle_id, round_num, -1)
            rs_new = self.rl.getHeuristicSolFromPath1(send_route, int(round(sent_t)), self.level, 30, 0, dummy)
            rs_new.xroad = rs.xroad
            
            if self.debug:
                util.pf(" Connecting after " + util.timeFromIntSec(rs.arr_time[0]) + 
                            "  xroad: " + str(xroad) + "   rn: " + str(rs_new.car_info.round_num))
                util.pf("   send dir: " + str(send_dir))
            
            arr_time = rs.dep_time[len(rs_new.dep_time) - 1]
            dep_time = rs_new.arr_time[0]
            tb = self.rl.turnbackList[rs.stopped_platforms[len(rs_new.stopped_platforms) - 1]]
            mintb = tb.min_tb_time
            
            if arr_time + mintb != dep_time:
                offset_this = arr_time + mintb - dep_time
                for p in range(len(rs_new.arr_time)):
                    rs_new.arr_time[p] = rs_new.arr_time[p] + offset_this
                    rs_new.dep_time[p] = rs_new.dep_time[p] + offset_this
            
            if self.debug:
                util.pf("  send time: " + util.timeFromIntSec(rs_new.arr_time[0]))
            
            rs_new.auxilary = "aux"
            
            rs_new.prev_ptr = rs
            rs.next_ptr = rs_new
            
            phase_res[0][send_dir].append(rs_new)
        
        tmp = self.phase5_convert(phase_res)
        tmp = self.sort_window_optimized(tmp)
        phase_res = []
        phase_res.append(tmp)
        
        self.debug = False
        return phase_res

    def is_ignored(self, rs):
        """
        检查列车是否应该因为时间原因被忽略
        
        Args:
            rs: 路线解决方案对象(RouteSolution)
            
        Returns:
            bool: 如果应该被忽略返回True，否则返回False
        """
        # 检查是否不是辅助列车且出发时间小于等于首班车时间+60秒
        if rs.auxilary != "aux" and rs.dep_time[len(rs.dep_time) - 1] <= self.us.first_car + 60:
            return True
        return False

    def handle_insufficent(self, dimb, phase_res):
        """
        处理车库车辆不足情况
        
        Args:
            dimb: DepotImbalance对象，表示车库不平衡情况
            phase_res: 包含车辆调度方案的嵌套列表
            
        Returns:
            处理后的车辆调度方案
        """
        print("handle_insufficent函数已执行")
        deleting_rts = set()
        
        # 0: up route start depot
        # 1: dn route start depot
        ins_depot = dimb.ins_depot
        add_amount = dimb.ins_cars
        send_dir = 1 - ins_depot
        side_earliest = 3600 * 24
        
        # 找到该方向最早的车
        for t in range(len(phase_res)):
            rss = phase_res[t][send_dir]
            for rs in rss:
                act_send_time = self.get_act_send_time_rev(rs, send_dir)
                if act_send_time < side_earliest:
                    side_earliest = act_send_time
        
        if self.debug:
            util.pf(util.ANSI_RED + "Found earliest car at direction" + 
                        str(send_dir) + " at " + util.timeFromIntSec(side_earliest))
        
        # 获取发车时间
        send_time = []
        pt = self.Phases[0]
        t_ptr = side_earliest
        interval = pt.interval
        
        for i in range(add_amount):
            t_ptr -= interval
            send_time.append(t_ptr)
        
        pk_idx = 0
        pk = self.us.peaks[pk_idx]
        
        if self.us.n_xroads > 1:
            while pk.op_rate2 < 0:
                pk_idx += 1
                pk = self.us.peaks[pk_idx]
        
        rss = phase_res[0][ins_depot]
        tar_idx = 0
        
        # 需要找到首班车之后的第一辆车
        for i in range(len(rss)):
            rs = rss[i]
            if rs.arr_time[0] > self.us.first_car or (rs.prev_ptr is not None and not self.is_ignored(rs.prev_ptr)):
                break
            tar_idx = i
        
        if self.debug:
            util.pf("Found the last car before " + util.timeFromIntSec(self.us.first_car) + 
                        " at " + util.timeFromIntSec(rss[tar_idx].arr_time[0]))
        
        for i in range(add_amount):
            sent_t = send_time[i]
            # 找到要连接的车
            rs = rss[tar_idx]
            while self.is_ignored(rs) and tar_idx > 0:
                tar_idx -= 1
                rs = rss[tar_idx]
            
            xroad = rs.xroad
            if self.debug:
                util.pf(" Car " + str(i) + " send time: " + 
                            util.timeFromIntSec(int(round(sent_t))) + 
                            "   should connect with " + util.timeFromIntSec(rs.arr_time[0]) + 
                            "  xroad: " + str(xroad))
            
            send_route = pk.getRoute(rs.xroad, send_dir)
            if xroad != 0:
                route = pk.routes[0].up_route
                routeX = pk.routes[1].up_route
                
                if send_dir == 1:
                    route = pk.routes[0].down_route
                    routeX = pk.routes[1].down_route
                
                sent_t = self.get_act_send_time(int(round(sent_t)), route, routeX, self.level)
            
            # 创建新车
            self.cont_n_sent += 1
            dummy = CarInfo(self.cont_n_sent, 1 + 100 * self.cont_n_sent, -1)
            # vehicle_id = self.get_available_vehicle_id()
            # round_num = self.get_next_round_num()  # 获取车次号
            # dummy = CarInfo(vehicle_id, round_num, -1)
            rs_new = self.rl.getHeuristicSolFromPath1(send_route, int(round(sent_t)), self.level, 30, 0, dummy)
            
            if self.debug:
                util.pf("   send dir: " + str(send_dir) + "   cn: " + 
                            str(dummy.round_num) + "  prev: " + str(rs.prev_ptr))
            
            rs_new.xroad = rs.xroad
            
            # 计算新时间
            arr_time = rs_new.dep_time[len(rs_new.dep_time) - 1]
            dep_time = rs.arr_time[0]
            tb = self.rl.turnbackList[rs_new.stopped_platforms[len(rs_new.stopped_platforms) - 1]]
            mintb = tb.min_tb_time
            
            if arr_time + mintb != dep_time:
                offset_this = arr_time + mintb - dep_time
                for p in range(len(rs_new.arr_time)):
                    rs_new.arr_time[p] = rs_new.arr_time[p] - offset_this
                    rs_new.dep_time[p] = rs_new.dep_time[p] - offset_this
            
            rs_new.auxilary = "aux"
            
            if rs.prev_ptr is not None:
                deleting_rts.add(rs.prev_ptr.car_info.round_num)
            
            rs_new.next_ptr = rs
            rs.prev_ptr = rs_new
            
            phase_res[0][send_dir].insert(0, rs_new)
            tar_idx -= 1
        
        # 检查是否有需要删除的列车
        if len(deleting_rts) != 0:
            tmp_phase_res = []
            for ptidx in range(len(phase_res)):
                tmp_phase_ress = []
                for dir in range(2):
                    tmp_phase_resss = []
                    for i in range(len(phase_res[ptidx][dir])):
                        rs = phase_res[ptidx][dir][i]
                        if rs.car_info.round_num in deleting_rts:
                            continue
                        tmp_phase_resss.append(rs)
                    tmp_phase_ress.append(tmp_phase_resss)
                tmp_phase_res.append(tmp_phase_ress)
            phase_res = tmp_phase_res
        
        # 需要发送车辆回去
        cars_offset = dimb.red_cars
        check_dir = send_dir
        send_dir = 1 - check_dir
        rss_last = phase_res[0][check_dir]
        
        # 找到起始位置
        starting_last_car = 0
        
        # 找到末班车之后且没有后续连接的第一辆车
        for i in range(len(rss_last)):
            starting_last_car = i
            rs = rss_last[i]
            if rs.dep_time[len(rs.dep_time) - 1] >= self.us.last_car and rs.next_ptr is None:
                break
        
        rss_size = len(rss_last)
        finder = 0
        
        for i in range(add_amount - cars_offset):
            # 找到要连接的车
            rs = rss_last[starting_last_car + finder]
            while rs.next_ptr is not None:
                finder += 1
                rs = rss_last[starting_last_car + finder]
            
            xroad = rs.xroad
            sent_t = -1
            
            send_route = pk.getRoute(rs.xroad, send_dir)
            if xroad != 0:
                route = pk.routes[0].up_route
                routeX = pk.routes[1].up_route
                if send_dir == 1:
                    route = pk.routes[0].down_route
                    routeX = pk.routes[1].down_route
                sent_t = self.get_act_send_time(int(round(sent_t)), route, routeX, self.level)
            
            self.cont_n_sent += 1
            dummy = CarInfo(self.cont_n_sent, 1 + 100 * self.cont_n_sent, -1)
            # vehicle_id = self.get_available_vehicle_id()
            # round_num = self.get_next_round_num()  # 获取车次号
            # dummy = CarInfo(vehicle_id, round_num, -1)
            rs_new = self.rl.getHeuristicSolFromPath1(send_route, int(round(sent_t)), self.level, 30, 0, dummy)
            rs_new.xroad = rs.xroad
            
            if self.debug:
                util.pf(" Connecting after " + util.timeFromIntSec(rs.arr_time[0]) + 
                            "  xroad: " + str(xroad) + "   rn: " + str(rs_new.car_info.round_num))
                util.pf("   send dir: " + str(send_dir))
            
            arr_time = rs.dep_time[len(rs_new.dep_time) - 1]
            dep_time = rs_new.arr_time[0]
            tb = self.rl.turnbackList[rs.stopped_platforms[len(rs_new.stopped_platforms) - 1]]
            mintb = tb.min_tb_time
            
            if arr_time + mintb != dep_time:
                offset_this = arr_time + mintb - dep_time
                for p in range(len(rs_new.arr_time)):
                    rs_new.arr_time[p] = rs_new.arr_time[p] + offset_this
                    rs_new.dep_time[p] = rs_new.dep_time[p] + offset_this
            
            if self.debug:
                util.pf("  send time: " + util.timeFromIntSec(rs_new.arr_time[0]))
            
            rs_new.auxilary = "aux"
            
            rs_new.prev_ptr = rs
            rs.next_ptr = rs_new
            
            phase_res[0][send_dir].append(rs_new)
            tar_idx += 1
        
        # 恢复所需的返回形式
        tmp = self.phase5_convert(phase_res)
        tmp = self.sort_window_optimized(tmp)
        phase_res = []
        phase_res.append(tmp)
        
        return phase_res

    def verify_trip_count_consistency(self, phase_res: List[List[List[RouteSolution]]], res_schedule) -> bool:
        """
        验证两种方法的车次数一致性
        
        Args:
            phase_res: 规则算法结果
            res_schedule: 优化模型结果
        Returns:
            True表示一致，False表示不一致
        """
        # 统计phase_res中的正常折返车次
        normal_counts = [0, 0, 0, 0]  # [大交路上行, 大交路下行, 小交路上行, 小交路下行]
        
        for phase_idx in range(len(phase_res)):
            if phase_idx == 0:  # 跳过初始出库阶段
                continue
                
            for dir_idx in range(2):
                for rs in phase_res[phase_idx][dir_idx]:
                    if rs and hasattr(rs, 'xroad') and hasattr(rs, 'dir'):
                        route_type = rs.xroad * 2 + rs.dir
                        # route_type = rs.xroad * 2 + dir_idx  #可能需要这样去统计，因为rs.dir有可能为-1
                        normal_counts[route_type] += 1
        
        # 统计res_schedule中的有效车次
        schedule_counts = []
        for row in range(4):
            count = np.sum(~np.isnan(res_schedule[row, :]))
            schedule_counts.append(count)
        
        # 比较结果
        is_consistent = normal_counts == schedule_counts
        
        print(f"规则算法车次数: {normal_counts}")
        print(f"优化模型车次数: {schedule_counts}")
        print(f"一致性检查: {'通过' if is_consistent else '失败'}")
        
        return is_consistent

    def update_routes_from_schedule_improved(self, phase_res: List[List[List[RouteSolution]]], res_schedule) -> None:
        """
        改进的车次匹配函数：精确匹配正常折返车次
        
        Args:
            phase_res: 三维列表 [阶段][方向][路线]
            res_schedule: 优化模型结果，形状为(4, q)，其中4代表大小交路上下行
        """
        if res_schedule is None:
            print("警告：res_schedule为空，无法更新到发时刻")
            return
        
        # 1. 收集所有正常折返车次（排除出库车次）
        normal_trains = [[] for _ in range(4)]  # [大交路上行, 大交路下行, 小交路上行, 小交路下行]
        
        for phase_idx in range(len(phase_res)):
            for dir_idx in range(2):  # 0=上行, 1=下行
                for rs in phase_res[phase_idx][dir_idx]:
                    if rs is None:
                        continue
                    
                    # 关键：过滤条件，只保留正常折返车次
                    if self.is_normal_service_train(rs):
                        route_type = self.get_route_type(rs, dir_idx)
                        if route_type >= 0:
                            normal_trains[route_type].append((phase_idx, dir_idx, rs))
        
        # 2. 按发车时间排序
        for route_type in range(4):
            normal_trains[route_type].sort(key=lambda x: x[2].dep_time[0] if x[2].dep_time else 0)
        
        # 3. 统计车次数量并调整匹配策略
        route_names = ["大交路上行", "大交路下行", "小交路上行", "小交路下行"]
        for route_type in range(4):
            phase_count = len(normal_trains[route_type])
            schedule_count = np.sum(~np.isnan(res_schedule[route_type, :]))
            
            print(f"{route_names[route_type]}: phase_res={phase_count}车次, res_schedule={schedule_count}车次")
            
            # 如果数量不匹配，采用智能匹配策略
            if phase_count != schedule_count:
                self.smart_match_trains(normal_trains[route_type], res_schedule[route_type, :], route_type)
            else:
                # 数量匹配，直接按顺序更新
                self.direct_match_trains(normal_trains[route_type], res_schedule[route_type, :], route_type)
    
    def update_routes_with_intelligent_matching(self, phase_res, res_schedule):
        """
        方案2：使用智能匹配方法更新规则算法结果
        
        Args:
            phase_res: 规则算法生成的阶段结果
            res_schedule: 优化模型生成的时刻表 (4, max_trips)
        """
        print("开始方案2：智能匹配更新...")
        
        # 1. 提取优化模型的正常折返车次发车时刻
        opt_departure_times = self.extract_normal_service_times(res_schedule)
        
        # 2. 提取规则算法的正常折返车次
        rule_normal_trains = self.extract_rule_normal_trains(phase_res)
        
        # 3. 执行智能匹配
        matches = self.intelligent_matching(opt_departure_times, rule_normal_trains)
        
        # 4. 应用匹配结果
        self.apply_matching_results(matches, phase_res)
        
        print("方案2智能匹配完成")

    def extract_normal_service_times(self, res_schedule):
        """
        从优化模型结果中提取正常折返车次的发车时刻
        
        Args:
            res_schedule: 优化模型时刻表 (4, max_trips)
            
        Returns:
            dict: {route_type: [departure_times]}
        """
        import numpy as np
        
        # 获取初始车次数（需要跳过的出库车次）
        initial_trip_nums = self.get_initial_trip_nums()
        
        normal_times = {}
        route_names = ['大交路上行', '大交路下行', '小交路上行', '小交路下行']
        
        for route_type in range(4):
            times = []
            start_idx = initial_trip_nums[route_type] if route_type < len(initial_trip_nums) else 0
            
            for i in range(start_idx, res_schedule.shape[1]):
                time_val = res_schedule[route_type, i]
                if not np.isnan(time_val):
                    times.append(time_val)
            
            normal_times[route_type] = sorted(times)
            print(f"{route_names[route_type]}: 提取到{len(times)}个正常折返车次时刻")
        
        return normal_times

    def extract_rule_normal_trains(self, phase_res):
        """
        从规则算法结果中提取正常折返车次
        
        Args:
            phase_res: 规则算法阶段结果
            
        Returns:
            dict: {route_type: [(phase_idx, dir_idx, rs, dep_time)]}
        """
        normal_trains = {0: [], 1: [], 2: [], 3: []}
        
        for phase_idx in range(len(phase_res)):
            for dir_idx in range(2):
                for rs in phase_res[phase_idx][dir_idx]:
                    if rs is None:
                        continue
                    
                    # 只保留正常折返车次
                    if self.is_normal_service_train(rs):
                        route_type = self.get_route_type(rs, dir_idx)
                        if route_type >= 0 and rs.dep_time:
                            dep_time = rs.dep_time[0]
                            normal_trains[route_type].append((phase_idx, dir_idx, rs, dep_time))
        
        # 按发车时间排序
        for route_type in range(4):
            normal_trains[route_type].sort(key=lambda x: x[3])
            print(f"交路类型{route_type}: 找到{len(normal_trains[route_type])}个正常折返车次")
        
        return normal_trains

    def intelligent_matching(self, opt_times, rule_trains):
        """
        执行智能匹配算法
        
        Args:
            opt_times: 优化模型发车时刻 {route_type: [times]}
            rule_trains: 规则算法车次 {route_type: [(phase_idx, dir_idx, rs, dep_time)]}
            
        Returns:
            list: 匹配结果 [(rs, new_dep_time)]
        """
        matches = []
        
        for route_type in range(4):
            opt_time_list = opt_times.get(route_type, [])
            rule_train_list = rule_trains.get(route_type, [])
            
            print(f"交路类型{route_type}: 优化模型{len(opt_time_list)}个时刻 vs 规则算法{len(rule_train_list)}个车次")
            
            # 使用贪心算法进行匹配
            used_opt_indices = set()
            
            for phase_idx, dir_idx, rs, rule_time in rule_train_list:
                best_match_idx = -1
                min_time_diff = float('inf')
                
                # 找到时间最接近且未使用的优化时刻
                for i, opt_time in enumerate(opt_time_list):
                    if i in used_opt_indices:
                        continue
                    
                    time_diff = abs(opt_time - rule_time)
                    if time_diff < min_time_diff:
                        min_time_diff = time_diff
                        best_match_idx = i
                
                # 如果找到合适的匹配
                if best_match_idx >= 0 and min_time_diff <= 3600:  # 1小时内的差异认为可接受
                    used_opt_indices.add(best_match_idx)
                    new_time = opt_time_list[best_match_idx]
                    matches.append((rs, new_time))
                    print(f"  匹配成功: {rule_time:.1f} -> {new_time:.1f} (差异: {min_time_diff:.1f}秒)")
                else:
                    print(f"  无法匹配车次，时间差异过大: {rule_time:.1f}")
        
        print(f"总共匹配成功{len(matches)}个车次")
        return matches

    def apply_matching_results(self, matches, phase_res):
        """
        应用匹配结果，更新车次时刻
        
        Args:
            matches: 匹配结果 [(rs, new_dep_time)]
            phase_res: 规则算法阶段结果
        """
        for rs, new_dep_time in matches:
            self.update_train_schedule(rs, int(round(new_dep_time)))
        
        print(f"已更新{len(matches)}个车次的时刻表")

    def get_initial_trip_nums(self):
        """
        获取各交路类型的初始车次数（出库车次数）
        
        Returns:
            list: [大交路上行初始数, 大交路下行初始数, 小交路上行初始数, 小交路下行初始数]
        """
        # 这里需要根据实际的初始化参数来获取
        # 可以从 initialize_params 或其他地方获取
        return [10, 10, 5, 5]  # 示例值，需要根据实际情况调整

    def get_route_type(self, rs: RouteSolution, dir_idx: int) -> int:
        """
        获取交路类型索引
        
        Args:
            rs: RouteSolution对象
            dir_idx: 方向索引（0=上行，1=下行）
            
        Returns:
            交路类型索引：0=大交路上行, 1=大交路下行, 2=小交路上行, 3=小交路下行
        """
        if not hasattr(rs, 'xroad'):
            return -1
        
        if rs.xroad == 0 and dir_idx == 0:  # 大交路上行
            return 0
        elif rs.xroad == 0 and dir_idx == 1:  # 大交路下行
            return 1
        elif rs.xroad == 1 and dir_idx == 0:  # 小交路上行
            return 2
        elif rs.xroad == 1 and dir_idx == 1:  # 小交路下行
            return 3
        
        return -1

    def smart_match_trains(self, trains: list, schedule_row: np.ndarray, route_type: int) -> None:
        """
        智能匹配策略：处理车次数量不匹配的情况
        
        Args:
            trains: 该交路类型的所有车次列表
            schedule_row: res_schedule中对应行的数据
            route_type: 交路类型索引
        """
        valid_schedules = schedule_row[~np.isnan(schedule_row)]
        
        if len(trains) > len(valid_schedules):
            # phase_res车次多于res_schedule，选择最重要的车次进行匹配
            # 策略：保留发车时间在运营时段内的车次
            filtered_trains = self.filter_peak_period_trains(trains)
            if len(filtered_trains) <= len(valid_schedules):
                trains = filtered_trains
            else:
                # 如果还是太多，按发车时间均匀采样
                trains = self.sample_trains_evenly(trains, len(valid_schedules))
        
        elif len(trains) < len(valid_schedules):
            # phase_res车次少于res_schedule，使用所有车次，多余的schedule数据忽略
            valid_schedules = valid_schedules[:len(trains)]
        
        # 执行匹配
        for i, (phase_idx, dir_idx, rs) in enumerate(trains):
            if i < len(valid_schedules):
                self.update_train_schedule(rs, int(round(valid_schedules[i])))

    def filter_peak_period_trains(self, trains: list) -> list:
        """
        过滤出运营高峰期的车次
        """
        filtered = []
        for phase_idx, dir_idx, rs in trains:
            if (hasattr(rs, 'dep_time') and rs.dep_time and 
                self.is_peak_period_time(rs.dep_time[0])):
                filtered.append((phase_idx, dir_idx, rs))
        return filtered
        
    def is_peak_period_time(self, dep_time: int) -> bool:
        """
        判断给定的发车时间是否在高峰期内
        
        Args:
            dep_time: 发车时间（秒）
            
        Returns:
            bool: 如果在高峰期内返回True，否则返回False
        """
        # 将秒转换为小时和分钟
        hours = dep_time // 3600
        minutes = (dep_time % 3600) // 60
        time_in_minutes = hours * 60 + minutes
        
        # 定义高峰期时间段（可根据实际需求调整）
        # 早高峰：7:00-9:30 (420-570分钟)
        # 晚高峰：17:00-19:30 (1020-1170分钟)
        morning_peak_start = 7 * 60  # 7:00
        morning_peak_end = 9 * 60 + 30  # 9:30
        evening_peak_start = 17 * 60  # 17:00
        evening_peak_end = 19 * 60 + 30  # 19:30
        
        return ((morning_peak_start <= time_in_minutes <= morning_peak_end) or 
                (evening_peak_start <= time_in_minutes <= evening_peak_end))

    def sample_trains_evenly(self, trains: list, target_count: int) -> list:
        """
        从车次列表中均匀采样指定数量的车次
        
        Args:
            trains: 车次列表，每个元素为(phase_idx, dir_idx, rs)的元组
            target_count: 目标采样数量
            
        Returns:
            list: 采样后的车次列表
        """
        if len(trains) <= target_count:
            return trains
        
        # 计算采样间隔
        step = len(trains) / target_count
        sampled_trains = []
        
        for i in range(target_count):
            index = int(i * step)
            if index < len(trains):
                sampled_trains.append(trains[index])
        
        return sampled_trains        
    def update_train_schedule(self, rs: RouteSolution, new_dep_time: int) -> None:
        """
        更新单个车次的时刻表
        
        Args:
            rs: RouteSolution对象
            new_dep_time: 新的发车时刻
        """
        if rs.dep_time and len(rs.dep_time) > 0:
            time_diff = new_dep_time - rs.dep_time[0]
            
            # 平移所有发车时刻
            for i in range(len(rs.dep_time)):
                rs.dep_time[i] += time_diff
            
            # 平移所有到达时刻
            if rs.arr_time:
                for i in range(len(rs.arr_time)):
                    rs.arr_time[i] += time_diff
class DepotImbalance:
    """
    车库不平衡信息类
    
    用于存储车库之间车辆不平衡的信息，包括缺车和多车的车库及数量
    """
    
    def __init__(self, a=None, b=None, c=None, d=None):
        """
        初始化车库不平衡信息
        
        Args:
            a: 缺少的车辆数量
            b: 缺车的车库编号
            c: 多余的车辆数量
            d: 多车的车库编号
        """
        self.ins_cars = -1 if a is None else a  # 缺少的车辆数量
        self.red_cars = -1 if c is None else c  # 多余的车辆数量
        self.ins_depot = -1 if b is None else b  # 缺车的车库编号
        self.red_depot = -1 if d is None else d  # 多车的车库编号

class TimeRSPair:
    """
    时间与路线解决方案配对类
    
    用于将时间点与对应的路线解决方案(RouteSolution)关联起来
    """
    
    def __init__(self, t, rs):
        """
        初始化时间-路线解决方案对
        
        Args:
            t: 时间点
            rs: 路线解决方案对象
        """
        self.time = t if t is not None else -1  # 时间点
        self.rs = rs  # 路线解决方案对象