from typing import List
from enum import Enum
from Platform import Platform

class Path:
    """
    Path类表示交路运行中的路径单元。
    包含标识、方向、节点序列和反转状态等属性。
    """
    
    def __init__(self, id: str, name: str, path_route_id: str, dir: str, is_reverse: str):
        """
        初始化Path对象
        Args:
            id: 路径ID
            name: 路径名称
            path_route_id: 路径路线ID
            dir: 方向("Left"或"Right")
            is_reverse: 是否反转("false"或"true")
        """
        self.id: str = id
        self.name: str = name
        self.path_route_id: str = path_route_id
        
        # 根据输入字符串设置方向枚举
        if dir == "Left":
            self.dir = Platform.Direction.LEFT
        elif dir == "Right":
            self.dir = Platform.Direction.RIGHT
            
        # 设置是否反转
        self.is_reverse: bool = False if is_reverse == "false" else True
        
        # 路径中的节点(站台目的地码)列表
        self.nodeList: List[str] = []
        
        # 出发和到达的站台代码
        self.dep_dest_code: str = ""
        self.arr_dest_code: str = ""
        
    def addNode(self, node_dest: str) -> None:
        """
        向路径添加节点（即添加站台目的地码）。
        第一个添加的节点被视为出发代码，
        最后一个添加的节点被视为到达代码。
        
        Args:
            node_dest: 要添加的节点的目标代码
        """
        if len(self.nodeList) == 0:
            self.dep_dest_code = node_dest
        self.arr_dest_code = node_dest
        self.nodeList.append(node_dest)