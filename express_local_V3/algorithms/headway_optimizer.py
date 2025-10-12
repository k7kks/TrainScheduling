"""
发车间隔优化器

基于线性规划优化发车间隔均衡性
这是快慢车运行图的核心目标函数
"""

from typing import List, Dict, Tuple, Optional
import pulp
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
from models.train import Train


@dataclass
class HeadwayOptimizationResult:
    """发车间隔优化结果"""
    success: bool                           # 是否优化成功
    objective_value: float                  # 目标函数值
    optimized_departures: Dict[str, int]    # 优化后的发车时间
    headway_variance: float                 # 发车间隔方差
    average_headway: float                  # 平均发车间隔
    message: str = ""                       # 消息


class HeadwayOptimizer:
    """
    发车间隔优化器
    
    通过线性规划优化发车时间，最小化发车间隔的不均衡性
    目标函数：min Σ (h_i - h_avg)^2
    其中 h_i 是相邻列车的发车间隔，h_avg 是平均发车间隔
    """
    
    def __init__(self,
                 min_headway: int = 120,
                 max_headway: int = 600,
                 time_window: int = 60):
        """
        初始化优化器
        
        Args:
            min_headway: 最小发车间隔（秒）
            max_headway: 最大发车间隔（秒）
            time_window: 发车时间调整窗口（秒）
        """
        self.min_headway = min_headway
        self.max_headway = max_headway
        self.time_window = time_window
    
    def optimize(self, 
                 timetable: ExpressLocalTimetable,
                 direction: str = "上行",
                 time_limit: int = 300) -> HeadwayOptimizationResult:
        """
        优化发车间隔
        
        Args:
            timetable: 快慢车时刻表
            direction: 方向
            time_limit: 求解时间限制（秒）
            
        Returns:
            优化结果
        """
        # 获取指定方向的所有列车
        trains = [t for t in timetable.express_trains + timetable.local_trains
                 if t.direction == direction and t.departure_time is not None]
        
        if len(trains) < 2:
            return HeadwayOptimizationResult(
                success=False,
                objective_value=0.0,
                optimized_departures={},
                headway_variance=0.0,
                average_headway=0.0,
                message="列车数量不足，无需优化"
            )
        
        # 按发车时间排序
        trains.sort(key=lambda t: t.departure_time)
        
        # 创建优化模型
        model = pulp.LpProblem("Headway_Optimization", pulp.LpMinimize)
        
        # 决策变量：每列车的发车时间
        departure_vars = {}
        for train in trains:
            # 在原发车时间前后time_window范围内调整
            lower_bound = train.departure_time - self.time_window
            upper_bound = train.departure_time + self.time_window
            
            departure_vars[train.train_id] = pulp.LpVariable(
                f"dep_{train.train_id}",
                lowBound=lower_bound,
                upBound=upper_bound,
                cat='Continuous'
            )
        
        # 辅助变量：发车间隔
        headway_vars = {}
        for i in range(len(trains) - 1):
            train_i = trains[i]
            train_j = trains[i + 1]
            headway_vars[f"{train_i.train_id}_{train_j.train_id}"] = pulp.LpVariable(
                f"headway_{train_i.train_id}_{train_j.train_id}",
                lowBound=self.min_headway,
                upBound=self.max_headway,
                cat='Continuous'
            )
        
        # 辅助变量：平均发车间隔
        avg_headway_var = pulp.LpVariable("avg_headway", cat='Continuous')
        
        # 辅助变量：发车间隔偏差（绝对值）
        headway_deviation_vars = {}
        for key in headway_vars.keys():
            headway_deviation_vars[f"{key}_pos"] = pulp.LpVariable(
                f"dev_{key}_pos", lowBound=0, cat='Continuous'
            )
            headway_deviation_vars[f"{key}_neg"] = pulp.LpVariable(
                f"dev_{key}_neg", lowBound=0, cat='Continuous'
            )
        
        # 约束1：发车间隔定义
        for i in range(len(trains) - 1):
            train_i = trains[i]
            train_j = trains[i + 1]
            key = f"{train_i.train_id}_{train_j.train_id}"
            
            model += (
                headway_vars[key] == departure_vars[train_j.train_id] - departure_vars[train_i.train_id],
                f"headway_def_{key}"
            )
        
        # 约束2：平均发车间隔定义
        if len(trains) > 1:
            total_headway = pulp.lpSum([headway_vars[key] for key in headway_vars.keys()])
            model += (
                avg_headway_var == total_headway / len(headway_vars),
                "avg_headway_def"
            )
        
        # 约束3：发车间隔偏差定义（使用绝对值的线性化）
        for key in headway_vars.keys():
            model += (
                headway_vars[key] - avg_headway_var == 
                headway_deviation_vars[f"{key}_pos"] - headway_deviation_vars[f"{key}_neg"],
                f"deviation_def_{key}"
            )
        
        # 约束4：保持列车顺序（可选，如果需要保持原有顺序）
        for i in range(len(trains) - 1):
            train_i = trains[i]
            train_j = trains[i + 1]
            model += (
                departure_vars[train_j.train_id] >= departure_vars[train_i.train_id] + self.min_headway,
                f"order_{train_i.train_id}_{train_j.train_id}"
            )
        
        # 目标函数：最小化发车间隔偏差的平方和（使用线性化近似）
        # min Σ |h_i - h_avg|
        objective = pulp.lpSum([
            headway_deviation_vars[f"{key}_pos"] + headway_deviation_vars[f"{key}_neg"]
            for key in headway_vars.keys()
        ])
        
        model += objective
        
        # 求解
        solver = pulp.PULP_CBC_CMD(msg=1, timeLimit=time_limit)
        status = model.solve(solver)
        
        # 解析结果
        if status == pulp.LpStatusOptimal:
            optimized_departures = {
                train_id: int(var.varValue)
                for train_id, var in departure_vars.items()
            }
            
            # 计算优化后的统计指标
            headways = []
            sorted_train_ids = sorted(optimized_departures.keys(), 
                                    key=lambda tid: optimized_departures[tid])
            
            for i in range(len(sorted_train_ids) - 1):
                h = optimized_departures[sorted_train_ids[i+1]] - optimized_departures[sorted_train_ids[i]]
                headways.append(h)
            
            avg_headway = sum(headways) / len(headways) if headways else 0.0
            headway_variance = (sum((h - avg_headway) ** 2 for h in headways) / len(headways)
                              if headways else 0.0)
            
            return HeadwayOptimizationResult(
                success=True,
                objective_value=pulp.value(model.objective),
                optimized_departures=optimized_departures,
                headway_variance=headway_variance,
                average_headway=avg_headway,
                message="优化成功"
            )
        else:
            return HeadwayOptimizationResult(
                success=False,
                objective_value=0.0,
                optimized_departures={},
                headway_variance=0.0,
                average_headway=0.0,
                message=f"优化失败，状态: {pulp.LpStatus[status]}"
            )
    
    def apply_optimization_result(self,
                                  timetable: ExpressLocalTimetable,
                                  result: HeadwayOptimizationResult) -> ExpressLocalTimetable:
        """
        将优化结果应用到时刻表
        
        Args:
            timetable: 原时刻表
            result: 优化结果
            
        Returns:
            更新后的时刻表
        """
        if not result.success:
            return timetable
        
        # 更新列车发车时间
        for train_id, new_departure in result.optimized_departures.items():
            train = timetable.get_train(train_id)
            if train is not None:
                # 计算时间偏移
                time_offset = new_departure - train.departure_time
                
                # 更新发车和到达时间
                train.departure_time = new_departure
                if train.arrival_time is not None:
                    train.arrival_time += time_offset
                
                # 更新时刻表条目
                entries = timetable.get_train_schedule(train_id)
                for entry in entries:
                    entry.arrival_time += time_offset
                    entry.departure_time += time_offset
        
        return timetable
    
    def calculate_balance_score(self, timetable: ExpressLocalTimetable, direction: str = "上行") -> float:
        """
        计算发车间隔均衡性得分
        
        得分 = 1 / (1 + normalized_variance)
        得分越接近1，均衡性越好
        
        Args:
            timetable: 时刻表
            direction: 方向
            
        Returns:
            均衡性得分 [0, 1]
        """
        variance = timetable.calculate_headway_variance(direction)
        avg_headway = timetable.calculate_average_headway(direction)
        
        if avg_headway == 0:
            return 0.0
        
        # 归一化方差
        normalized_variance = variance / (avg_headway ** 2)
        
        # 计算得分
        score = 1.0 / (1.0 + normalized_variance)
        
        return score

