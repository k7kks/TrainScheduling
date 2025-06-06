from enum import Enum
from typing import List
from Platform import Platform
from Turnback import Turnback

class Station:
    """
    Station类表示铁路系统中的车站。
    
    每个车站包含：
    - 基本信息（ID、名称、缩写）
    - 车站类型（车库、折返、普通、换乘）
    - 中心公里标
    - 是否为设备站
    - 站台列表
    - 折返轨列表
    
    提供添加站台和折返轨的功能。
    """
    
    class StationType(Enum):
        """车站类型枚举"""
        DEPOT = "Depot"
        TURNBACK = "Turnback"
        NORMAL = "Normal"
        TRANSFER = "Transfer"
        
    def __init__(self, id: str,
                 name: str,
                 abbrv: str,
                 station_type: str,
                 centerKp: str,
                 is_equip_station: str):
        """
        构造函数
        Args:
            id: 车站ID
            name: 车站名称
            abbrv: 车站缩写
            station_type: 车站类型
            centerKp: 中心公里标
            is_equip_station: 是否为设备站
        """
        self.id: str = id
        self.name: str = name
        self.abbrv: str = abbrv
        self.centerKp: int = int(centerKp)
        
        # 设置车站类型
        if station_type == "Turnback":
            self.station_type = self.StationType.TURNBACK
        elif station_type == "Depot":
            self.station_type = self.StationType.DEPOT
        elif station_type == "Normal":
            self.station_type = self.StationType.NORMAL
        elif station_type == "Transfer":
            self.station_type = self.StationType.TRANSFER
            
        # 设置是否为设备站
        self.is_equip_station: bool = False if is_equip_station == "false" else True
        
        # 初始化站台和折返轨列表
        self.platformList: List[Platform] = []
        self.turnbackList: List[Turnback] = []
    ### Platform和Turnback都是Station下的属性
    def addPlatform(self, id: str,
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
                    depot_id:str) -> None:
        """
        向车站添加站台。
        自动将本车站的ID分配给站台的station_id。
        """
        self.platformList.append(
            Platform(id, name, platform_type, dir, is_virtual, 
                    dest_code, link_platform, def_dwell_time, 
                    def_pl, min_track_time, min_dwell_time, 
                    max_dwell_time, self.id,depot_id)
        )
        
    def addTurnback(self, id: str,
                    name: str,
                    show_name: str,
                    dest_code: str,
                    min_tb_time: str,
                    def_tb_time: str,
                    max_tb_time: str) -> None:
        """向车站添加折返轨。"""
        self.turnbackList.append(
            Turnback(id, name, show_name, dest_code, 
                    min_tb_time, def_tb_time, max_tb_time)
        )