from enum import Enum
from typing import Set, Optional
from Peak import Peak
# from Util import Util

class PHASETYPE(Enum):
    """调度阶段类型枚举"""
    STABLE = "STABLE"         # 稳定阶段
    ADDCAR = "ADDCAR"        # 增加车辆阶段
    REDUCECAR = "REDUCECAR"  # 减少车辆阶段
    PREREDUCE = "PREREDUCE"  # 预减少车辆阶段

class PhaseTime:
    """
    调度阶段时间类
    用于存储和管理调度阶段的时间信息
    """
    def __init__(self, lhs: int, rhs: int, n_cars: int, interval: float, 
                 phase_type: PHASETYPE, pk: Peak, up_interval: int, dn_interval: int):
        # 基本时间属性
        self.t_s: int = lhs            # 阶段开始时间
        self.t_e: int = rhs            # 阶段结束时间
        self.t_: int = rhs - lhs       # 时间段长度
        
        # 阶段类型和车辆信息
        self.p_type: PHASETYPE = phase_type  # 阶段类型
        self.n_cars: int = n_cars            # 车辆数量
        self.interval: float = interval      # PhaseTime类中计算的发车间隔
        
        # 上下行间隔
        self.up_interval: int = up_interval  # 上行间隔
        self.dn_interval: int = dn_interval  # 下行间隔
        
        # 峰期信息
        self.pk: Optional[Peak] = pk         #峰期对象
        
        # 偏移量
        self.offset_up: int = 0              # 上行偏移
        self.offset_dn: int = 0              # 下行偏移
        
        # 间隔记录
        self.tested_int: Set[float] = {interval}  # 已测试的间隔集合
        self.last_int: float = interval          # 最后使用的间隔

    def timeFromIntSec(self, time: int) -> str:
        """
        将时间戳(秒)转换为格式化字符串HH:MM:SS
        Args:
            time: 时间戳(秒)
        Returns:
            格式化的时间字符串
        """
        sec = time % 60
        mins = (time - sec) // 60
        hr = mins // 60
        hr = hr % 24
        mins = mins % 60
        
        sthr = str(hr)
        stmins = f"0{mins}" if mins < 10 else str(mins)
        stsec = f"0{sec}" if sec < 10 else str(sec)
        
        return f"{sthr}:{stmins}:{stsec}"

    def __str__(self) -> str:
        """返回阶段信息的字符串表示"""
        type_str = self.p_type.value
        return (f"Phase type: {type_str}......   "
                f"time: ({self.timeFromIntSec(self.t_s)}, {self.timeFromIntSec(self.t_e)})."
                f"      # cars: {self.n_cars} interval:{self.interval}")