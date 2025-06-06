from typing import List

class DepotRoutesInfo:
    """
    DepotRoutesInfo类用于保存每个车库的进出计划，包括类型、路径和时间：即DepotRoutes
    """
    def __init__(self, Direction,InOrOut,UpIn, DownIn, UpOut, DownOut):
        """
        构造函数，根据四条路线创建车库信息
        Args:
            UpIn: 上行进站路线(字符串格式"type:id1,id2..."或整数列表[id1,id2...])
            DownIn: 下行进站路线(字符串格式"type:id1,id2..."或整数列表[id1,id2...])
            UpOut: 上行出站路线(字符串格式"type:id1,id2..."或整数列表[id1,id2...])
            DownOut: 下行出站路线(字符串格式"type:id1,id2..."或整数列表[id1,id2...])
        """
        # 路线类型列表
        # routeType[inout][updown]
        # inout: 进站=0 出站=1
        # updown: 上行=0 下行=1
        self.direction = Direction
        self.inOrOut = InOrOut
        self.routeType: List[List[str]] = [[], []]
        
        # 每个进出站路线的实际计划
        # 路径ID: routes[inout][updown][path_index]
        # 路径时间: routes_time[inout][updown][path_index]
        # inout: 进站=0 出站=1
        # updown: 上行=0 下行=1
        self.routes: List[List[List[str]]] = [[], []]
        self.routes_time: List[List[List[int]]] = [[], []]
        
        # 处理上行进站路线
        if isinstance(UpIn, list):
            self.routeType[0].append("default")  # 如果是列表输入，使用默认类型
            tmp_routes = [str(x) for x in UpIn]  # 转换为字符串列表
            tmp_times = [-1] * len(UpIn)
            self.routes[0].append(tmp_routes)
            self.routes_time[0].append(tmp_times)
        else:# 如果不是列表输入
            regex = ":"
            comma = ","
            lst = UpIn.split(regex)
            self.routeType[0].append(lst[0])
            lst = lst[1].split(comma)
            tmp_routes = []
            tmp_times = []
            for i in range(len(lst)):
                tmp_routes.append(lst[i])
                tmp_times.append(-1)
            self.routes[0].append(tmp_routes)
            self.routes_time[0].append(tmp_times)
        
        # 处理下行进站路线
        if isinstance(DownIn, list):
            self.routeType[0].append("default")
            tmp_routes = [str(x) for x in DownIn]
            tmp_times = [-1] * len(DownIn)
            self.routes[0].append(tmp_routes)
            self.routes_time[0].append(tmp_times)
        else:
            lst = DownIn.split(regex)
            self.routeType[0].append(lst[0])
            lst = lst[1].split(comma)
            tmp_routes = []
            tmp_times = []
            for i in range(len(lst)):
                tmp_routes.append(lst[i])
                tmp_times.append(-1)
            self.routes[0].append(tmp_routes)
            self.routes_time[0].append(tmp_times)
        
        # 处理上行出站路线
        if isinstance(UpOut, list):
            self.routeType[1].append("default")
            tmp_routes = [str(x) for x in UpOut]
            tmp_times = [-1] * len(UpOut)
            self.routes[1].append(tmp_routes)
            self.routes_time[1].append(tmp_times)
        else:
            lst = UpOut.split(regex)
            self.routeType[1].append(lst[0])
            lst = lst[1].split(comma)
            tmp_routes = []
            tmp_times = []
            for i in range(len(lst)):
                tmp_routes.append(lst[i])
                tmp_times.append(-1)
            self.routes[1].append(tmp_routes)
            self.routes_time[1].append(tmp_times)
        
        # 处理下行出站路线
        if isinstance(DownOut, list):
            self.routeType[1].append("default")
            tmp_routes = [str(x) for x in DownOut]
            tmp_times = [-1] * len(DownOut)
            self.routes[1].append(tmp_routes)
            self.routes_time[1].append(tmp_times)
        else:
            lst = DownOut.split(regex)
            self.routeType[1].append(lst[0])
            lst = lst[1].split(comma)
            tmp_routes = []
            tmp_times = []
            for i in range(len(lst)):
                tmp_routes.append(lst[i])
                tmp_times.append(-1)
            self.routes[1].append(tmp_routes)
            self.routes_time[1].append(tmp_times)
            
        
    def get_type(self, inout: int, updown: int) -> str:
        """
        根据进出站方向和上下行方向获取路线类型
        Args:
            inout: 进出站方向（进站=0 出站=1）
            updown: 上下行方向（上行=0 下行=1）
        Returns:
            路线类型
        """
        return self.routeType[inout][updown]

    def __repr__(self):
        return f"DepotRoutesInfo(direction={self.direction}, inOrOut={self.inOrOut})"