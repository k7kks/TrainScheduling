from typing import List, Dict
from dataclasses import dataclass
from Peak import Peak
from Path import Path 
from Turnback import Turnback
from DepotRoutesInfo import DepotRoutesInfo

class UserSetting:
    """
    UserSetting类包含铁路系统的用户定义调度参数。
    它管理车库配置、高峰期、车辆调度规则和预测间隔。

    它作为调度引擎的配置输入，提供：
    - 车库信息（ID、容量、路线）
    - 车辆发车时间（首末班车）
    - 带运营设置的高峰时段
    - 动态更新或计算发车间隔的方法
    """

    def __init__(self):
        """初始化一个空的用户设置，包含默认事件计数和列表"""
        # 车库信息
        self.depot_ids: List[str] = []
        self.depot_trains: List[int] = []
        self.depot_caps: List[int] = []# 每个车库的初始容量
        self.depot_routes_infos: List[DepotRoutesInfo] = []

        # 首末班车时间
        self.first_car: int = 0
        self.last_car: int = 0

        # 高峰期相关
        self.peaks: List[Peak] = []
        self.predict_Interval: List[int] = []
        self.predict_Interval_up: List[int] = []
        self.predict_Interval_dn: List[int] = []

        # 事件计数
        self.n_events: List[int] = [6, 2, -1, -1]
        
        # 交叉路数量
        self.n_xroads: int = 1

    def addDepot(self, id: str, ntrain: str, caps: str) -> None:
        """添加车库定义，包括ID、初始列车数和容量"""
        self.depot_ids.append(id)
        self.depot_trains.append(int(ntrain))
        self.depot_caps.append(int(caps))

    def addDepotRoutes(self, Direction,InOrOut,UpIn: str, DownIn: str, UpOut: str, DownOut: str) -> None:
        """添加车库的路线信息（上下行进出路径）"""
        self.depot_routes_infos.append(DepotRoutesInfo(Direction,InOrOut,UpIn, DownIn, UpOut, DownOut))

    def setFirstCarTime(self, fc_time: str) -> None:
        """设置第一辆列车离开车库的时间戳"""
        self.first_car = int(fc_time)

    def setLastCarTime(self, fc_time: str) -> None:
        """设置最后一辆列车离开车库的时间戳"""
        self.last_car = int(fc_time)

    def addPeak(self, peak_time_start_: str, peak_time_end_: str,
                route_cat1_: int, up_route1_: str, dn_route1_: str,
                route_cat2_: int, up_route2_: str, dn_route2_: str,
                or_rate1_: str, or_rate2_: str, perf_lvl_: str,
                train_num_: str,train_num1_: str,train_num2_: str, interval_: str, forbid_str: str) -> None:
        """添加具有特定路线类别和性能等级的高峰期"""
        forbid = False
        if forbid_str != "-1":
            forbid = True
            
        pk = Peak(peak_time_start_, peak_time_end_, route_cat1_, up_route1_, dn_route1_,
                 route_cat2_, up_route2_, dn_route2_,
                 or_rate1_, or_rate2_, perf_lvl_,
                 train_num_,train_num1_,train_num2_, interval_, forbid)
                 
        self.peaks.append(pk)
        self.n_xroads = max(self.n_xroads, len(pk.routes))
        self.predict_Interval.append(0)
        self.predict_Interval_up.append(0)
        self.predict_Interval_dn.append(0)

    def update_interval(self, total_time: int, offset: int) -> None:
        """使用总时间和偏移更新所有高峰间隔"""
        print(f"进入update_interval函数中")
        for i in range(len(self.predict_Interval)):
            # interval = self.peaks[i].computeInterval(total_time, offset)
            #使用读取的xml中的共线间隔时间
            interval = self.peaks[i].interval
            # print(f"update_interval：计算的interval[i]: {interval}")

            self.predict_Interval[i] = interval
            self.peaks[i].interval = interval
            self.peaks[i].interval_up = interval
            self.peaks[i].interval_dn = interval

    def update_interval_delta(self, total_time_up: int, total_time_dn: int, delta: int) -> None:
        """使用时间增量调整更新间隔预测"""
        print(f"进入update_interval_delta函数中")
        for i in range(len(self.predict_Interval)):
            # interval = self.peaks[i].computeIntervalwithDelta(total_time_up, total_time_dn, delta)#使用代码中计算的列车周转时间
            #使用读取的xml中的共线间隔时间:其实就是不改，使用xml中的时间
            interval = self.peaks[i].interval
            # print(f"读取的xml中interval[i]: {interval}")
            self.predict_Interval[i] = interval
            self.peaks[i].interval = interval
            self.peaks[i].interval_up = interval
            self.peaks[i].interval_dn = interval

    def update_interval_with_direction(self, total_time: int, up_time: int, dn_time: int, offset: int) -> None:
        """分别更新上下行方向的间隔"""
        for i in range(len(self.predict_Interval)):
            self.predict_Interval[i] = self.peaks[i].computeInterval(total_time, offset)
            self.predict_Interval_up[i] = self.peaks[i].computeInterval_up(up_time, offset)
            self.predict_Interval_dn[i] = self.peaks[i].computeInterval_dn(dn_time, offset)
            self.peaks[i].interval = self.peaks[i].computeInterval(total_time, offset)
            self.peaks[i].interval_up = self.peaks[i].computeInterval_up(up_time, offset)
            self.peaks[i].interval_dn = self.peaks[i].computeInterval_dn(dn_time, offset)

    def update_interval_with_turnback(self, total_time: int, pathList: Dict[str, Path], 
                       turnbackList: Dict[str, Turnback]) -> None:
        """使用从路径和折返数据获取的折返站台时间调整间隔"""
        for i in range(len(self.predict_Interval)):
            pk = self.peaks[i]
            total_cars = pk.train_num
            residual = total_time % total_cars
            to_add_time = total_cars - residual

            add_to_up = to_add_time // 2
            add_to_dn = to_add_time - add_to_up
            
            # 获取上行路线折返时间
            path_up = pathList[pk.routes[0].up_route]
            turn_back_id = path_up.nodeList[-1]
            tb = turnbackList[turn_back_id]
            self.peaks[i].turnback_time_up_rt1 = tb.def_tb_time + add_to_up
            self.peaks[i].turn_back_time[tb.dest_code] = tb.def_tb_time + add_to_up
            
            # 获取下行路线折返时间
            path_dn = pathList[pk.routes[0].down_route]
            turn_back_id = path_dn.nodeList[-1]
            tb = turnbackList[turn_back_id]
            self.peaks[i].turnback_time_dn_rt1 = tb.def_tb_time + add_to_dn
            self.peaks[i].turn_back_time[tb.dest_code] = tb.def_tb_time + add_to_dn

            norm_interval = (total_time + to_add_time) // total_cars
            self.predict_Interval[i] = norm_interval