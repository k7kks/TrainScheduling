"""
快慢车运行图自动编制程序V3主入口

基于发车时间均衡性的快慢车运行图自动编制系统
整合algorithms和models模块，实现优化算法

主要流程：
1. 读取输入数据（复用src的DataReader）
2. 使用ExpressLocalGenerator生成快慢车运行图（优化算法）
3. 使用TimetableBuilder构建详细时刻表
4. 转换为RouteSolution对象（兼容src的数据结构）
5. 输出Excel文件（复用src的Solution.writeExcel）
"""

import sys
import os
import time
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# 添加项目根目录和src到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
src_dir = os.path.join(project_root, 'src')

if project_root not in sys.path:
    sys.path.insert(0, project_root)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

# 导入src模块
from DataReader import DataReader
from RailInfo import RailInfo
from UserSetting import UserSetting
from Solution import Solution
from RouteSolution import RouteSolution
from CarInfo import CarInfo
from Route import Route

# 导入algorithms和models模块
from algorithms.express_local_generator import ExpressLocalGenerator, ExpressLocalConfig
from algorithms.timetable_builder import TimetableBuilder
from algorithms.headway_optimizer import HeadwayOptimizer  # 发车间隔优化器
from algorithms.connection_manager import ConnectionManager  # 车次勾连管理器
from models.express_local_timetable import ExpressLocalTimetable
from models.train import Train, ExpressTrain, LocalTrain
from models.timetable_entry import TimetableEntry


class ExpressLocalSchedulerV3:
    """
    快慢车运行图自动编制器V3
    
    整合所有功能模块的主类
    生成标准的RouteSolution对象，兼容src的输出接口
    """
    
    def __init__(self,
                 rail_info_file: str,
                 user_setting_file: str,
                 output_dir: str = "../data/output_data/results",
                 express_ratio: float = 0.5,
                 target_headway: int = 180,
                 speed_level: int = 1,
                 default_dwell_time: int = 30,
                 express_stop_stations: List[str] = None,  # 快车停站列表（站台码）
                 enable_short_route: bool = True,  # 是否启用小交路
                 short_route_ratio: float = 0.5,   # 小交路比例
                 debug: bool = False):
        """
        初始化调度器
        
        Args:
            rail_info_file: 线路信息文件路径
            user_setting_file: 用户设置文件路径
            output_dir: 输出目录
            express_ratio: 快车比例（0-1）
            target_headway: 目标发车间隔（秒）
            speed_level: 速度等级（默认1）
            default_dwell_time: 默认停站时间（秒）
            express_stop_stations: 快车停站列表（站台码），None表示自动选择
            enable_short_route: 是否启用小交路
            short_route_ratio: 小交路比例（相对于慢车）
            debug: 是否开启调试模式
        """
        self.rail_info_file = rail_info_file
        self.user_setting_file = user_setting_file
        self.output_dir = output_dir
        self.debug = debug
        
        # 数据
        self.rail_info: RailInfo = None
        self.user_setting: UserSetting = None
        self.solution: Solution = None
        self.timetable: ExpressLocalTimetable = None  # 快慢车时刻表
        
        # 配置参数
        self.express_ratio = express_ratio
        self.target_headway = target_headway
        self.speed_level = speed_level
        self.default_dwell_time = default_dwell_time
        self.express_stop_stations = express_stop_stations  # 快车停站方案
        self.enable_short_route = enable_short_route
        self.short_route_ratio = short_route_ratio
        
        # 算法模块
        self.generator: ExpressLocalGenerator = None
        self.builder: TimetableBuilder = None
        self.optimizer: HeadwayOptimizer = None  # 发车间隔优化器
        self.connection_manager: ConnectionManager = None  # 车次勾连管理器
        
        # 车次计数器
        self.table_num_counter = 1
        self.round_num_counter = 1
        
    def read_data(self) -> bool:
        """
        读取输入数据
        
        Returns:
            是否读取成功
        """
        try:
            print("\n[信息] 开始读取输入数据...")
            
            # 读取线路信息
            self.rail_info = DataReader.read_file(self.rail_info_file)
            print(f"[OK] 线路信息读取成功")
            print(f"  - 车站数: {len(self.rail_info.stationList)}")
            print(f"  - 路径数: {len(self.rail_info.pathList)}")
            
            # 初始化platform_station_map（必须在使用generateSinglePathSolution之前调用）
            self.rail_info.generate_platform_staiton_map()
            self.rail_info.generate_platform_occupation()
            print(f"[OK] 站台映射初始化完成")
            
            # 读取用户设置
            self.user_setting = DataReader.read_setting_file(self.user_setting_file)
            print(f"[OK] 用户设置读取成功")
            print(f"  - 峰期数: {len(self.user_setting.peaks)}")
            
            # 如果没有指定快车停站方案，自动生成
            if self.express_stop_stations is None:
                self._generate_express_stop_plan()
            
            # 初始化算法模块
            self._initialize_algorithms()
            
            return True
            
        except Exception as e:
            print(f"[ERROR] 读取数据失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def _initialize_algorithms(self):
        """
        初始化算法模块
        """
        try:
            # 创建快慢车配置
            config = ExpressLocalConfig(
                express_ratio=self.express_ratio,
                target_headway=self.target_headway,
                min_headway=120,
                max_headway=600,
                express_stop_ratio=0.6,
                express_skip_pattern=None,  # 将使用express_stop_stations
                min_overtaking_interval=120,
                min_overtaking_dwell=240,
                base_running_time_per_section=120,
                base_dwell_time=self.default_dwell_time,
                express_speed_factor=1.2,
                enable_short_route=self.enable_short_route,
                short_route_ratio=self.short_route_ratio
            )
            
            # 创建生成器
            self.generator = ExpressLocalGenerator(config)
            
            # 创建时刻表构建器
            self.builder = TimetableBuilder(self.rail_info)
            
            # 创建发车间隔优化器
            self.optimizer = HeadwayOptimizer(
                min_headway=config.min_headway,
                max_headway=config.max_headway,
                time_window=60  # 允许±60秒的调整范围
            )
            
            # 创建车次勾连管理器
            self.connection_manager = ConnectionManager(
                rail_info=self.rail_info,
                debug=self.debug
            )
            
            print(f"[OK] 算法模块初始化完成")
            print(f"  - 快车比例: {self.express_ratio*100:.0f}%")
            print(f"  - 目标发车间隔: {self.target_headway}秒")
            print(f"  - 小交路: {'启用' if self.enable_short_route else '禁用'}")
            print(f"  - 优化器: 线性规划 (CBC求解器)")
            
        except Exception as e:
            print(f"[WARNING] 算法模块初始化失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def _generate_express_stop_plan(self):
        """
        自动生成快车停站方案
        策略：只停首末站 + 中间均匀选择5个大站
        """
        try:
            # 获取第一个峰期的第一个路径
            peak = self.user_setting.peaks[0]
            route_id = peak.routes[0].up_route
            if not isinstance(route_id, str):
                route_id = str(route_id)
            
            if route_id not in self.rail_info.pathList:
                print(f"[WARNING] 无法获取路径{route_id}，使用默认停站方案")
                return
            
            path = self.rail_info.pathList[route_id]
            
            # 获取路径的所有站台码
            all_stations = path.nodeList  # Path对象的nodeList就是站台码列表
            
            total_stations = len(all_stations)
            
            if total_stations <= 7:
                # 如果站点太少，全部停靠
                self.express_stop_stations = all_stations
                print(f"[信息] 快车停站方案：全部{total_stations}站")
            else:
                # 首末站 + 中间5站
                express_stops = [all_stations[0]]  # 首站
                
                # 中间均匀选择5站
                middle_stations = all_stations[1:-1]  # 去掉首末站
                step = len(middle_stations) / 5
                for i in range(5):
                    idx = int(i * step)
                    if idx < len(middle_stations):
                        express_stops.append(middle_stations[idx])
                
                express_stops.append(all_stations[-1])  # 末站
                
                self.express_stop_stations = express_stops
                
                print(f"[信息] 快车停站方案：{len(express_stops)}/{total_stations}站")
                print(f"  停靠站台码: {express_stops}")
                
        except Exception as e:
            print(f"[WARNING] 生成快车停站方案失败: {str(e)}")
            # 失败时使用空列表，表示全站停
            self.express_stop_stations = []
    
    def get_next_table_num(self) -> int:
        """获取下一个表号"""
        num = self.table_num_counter
        self.table_num_counter += 1
        return num
    
    def get_next_round_num(self) -> int:
        """获取下一个车次号"""
        num = self.round_num_counter
        self.round_num_counter += 1
        return num
    
    def generate_express_local_timetable(self) -> bool:
        """
        使用优化算法生成快慢车运行图
        
        Returns:
            是否生成成功
        """
        try:
            print("\n[信息] 开始生成快慢车运行图（使用优化算法）...")
            
            # 获取第一个峰期的配置
            if not self.user_setting.peaks:
                print("[ERROR] 用户设置中没有峰期配置")
                return False
            
            peak = self.user_setting.peaks[0]
            
            print(f"  - 峰期时长: {peak.end_time - peak.start_time}秒 ({(peak.end_time - peak.start_time)/60:.1f}分钟)")
            print(f"  - 快车比例: {self.express_ratio*100:.0f}%")
            
            # 步骤1：使用ExpressLocalGenerator生成快慢车时刻表
            print("\n[信息] 步骤1/3: 使用优化算法生成快慢车方案...")
            self.timetable = self.generator.generate(
                rail_info=self.rail_info,
                user_setting=self.user_setting,
                start_time=peak.start_time,
                end_time=peak.end_time
            )
            
            print(f"[OK] 优化算法完成")
            print(f"  - 快车数: {self.timetable.express_trains_count}")
            print(f"  - 慢车数: {self.timetable.local_trains_count}")
            print(f"  - 总列车数: {self.timetable.total_trains}")
            
            # 步骤2：使用TimetableBuilder构建详细时刻表
            print("\n[信息] 步骤2/4: 构建详细时刻表...")
            self.timetable = self.builder.build_timetable(self.timetable)
            
            print(f"[OK] 时刻表构建完成")
            print(f"  - 时刻表条目数: {len(self.timetable.timetable_entries)}")
            
            # 步骤3：使用HeadwayOptimizer进行发车间隔优化（核心优化步骤）
            print("\n[信息] 步骤3/4: 发车间隔优化（使用CBC求解器）...")
            
            # 计算优化前的均衡性指标
            before_variance = self.timetable.calculate_headway_variance("上行")
            before_avg = self.timetable.calculate_average_headway("上行")
            before_score = self.optimizer.calculate_balance_score(self.timetable, "上行")
            
            print(f"  优化前:")
            print(f"    - 平均发车间隔: {before_avg:.1f}秒")
            print(f"    - 发车间隔方差: {before_variance:.1f}")
            print(f"    - 均衡性得分: {before_score:.3f}")
            
            # 执行线性规划优化
            optimization_result = self.optimizer.optimize(
                timetable=self.timetable,
                direction="上行",
                time_limit=300  # 5分钟求解时间限制
            )
            
            if optimization_result.success:
                print(f"  [OK] 优化成功（CBC求解器）")
                print(f"    - 目标函数值: {optimization_result.objective_value:.2f}")
                print(f"    - 平均发车间隔: {optimization_result.average_headway:.1f}秒")
                print(f"    - 发车间隔方差: {optimization_result.headway_variance:.1f}")
                
                # 应用优化结果
                self.timetable = self.optimizer.apply_optimization_result(
                    self.timetable, optimization_result
                )
                
                # 计算优化后的均衡性得分
                after_score = self.optimizer.calculate_balance_score(self.timetable, "上行")
                improvement = (after_score - before_score) / before_score * 100 if before_score > 0 else 0
                print(f"    - 优化后均衡性得分: {after_score:.3f} (提升{improvement:+.1f}%)")
            else:
                print(f"  [WARNING] 优化未成功: {optimization_result.message}")
                print(f"  将使用启发式算法的结果")
            
            # 验证时刻表
            issues = self.timetable.validate_timetable()
            if issues:
                print(f"[WARNING] 时刻表验证发现{len(issues)}个问题:")
                for issue in issues[:10]:  # 只显示前10个问题
                    print(f"  - {issue}")
            else:
                print(f"[OK] 时刻表验证通过")
            
            # 步骤4：转换为RouteSolution格式
            print("\n[信息] 步骤4/4: 转换为RouteSolution格式...")
            self.solution = self.convert_timetable_to_solution()
            
            print(f"[OK] 转换完成")
            print(f"  - RouteSolution数: {len(self.solution.route_lists)}")
            
            return True
            
        except Exception as e:
            print(f"[ERROR] 生成快慢车运行图失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def convert_timetable_to_solution(self) -> Solution:
        """
        将ExpressLocalTimetable转换为Solution对象
        
        这是连接优化算法和src输出接口的关键转换层
        
        主要步骤：
        1. 转换所有列车为RouteSolution对象
        2. 建立车次勾连关系（快车连快车，慢车连慢车）
        3. 分配表号
        
        Returns:
            Solution对象
        """
        try:
            solution = Solution(self.debug)
            route_solutions = []
            
            # 获取第一个峰期作为参考
            peak = self.user_setting.peaks[0]
            
            # 步骤1：转换所有列车为RouteSolution对象
            all_trains = self.timetable.express_trains + self.timetable.local_trains
            
            if self.debug:
                print(f"\n[转换] 开始转换 {len(all_trains)} 个列车...")
            
            for train in all_trains:
                # 根据列车属性获取正确的路径ID
                route_id = self._get_route_id_for_train(train, peak)
                
                if not route_id:
                    print(f"[WARNING] 无法获取列车{train.train_id}的路径ID")
                    continue
                
                # 获取路径对象
                if route_id not in self.rail_info.pathList:
                    print(f"[ERROR] 路径{route_id}不存在")
                    continue
                
                path = self.rail_info.pathList[route_id]
                
                # 【关键修复】直接根据path.nodeList生成RouteSolution
                # 不再使用timetable_builder生成的entries，因为其站台码可能与path不匹配
                rs = self._create_route_solution_from_path(train, route_id, path)
                
                if rs:
                    route_solutions.append(rs)
            
            if self.debug:
                print(f"[转换] 成功转换 {len(route_solutions)} 个列车")
            
            # 步骤2：建立车次勾连关系
            if self.debug:
                print(f"\n[勾连] 开始建立车次勾连...")
            
            route_solutions = self.connection_manager.connect_all_trains(route_solutions)
            
            # 步骤3：添加到Solution对象
            for rs in route_solutions:
                solution.addTrainService(rs)
            
            return solution
            
        except Exception as e:
            print(f"[ERROR] 转换时刻表失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return Solution(self.debug)
    
    def _create_route_solution_from_path(self, train: Train, route_id: str, path) -> RouteSolution:
        """
        直接根据path.nodeList创建RouteSolution
        
        这个方法完全根据路径的站台码序列生成RouteSolution，
        避免了timetable_builder生成的entries与path不匹配的问题。
        
        Args:
            train: 列车对象
            route_id: 路径ID
            path: 路径对象
            
        Returns:
            RouteSolution对象
        """
        try:
            if not path or not hasattr(path, 'nodeList') or not path.nodeList:
                print(f"[ERROR] 路径{route_id}没有nodeList")
                return None
            
            # 创建车辆信息
            table_num = self.get_next_table_num()
            round_num = self.get_next_round_num()
            route_num = int(route_id) if isinstance(route_id, str) else route_id
            
            # 创建RouteSolution
            dep_time = train.departure_time if train.departure_time else 0
            rs = RouteSolution(dep_time, table_num, round_num, route_num)
            
            # 设置方向
            if train.direction == "上行":
                rs.dir = 0
            elif train.direction == "下行":
                rs.dir = 1
            else:
                rs.dir = 0
            
            rs.operating = True
            
            # 设置快车标志
            is_express = isinstance(train, ExpressTrain)
            rs.is_express = is_express
            
            # 设置交路类型
            if isinstance(train, LocalTrain) and train.is_short_route:
                rs.xroad = 1  # 小交路
            else:
                rs.xroad = 0  # 大交路
            
            rs.phase = 0
            
            # 【关键】直接遍历path.nodeList（站台码列表）
            path_destcodes = path.nodeList
            current_time = dep_time
            
            for i, dest_code in enumerate(path_destcodes):
                # 判断该站台是否停站
                # 对于快车，检查是否在停站列表中
                # 对于慢车，全部停站（除了折返轨等虚拟站台）
                is_stop = self._should_stop_at_destcode(train, dest_code, i, len(path_destcodes))
                
                # 计算到站时间
                if i == 0:
                    # 首站：到站时间=发车时间
                    arrival_time = current_time
                else:
                    # 其他站：到站时间=上一站离站时间+运行时间
                    prev_dest = path_destcodes[i-1]
                    running_time = self._get_travel_time_between_destcodes(prev_dest, dest_code)
                    arrival_time = current_time + running_time
                
                # 计算停站时间
                if is_stop:
                    if i == 0 or i == len(path_destcodes) - 1:
                        dwell_time = 0  # 首末站不停站
                    else:
                        dwell_time = self.default_dwell_time
                else:
                    dwell_time = 0
                
                dep_time_at_station = arrival_time + dwell_time
                
                # 添加停站
                rs.addStop(
                    platform=dest_code,
                    stop_time=dwell_time,
                    perf_level=self.speed_level,
                    current_time=arrival_time,
                    dep_time=dep_time_at_station
                )
                
                # 更新当前时间
                current_time = dep_time_at_station
            
            return rs
            
        except Exception as e:
            print(f"[ERROR] 根据路径创建RouteSolution失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def _should_stop_at_destcode(self, train: Train, dest_code: str, index: int, total: int) -> bool:
        """
        判断列车是否在指定站台码停站
        
        Args:
            train: 列车对象
            dest_code: 站台目的地码
            index: 站台在路径中的索引
            total: 路径总站台数
            
        Returns:
            是否停站
        """
        # 首末站（折返轨）不停站
        if index == 0 or index == total - 1:
            # 检查是否是折返轨（通常以1结尾，如111, 112）
            if dest_code.endswith('1') or dest_code.endswith('2') or dest_code.endswith('3'):
                if len(dest_code) == 3:  # 如111, 112, 333等
                    return False
        
        # 对于快车，检查跳站设置
        if isinstance(train, ExpressTrain):
            # 根据dest_code查找对应的车站ID
            station_id = self._get_station_id_from_destcode(dest_code)
            
            if station_id:
                # 检查该车站是否在跳站列表中
                if station_id in train.skip_stations:
                    return False  # 快车跳过该站
                else:
                    return True  # 快车停靠该站
            else:
                # 找不到对应车站，默认停站
                return True
        
        # 慢车全部停站（除了折返轨）
        return True
    
    def _get_station_id_from_destcode(self, dest_code: str) -> Optional[str]:
        """
        根据站台目的地码查找对应的车站ID
        
        Args:
            dest_code: 站台目的地码
            
        Returns:
            车站ID，如果找不到返回None
        """
        # 遍历所有车站，查找包含该dest_code的站台
        for station_id, station in self.rail_info.stationList.items():
            for platform in station.platformList:
                if hasattr(platform, 'dest_code') and platform.dest_code == dest_code:
                    return station.id
        
        # 找不到对应的车站
        return None
    
    def _get_travel_time_between_destcodes(self, from_dest: str, to_dest: str) -> int:
        """
        获取两个站台码之间的运行时间
        
        Args:
            from_dest: 起始站台码
            to_dest: 目标站台码
            
        Returns:
            运行时间（秒）
        """
        # 尝试从rail_info获取
        key = f"{from_dest}_{to_dest}_{self.speed_level}"
        if key in self.rail_info.travel_time_map:
            return self.rail_info.travel_time_map[key]
        
        # 默认运行时间
        return 120
    
    def _adjust_entries_to_path(self, entries: List[TimetableEntry], 
                                path_destcodes: List[str], 
                                train: Train) -> List[TimetableEntry]:
        """
        调整时刻表条目以匹配路径的站台码序列
        
        当entries数量少于path_destcodes时，补充缺失的站台（通常是折返轨等虚拟站台）
        
        Args:
            entries: 原始时刻表条目列表
            path_destcodes: 路径的站台码列表
            train: 列车对象
            
        Returns:
            调整后的时刻表条目列表
        """
        from models.timetable_entry import TimetableEntry
        
        if len(entries) >= len(path_destcodes):
            # 如果entries更多，直接截断
            return entries[:len(path_destcodes)]
        
        # 如果entries少于path_destcodes，需要补充
        # 策略：找出path_destcodes中缺失的部分，通常是首站的折返轨或末站
        missing_count = len(path_destcodes) - len(entries)
        
        adjusted_entries = []
        
        # 检查是否是首站缺失（折返轨）
        # 假设：如果第一个entry的dest_code不等于path_destcodes[0]，说明首站有缺失
        first_entry = entries[0] if entries else None
        
        # 简化策略：在开头插入missing_count个站台
        # 使用首站的时间作为基准时间
        base_time = first_entry.arrival_time if first_entry else (train.departure_time if train.departure_time else 0)
        
        # 插入缺失的站台（通常是折返轨）
        for i in range(missing_count):
            dest_code = path_destcodes[i]
            
            # 创建虚拟entry（折返轨，停站时间=0）
            new_entry = TimetableEntry(
                train_id=train.train_id,
                station_id=dest_code,  # 使用dest_code作为临时station_id
                station_name=f"站台{dest_code}",
                arrival_time=base_time,  # 与首站同时间
                departure_time=base_time,  # 不停站
                dwell_time=0,
                is_stop=False,  # 折返轨不停站
                is_skip=True,
                platform_id=dest_code,
                dest_code=dest_code
            )
            adjusted_entries.append(new_entry)
            
            print(f"[DEBUG] 补充站台码 {dest_code}，时间={base_time}")
        
        # 追加原有的entries
        adjusted_entries.extend(entries)
        
        # 验证：检查调整后的entries是否与path_destcodes对齐
        if len(adjusted_entries) == len(path_destcodes):
            print(f"[INFO] 为列车{train.train_id}补充了{missing_count}个站台条目，当前总数={len(adjusted_entries)}")
        else:
            print(f"[WARNING] 调整后entries数量({len(adjusted_entries)})仍与path_destcodes({len(path_destcodes)})不一致")
        
        return adjusted_entries
    
    def _get_route_id_for_train(self, train: Train, peak) -> Optional[str]:
        """
        根据列车属性获取正确的路径ID
        
        Args:
            train: 列车对象
            peak: 峰期对象
            
        Returns:
            路径ID字符串，如果无法确定则返回None
        """
        try:
            # 确定方向：0=上行，1=下行
            if train.direction == "上行":
                dir_idx = 0
            elif train.direction == "下行":
                dir_idx = 1
            else:
                print(f"[WARNING] 列车{train.train_id}方向未知: {train.direction}")
                return None
            
            # 确定交路索引（xroad）
            # 快车和大交路慢车使用xroad=0（第一条交路）
            # 小交路慢车使用xroad=1（第二条交路，如果存在）
            if isinstance(train, ExpressTrain):
                xroad_idx = 0  # 快车使用大交路
            elif isinstance(train, LocalTrain) and train.is_short_route:
                # 小交路慢车
                if peak.has_route2 and len(peak.routes) > 1:
                    xroad_idx = 1  # 使用第二条交路
                else:
                    print(f"[WARNING] 小交路列车{train.train_id}但峰期没有第二条交路")
                    xroad_idx = 0  # 回退到第一条交路
            else:
                xroad_idx = 0  # 大交路慢车使用第一条交路
            
            # 从peak中获取路径ID
            if xroad_idx >= len(peak.routes):
                print(f"[ERROR] 交路索引{xroad_idx}超出范围，峰期只有{len(peak.routes)}条交路")
                return None
            
            route = peak.routes[xroad_idx]
            route_id = route.up_route if dir_idx == 0 else route.down_route
            
            # 确保route_id是字符串
            if not isinstance(route_id, str):
                route_id = str(route_id)
            
            return route_id
            
        except Exception as e:
            print(f"[ERROR] 获取列车{train.train_id}的路径ID失败: {str(e)}")
            return None
    
    def _create_route_solution_from_train(self,
                                          train: Train,
                                          entries: List[TimetableEntry],
                                          route_id: str,
                                          path) -> RouteSolution:
        """
        从Train和TimetableEntry创建RouteSolution
        
        Args:
            train: 列车对象
            entries: 时刻表条目列表
            route_id: 路径ID
            path: 路径对象
            
        Returns:
            RouteSolution对象
        """
        try:
            # 获取首站发车时间
            if not entries:
                return None
            
            first_entry = entries[0]
            dep_time = first_entry.departure_time
            
            # 创建车辆信息
            table_num = self.get_next_table_num()
            round_num = self.get_next_round_num()
            route_num = int(route_id) if isinstance(route_id, str) else route_id
            
            # 创建RouteSolution
            rs = RouteSolution(dep_time, table_num, round_num, route_num)
            
            # 设置方向：根据train.direction设置
            if train.direction == "上行":
                rs.dir = 0
            elif train.direction == "下行":
                rs.dir = 1
            else:
                rs.dir = 0  # 默认上行
            
            rs.operating = True
            
            # 设置快车标志
            is_express = isinstance(train, ExpressTrain)
            rs.is_express = is_express
            
            # 设置交路类型
            if isinstance(train, LocalTrain) and train.is_short_route:
                rs.xroad = 1  # 小交路
            else:
                rs.xroad = 0  # 大交路
            
            rs.phase = 0
            
            # 【关键修复】使用Path的nodeList（DestcodesOfPath）作为站台码序列
            # 这是XML中定义的该路径的完整站台目的地码列表
            if not path or not hasattr(path, 'nodeList') or not path.nodeList:
                print(f"[ERROR] 路径{route_id}没有nodeList，无法创建RouteSolution")
                return None
            
            path_destcodes = path.nodeList  # 路径的完整站台码列表
            
            # 【关键修复】当entries数量与path_destcodes不一致时，需要补充或插值
            if len(entries) != len(path_destcodes):
                print(f"[INFO] 列车{train.train_id}的时刻表条目数({len(entries)})与路径{route_id}的站台数({len(path_destcodes)})不一致，进行调整")
                entries = self._adjust_entries_to_path(entries, path_destcodes, train)
            
            # 添加所有站台（包括停站和跳站）
            # 使用path.nodeList中的站台码，确保与XML中的DestcodesOfPath完全一致
            for i, (entry, platform_code) in enumerate(zip(entries, path_destcodes)):
                # 对于跳站，到站时间=离站时间（表示通过不停）
                if entry.is_stop:
                    # 正常停站
                    rs.addStop(
                        platform=platform_code,  # 使用path.nodeList中的站台码
                        stop_time=entry.dwell_time,
                        perf_level=self.speed_level,
                        current_time=entry.arrival_time,
                        dep_time=entry.departure_time
                    )
                else:
                    # 跳站：到站时间=离站时间，停站时间=0
                    rs.addStop(
                        platform=platform_code,  # 使用path.nodeList中的站台码
                        stop_time=0,
                        perf_level=self.speed_level,
                        current_time=entry.arrival_time,
                        dep_time=entry.arrival_time  # 跳站时，离站=到站
                    )
            
            return rs
            
        except Exception as e:
            print(f"[ERROR] 创建RouteSolution失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def create_route_solution(self, route_id: str, dep_time: int, 
                            is_express: bool, direction: int) -> RouteSolution:
        """
        创建一个RouteSolution对象（手动构建，实现快车跳站）
        
        [已弃用] 此方法已被convert_timetable_to_solution替代
        
        Args:
            route_id: 路径ID（字符串）
            dep_time: 发车时间（秒）
            is_express: 是否为快车
            direction: 方向（0=上行, 1=下行）
            
        Returns:
            RouteSolution对象
        """
        try:
            # 创建车辆信息
            table_num = self.get_next_table_num()
            round_num = self.get_next_round_num()
            # 路径编号：使用实际的路径ID（整数），不能为0
            route_num = int(route_id) if isinstance(route_id, str) else route_id
            
            # 创建RouteSolution
            rs = RouteSolution(dep_time, table_num, round_num, route_num)
            rs.dir = direction
            rs.xroad = 0  # 0=大交路
            rs.phase = 0  # 第0阶段
            rs.operating = True
            rs.is_express = is_express
            
            # 获取路径
            if route_id not in self.rail_info.pathList:
                print(f"[ERROR] 路径{route_id}不存在")
                return None
            
            path = self.rail_info.pathList[route_id]
            
            # 手动构建运行方案
            current_time = dep_time
            
            # 遍历路径中的所有站点（nodeList是站台码列表）
            for i, station_code in enumerate(path.nodeList):
                # 判断是否停站
                if is_express:
                    # 快车：只在指定站点停车
                    should_stop = station_code in self.express_stop_stations
                else:
                    # 慢车：所有站都停
                    should_stop = True
                
                # 计算到达当前站的时间
                if i > 0:
                    # 获取区间运行时间
                    prev_code = path.nodeList[i - 1]
                    travel_time = self._get_travel_time(prev_code, station_code)
                    current_time += travel_time
                
                # 确定停站时间
                if should_stop:
                    # 首站只有发车时间，没有到达时间
                    # 末站只有到达时间，没有停站时间
                    if i == 0:
                        dwell_time = 0  # 首站不需要停站时间
                        arr_time = current_time
                        dep_time_at_station = current_time
                    elif i == len(path.nodeList) - 1:
                        dwell_time = 0  # 末站不需要停站时间
                        arr_time = current_time
                        dep_time_at_station = current_time
                    else:
                        dwell_time = self.default_dwell_time
                        arr_time = current_time
                        dep_time_at_station = current_time + dwell_time
                    
                    # 添加停站
                    rs.addStop(
                        platform=station_code,
                        stop_time=dwell_time,
                        perf_level=self.speed_level,
                        current_time=arr_time,
                        dep_time=dep_time_at_station
                    )
                    
                    # 更新当前时间
                    current_time = dep_time_at_station
                else:
                    # 不停站，直接通过（到站时间=离站时间，表示通过不停）
                    # 快车也要包含所有站台码，跳站时到站=离站时间
                    arr_time = current_time
                    dep_time_at_station = current_time  # 不停站：到站=离站
                    
                    rs.addStop(
                        platform=station_code,
                        stop_time=0,
                        perf_level=self.speed_level,
                        current_time=arr_time,
                        dep_time=dep_time_at_station
                    )
            
            return rs
            
        except Exception as e:
            print(f"[ERROR] 创建RouteSolution失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def _get_travel_time(self, from_station: str, to_station: str) -> int:
        """
        获取两站之间的运行时间
        
        Args:
            from_station: 起始站台码
            to_station: 目标站台码
            
        Returns:
            运行时间（秒）
        """
        key = f"{from_station}_{to_station}_{self.speed_level}"
        
        if key in self.rail_info.travel_time_map:
            return self.rail_info.travel_time_map[key]
        else:
            # 默认运行时间120秒
            return 120
    
    def write_output(self) -> bool:
        """
        输出Excel文件
        
        Returns:
            是否输出成功
        """
        try:
            print("\n[信息] 开始输出Excel文件...")
            
            # 确保输出目录存在
            output_path = Path(self.output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # 重新编号路线（基于规则的算法）
            self.solution.renumb_routes()
            
            # 修改每个RouteSolution的retCSVStringPlanned_num方法，设置正确的快车标志位
            self._patch_express_flag()
            
            # 调用Solution的writeExcel方法
            self.solution.writeExcel(self.output_dir, self.rail_info, "gbk")
            
            print(f"[OK] Excel文件已生成: {self.output_dir}/result.xls")
            
            # 转换为xlsx格式
            self.convert_to_xlsx(self.output_dir)
            print(f"[OK] XLSX文件已生成: {self.output_dir}/result.xlsx")
            
            return True
            
        except Exception as e:
            print(f"[ERROR] 输出Excel文件失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def _patch_express_flag(self):
        """
        为每个RouteSolution动态修改retCSVStringPlanned_num方法
        使其返回正确的快车标志位和路径编号
        
        重要：确保路径编号(route_num)正确输出，否则无法加载运行图
        """
        for rs in self.solution.route_lists:
            is_express = getattr(rs, 'is_express', False)
            
            # 保存原始的car_info引用
            car_info = rs.car_info
            dep_time = rs.dep_time
            operating = rs.operating
            
            # 验证route_num是否为0（常见错误）
            if car_info.route_num == 0:
                print(f"[WARNING] 列车{car_info.table_num}的路径编号为0，这可能导致加载失败")
            
            # 创建新的方法
            def make_method(is_exp, ci, dt, op):
                def new_retCSVStringPlanned_num():
                    components = [
                        str(ci.table_num),      # 表号
                        str(ci.round_num),      # 车次号
                        str(ci.route_num),      # 路径编号（关键！）
                        str(dt[0]),             # 发车时间
                        "1",                    # 自动车次号
                        "1" if is_exp else "0", # 快车标志：快车=1，慢车=0
                        "1 1" if op else "0 1"  # 载客和列车编号
                    ]
                    return " ".join(components)
                return new_retCSVStringPlanned_num
            
            # 替换方法
            rs.retCSVStringPlanned_num = make_method(is_express, car_info, dep_time, operating)
    
    def convert_to_xlsx(self, output_dir: str):
        """
        将xls文件转换为xlsx格式（从src/Engineering.py复制）
        
        Args:
            output_dir: 输出目录
        """
        import pandas as pd
        
        input_path = os.path.join(output_dir, "result.xls")
        output_path = os.path.join(output_dir, "result.xlsx")
        
        try:
            # 读取原始xls文件中的所有sheet页
            excel_file = pd.ExcelFile(input_path)
            sheet_names = excel_file.sheet_names
            
            # 创建ExcelWriter对象
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                # 遍历所有sheet页并保持原有名称
                for sheet_name in sheet_names:
                    # 读取当前sheet页的数据
                    df = pd.read_excel(input_path, sheet_name=sheet_name, dtype=str)
                    
                    # 写入数据，保持原有sheet名称
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    
                    # 获取当前工作表
                    worksheet = writer.sheets[sheet_name]
                    
                    # 调整列宽以匹配原始文件
                    for idx, col in enumerate(df.columns):
                        max_length = max(df[col].astype(str).apply(len).max(), len(str(col)))
                        if idx < 26:  # 只处理A-Z列
                            worksheet.column_dimensions[chr(65 + idx)].width = max_length + 2
            
            print(f"[OK] XLS转XLSX完成")
            
        except Exception as e:
            print(f"[WARNING] XLS转XLSX失败: {str(e)}")
            # 转换失败不影响主流程
    
    def run(self) -> bool:
        """
        执行完整的调度流程
        
        Returns:
            是否执行成功
        """
        start_time = time.time()
        
        print("="*60)
        print("快慢车运行图自动编制程序 V3")
        print("="*60)
        
        # 1. 读取数据
        if not self.read_data():
            return False
        
        # 2. 生成快慢车运行图
        if not self.generate_express_local_timetable():
            return False
        
        # 3. 输出Excel
        if not self.write_output():
            return False
        
        elapsed_time = time.time() - start_time
        print("\n" + "="*60)
        print(f"[OK] 快慢车运行图编制完成！")
        print(f"耗时: {elapsed_time:.2f}秒")
        print("="*60)
        
        return True


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='快慢车运行图自动编制程序 V3')
    
    # 输入文件参数
    parser.add_argument('--rail_info', type=str,
                      default='../data/input_data_new/RailwayInfo/Schedule-cs2.xml',
                      help='线路信息文件路径')
    parser.add_argument('--user_setting', type=str,
                      default='../data/input_data_new/UserSettingInfoNew/cs2_real_28.xml',
                      help='用户设置文件路径')
    parser.add_argument('--output', type=str,
                      default='../data/output_data/results_express_local_v3',
                      help='输出目录')
    
    # 快慢车参数
    parser.add_argument('--express_ratio', type=float, default=0.5,
                      help='快车比例（0-1，默认0.5）')
    parser.add_argument('--target_headway', type=int, default=180,
                      help='目标发车间隔（秒，默认180）')
    parser.add_argument('--speed_level', type=int, default=1,
                      help='速度等级（默认1）')
    parser.add_argument('--dwell_time', type=int, default=30,
                      help='默认停站时间（秒，默认30）')
    parser.add_argument('--express_stops', type=str, default=None,
                      help='快车停站方案（站台码列表，逗号分隔，如"111,222,333"）')
    
    # 大小交路参数
    parser.add_argument('--enable_short_route', type=bool, default=True,
                      help='是否启用小交路（默认True）')
    parser.add_argument('--short_route_ratio', type=float, default=0.5,
                      help='小交路比例（相对于慢车，0-1，默认0.5）')
    
    # 调试参数
    parser.add_argument('--debug', action='store_true',
                      help='开启调试模式')
    
    args = parser.parse_args()
    
    # 解析快车停站方案
    express_stop_stations = None
    if args.express_stops:
        express_stop_stations = args.express_stops.split(',')
    
    # 创建调度器
    scheduler = ExpressLocalSchedulerV3(
        rail_info_file=args.rail_info,
        user_setting_file=args.user_setting,
        output_dir=args.output,
        express_ratio=args.express_ratio,
        target_headway=args.target_headway,
        speed_level=args.speed_level,
        default_dwell_time=args.dwell_time,
        express_stop_stations=express_stop_stations,
        enable_short_route=args.enable_short_route,
        short_route_ratio=args.short_route_ratio,
        debug=args.debug
    )
    
    # 运行
    success = scheduler.run()
    
    # 返回退出代码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
