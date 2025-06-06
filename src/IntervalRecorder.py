from typing import List

class IntervalRecorder:
    """
    intervalRecorder类用于记录和计算列车调度中的间隔信息。
    包含:
    - 间隔列表
    - 冗余和不足车辆的计数器
    - 不同阶段的车辆状态评分
    """
    
    def __init__(self, n_pt: int):
        """
        构造函数
        Args:
            n_pt: 阶段数量
        """
        self.intervals: List[float] = [-1.0] * n_pt
        # 初始化所有计数器为最大值
        self.redund_cars: int = 99999
        self.insuff_cars: int = 99999
        self.redund_cars_end: int = 99999
        self.insuff_cars_end: int = 99999
        self.redund_cars_prered: int = 99999
        self.insuff_cars_prered: int = 99999
        
    def computeScore(self) -> int:
        """
        计算总体评分
        Returns:
            根据各项指标加权计算的总分
        """
        res = self.redund_cars * 5
        res += self.insuff_cars * 6
        res += self.redund_cars_end * 4
        res += self.insuff_cars_end * 3
        res += self.redund_cars_prered * 2
        res += self.insuff_cars_prered * 1
        return res
        
    def setInterval(self, idx: int, interval: float) -> None:
        """
        设置指定索引位置的间隔值
        Args:
            idx: 要设置的索引
            interval: 间隔值
        """
        self.intervals[idx] = interval
        
    def setScore(self) -> None:
        """重置所有评分计数器为0"""
        self.redund_cars = 0
        self.insuff_cars = 0
        self.redund_cars_end = 0
        self.insuff_cars_end = 0
        self.redund_cars_prered = 0
        self.insuff_cars_prered = 0