class Turnback:
    """
    Turnback类表示车站内的折返轨，
    用于列车改变行驶方向。
    
    每个折返轨包含：
    - 唯一的ID和目的地代码
    - 显示名称和内部名称
    - 时间约束，定义列车在折返前必须等待的时间
    """
    
    def __init__(self, id: str,
                 name: str,
                 show_name: str,
                 dest_code: str,
                 min_tb_time: str,
                 def_tb_time: str,
                 max_tb_time: str):
        """
        构造函数
        Args:
            id: 折返轨ID
            name: 内部名称
            show_name: 显示名称
            dest_code: 折返轨目的地码
            min_tb_time: 最小折返时间
            def_tb_time: 默认折返时间
            max_tb_time: 最大折返时间
        """
        self.id: int = int(id)
        self.name: str = name
        self.show_name: str = show_name
        self.dest_code: str = dest_code
        self.min_tb_time: int = int(min_tb_time)
        self.def_tb_time: int = int(def_tb_time)
        self.max_tb_time: int = int(max_tb_time)