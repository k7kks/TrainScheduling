"""
越行事件模型

定义快车越行慢车的事件信息
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class OvertakingType(Enum):
    """越行类型"""
    SINGLE = "单次越行"          # 一列快车越行一列慢车
    DOUBLE = "二次越行"          # 一列慢车被连续两列快车越行
    EXPRESS_OVERTAKES_TWO = "快车越行两慢车"  # 一列快车越行两列慢车


@dataclass
class OvertakingEvent:
    """
    越行事件
    
    记录快车越行慢车的详细信息
    """
    event_id: str                       # 事件ID
    overtaking_train_id: str            # 越行列车ID（快车）
    overtaken_train_id: str             # 被越行列车ID（慢车）
    
    # 越行位置
    overtaking_station_id: str          # 越行站ID
    overtaking_station_name: str        # 越行站名称
    direction: str                      # 方向（上行/下行）
    
    # 时间信息（秒）
    local_arrival_time: int             # 慢车到达时间
    local_departure_time: int           # 慢车发车时间
    express_pass_time: int              # 快车通过时间
    
    # 间隔时间
    arrival_to_pass_interval: int       # 到通间隔（慢车到达→快车通过）
    pass_to_departure_interval: int     # 通发间隔（快车通过→慢车发车）
    
    # 越行类型和属性
    overtaking_type: OvertakingType = OvertakingType.SINGLE
    is_avoidable: bool = False          # 是否可避免
    
    # 待避信息
    local_waiting_time: int = 0         # 慢车等待时间
    local_normal_dwell: int = 40        # 慢车正常停站时间
    
    # 越行原因
    reason: str = "追踪间隔冲突"         # 越行原因
    conflict_section: Optional[str] = None  # 冲突区间
    
    # 优化建议
    optimization_suggestion: Optional[str] = None  # 优化建议
    can_adjust_headway: bool = False    # 是否可通过调整间隔避免
    can_swap_order: bool = False        # 是否可通过交换顺序避免
    
    @property
    def total_delay(self) -> int:
        """慢车总延误时间（秒）"""
        return max(0, self.local_waiting_time - self.local_normal_dwell)
    
    @property
    def is_valid_overtaking(self) -> bool:
        """
        判断越行是否合规
        
        合规要求：
        1. 到通间隔 >= 120秒
        2. 通发间隔 >= 120秒
        3. 慢车停站时间 >= 240秒（4分钟）
        """
        return (self.arrival_to_pass_interval >= 120 and 
                self.pass_to_departure_interval >= 120 and
                (self.local_departure_time - self.local_arrival_time) >= 240)
    
    def get_optimization_suggestion(self) -> str:
        """
        获取优化建议
        
        Returns:
            优化建议字符串
        """
        if not self.is_avoidable:
            return "越行不可避免，建议保持现状"
        
        suggestions = []
        
        if self.can_adjust_headway:
            suggestions.append("调整快慢车发车间隔")
        
        if self.can_swap_order:
            suggestions.append("交换快慢车发车顺序（快车大交路追踪慢车小交路）")
        
        if not suggestions:
            return "越行可避免，但需要进一步分析"
        
        return "、".join(suggestions)
    
    def __repr__(self) -> str:
        return (f"OvertakingEvent({self.overtaking_train_id} 越行 {self.overtaken_train_id} "
                f"@ {self.overtaking_station_name}, 延误{self.total_delay}秒)")

