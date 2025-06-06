class CarInfo:
    """
    CarInfo类保存列车班次的信息，主要包括：
     table_num: 列车编号
     round_num: 班次编号
     route_num: 该班次运行的路径编号
     
    其他字段目前为未来开发预留
    """
    def __init__(self, table_num=None, round_num=None, route_num=None, cinfo=None):
        """
        构造函数，支持两种初始化方式：
        1. 使用表格信息创建CarInfo
        2. 直接复制另一个CarInfo对象的信息
        
        Args:
            table_num: 列车编号（表号）
            round_num: 班次编号（车次号）
            route_num: 路径编号
            cinfo: 另一个CarInfo对象
        """
        self.id = -1
        
        # 如果传入的是另一个CarInfo对象，则复制其信息
        if cinfo is not None:
            self.id = cinfo.id
            self.table_num = cinfo.table_num
            self.implicit_round_num = cinfo.implicit_round_num
            self.round_num = cinfo.round_num
            self.route_num = cinfo.route_num
            self.target_platform = cinfo.target_platform
            self.arr_time = cinfo.arr_time
            self.current_location = cinfo.current_location
            self.helper_indx = cinfo.helper_indx
            self.original_platform = cinfo.original_platform
            self.turn_back_start_time = cinfo.turn_back_start_time
        # 否则使用传入的参数初始化
        else:
            # 表号
            self.table_num = table_num
            # 车次号，如果为 None 则设置为 0
            self.round_num = 0 if round_num is None else round_num
            # 路径编号
            self.route_num = route_num
            # 用于确定下一辆/上一辆车的round_num，如果为 None 则设置为 0
            self.implicit_round_num = 0 if round_num is None else round_num
            
            # 为未来开发预留的额外字段
            # 目标站台
            self.target_platform = None
            # 到达时间
            self.arr_time = 0 
            # 当前站台
            self.current_location = None
            # 下一辆车的索引
            self.helper_indx = 0 
            
            # 出发站台
            self.original_platform = None
            
            # 调头开始时间
            self.turn_back_start_time = 0
        
    @classmethod
    def from_car_info(cls, cinfo: 'CarInfo') -> 'CarInfo':
        """
        Constructor 2, 直接从另一个CarInfo对象复制信息
        Args:
            cinfo: 源CarInfo对象
        Returns:
            新的CarInfo对象
        """
        instance = cls(cinfo.table_num, cinfo.round_num, cinfo.route_num)
        instance.id = cinfo.id
        instance.implicit_round_num = cinfo.implicit_round_num
        instance.target_platform = cinfo.target_platform
        instance.arr_time = cinfo.arr_time
        instance.current_location = cinfo.current_location
        instance.helper_indx = cinfo.helper_indx
        instance.original_platform = cinfo.original_platform
        instance.turn_back_start_time = cinfo.turn_back_start_time
        return instance
        
    def modify_round(self, quant: int) -> None:
        """
        将此车的轮次号(shift index)增加指定数量
        Args:
            quant: 增加的数量
        """
        self.round_num += quant
        self.implicit_round_num += quant