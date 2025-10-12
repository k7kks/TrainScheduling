"""
列车模型模块

定义快车和慢车的数据模型
"""

from enum import Enum
from typing import List, Optional, Set
from dataclasses import dataclass, field


class TrainType(Enum):
    """列车类型枚举"""
    EXPRESS = "快车"  # 快车
    LOCAL = "慢车"    # 慢车
    

@dataclass
class Train:
    """
    列车基类
    
    包含列车的基本属性和方法
    """
    train_id: str                # 列车ID
    train_name: str             # 列车名称
    train_type: TrainType       # 列车类型
    route_id: str               # 所属交路ID
    direction: str              # 方向（上行/下行）
    
    # 停站方案
    stop_stations: List[str] = field(default_factory=list)     # 停靠车站列表
    skip_stations: Set[str] = field(default_factory=set)       # 跳停车站集合
    
    # 时刻信息
    departure_time: Optional[int] = None    # 发车时间（秒）
    arrival_time: Optional[int] = None      # 到达时间（秒）
    
    # 连接信息
    prev_train_id: Optional[str] = None     # 前序车次ID（用于大小交路套跑）
    next_train_id: Optional[str] = None     # 后续车次ID
    
    # 运营属性
    is_first_train: bool = False            # 是否为首班车
    is_last_train: bool = False             # 是否为末班车
    is_depot_out: bool = False              # 是否出库车
    is_depot_in: bool = False               # 是否入库车
    
    def get_travel_time(self) -> int:
        """获取全程旅行时间（秒）"""
        if self.departure_time is not None and self.arrival_time is not None:
            return self.arrival_time - self.departure_time
        return 0
    
    def stops_at_station(self, station_id: str) -> bool:
        """判断是否在指定车站停车"""
        return station_id not in self.skip_stations
    
    def get_dwell_time(self, station_id: str) -> int:
        """
        获取在指定车站的停站时间（秒）
        
        Args:
            station_id: 车站ID
            
        Returns:
            停站时间（秒），跳停返回0
        """
        if not self.stops_at_station(station_id):
            return 0
        
        # 默认停站时间
        if self.train_type == TrainType.EXPRESS:
            return 30  # 快车默认30秒
        else:
            return 40  # 慢车默认40秒
    
    def __repr__(self) -> str:
        return f"{self.train_type.value}({self.train_id})"


@dataclass
class ExpressTrain(Train):
    """
    快车类
    
    快车特点：
    1. 部分车站跳停（站站停比例约50-70%）
    2. 停站时间较短
    3. 运行速度较快
    4. 与慢车独立运用（不套跑）
    """
    
    # 快车特有属性
    express_stop_ratio: float = 0.6         # 停站比例
    overtaking_capable: bool = True          # 是否具有越行能力
    
    def __post_init__(self):
        """初始化后处理"""
        self.train_type = TrainType.EXPRESS
    
    def get_dwell_time(self, station_id: str) -> int:
        """
        快车停站时间
        
        Args:
            station_id: 车站ID
            
        Returns:
            停站时间（秒），跳停返回0，停车返回25-30秒
        """
        if not self.stops_at_station(station_id):
            return 0
        
        # 快车停站时间较短：25-30秒
        return 30


@dataclass
class LocalTrain(Train):
    """
    慢车类
    
    慢车特点：
    1. 站站停
    2. 停站时间较长
    3. 运行速度较慢
    4. 支持大小交路套跑
    5. 可能被快车越行
    """
    
    # 慢车特有属性
    is_short_route: bool = False            # 是否为小交路
    turnback_station: Optional[str] = None  # 折返站（小交路）
    can_be_overtaken: bool = True           # 是否可被越行
    overtaken_count: int = 0                # 被越行次数
    
    # 待避信息
    wait_for_overtaking: bool = False       # 是否正在待避
    overtaking_station: Optional[str] = None # 越行发生站
    additional_dwell: int = 0               # 额外停站时间（待避）
    
    def __post_init__(self):
        """初始化后处理"""
        self.train_type = TrainType.LOCAL
    
    def get_dwell_time(self, station_id: str) -> int:
        """
        慢车停站时间
        
        Args:
            station_id: 车站ID
            
        Returns:
            停站时间（秒），包含正常停站时间和额外待避时间
        """
        # 慢车站站停，正常停站时间35-40秒
        base_dwell = 40
        
        # 如果在越行站待避，需要额外停站时间（至少240秒，即4分钟）
        if self.wait_for_overtaking and station_id == self.overtaking_station:
            return max(base_dwell + self.additional_dwell, 240)
        
        return base_dwell
    
    def mark_overtaken(self, station_id: str, additional_wait: int = 240):
        """
        标记在指定车站被越行
        
        Args:
            station_id: 越行发生车站ID
            additional_wait: 额外等待时间（秒），默认240秒（4分钟）
        """
        self.overtaken_count += 1
        self.wait_for_overtaking = True
        self.overtaking_station = station_id
        self.additional_dwell = additional_wait
    
    def is_small_route(self) -> bool:
        """判断是否为小交路"""
        return self.is_short_route
    
    def __repr__(self) -> str:
        route_type = "小交路" if self.is_short_route else "大交路"
        return f"慢车{route_type}({self.train_id})"

