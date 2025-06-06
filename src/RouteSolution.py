from typing import List, Dict, Optional
from CarInfo import CarInfo

class RouteSolution:
    """
    RouteSolution用来存放求解器的解，包括停站序列、时间和元数据。
    
    它存储：
    - 站台停靠列表（包含到达/离开时间）
    - 列车的CarInfo（车次号、路线号等）
    - 每个区段的运行等级
    - 与其他RouteSolutions的链接（用于链接路径或持续运营）
    - CSV导出功能，用于与任务线和计划线表格集成
    
    它支持：
    - 停站的插入/删除
    - 时间偏移调整
    - 用于模拟/变更的克隆
    - 处理路径扩展和交叉路信息
    """
    
    def __init__(self, initial_time_stamp: int, table_num: int = None, 
                 round_num: int = None, route_num: int = None):
        """
        构造函数
        Args:
            initial_time_stamp: 路线的起始时间
            table_num: 可选,列车编号（表号）：计划线数据需要
            round_num: 可选,班次编号（车次号）：计划线数据需要
            route_num: 可选,路线编号(路径编号)：计划线数据需要
        """
        self.initial_time_stamp: int = initial_time_stamp
        self.operating: bool = False
        
        self.dir: int = -1  #默认为-1，这可能是导致rs.dir不对的原因，只有默认值，没有被赋值
        self.auxilary: str = ""
        
        self.stopped_platforms: List[str] = []#停靠的站台码：任务线数据需要
        self.stopped_time: List[int] = []#停站时长
        self.arr_time: List[int] = []# 到达时间
        self.dep_time: List[int] = []# 出发时间
        self.performance_levels: List[int] = []#运行等级：任务线数据需要
        self.total_stopped_stations: int = 0#总共停靠的站台
        
        self.car_info: Optional[CarInfo]
        if all(x is not None for x in [table_num, round_num, route_num]):
            self.car_info = CarInfo(table_num, round_num, route_num)
            
        self.next_ptr: Optional['RouteSolution'] = None#车次间链接关系，下一车次
        self.prev_ptr: Optional['RouteSolution'] = None#车次间链接关系，上一车次
        
        self.xroad: int = 0
        self.phase: int = -1
        
        # 此字段标识路线的状态,每个位对应一侧(起点和终点)
        # 0表示无变化,1表示变为大路线
        self.side_notification: int = 0
        
    def clone(self) -> 'RouteSolution':
        """
        创建当前RouteSolution的深拷贝。
        用于模拟或修改调度而不改变原始数据。
        Returns:
            克隆的RouteSolution实例
        """
        cp = RouteSolution(self.initial_time_stamp)
        cp.operating = self.operating
        
        cp.stopped_platforms.extend(self.stopped_platforms)
        cp.stopped_time.extend(self.stopped_time)
        cp.arr_time.extend(self.arr_time)
        cp.dep_time.extend(self.dep_time)
        cp.performance_levels.extend(self.performance_levels)
        cp.total_stopped_stations = self.total_stopped_stations
        
        cp.xroad = self.xroad
        cp.phase = self.phase
        
        # 确保深度复制 car_info
        if self.car_info is not None:
            cp.car_info = CarInfo.from_car_info(self.car_info)
        else:
            cp.car_info = None
        return cp
        
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
        
    def updateInfo(self, table_num: int, round_num: int, route_num: int) -> None:
        """更新当前路线的标识符"""
        self.car_info = CarInfo(table_num, round_num, route_num)
        
    def addStop(self, platform: str, stop_time: int, perf_level: int, 
                current_time: int, dep_time: int, index: int = None) -> None:
        """
        向路线添加一个停站。任务线数据表格中必须要有停站的站台码
        Args:
            platform: 停靠的站台
            stop_time: 站台停站时长
            perf_level: 性能等级
            current_time: 站台到达时间
            dep_time: 站台出发时间
            index: 可选,插入位置的索引
        """
        # if stop_time == 0:
        #     print("调用addStop函数添加stop_time = 0 ")
        if index is not None:
            self.stopped_platforms.insert(index, platform)
            self.stopped_time.insert(index, stop_time)
            self.performance_levels.insert(index, perf_level)
            self.arr_time.insert(index, current_time)
            self.dep_time.insert(index, dep_time)
        else:
            self.stopped_platforms.append(platform)
            self.stopped_time.append(stop_time)
            self.performance_levels.append(perf_level)
            self.arr_time.append(current_time)
            self.dep_time.append(dep_time)
            
        if dep_time - current_time > 0:
            self.total_stopped_stations += 1
            
    def offset_stop(self, stop_offset: int) -> None:
        """
        对所有到达和出发时间应用统一的时间偏移(秒)。
        用于因调度变更而移动整个路线。
        """
        for i in range(len(self.arr_time)):
            self.arr_time[i] -= stop_offset
            self.dep_time[i] -= stop_offset
            
    def retCSVStringPlanned(self) -> str:
        """将路线转换为计划表的CSV字符串"""
        components = [
            str(self.car_info.table_num),
            str(self.car_info.round_num),
            str(self.car_info.route_num),
            self.timeFromIntSec(self.initial_time_stamp),
            "1", "0",
            "1 1" if self.operating else "0 1"
        ]
        return " ".join(components)
        
    def retCSVStringPlanned_num(self) -> str:
        """将路线转换为计划表的CSV字符串(日期未格式化)"""
        components = [
            str(self.car_info.table_num),
            str(self.car_info.round_num),
            str(self.car_info.route_num),
            str(self.dep_time[0]),
            "1", "0",
            "1 1" if self.operating else "0 1"
        ]
        return " ".join(components)
        
    def retCSVStringMission(self, formatted: bool = True) -> Dict[int, str]:
        """
        将路线转换为任务线数据的CSV字符串
        Args:
            formatted: 是否格式化时间
        Returns:
            以到达时间为键的字符串映射
        """
        # print(f"retCSVStringMission中stopped_platforms: {self.stopped_platforms}") #stopped_platforms必须要有值，否则进不去赋值逻辑
        # print(f"arr_time: {self.arr_time}")#已经有顺序错误
        # print(f"dep_time: {self.dep_time}")
        # # print(f"performance_levels: {self.performance_levels}")
        # print(f"retCSVStringMission中car_info.round_num: {self.car_info.round_num}")
        res_map: Dict[int, str] = {}
        for i in range(len(self.stopped_platforms)):
            components = [
                str(self.car_info.table_num),#表号
                str(self.car_info.round_num),#车次号
                self.stopped_platforms[i]#站台目的地码
            ]
            
            # 添加时间信息
            if i == 0:
                time_str = self.timeFromIntSec(self.dep_time[0]) if formatted else str(self.dep_time[0])
            else:
                time_str = self.timeFromIntSec(self.arr_time[i]) if formatted else str(self.arr_time[i])
            components.append(time_str)  #添加该站台的到达时间
            
            # 添加出发/到达时间
            if i < len(self.stopped_platforms) - 1:
                time_str = self.timeFromIntSec(self.dep_time[i]) if formatted else str(self.dep_time[i])
            else:
                time_str = self.timeFromIntSec(self.arr_time[i]) if formatted else str(self.arr_time[i])
            components.append(time_str) #添加该站台的发车时间
            
            # 添加运行等级
            components.append(str(self.performance_levels[i]))
            #添加结束标记（最后一个站台为1）
            components.append("1" if i == len(self.stopped_platforms) - 1 else "0")
            
            res_map[self.arr_time[i]] = " ".join(components) + "\n"
        # print(f"retCSVStringMission的返回值={res_map}")
        return res_map
        
    def retCSVStringMission_num(self) -> Dict[int, str]:
        """将路线转换为任务表的CSV字符串(日期未格式化)"""
        return self.retCSVStringMission(formatted=False)
        
    def getHeadModificationHEAD(self) -> bool:
        """检查路线头部是否已更改为大路线"""
        return self.checkBitIsOne(self.side_notification, 1)
        
    def getHeadModificationTAIL(self) -> bool:
        """检查路线尾部是否已更改为大路线"""
        return self.checkBitIsOne(self.side_notification, 0)
        
    def getHeadXroad(self) -> int:
        """返回头部的xroad索引。如果头部已修改(切换),返回默认值0"""
        return 0 if self.getHeadModificationHEAD() else self.xroad
        
    def getTailXroad(self) -> int:
        """返回尾部的xroad索引。如果尾部已修改(切换),返回默认值0"""
        return 0 if self.getHeadModificationTAIL() else self.xroad

    def checkBitIsOne(self,n: int, k: int) -> bool:
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