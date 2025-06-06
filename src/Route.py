class Route:
    """
    Route类表示一对方向性列车路径—每个方向各一条。
    
    每个路线包含：
    - 唯一的整数ID
    - 人类可读的名称
    - 上行和下行方向路径ID的引用
    
    主要用于调度时识别归属于单一路线的方向性路径。
    """
    
    def __init__(self, id: str, name: str, up_route: str, down_route: str):
        """
        构造Route对象,包含ID、名称和上下行路径引用。
        
        Args:
            id: 唯一ID(字符串,会被转换为整数)
            name: 路线的描述性名称
            up_route: 上行方向的路径ID
            down_route: 下行方向的路径ID
        """
        self.id: int = int(id)
        self.name: str = name
        self.up_route: str = up_route
        self.down_route: str = down_route
        
    def get_path(self, up_down: int) -> str:
        """
        根据方向获取路径ID。
        
        Args:
            up_down: 方向指示器(0 = 上行, 1 = 下行)
        Returns:
            对应的路径ID(上行或下行)
        """
        if up_down == 0:
            return self.up_route
        else:
            return self.down_route