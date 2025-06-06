from typing import Optional
from RouteSolution import RouteSolution

class ConflictPair:
    """
    ConflictPair类用于表示列车调度中的冲突对。
    包含:
    - 主要路线解决方案
    - 左右冲突路线
    - 运行时间和轨道时间约束
    - 折返时间约束
    - 方向和站台信息
    """
    
    def __init__(self, rs: RouteSolution,
                 dir: int,
                 conf_left: RouteSolution,
                 conf_right: RouteSolution,
                 travel_time: int,
                 min_track_t: int,
                 min_tb1: int,
                 max_tb1: int,
                 min_tb2: int,
                 max_tb2: int,
                 ishead: bool,
                 idx: int):
        """
        构造函数
        Args:
            rs: 主要路线解决方案
            dir: 方向
            conf_left: 左侧冲突路线
            conf_right: 右侧冲突路线
            travel_time: 运行时间
            min_track_t: 最小轨道时间
            min_tb1: 最小折返时间1
            max_tb1: 最大折返时间1
            min_tb2: 最小折返时间2
            max_tb2: 最大折返时间2
            ishead: 是否为头部(head: 0, tail: 1)
            idx: 站台索引
        """
        self.rs: RouteSolution = rs
        self.conf_left: RouteSolution = conf_left
        self.conf_right: RouteSolution = conf_right
        
        # head: 0, tail: 1
        self.travel_time: int = travel_time
        self.min_track_t: int = min_track_t
        self.min_tb1: int = min_tb1
        self.min_tb2: int = min_tb2
        self.max_tb1: int = max_tb1
        self.max_tb2: int = max_tb2
        self.istwo: bool = ishead
        self.dir: int = dir
        self.station_idx: int = idx