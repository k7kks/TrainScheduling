"""
时刻表条目模型

定义列车在各车站的到发时刻信息
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TimetableEntry:
    """
    时刻表条目
    
    记录某列车在某车站的到发时刻、停站时间等信息
    """
    train_id: str               # 列车ID
    station_id: str             # 车站ID（真正的车站ID）
    station_name: str           # 车站名称
    
    # 时刻信息（秒）
    arrival_time: int           # 到达时间
    departure_time: int         # 发车时间
    dwell_time: int             # 停站时间
    
    # 停站属性
    is_stop: bool = True        # 是否停车
    is_skip: bool = False       # 是否跳停
    
    # 特殊属性
    is_turnback: bool = False   # 是否折返
    is_overtaking: bool = False # 是否发生越行
    is_depot_in: bool = False   # 是否入库
    is_depot_out: bool = False  # 是否出库
    
    # 越行相关
    overtaken_by: Optional[str] = None      # 被哪列车越行
    overtaking_train: Optional[str] = None  # 越行哪列车
    waiting_time: int = 0                   # 等待时间（待避）
    
    # 附加信息
    platform_id: Optional[str] = None       # 站台ID（用于内部引用）
    track_id: Optional[str] = None          # 股道ID
    dest_code: Optional[str] = None         # 站台目的地码（Destcode，用于输出）
    
    @property
    def is_normal_stop(self) -> bool:
        """是否为正常停站（非跳停、非越行待避）"""
        return self.is_stop and not self.is_skip and not self.is_overtaking
    
    @property
    def actual_dwell_time(self) -> int:
        """实际停站时间（包含等待时间）"""
        return self.dwell_time + self.waiting_time
    
    def format_time(self, seconds: int) -> str:
        """
        将秒数格式化为时:分:秒字符串
        
        Args:
            seconds: 秒数
            
        Returns:
            格式化的时间字符串，如 "06:30:45"
        """
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    @property
    def arrival_time_str(self) -> str:
        """到达时间字符串"""
        return self.format_time(self.arrival_time)
    
    @property
    def departure_time_str(self) -> str:
        """发车时间字符串"""
        return self.format_time(self.departure_time)
    
    def __repr__(self) -> str:
        status = "跳停" if self.is_skip else "停车"
        if self.is_overtaking:
            status += "(越行)"
        return f"TimetableEntry({self.train_id} @ {self.station_name}: {self.arrival_time_str}-{self.departure_time_str} {status})"

