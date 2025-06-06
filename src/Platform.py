from enum import Enum

class PlatformType(Enum):
    """枚举表示站台类型"""
    DEPOT = "Depot"
    TURNBACK = "Turnback" 
    NORMAL = "Normal"
    TRANSFER = "Transfer"

class Platform:
    """
    表示铁路调度系统中的站台。
    包含元数据如类型、方向、时间约束和连接信息。
    """
    

        
    class Direction(Enum):
        """枚举表示站台方向"""
        LEFT = "Left"
        RIGHT = "Right"
        
    def __init__(self, id: str,
                 name: str,
                 platform_type: str,
                 dir: str,
                 is_virtual: str,
                 dest_code: str,
                 link_platform: str,
                 def_dwell_time: str,
                 def_pl: str,
                 min_track_time: str,
                 min_dwell_time: str,
                 max_dwell_time: str,
                 station_id: str,
                 depot_id: str):
        """
        Platform的构造函数。
        从字符串输入解析并分配所有站台属性。
        
        Args:
            id: 站台ID
            name: 站台名称
            platform_type: 站台类型
            dir: 方向
            is_virtual: 是否虚拟站台
            dest_code: 站台目的地码
            link_platform: 关联站台的目的地码（不是每个站台都有）
            def_dwell_time: 默认停站时间
            def_pl: 默认性能等级
            min_track_time: 最小轨道时间
            min_dwell_time: 最小停站时间
            max_dwell_time: 最大停站时间
            station_id: 所属车站ID
            depot_id:所属车辆段的ID
        """
        self.id: str = id
        self.name: str = name
        
        # 设置站台类型
        if platform_type == "Turnback":
            self.platform_type = PlatformType.TURNBACK
        elif platform_type == "Depot":
            self.platform_type = PlatformType.DEPOT
        elif platform_type == "Normal":
            self.platform_type = PlatformType.NORMAL
        elif platform_type == "Transfer":
            self.platform_type = PlatformType.TRANSFER
            
        # 设置方向
        if dir == "Left":
            self.dir = self.Direction.LEFT
        elif dir == "Right":
            self.dir = self.Direction.RIGHT
            
        # 设置是否为虚拟站台
        self.is_virtual: bool = False if is_virtual == "false" else True
        
        # 设置其他属性
        self.dest_code: str = dest_code
        self.link_platform: str = link_platform
        self.def_dwell_time: int = int(def_dwell_time)
        self.def_pl: int = int(def_pl)
        self.min_track_time: int = int(min_track_time)
        self.min_dwell_time: int = int(min_dwell_time)
        self.max_dwell_time: int = int(max_dwell_time)
        self.station_id: str = station_id
        self.depot_id:str = depot_id