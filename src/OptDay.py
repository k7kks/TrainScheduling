from typing import List, Dict, Set, Optional
from gurobipy import GRB
from .OptInterface import OptInterface
from TBtimes import TBtimes
from RouteSolution import RouteSolution
from util import util

class OptDay:
    """
    OptDay类用于处理列车调度的优化问题
    """
    
    def __init__(self, solver_type: str, obj_mode: int):
        """
        构造函数
        Args:
            solver_type: 求解器类型
            obj_mode: 目标函数类型
        """
        # 优化器接口
        self.model: Optional[OptInterface] = OptInterface(solver_type)
        
        # 列车及其在输入时刻表中的顺序映射
        self.order_map: Dict[int, int] = {}
        # 已固定的列车集合
        self.fixed_train: Set[int] = set()
        
        # TBtimes类,保存所有事件(头部,折返,尾部)
        self.tbm: Optional[TBtimes] = None
        
        # 目标函数类型,在main.cpp中描述
        self.obj_mode: int = obj_mode
        # 晚班车/早班车时间
        self.last_time: int = -1
        self.first_time: int = -1
        
        # 每个方向计算的最小停留时间差
        self.global_dwell_diff: List[int] = []
        
    def dispose(self) -> None:
        """析构函数,释放资源"""
        if self.model:
            self.model.dispose()
            
    def createModel(self) -> None:
        """创建并初始化所有必要的字段"""
        self.global_dwell_diff.extend([0, 0, 0, 0])
        if self.model:
            self.model.create_model()
            
    def writeModel(self, fnm: str = None) -> None:
        """
        将模型写入LP文件
        Args:
            fnm: 文件名,如果为None则使用默认位置
        """
        if self.model:
            if fnm:
                self.model.writeModel(fnm)
            else:
                self.model.writeModel()
                
    def buildModel(self, rss: List[List[RouteSolution]], 
                  tbm: TBtimes, fix_first: bool, obj_mode: int) -> None:
        """
        构建模型并为模型创建变量/约束
        Args:
            rss: 路由解决方案列表
            tbm: TBtimes对象
            fix_first: 是否固定第一个
            obj_mode: 目标函数类型(0:对齐原计划, 1:对齐原间隔)
        """
        self.obj_mode = obj_mode
        if self.model:
            self.model.build()
        self.construct_order_map(rss)
        travel_time_xroad = self.construct_conflicts(rss, tbm)
        self.tbm = tbm
        
        # 添加OPT模型变量和约束
        self.addVariables(rss, tbm, fix_first)
        self.addConstraints(rss, tbm, travel_time_xroad)
        
    def setGlobalMaxDwell(self, global_dwell_diff: List[int]) -> None:
        """
        设置全局最大停留时间
        Args:
            global_dwell_diff: 全局停留时间差列表
        """
        self.global_dwell_diff = global_dwell_diff
        
    def generateVarName(self, x: str, i: int, j: int) -> str:
        """
        根据信息生成变量名
        Args:
            x: 基础名称
            i: 第一个索引
            j: 第二个索引
        Returns:
            生成的变量名
        """
        return f"{x}_{i}_{j}"
    
    def add_variables(self, rss: List[List[RouteSolution]], 
                     tbm: TBtimes, fix_first: bool) -> None:
        """
        添加所有变量
        Args:
            rss: 路由解决方案列表
            tbm: TBtimes对象,包含可调整的停站信息
            fix_first: 是否固定第一个
        """
        min_track_times = tbm.min_track_times
        min_tb_times = tbm.min_tb_times
        max_tb_times = tbm.max_tb_times

        # 添加变量
        for dir in range(2):
            rs_last_car = None
            best_gap_last = -1
            rs_first_car = None 
            best_gap_first = -1
            
            for c_indx in range(len(rss[dir])):
                # 获取车辆信息
                rs = rss[dir][c_indx]
                
                # 找到最接近末班车时间的车
                if self.last_time > 0 and (rs_last_car is None or 
                    best_gap_last > abs(rs.arr_time[0] - self.last_time)):
                    best_gap_last = abs(rs.arr_time[0] - self.last_time)
                    rs_last_car = rs
                    
                # 找到最接近首班车时间的车    
                if self.first_time > 0 and (rs_first_car is None or 
                    best_gap_first > abs(rs.arr_time[0] - self.first_time)):
                    best_gap_first = abs(rs.arr_time[0] - self.first_time)
                    rs_first_car = rs

                # 获取车辆的交叉口信息(头部/尾部)
                i = rs.car_info.round_num
                xroad = rs.xroad
                xroad_head = rs.get_head_xroad()
                xroad_tail = rs.get_tail_xroad()

                # 获取事件大小
                head_size = len(min_track_times[xroad_head][dir][0])
                tail_size = len(min_track_times[xroad_tail][dir][2])

                # 添加发车时间变量
                st_vnm = f"t_dir{dir}_i{i}_0"
                lb = 0.0
                ub = 3600.0 * 48
                if self.model:
                    self.model.addVar_(lb, ub, 0.0, GRB.CONTINUOUS, st_vnm)

                # 添加头部事件时间(到达时间,停站时间,发车时间)
                for t in range(head_size):
                    # 停站开始
                    intm_vnm = f"head_s_t_dir{dir}_i{i}_{t}"
                    lb = 0.0
                    ub = 3600.0 * 48
                    if self.model:
                        self.model.addVar_(lb, ub, 0.0, GRB.CONTINUOUS, intm_vnm)
                    
                    # 停站结束
                    intm_vnm = f"head_e_t_dir{dir}_i{i}_{t}"
                    if self.model:
                        self.model.addVar_(lb, ub, 0.0, GRB.CONTINUOUS, intm_vnm)

                    # 停站时间
                    intm_vnm = f"head_delta_t_dir{dir}_i{i}_{t}"
                    lb = min_tb_times[xroad_head][dir][0][t]
                    ub = max_tb_times[xroad_head][dir][0][t]
                    if self.model:
                        self.model.addVar_(lb, ub, 0.0, GRB.CONTINUOUS, intm_vnm)

                # 添加车辆结束时间
                ed_vnm = f"t_dir{dir}_i{i}_1"
                lb = 0.0
                ub = 3600.0 * 48
                if self.model:
                    self.model.addVar_(lb, ub, 0.0, GRB.CONTINUOUS, ed_vnm)

                # 添加尾部事件时间(到达时间,停站时间,发车时间)
                for t in range(tail_size):
                    # 停站开始
                    intm_vnm = f"tail_s_t_dir{dir}_i{i}_{t}"
                    lb = 0.0
                    ub = 3600.0 * 48
                    if self.model:
                        self.model.addVar_(lb, ub, 0.0, GRB.CONTINUOUS, intm_vnm)
                    
                    # 停站结束
                    intm_vnm = f"tail_e_t_dir{dir}_i{i}_{t}"
                    if self.model:
                        self.model.addVar_(lb, ub, 0.0, GRB.CONTINUOUS, intm_vnm)

                    # 停站时间
                    intm_vnm = f"tail_delta_t_dir{dir}_i{i}_{t}"
                    lb = min_tb_times[xroad_tail][dir][2][t]
                    ub = max_tb_times[xroad_tail][dir][2][t]
                    if self.model:
                        self.model.addVar_(lb, ub, 0.0, GRB.CONTINUOUS, intm_vnm)

                # 如果需要添加折返时间
                if (rs.next_ptr is not None and 
                    rs.next_ptr.car_info.round_num in self.order_map):
                    # 需要添加折返
                    tb_vnm = f"tb_delta_t_dir{dir}_i{i}"
                    lb = min_tb_times[xroad_tail][dir][1][0]
                    ub = max_tb_times[xroad_tail][dir][1][0]
                    if self.model:
                        self.model.addVar_(lb, ub, 0.0, GRB.CONTINUOUS, tb_vnm)

                # 添加用于衡量某些指标的目标变量
                self.add_obj_var(dir, i, rs, 5, 1)
                
                # 如果两个交叉口之间可能存在冲突,添加变量
                self.add_conflict_var(dir, i, rs, xroad_head, xroad_tail)

            # 处理末班车
            if self.last_time > 0 and rs_last_car is not None:
                self.fixed_train.add(rs_last_car.car_info.round_num)
                i = rs_last_car.car_info.round_num
                st_vnm = f"t_dir{dir}_i{i}_0"
                if self.model:
                    self.model.addConstr_([st_vnm], [1.0], GRB.EQUAL, 
                                        self.last_time, f"last_car_cons{i}_dir{dir}")

            # 处理首班车
            if self.first_time > 0 and rs_first_car is not None:
                i = rs_first_car.car_info.round_num
                # 惩罚项
                pen_1 = f"early_d{dir}_i{i}_pos"
                l = 0.0
                u = 3600.0 * 24.0
                if self.model:
                    self.model.addVar_(l, u, 1, GRB.CONTINUOUS, pen_1)
                    pen_2 = f"early_d{dir}_i{i}_neg"
                    self.model.addVar_(l, u, 1, GRB.CONTINUOUS, pen_2)
                
                    st_vnm = f"t_dir{dir}_i{i}_0"
                    self.model.addConstr_([st_vnm, pen_1], [-1.0, 1.0], 
                                        GRB.GREATER_EQUAL, -self.first_time, 
                                        f"first_car_cons1{i}_dir{dir}")
                    self.model.addConstr_([st_vnm, pen_1], [1.0, 1.0],
                                        GRB.GREATER_EQUAL, self.first_time,
                                        f"first_car_cons2{i}_dir{dir}")

    def add_conflict_var(self, dir: int, i: int, rs: RouteSolution, 
                        xroad_head: int, xroad_tail: int) -> None:
        """
        如果两个相邻列车来自不同的交叉口,添加冲突变量
        """
        lb = 0.0
        ub = 3600.0 * 48
        
        # 如果有多个交叉口,需要识别冲突点
        # 只需要为大的添加
        if self.tbm.n_xroads > 1:
            if xroad_head == 0:
                vnm = f"conflict_d{dir}_i{i}_0"
                if self.model:
                    self.model.addVar_(lb, ub, 0.0, GRB.CONTINUOUS, vnm)
            if xroad_tail == 0:
                vnm = f"conflict_d{dir}_i{i}_1"
                if self.model:
                    self.model.addVar_(lb, ub, 0.0, GRB.CONTINUOUS, vnm)

    def add_obj_var(self, dir: int, i: int, rs: RouteSolution, 
                    ratio1: float, ratio2: float) -> None:
        """
        添加目标变量,由ratio1和ratio2加权
        """
        lb = 0.0
        ub = 3600.0 * 48

        # 目标变量第一部分,最小化与原计划的差距
        vnm = f"offset_pos{dir}_i{i}"
        if self.model:
            self.model.addVar_(lb, ub, ratio1, GRB.CONTINUOUS, vnm)
            vnm = f"offset_neg{dir}_i{i}"
            self.model.addVar_(lb, ub, ratio1, GRB.CONTINUOUS, vnm)

        # 这是为了均匀性
        vnm = f"offset2_pos{dir}_i{i}"
        if self.model:
            self.model.addVar_(lb, ub, ratio2, GRB.CONTINUOUS, vnm)
            vnm = f"offset2_neg{dir}_i{i}"
            self.model.addVar_(lb, ub, ratio2, GRB.CONTINUOUS, vnm)

    def construct_conflicts(self, rss: List[List[RouteSolution]], 
                          tbm: TBtimes) -> List[List[int]]:
        """
        获取冲突时间,以及从a的最后一个事件到b的第一个事件的经过时间
        返回值格式: [dir X (head, tail)]
        Args:
            rss: 路由解决方案列表
            tbm: TBtimes对象
        Returns:
            冲突信息列表
        """
        res: List[List[int]] = []
        # 如果只有1个交叉口,不需要处理,直接返回
        if tbm.n_xroads < 2:
            return res
            
        min_track_times = tbm.min_track_times
        
        # 遍历所有车辆
        for dir in range(2):
            rs_small = None
            rs_large = None
            
            res.append([])
            
            # 首先需要找到一个小路线和一个大路线
            for i in range(len(rss[dir])):
                rs = rss[dir][i]
                # 我们只需要原始路径,所以跳过任何被修改的
                if rs.side_notification != 0:
                    continue
                if rs.xroad == 0:
                    rs_large = rs
                elif rs.xroad == 1:
                    rs_small = rs
                if rs_small and rs_large:
                    break
                    
            # 需要找到碰撞站点
            # 然后,我们可以找到结束事件和小交叉口开始之间的运行时间
            # 获取事件大小
            n_events_0 = len(min_track_times[0][dir][0])
            n_events_2 = len(min_track_times[0][dir][2])
            n_events_0_s = len(min_track_times[1][dir][0])
            n_events_2_s = len(min_track_times[1][dir][2])
            
            max_stop = -1
            
            # 计算时间(头部)
            head_stop = 0
            start_time = rs_large.dep_time[n_events_0]
            end_time_l = -1
            for i, plt_nm in enumerate(rs_large.stopped_platforms):
                if plt_nm == rs_small.stopped_platforms[n_events_0_s]:
                    # 找到了,计算时间
                    end_time_l = rs_large.arr_time[i]
                    head_stop = rs_large.dep_time[i] - rs_large.arr_time[i]
                    
            if end_time_l < 0:
                print("ERROR:::: no colliding1 large/small xroad")
                sys.exit(0)
            travel_l = end_time_l - start_time
            res[dir].append(travel_l)
            
            # 计算时间(尾部)
            tail_stop = 0
            start_time_l = -1
            end_time = rs_large.arr_time[len(rs_large.arr_time) - 1 - n_events_2]
            for i, plt_nm in enumerate(rs_large.stopped_platforms):
                if plt_nm == rs_small.stopped_platforms[len(rs_small.stopped_platforms) - 1 - n_events_2_s]:
                    # 找到了,计算时间
                    start_time_l = rs_large.dep_time[i]
                    tail_stop = rs_large.dep_time[i] - rs_large.arr_time[i]
                    
            if start_time_l < 0:
                print("ERROR:::: no colliding2 large/small xroad")
                sys.exit(0)
            travel_l = end_time - start_time_l
            res[dir].append(travel_l)
            
            # 计算停站时间(头部)
            res[dir].append(head_stop)
            res[dir].append(tail_stop)
            
        # 返回计算的冲突信息
        return res
        
    def construct_order_map(self, rss: List[List[RouteSolution]]) -> None:
        """
        获取每个列车的顺序,返回带有其索引的映射
        Args:
            rss: 路由解决方案列表
        """
        self.order_map.clear()
        for dir in range(2):
            for i in range(len(rss[dir])):
                self.order_map[rss[dir][i].car_info.round_num] = i

    def add_tb_cons(self, rs_this: RouteSolution, rs_next: RouteSolution, dir: int) -> None:
        """
        添加折返约束到模型
        t_A_1 + tb_delta_t_dir_A = t_B_0
        Args:
            rs_this: 当前路由解决方案
            rs_next: 下一个路由解决方案
            dir: 方向
        """
        # 当前车次结束 + 折返时间 - 下一车次开始 == 0
        round_n_this = rs_this.car_info.round_num
        round_n_next = rs_next.car_info.round_num
        vnm_this_end = f"t_dir{dir}_i{round_n_this}_1"
        tb_vnm = f"tb_delta_t_dir{dir}_i{round_n_this}"
        vnm_next_start = f"t_dir{1-dir}_i{round_n_next}_0"

        # 添加约束
        if self.model:
            self.model.addConstr_([vnm_this_end, tb_vnm, vnm_next_start],
                                [1.0, 1.0, -1.0],
                                GRB.EQUAL, 0.,
                                f"Turnback_{round_n_this}_{round_n_next}")

    def add_inout_handlers(self, cpr_out: List[ConflictPair], 
                          cpr_in: List[ConflictPair]) -> None:
        """
        根据输入添加进出站列车的约束
        Args:
            cpr_out: 出站冲突对列表
            cpr_in: 进站冲突对列表
        """
        if self.tbm:
            min_track_times = self.tbm.min_track_times
            for cpr in cpr_out:
                self.add_out_conflict(cpr, min_track_times)
            for cpr in cpr_in:
                self.add_in_conflict(cpr, min_track_times)

    def add_out_conflict(self, cpr: ConflictPair,
                        min_track_times: List[List[List[List[int]]]]) -> None:
        """
        添加出站列车的约束
        Args:
            cpr: 冲突对
            min_track_times: 最小轨道时间
        """
        # 获取基本信息
        dir = cpr.dir
        dir_oppo = 1 - dir
        tail_size = len(min_track_times[1][dir_oppo][2])
        idx = cpr.station_idx
        rs = cpr.rs
        i = rs.car_info.round_num

        if not self.model:
            return

        # 1. 添加第一个折返时间变量
        tb1_vnm = f"out_tb1_delta_i{i}"
        if not self.model.checkHasVar_(tb1_vnm):
            self.model.addVar_(cpr.min_tb1, cpr.max_tb1, 0.0001, 
                             GRB.CONTINUOUS, tb1_vnm)

        # 2. 添加第一段运行时间变量(头尾)
        # - 头部
        rs_head_time = f"out_t_i{i}_0"
        if not self.model.checkHasVar_(rs_head_time):
            self.model.addVar_(0.0, 3600.0 * 48, 0.0, 
                             GRB.CONTINUOUS, rs_head_time)

        # - 尾部(与第一个折返连接)
        rs_tail_time = f"out_t_i{i}_1"
        if not self.model.checkHasVar_(rs_tail_time):
            self.model.addVar_(0.0, 3600.0 * 48, 0.0, 
                             GRB.CONTINUOUS, rs_tail_time)

        # 3. 添加第二个折返时间变量
        tb2_vnm = f"out_tb2_delta_i{i}"
        if not self.model.checkHasVar_(tb2_vnm):
            self.model.addVar_(cpr.min_tb2, cpr.max_tb2, 0.0, 
                             GRB.CONTINUOUS, tb2_vnm)

        rs_tail2_time = f"out2_t_i{i}_1"
        if not self.model.checkHasVar_(rs_tail2_time):
            self.model.addVar_(0.0, 3600.0 * 48, 0.0, 
                             GRB.CONTINUOUS, rs_tail2_time)

        # 添加自身约束
        # 1. 第一个折返时间约束
        rs_start = f"t_dir{dir}_i{i}_0"
        self.model.addConstr_([rs_start, tb1_vnm, rs_tail_time],
                            [1.0, -1.0, -1.0],
                            GRB.EQUAL, 0.,
                            f"out_con_tb1_{dir}_{i}")

        # 2. 第一段运行时间约束
        self.model.addConstr_([rs_head_time, rs_tail_time],
                            [-1.0, 1.0],
                            GRB.EQUAL, cpr.travel_time,
                            f"out_travelt_{dir}_{i}")

        # 3. 第二个折返时间约束
        self.model.addConstr_([rs_head_time, tb2_vnm, rs_tail2_time],
                            [1.0, -1.0, -1.0],
                            GRB.EQUAL, 0,
                            f"out_con_tb2_{dir}_{i}")

        # 添加冲突约束
        if cpr.conf_left:
            rs_l = cpr.conf_left
            l_rn = rs_l.car_info.round_num
            rs_l_conf = f"t_dir{dir_oppo}_i{l_rn}_1"
            if idx != 0:
                # 需要使用事件
                rs_l_conf = f"tail_e_t_dir{dir_oppo}_i{l_rn}_{tail_size - idx}"
            
            mtt = min_track_times[1][dir_oppo][2][tail_size - idx]
            # rs_tail2_time - mtt >= event end
            util.pf(util.ANSI_GREEN + f"{rs_tail2_time} - {mtt} >= {rs_l_conf}")
            self.model.addConstr_([rs_tail2_time, rs_l_conf],
                                [1.0, -1.0],
                                GRB.GREATER_EQUAL, mtt,
                                f"out_conf_{dir}_{i}")

        # 右侧约束
        if cpr.conf_right:
            rs_r = cpr.conf_right
            r_rn = rs_r.car_info.round_num
            rs_r_conf = f"t_dir{dir_oppo}_i{r_rn}_0"
            if idx != 0:
                # 需要使用事件
                rs_r_conf = f"head_s_t_dir{dir_oppo}_i{r_rn}_{idx}"
            
            mtt = min_track_times[1][dir_oppo][0][idx]
            # event start - mtt >= rs_tail2_time
            util.pf(util.ANSI_GREEN + f"{rs_r_conf} - {mtt} >= {rs_tail2_time}")
            self.model.addConstr_([rs_r_conf, rs_tail2_time],
                                [1.0, -1.0],
                                GRB.GREATER_EQUAL, mtt,
                                f"out_conf2_{dir}_{i}")
    
    # ... existing code ...

    def add_in_conflict(self, cpr: ConflictPair,
                       min_track_times: List[List[List[List[int]]]]) -> None:
        """
        添加进站列车的约束
        Args:
            cpr: 冲突对
            min_track_times: 最小轨道时间
        """
        # 获取基本信息
        dir = cpr.dir
        dir_oppo = 1 - dir
        head_size = len(min_track_times[1][dir_oppo][0])
        idx = cpr.station_idx
        rs = cpr.rs
        i = rs.car_info.round_num

        if not self.model:
            return

        # 1. 添加第一个折返时间变量
        tb1_vnm = f"in_tb1_delta_i{i}"
        if not self.model.checkHasVar_(tb1_vnm):
            self.model.addVar_(cpr.min_tb1, cpr.max_tb1, 0.0001, 
                             GRB.CONTINUOUS, tb1_vnm)

        # 2. 添加第一段运行时间变量(头尾)
        # - 头部
        rs_head_time = f"in_t_i{i}_0"
        if not self.model.checkHasVar_(rs_head_time):
            self.model.addVar_(0.0, 3600.0 * 48, 0.0, 
                             GRB.CONTINUOUS, rs_head_time)

        # - 尾部(与第一个折返连接)
        rs_tail_time = f"in_t_i{i}_1"
        if not self.model.checkHasVar_(rs_tail_time):
            self.model.addVar_(0.0, 3600.0 * 48, 0.0, 
                             GRB.CONTINUOUS, rs_tail_time)

        # 3. 添加第二个折返时间变量
        tb2_vnm = f"in_tb2_delta_i{i}"
        if not self.model.checkHasVar_(tb2_vnm):
            self.model.addVar_(cpr.min_tb2, cpr.max_tb2, 0.0, 
                             GRB.CONTINUOUS, tb2_vnm)

        rs_tail2_time = f"in2_t_i{i}_1"
        if not self.model.checkHasVar_(rs_tail2_time):
            self.model.addVar_(0.0, 3600.0 * 48, 0.0, 
                             GRB.CONTINUOUS, rs_tail2_time)

        # 添加自身约束
        # 1. 第一个折返时间约束
        rs_start = f"t_dir{dir}_i{i}_1"
        self.model.addConstr_([rs_start, tb1_vnm, rs_tail_time],
                            [1.0, -1.0, -1.0],
                            GRB.EQUAL, 0.,
                            f"in_con_tb1_{dir}_{i}")

        # 2. 第一段运行时间约束
        self.model.addConstr_([rs_head_time, rs_tail_time],
                            [-1.0, 1.0],
                            GRB.EQUAL, cpr.travel_time,
                            f"in_travelt_{dir}_{i}")

        # 3. 第二个折返时间约束
        self.model.addConstr_([rs_head_time, tb2_vnm, rs_tail2_time],
                            [1.0, -1.0, -1.0],
                            GRB.EQUAL, 0,
                            f"in_con_tb2_{dir}_{i}")

        # 添加冲突约束
        if cpr.conf_left:
            rs_l = cpr.conf_left
            l_rn = rs_l.car_info.round_num
            rs_l_conf = f"t_dir{dir_oppo}_i{l_rn}_1"
            if idx != 0:
                # 需要使用事件
                rs_l_conf = f"head_e_t_dir{dir_oppo}_i{l_rn}_{idx}"
            
            mtt = min_track_times[1][dir_oppo][0][idx]
            # rs_tail2_time - mtt >= event end
            util.pf(util.ANSI_GREEN + f"{rs_tail2_time} - {mtt} >= {rs_l_conf}")
            self.model.addConstr_([rs_tail2_time, rs_l_conf],
                                [1.0, -1.0],
                                GRB.GREATER_EQUAL, mtt,
                                f"in_conf_{dir}_{i}")

        # 右侧约束
        if cpr.conf_right:
            rs_r = cpr.conf_right
            r_rn = rs_r.car_info.round_num
            rs_r_conf = f"t_dir{dir_oppo}_i{r_rn}_0"
            if idx != 0:
                # 需要使用事件
                rs_r_conf = f"head_s_t_dir{dir_oppo}_i{r_rn}_{idx}"
            
            mtt = min_track_times[1][dir_oppo][0][idx]
            # event start - mtt >= rs_tail2_time
            util.pf(util.ANSI_GREEN + f"{rs_r_conf} - {mtt} >= {rs_tail2_time}")
            self.model.addConstr_([rs_r_conf, rs_tail2_time],
                                [1.0, -1.0],
                                GRB.GREATER_EQUAL, mtt,
                                f"in_conf2_{dir}_{i}")

    def optimize(self) -> None:
        """执行优化求解"""
        if self.model:
            self.model.optimize()

    def get_objval(self) -> float:
        """
        获取目标函数值
        Returns:
            目标函数的最优值
        """
        if self.model:
            return self.model.getobjval()
        return 0.0

    def is_solved2opt(self) -> bool:
        """
        检查是否求得最优解
        Returns:
            是否找到最优解
        """
        if self.model:
            return self.model.isSolved2Opt()
        return False

    def retrieve_X(self, var_name: str) -> int:
        """
        获取整数变量的解
        Args:
            var_name: 变量名
        Returns:
            变量的整数解
        """
        if self.model:
            return self.model.retrieve_X(var_name)
        return 0

    def retrieve_realX(self, var_name: str) -> float:
        """
        获取实数变量的解
        Args:
            var_name: 变量名
        Returns:
            变量的实数解
        """
        if self.model:
            return self.model.retrieve_realX(var_name)
        return 0.0