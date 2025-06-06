from typing import List, Dict, Optional, Union
import sys
# from RouteSolution import RouteSolution
from Platform import Platform

class util:
    """
    工具类,包含以下辅助方法:
    - 时间格式化
    - 控制台输出(支持ANSI颜色)
    - 位掩码检查
    - 调试工具(如打印路线、暂停执行)
    - 按车次号搜索路线
    
    这些工具用于格式化输出和调试铁路调度系统。
    """
    
    # 预定义颜色,用于清晰展示
    ANSI_RESET = "\u001B[0m"
    ANSI_BLACK = "\u001B[30m"
    ANSI_RED = "\u001B[31m"
    ANSI_GREEN = "\u001B[32m"
    ANSI_YELLOW = "\u001B[33m"
    ANSI_BLUE = "\u001B[34m"
    ANSI_PURPLE = "\u001B[35m"
    ANSI_CYAN = "\u001B[36m"
    ANSI_WHITE = "\u001B[37m"
    ANSI_BLACK_BACKGROUND = "\u001B[40m"
    ANSI_RED_BACKGROUND = "\u001B[41m"
    ANSI_GREEN_BACKGROUND = "\u001B[42m"
    ANSI_YELLOW_BACKGROUND = "\u001B[43m"
    ANSI_BLUE_BACKGROUND = "\u001B[44m"
    ANSI_PURPLE_BACKGROUND = "\u001B[45m"
    ANSI_CYAN_BACKGROUND = "\u001B[46m"
    ANSI_WHITE_BACKGROUND = "\u001B[47m"
    
    @staticmethod
    def timeFromIntSec(time: int) -> str:
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
        mins = mins % 60
        
        return f"{hr}:{mins}:{sec}"
        
    @staticmethod
    def pause() -> None:
        """暂停程序执行直到用户按下任意键"""
        try:
            sys.stdin.read(1)
        except Exception:
            print("ERR")
            
    @staticmethod
    def pf(content: Union[str, int]) -> None:
        """控制台打印函数"""
        if isinstance(content, str):
            print(content + util.ANSI_RESET)
        else:
            print(str(content) + util.ANSI_RESET)
            
    @staticmethod
    def ps(d: int) -> str:
        """整数转字符串的快捷方式"""
        return str(d)
        
    @staticmethod
    def checkBitIsOne(n: int, k: int) -> bool:
        """
        检查整数n的第k位是否为1。
        用于位掩码状态跟踪。
        Args:
            n: 整数位掩码
            k: 要检查的位索引
        Returns:
            如果第k位为1则返回True
        """
        if n == 0:
            return False
        if n == 3:
            return True
        return ((n >> k) & 1) == 1
        
    @staticmethod
    def getLast(tmp: List[int]) -> int:
        """
        返回整数列表的最后一个元素
        Args:
            tmp: 整数列表
        Returns:
            最后一个元素
        """
        return tmp[-1]
        
    @staticmethod
    def printCar(rs: 'RouteSolution', platform_list: Optional[Dict[str, Platform]] = None) -> None:
        """
        使用绿色ANSI颜色打印车辆路线的格式化摘要。
        包括所有停靠站台的到达和出发时间。
        Args:
            rs: RouteSolution对象
            platform_list: 可选,用于打印站台实际名称的辅助字典
        """
        util.pf(util.ANSI_GREEN + " Car: " + str(rs.car_info.round_num))
        for k in range(len(rs.stopped_platforms)):
            platform = rs.stopped_platforms[k]
            if platform_list:
                platform = platform_list[platform].name
            util.pf(util.ANSI_GREEN + "         " + platform + "   " + 
                   util.timeFromIntSec(rs.arr_time[k]) + "~" + 
                   util.timeFromIntSec(rs.dep_time[k]))
                   
    @staticmethod
    def findByRoundnum(round_n: int, pppp: List[List[List['RouteSolution']]]) -> Optional['RouteSolution']:
        """
        在嵌套路线结构中按车次号查找RouteSolution对象
        Args:
            round_n: 要搜索的车次号
            pppp: 包含RouteSolution对象的嵌套列表结构
        Returns:
            找到的RouteSolution,如果未找到则返回None
        """
        for ppp in pppp:
            for pp in ppp:
                for p in pp:
                    if p.car_info.round_num == round_n:
                        return p
        return None
        
    @staticmethod
    def printAll(phase_res: List[List[List['RouteSolution']]]) -> None:
        """
        打印所有车辆的起止时间
        Args:
            phase_res: 计划的RouteSolutions
        """
        for rsss in phase_res:
            for rss in rsss:
                for rs in rss:
                    util.pf(util.ANSI_GREEN + " dir" + str(rs.dir) + 
                           " Car: " + str(rs.car_info.round_num) + "   " + 
                           util.timeFromIntSec(rs.arr_time[0]) + " ~ " + 
                           util.timeFromIntSec(rs.dep_time[-1]))