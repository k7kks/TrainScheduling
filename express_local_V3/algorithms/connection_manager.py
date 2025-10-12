"""
快慢车车次勾连管理器

参考src/Engineering.py中的Phase2和Phase3逻辑
实现车次之间的勾连（使相邻车次共享相同的表号）

核心功能：
1. Phase2：同一时段内的车次勾连（通过平移找最佳方案）
2. 连接验证：检查折返约束是否满足
3. 表号分配：为勾连的车次分配相同的表号

作者：AI Assistant
日期：2025-10-12
"""

from typing import List, Dict, Optional, Tuple
import sys
import os

# 添加src目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
src_dir = os.path.join(project_root, 'src')
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from RouteSolution import RouteSolution
from RailInfo import RailInfo


class ConnectionManager:
    """
    车次勾连管理器
    
    负责建立车次之间的连接关系（next_ptr/prev_ptr）
    并分配相同的表号（table_num）
    """
    
    def __init__(self, rail_info: RailInfo, debug: bool = False):
        """
        初始化勾连管理器
        
        Args:
            rail_info: 线路信息对象
            debug: 是否开启调试模式
        """
        self.rail_info = rail_info
        self.debug = debug
        
    def connect_all_trains(self, route_solutions: List[RouteSolution]) -> List[RouteSolution]:
        """
        连接所有车次
        
        主流程：
        1. 按照方向和是否快车分组
        2. Phase2: 在同一组内建立勾连
        3. 分配表号
        
        Args:
            route_solutions: RouteSolution对象列表
            
        Returns:
            建立了勾连关系的RouteSolution列表
        """
        if not route_solutions:
            return route_solutions
            
        if self.debug:
            print("\n[ConnectionManager] 开始车次勾连...")
            print(f"总车次数: {len(route_solutions)}")
        
        # 步骤1：按方向、是否快车、交路类型分组
        grouped_trains = self._group_trains(route_solutions)
        
        if self.debug:
            for key, trains in grouped_trains.items():
                print(f"分组 {key}: {len(trains)} 个车次")
        
        # 步骤2：对每组独立进行勾连
        for group_key, trains in grouped_trains.items():
            if len(trains) < 2:
                if self.debug:
                    print(f"[{group_key}] 车次数少于2，跳过勾连")
                continue
                
            if self.debug:
                print(f"\n[{group_key}] 开始勾连 {len(trains)} 个车次...")
            
            # Phase2：尝试连接车次（不移位，简化版）
            self._connect_within_group(trains)
        
        # 步骤3：分配表号
        self._assign_table_numbers(route_solutions)
        
        if self.debug:
            print("\n[ConnectionManager] 勾连完成")
            self._print_connection_summary(route_solutions)
        
        return route_solutions
    
    def _group_trains(self, route_solutions: List[RouteSolution]) -> Dict[str, List[RouteSolution]]:
        """
        将车次按照方向、是否快车、交路类型分组
        
        快车只能连快车，慢车只能连慢车
        大交路和小交路分开处理
        
        Args:
            route_solutions: RouteSolution对象列表
            
        Returns:
            分组后的字典 {group_key: [RouteSolution列表]}
        """
        grouped = {}
        
        for rs in route_solutions:
            # 生成分组键：快慢类型_交路类型
            is_express = rs.is_express if hasattr(rs, 'is_express') else False
            xroad = rs.xroad if hasattr(rs, 'xroad') else 0
            
            train_type = "express" if is_express else "local"
            route_type = f"xroad{xroad}"
            
            group_key = f"{train_type}_{route_type}"
            
            if group_key not in grouped:
                grouped[group_key] = []
            
            grouped[group_key].append(rs)
        
        # 对每组按照首站到达时间排序（使用arr_time[0]而不是car_info.arr_time）
        for trains in grouped.values():
            trains.sort(key=lambda x: x.arr_time[0] if x.arr_time else 0)
        
        return grouped
    
    def _connect_within_group(self, trains: List[RouteSolution]) -> None:
        """
        在同一组内建立勾连
        
        改进策略：
        1. 将车次按方向分开
        2. 对每个上行车，找能连接的最近下行车
        3. 对每个下行车，找能连接的最近上行车
        4. 使用贪心算法，优先连接折返时间最短的配对
        
        Args:
            trains: 同一组的车次列表（已按时间排序）
        """
        # 将车次按方向分开
        uplink_trains = [t for t in trains if t.dir == 0]  # 上行
        downlink_trains = [t for t in trains if t.dir == 1]  # 下行
        
        if self.debug:
            print(f"  上行车次: {len(uplink_trains)}")
            print(f"  下行车次: {len(downlink_trains)}")
        
        # 按首站到达时间排序
        uplink_trains.sort(key=lambda x: x.arr_time[0] if x.arr_time else 0)
        downlink_trains.sort(key=lambda x: x.arr_time[0] if x.arr_time else 0)
        
        connections_made = 0
        
        # 策略1: 为每个上行车找最佳下行车
        for up_train in uplink_trains:
            if up_train.next_ptr is not None:
                continue  # 已连接
            
            up_end_time = up_train.dep_time[-1] if up_train.dep_time else 0
            
            # 找首站到达时间晚于up_end_time的所有下行车
            candidates = []
            for down_train in downlink_trains:
                if down_train.prev_ptr is not None:
                    continue  # 已被连接
                
                down_start_time = down_train.arr_time[0] if down_train.arr_time else 0
                turnback_time = down_start_time - up_end_time
                
                # 折返时间必须为正且在合理范围内
                if turnback_time >= 30 and turnback_time <= 1800:  # 30秒到30分钟
                    if self._can_connect(up_train, down_train):
                        candidates.append((down_train, turnback_time))
            
            # 选择折返时间最短的
            if candidates:
                candidates.sort(key=lambda x: x[1])
                best_down, best_turnback = candidates[0]
                
                up_train.next_ptr = best_down
                best_down.prev_ptr = up_train
                connections_made += 1
                
                if self.debug:
                    print(f"  连接: 上行车{up_train.car_info.table_num} -> 下行车{best_down.car_info.table_num} "
                          f"(折返{best_turnback}秒={best_turnback//60}分{best_turnback%60}秒)")
        
        # 策略2: 为每个下行车找最佳上行车（处理剩余未连接的下行车）
        for down_train in downlink_trains:
            if down_train.next_ptr is not None:
                continue  # 已连接
            
            down_end_time = down_train.dep_time[-1] if down_train.dep_time else 0
            
            # 找首站到达时间晚于down_end_time的所有上行车
            candidates = []
            for up_train in uplink_trains:
                if up_train.prev_ptr is not None:
                    continue  # 已被连接
                
                up_start_time = up_train.arr_time[0] if up_train.arr_time else 0
                turnback_time = up_start_time - down_end_time
                
                # 折返时间必须为正且在合理范围内
                if turnback_time >= 30 and turnback_time <= 1800:
                    if self._can_connect(down_train, up_train):
                        candidates.append((up_train, turnback_time))
            
            # 选择折返时间最短的
            if candidates:
                candidates.sort(key=lambda x: x[1])
                best_up, best_turnback = candidates[0]
                
                down_train.next_ptr = best_up
                best_up.prev_ptr = down_train
                connections_made += 1
                
                if self.debug:
                    print(f"  连接: 下行车{down_train.car_info.table_num} -> 上行车{best_up.car_info.table_num} "
                          f"(折返{best_turnback}秒={best_turnback//60}分{best_turnback%60}秒)")
        
        if self.debug:
            print(f"  建立了 {connections_made} 个勾连")
    
    def _can_connect(self, from_train: RouteSolution, to_train: RouteSolution) -> bool:
        """
        检查两个车次是否可以勾连
        
        勾连条件：
        1. from_train还没有后续车次
        2. to_train还没有前序车次
        3. from_train的终点站和to_train的起点站匹配（或在同一折返区域）
        4. 折返时间满足约束
        
        Args:
            from_train: 前序车次
            to_train: 后续车次
            
        Returns:
            True表示可以勾连，False表示不能勾连
        """
        # 条件1: 不能已经有连接
        if from_train.next_ptr is not None:
            return False
        if to_train.prev_ptr is not None:
            return False
        
        # 条件2: 方向必须相反
        if from_train.dir == to_train.dir:
            return False
        
        # 条件3: 交路类型必须相同
        from_xroad = from_train.xroad if hasattr(from_train, 'xroad') else 0
        to_xroad = to_train.xroad if hasattr(to_train, 'xroad') else 0
        if from_xroad != to_xroad:
            return False
        
        # 条件4: 检查时间约束
        # from_train的最后离站时间
        from_departure = from_train.dep_time[-1] if from_train.dep_time else from_train.car_info.arr_time
        
        # to_train的首站到达时间
        to_arrival = to_train.arr_time[0] if to_train.arr_time else to_train.car_info.arr_time
        
        # 折返时间
        turnback_time = to_arrival - from_departure
        
        # 检查折返时间是否在合理范围内
        # 参考src中的逻辑：折返时间应该在[min_tb, max_tb + buffer]范围内
        # 放宽约束：至少需要30秒，最多不超过30分钟
        min_turnback = 30    # 最少30秒（放宽）
        max_turnback = 1800  # 最多30分钟（放宽）
        
        # 尝试获取实际的折返时间约束
        min_tb, max_tb = self._get_turnback_time_constraint(from_train, to_train)
        if min_tb is not None and max_tb is not None:
            min_turnback = min_tb
            max_turnback = max_tb + 300  # 给一些buffer
        
        if turnback_time < min_turnback:
            if self.debug:
                print(f"    折返时间不足: {turnback_time}s < {min_turnback}s")
            return False
        
        if turnback_time > max_turnback:
            if self.debug:
                print(f"    折返时间过长: {turnback_time}s > {max_turnback}s")
            return False
        
        # 条件5: 检查站台匹配
        # from_train的最后一个站台应该和to_train的第一个站台在同一折返区域
        if not self._check_platform_compatibility(from_train, to_train):
            if self.debug:
                print(f"    站台不兼容")
            return False
        
        return True
    
    def _get_turnback_time_constraint(self, from_train: RouteSolution, to_train: RouteSolution) -> Tuple[Optional[int], Optional[int]]:
        """
        获取折返时间约束
        
        Args:
            from_train: 前序车次
            to_train: 后续车次
            
        Returns:
            (min_turnback_time, max_turnback_time)，如果无法获取则返回(None, None)
        """
        try:
            # 获取from_train的最后一个站台
            # RouteSolution使用stopped_platforms属性
            if not hasattr(from_train, 'stopped_platforms') or not from_train.stopped_platforms:
                return None, None
            
            last_platform = from_train.stopped_platforms[-1]
            
            # 从rail_info中查找该站台的折返信息
            if last_platform in self.rail_info.turnbackList:
                turnback = self.rail_info.turnbackList[last_platform]
                return turnback.min_tb_time, turnback.max_tb_time
            
            return None, None
            
        except Exception as e:
            if self.debug:
                print(f"    获取折返时间约束失败: {e}")
            return None, None
    
    def _check_platform_compatibility(self, from_train: RouteSolution, to_train: RouteSolution) -> bool:
        """
        检查两个车次的站台是否兼容（可以在同一折返区域折返）
        
        Args:
            from_train: 前序车次
            to_train: 后续车次
            
        Returns:
            True表示兼容，False表示不兼容
        """
        try:
            # 获取站台（使用stopped_platforms属性）
            if not hasattr(from_train, 'stopped_platforms') or not hasattr(to_train, 'stopped_platforms'):
                return False
            
            if not from_train.stopped_platforms or not to_train.stopped_platforms:
                return False
            
            from_last_platform = from_train.stopped_platforms[-1]
            to_first_platform = to_train.stopped_platforms[0]
            
            # 简化判断：如果两个站台的前缀相同（同一车站），则认为兼容
            # 例如：111和114都是车站11的站台
            from_station = from_last_platform[:2] if len(from_last_platform) >= 2 else from_last_platform
            to_station = to_first_platform[:2] if len(to_first_platform) >= 2 else to_first_platform
            
            # 如果在同一车站，则兼容
            if from_station == to_station:
                return True
            
            # 否则检查是否有折返信息
            # 如果from_last_platform有折返配置，说明可以折返
            if from_last_platform in self.rail_info.turnbackList:
                return True
            
            return False
            
        except Exception as e:
            if self.debug:
                print(f"    检查站台兼容性失败: {e}")
            return False
    
    def _assign_table_numbers(self, route_solutions: List[RouteSolution]) -> None:
        """
        为所有车次分配表号
        
        勾连的车次将获得相同的表号
        
        Args:
            route_solutions: RouteSolution对象列表
        """
        if self.debug:
            print("\n[ConnectionManager] 分配表号...")
        
        connected = {}  # {table_num: round_num}
        assigned_count = 0
        
        for rs in route_solutions:
            # 如果这个车次还没有被分配表号（通过连接）
            if rs.car_info.table_num not in connected:
                try:
                    self._connect_routes_recursive(rs, connected)
                    assigned_count += 1
                except Exception as e:
                    if self.debug:
                        print(f"  警告: 分配表号失败: {e}")
                    continue
        
        if self.debug:
            print(f"  共分配了 {assigned_count} 个独立表号")
            print(f"  共有 {len(connected)} 个不同的表号")
    
    def _connect_routes_recursive(self, rs: RouteSolution, connected: Dict[int, int]) -> int:
        """
        递归地为勾连的车次分配相同的表号
        
        参考src/Engineering.py中的connect_routes方法
        
        Args:
            rs: 当前车次
            connected: 已连接的车次字典 {table_num: round_num}
            
        Returns:
            表号
        """
        if rs.next_ptr is not None:
            # 如果后续车次已经被分配了表号
            if rs.next_ptr.car_info.table_num in connected:
                # 使用后续车次的表号
                rs.car_info.table_num = rs.next_ptr.car_info.table_num
                rs.car_info.round_num = connected[rs.next_ptr.car_info.table_num]
                connected[rs.car_info.table_num] = rs.car_info.round_num + 1
                return rs.car_info.table_num
            else:
                # 递归处理后续车次
                table_num = self._connect_routes_recursive(rs.next_ptr, connected)
                rs.car_info.table_num = table_num
                rs.car_info.round_num = connected[table_num]
                connected[rs.car_info.table_num] = rs.car_info.round_num + 1
                return table_num
        else:
            # 这是链的末端，使用自己的表号
            table_num = rs.car_info.table_num
            connected[table_num] = rs.car_info.round_num + 1
            return table_num
    
    def _print_connection_summary(self, route_solutions: List[RouteSolution]) -> None:
        """
        打印勾连摘要信息
        
        Args:
            route_solutions: RouteSolution对象列表
        """
        # 统计勾连情况
        total_trains = len(route_solutions)
        connected_trains = 0
        connection_chains = {}  # {table_num: [车次列表]}
        
        for rs in route_solutions:
            table_num = rs.car_info.table_num
            if table_num not in connection_chains:
                connection_chains[table_num] = []
            connection_chains[table_num].append(rs)
            
            if rs.next_ptr is not None or rs.prev_ptr is not None:
                connected_trains += 1
        
        print(f"\n勾连摘要:")
        print(f"  总车次数: {total_trains}")
        print(f"  参与勾连的车次: {connected_trains}")
        print(f"  独立表号数: {len(connection_chains)}")
        
        # 找出最长的勾连链
        max_chain_length = max(len(chain) for chain in connection_chains.values())
        print(f"  最长勾连链: {max_chain_length} 个车次")
        
        # 统计勾连链长度分布
        chain_length_dist = {}
        for chain in connection_chains.values():
            length = len(chain)
            chain_length_dist[length] = chain_length_dist.get(length, 0) + 1
        
        print(f"  勾连链长度分布:")
        for length in sorted(chain_length_dist.keys(), reverse=True):
            count = chain_length_dist[length]
            print(f"    {length}个车次: {count}条链")

