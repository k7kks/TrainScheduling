from typing import List, Tuple
#### 这个类无需使用
class TurnBackInfo:
    """
    TurnBackInfo表示折返操作的元数据,
    通常用于列车调度系统中跟踪停留时间和进出事件。
    
    它定义:
    - 与折返相关的计划事件列表
    - 表示进出点的索引
    - 约束条件,如最小/最大停留时间
    - 关键事件之间的发车-到达间隔
    """
    
    def __init__(self, n_events: int,
                 MinMaxDwellTime: List[Tuple[int, int]],
                 DeptArrivalDif: List[int],
                 Enter_event_index: int,
                 Exit_event_index: int):
        """
        构造函数
        Args:
            n_events: 事件总数
            MinMaxDwellTime: 最小最大停留时间列表
            DeptArrivalDif: 发车到达时间差列表
            Enter_event_index: 出库点索引
            Exit_event_index: 回库点索引
        """
        self.n_events: int = n_events
        
        # 回库点
        self.Exit_event_index: int = Exit_event_index
        
        # 出库点
        self.Enter_event_index: int = Enter_event_index
        
        # 停留时间
        self.MinMaxDwellTime: List[Tuple[int, int]] = MinMaxDwellTime
        
        # 发到间隔
        self.DeptArrivalDif: List[int] = DeptArrivalDif