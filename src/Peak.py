from typing import List, Dict
from Route import Route

class Peak:
    """
    表示列车调度系统中的高峰期,
    包括运营路线、速率、列车数量、时间间隔,
    以及用于计算高峰期间列车间隔的逻辑。
    """
    
    def __init__(self, peak_time_start_: str, peak_time_end_: str,
                 route_cat1_: int, up_route1_: str, dn_route1_: str,
                 route_cat2_: int, up_route2_: str, dn_route2_: str,
                 or_rate1_: str, or_rate2_: str, perf_lvl_: str,
                 train_num_: str,train_num1_: str,train_num2_: str, interval_: str, forbid: bool):
        """
        初始化Peak对象
        Args:
            peak_time_start_: 高峰期开始时间
            peak_time_end_: 高峰期结束时间
            route_cat1_: 路线1类别
            up_route1_: 路线1上行
            dn_route1_: 路线1下行
            route_cat2_: 路线2类别
            up_route2_: 路线2上行
            dn_route2_: 路线2下行
            or_rate1_: 开行比例1
            or_rate2_: 开行比例2
            perf_lvl_: 运行性能等级
            train_num_: 列车数量
            interval_: 间隔时间
            forbid: 是否禁止车库
            train_num1：路线1的用车数量
            train_num2：路线1的用车数量
        """
        # 高峰期的开始和结束时间(整数格式,如从午夜开始的分钟数)
        self.start_time: int = int(peak_time_start_)
        self.end_time: int = int(peak_time_end_)
        self.route_cat1_: int = route_cat1_
        self.route_cat2_: int = route_cat2_
        # 此高峰期内活跃的路线列表
        self.routes: List[Route] = []
        
        self.has_route2: bool = False
        
        self.op_rate1: int = 1
        self.op_rate2: int = 0
        
        self.op_lvl: str = ""
        
        self.use_interval: bool = False
        self.train_num: int = 0
        self.up_train_num: int = 0
        self.dn_train_num: int = 0
        self.train_num1:int = 0
        self.train_num2:int = 0
        self.interval: int = 0
        
        self.interval_up: int = 0
        self.interval_dn: int = 0
        
        self.transition_start: int = -1
        
        self.turnback_time_up_rt1: int = 0
        self.turnback_time_dn_rt1: int = 0
        
        self.forbiden_depot: bool = forbid
        
        self.turn_back_time: Dict[str, int] = {}
        
        # 初始化路线
        self.routes.append(Route(route_cat1_, f"rt1_peak_{peak_time_start_}_{peak_time_end_}", 
                               up_route1_, dn_route1_))
        if route_cat2_ != "-1":
            self.has_route2 = True
            self.routes.append(Route(route_cat2_, f"rt2_peak_{peak_time_start_}_{peak_time_end_}", 
                                   up_route2_, dn_route2_))
            
        self.op_rate1 = int(or_rate1_)
        self.op_rate2 = int(or_rate2_)
        
        self.op_lvl = perf_lvl_
        
        if interval_ != "-1":
            self.use_interval = True
            self.interval = int(interval_)
            
        self.train_num = int(train_num_)
        self.train_num1 = int(train_num1_)
        self.train_num2 = int(train_num2_)
        
        self.up_train_num = self.train_num // 2
        self.dn_train_num = self.train_num - self.up_train_num
        
    def computeInterval(self, total_time: int, offset: int) -> int:
        """
        根据总可用时间和可选偏移计算列车之间的平均间隔
        """
        avg_interval = total_time // (self.train_num + offset)
        return avg_interval
        
    def computeInterval_up(self, total_time: int, offset: int) -> int:
        """计算上行列车间隔"""
        avg_interval = total_time // (self.up_train_num + offset)
        return avg_interval
        
    def computeInterval_dn(self, total_time: int, offset: int) -> int:
        """计算下行列车间隔"""
        avg_interval = total_time // (self.dn_train_num + offset)
        return avg_interval
        
    def computeIntervalwithDelta(self, total_time_up: int, total_time_dn: int, delta: int) -> int:
        """
        考虑增量时间和小型交叉路线延迟风险的高级间隔计算。
        此方法检查使用多个交叉路线时的时序风险(即多个运营率：大小交路开行比例)。
        """
        # 处理有多个交叉路线的情况
        # 检查是否存在错过车辆的潜在风险(最后几个小交叉路线比预期晚发送)
        # 1. 首先计算默认间隔时间：计算出来就是列车周转时间
        default_interval = self.computeInterval(total_time_up + total_time_dn, 0)
        
        # 2. 如果只有一条路线需要开行，直接返回默认间隔
        if self.op_rate2 == 0:
            return default_interval
            
        # 获取条件并检查
        # 计算单侧列车数量
        side_cars = self.train_num // 2 + self.train_num % 2
        # 计算运营周期（两条路线的运营率之和）
        period = self.op_rate1 + self.op_rate2
        # 计算剩余车辆数
        residual_car = side_cars % period
        n_car_to_next_large = residual_car
        # 4. 风险处理：- 如果 residual_car 不等于1，将其设为0
        if residual_car != 1:
            residual_car = 0
            
        # 如果residual_car == 1,最后一辆车是大型的,需要使用n-1
        # 如果最后一个小交叉路线的实际开始时间晚于目标时间,存在潜在风险
        checker_time = (-residual_car - 1) * default_interval + delta
        if checker_time <= 0:
            # 无风险
            return default_interval
        else:
            # 存在潜在风险
            delta = delta // 2#如果存在风险，则：将delta减半
            # 计算新的间隔时间：
            res1 = (max(total_time_up, total_time_dn) - delta) // (side_cars - residual_car)
            
            # 计算下一个大型列车到达的时间
            res2 = max(total_time_up, total_time_dn) // (side_cars + 1)
            
            print(f"  side_cars {side_cars}      total_time {max(total_time_up, total_time_dn)}  "
                  f"t_hat {delta}       new_T {res1}  old_T {default_interval}    res2: {res2}\n"
                  f"     last car is: {side_cars % period}")
            # return max(res1, res2)
            # 虽然代码计算了多个可能的间隔时间（res1和res2），但最终还是返回了default_interval
            return default_interval
            
    def getRoute(self, xroad: int, dir: int) -> str:
        """
        从路线列表中按索引和方向检索路线字符串
        Args:
            xroad: 路线在列表中的索引
            dir: 0表示上行,1表示下行
        Returns:
            路线字符串
        """
        rt = self.routes[xroad]
        return rt.up_route if dir == 0 else rt.down_route
        
    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return f"Peak(start_time={self.start_time}, end_time={self.end_time}, train_num={self.train_num})"