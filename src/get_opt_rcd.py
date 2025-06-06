import pulp
import numpy as np
from AdjRcd_Rule import *
from time import time


class RcdGenerator:
    def __init__(self, params, st1, st2):
        self.params = params
        self.st1 = st1
        self.st2 = st2
        self.params.up_time2turnback = 30
        self.params.down_time2turnback = 30
        self.M = 1e5  # 大常数
        self.fast_mod = 0
        self.start_time = time()
        # 变量索引计算函数
        self.get_idx = lambda route, trip: (route * self.v_num + trip) if route <= 1 else (
                                                                                                  route - 2) * self.v_num + trip
        # 初始化模型
        self.model = None
        self.solution = np.zeros((4, self.params.v_num))
        self.r = -1

    def _init_variables(self):
        """初始化决策变量"""
        self.v_num = max(self.params.trip_num[self.r], self.params.trip_num[self.r + 1])
        if self.r == 0:
            trip_num1 = self.params.trip_num[0]
            # 计算辅助变量维度
            cnt = sum(1 for i in range(trip_num1) if self.params.the_aft_variable[0][i] == -1)
            self.aux_num = cnt * trip_num1
        else:
            self.aux_num = 0

        # 总变量数（主变量+辅助变量+其他）
        if self.r == 0:
            self.n_vars = 2 * self.v_num + self.params.trip_num[0] * self.params.trip_num[1] + self.aux_num + \
                          self.params.trip_num[self.r] - 1 + self.params.trip_num[self.r + 1] - 1 + 1

        else:
            self.n_vars = 2 * self.v_num + self.params.trip_num[self.r] - 1 + self.params.trip_num[self.r + 1] - 1 + 1
        self.x = []
        self.y = []
        x_cnt = 0
        for i in range(2 * self.v_num):
            self.x.append(pulp.LpVariable('x' + str(x_cnt), cat='Continuous'))
            x_cnt += 1

        if self.r == 0:
            for i in range(self.params.trip_num[0] * self.params.trip_num[1] + self.aux_num):
                self.x.append(pulp.LpVariable('x' + str(x_cnt), cat='Binary'))
                x_cnt += 1

        for i in range(self.params.trip_num[self.r] - 1 + self.params.trip_num[self.r + 1] - 1 + 1):
            self.x.append(pulp.LpVariable('x' + str(x_cnt), cat='Continuous'))
            x_cnt += 1

        self.w = pulp.LpVariable('w', cat='Continuous')

        self.y.append(pulp.LpVariable('y' + str(0), cat='Continuous'))
        self.y.append(pulp.LpVariable('y' + str(1), cat='Continuous'))
        self.y.append(pulp.LpVariable('y' + str(2), cat='Continuous'))
        self.y.append(pulp.LpVariable('y' + str(3), cat='Continuous'))

    def solve_smart(self):
        self.r = 0
        self.model = pulp.LpProblem("TrainScheduling", sense=pulp.LpMinimize)
        self.fast_mod = 1
        self._init_variables()
        s1, v1 = self._solve_smart()
        self._process_solution()

        self.r = 2
        self.model = pulp.LpProblem("TrainScheduling", sense=pulp.LpMinimize)
        self._init_variables()
        s2, v2 = self._solve_smart()
        self._process_solution()

        # 生成rcd
        for i in range(2):
            p = [0, 0]
            for j in range(len(self.params.rcd[i])):
                if p[0] < self.params.trip_num[i] and (p[1] >= self.params.trip_num[i + 2] or self.solution[i, p[0]] < self.solution[i + 2, p[1]]):
                    self.params.rcd[i][j] = i
                    p[0] += 1
                else:
                    self.params.rcd[i][j] = i + 2
                    p[1] += 1

        print("rcd生成完成", s1 + s2)
        return self.solution, self.params

    def _solve_smart(self):
        """构建并求解模型"""
        self._add_objective()
        self._add_obj_constraints()
        self._add_first_last_trip_constraints()
        self._add_return_constraints()
        self._add_down_direction_constraints()
        self._add_up_direction_constraints()
        self._add_turnback_constraints()
        self._add_peak_period_constraints()
        # self.model.solve(solver=pulp.GUROBI())
        self.model.solve()
        print("Status:", pulp.LpStatus[self.model.status])
        if pulp.LpStatus[self.model.status] == "Infeasible":
            return 0, pulp.value(self.model.objective)

        while pulp.LpStatus[self.model.status] != "Infeasible":
            the_set = self.check_feasibility()
            if len(the_set) == 0: break
            for i, j, k in the_set:
                self._add_coupling_constraints_smart(i, j, k)
            # 参数设置
            self.model.solve()
            print("Status:", pulp.LpStatus[self.model.status])

        if pulp.LpStatus[self.model.status] == "Infeasible":
            return 0, pulp.value(self.model.objective)
        # 输出每个变量的最优值
        return 1, pulp.value(self.model.objective)

    def _add_objective(self):
        """设置目标函数"""
        # 主变量惩罚项
        temp = 0
        for r in range(2):
            idx = self.get_idx(r, self.params.trip_num[r] - 1)
            temp += 0.001 * self.x[idx]

        if self.r == 0:
            # 辅助变量惩罚项
            self.interval_constant = 2 * self.v_num + self.params.trip_num[0] * self.params.trip_num[
                1] + self.aux_num
        else:
            self.interval_constant = 2 * self.v_num

        for i in range(self.interval_constant, self.n_vars - 1):
            temp += 10 * self.x[i]

        temp += 10 * (self.y[0] + self.y[1] + self.y[2] + self.y[3])

        self.model += temp + 10000 * self.w

    def _add_constraints(self):
        """添加约束条件"""
        self._add_obj_constraints()
        self._add_first_last_trip_constraints()
        self._add_coupling_constraints()
        self._add_return_constraints()
        self._add_shared_track_constraints()
        self._add_turnback_constraints()
        self._add_peak_period_constraints()

    def _add_obj_constraints(self):
        """添加列车耦合约束"""
        down_first = self.get_idx(self.r, 0)
        down_last = self.get_idx(self.r, self.params.trip_num[self.r] - 1)

        cons = 1 / (self.params.trip_num[self.r] - 1)
        for i in range(1, self.params.trip_num[self.r]):
            ex = self.x[self.get_idx(self.r, i)] - self.x[self.get_idx(self.r, i - 1)]
            expr = ex - cons * self.x[down_last] + cons * self.x[down_first]
            self.model += (expr <= self.x[self.interval_constant + i - 1])
            self.model += (-expr <= self.x[self.interval_constant + i - 1])

        down_first = self.get_idx(self.r + 1, 0)
        down_last = self.get_idx(self.r + 1, self.params.trip_num[self.r + 1] - 1)
        cons = 1 / (self.params.trip_num[self.r + 1] - 1)
        for i in range(1, self.params.trip_num[self.r + 1]):
            ex = self.x[self.get_idx(self.r + 1, i)] - self.x[self.get_idx(self.r + 1, i - 1)]
            expr = ex - cons * self.x[down_last] + cons * self.x[down_first]
            self.model += (expr <= self.x[self.interval_constant + self.params.trip_num[self.r] - 1 + i - 1])
            self.model += (-expr <= self.x[self.interval_constant + self.params.trip_num[self.r] - 1 + i - 1])

    def get_travel_time(self, i, j):
        if i > j:
            return self.params.travel_time_matrix[1][i][j]
        return self.params.travel_time_matrix[0][i][j]

    # 需要注意的是，get_stop_time应对i=j的情况会出问题，默认为上行，但是不会出现i=j的情况
    def get_stop_time(self, i, j):
        if i > j:
            return self.params.stop_time_matrix[1][i][j]
        return self.params.stop_time_matrix[0][i][j]

    def _add_coupling_constraints_smart(self, i, j, k):
        """双向不同时到达约束"""
        # 统一参数计算格式
        if len(self.params.key_stations) == 0 or self.fast_mod == 1:
            return
        t1 = self.get_travel_time(self.params.jiaolu_start[0], self.params.key_stations[0]) + self.get_stop_time(
            self.params.jiaolu_start[0], self.params.key_stations[0])
        t2 = self.get_travel_time(self.params.jiaolu_end[0], self.params.key_stations[0]) + self.get_stop_time(
            self.params.jiaolu_end[0], self.params.key_stations[0])
        if k >= 30:
            expr = (self.x[self.get_idx(0, i)] + t1 - self.x[self.get_idx(1, j)] - t2)
            self.model += (expr >= self.params.same_arrive_delta + self.get_stop_time(self.params.key_stations[0],
                                                                                      self.params.key_stations[0]))
        elif k <= -30:
            expr = (self.x[self.get_idx(0, i)] + t1 - self.x[self.get_idx(1, j)] - t2)
            self.model += (-expr >= self.params.same_arrive_delta + self.get_stop_time(self.params.key_stations[0],
                                                                                       self.params.key_stations[0]))

        # 示例：大交路上行与下行耦合
        aux_idx = (2 * self.v_num + i * self.params.trip_num[1] + j)
        # 正向约束
        expr = (self.x[self.get_idx(0, i)] + t1 - self.x[self.get_idx(1, j)] - t2 + self.M * self.x[aux_idx])
        self.model += (expr >= self.params.same_arrive_delta + self.get_stop_time(self.params.key_stations[0],
                                                                                  self.params.key_stations[0]))
        # 反向约束
        self.model += (
                -expr >= -self.M + self.params.same_arrive_delta + self.get_stop_time(self.params.key_stations[0],
                                                                                      self.params.key_stations[0]))

    def _add_coupling_constraints(self):
        """双向不同时到达约束"""
        # 统一参数计算格式
        if len(self.params.key_stations) == 0 or self.r == 2:
            return
        t1 = self.get_travel_time(self.params.jiaolu_start[0], self.params.key_stations[0]) + self.get_stop_time(
            self.params.jiaolu_start[0], self.params.key_stations[0])
        t2 = self.get_travel_time(self.params.jiaolu_end[0], self.params.key_stations[0]) + self.get_stop_time(
            self.params.jiaolu_end[0], self.params.key_stations[0])

        # 示例：大交路上行与下行耦合
        for i in range(self.params.trip_num[0]):
            for j in range(self.params.trip_num[1]):
                aux_idx = (self.params.n_r * self.v_num + i * self.params.trip_num[1] + j)
                # 正向约束
                expr = (self.x[self.get_idx(0, i)] + t1 -
                        self.x[self.get_idx(1, j)] - t2 +
                        self.M * self.x[aux_idx])
                self.model += (expr >= self.params.same_arrive_delta + self.get_stop_time(self.params.key_stations[0],
                                                                                          self.params.key_stations[0]))
                # 反向约束
                self.model += (-expr >= -self.M + self.params.same_arrive_delta + self.get_stop_time(
                    self.params.key_stations[0], self.params.key_stations[0]))

    def _add_down_direction_constraints(self):
        """下行约束添加"""
        for i in range(1, self.params.trip_num[self.r + 1]):
            a = self.r + 1
            b = self.r + 1
            c1 = i
            c2 = i - 1
            # 构建约束
            idx_a = self.get_idx(a, c1)
            idx_b = self.get_idx(b, c2)
            # 正向约束
            expr = self.x[idx_a] - self.x[idx_b]
            # 虽然这几个判断语句都有同样的约束，但是保持这个结构便于扩展模型
            if self.params.the_pre_variable[a][c1] == -1 and self.params.the_pre_variable[b][c2] == -1:
                self.model += (expr >= self.params.min_shared_interval)
            elif self.params.the_pre_variable[a][c1] == -1 and self.params.the_pre_variable[b][c2] != -1:
                self.model += (expr >= self.params.min_shared_interval)
            elif self.params.the_pre_variable[a][c1] != -1 and self.params.the_pre_variable[b][c2] == -1:
                self.model += (expr >= self.params.min_shared_interval)
            else:
                self.model += (expr >= self.params.min_shared_interval)
                # 下行是否是共线折返，如果结束的站点不同，那么不是，如果结束的站点相同，则是共线折返
                pre = self.params.the_pre_variable[a][c1]
                if a == 1:
                    travel_time = self.params.up_time1
                elif a == 3:
                    travel_time = self.params.up_time2
                # 判断是否能够站后折返
                if self.params.isBackTurnbackStation[self.params.jiaolu_end[a // 2] - 1]:
                    # if 0:
                    self.model += (self.x[self.get_idx(a - 1, pre)] - self.x[
                        idx_b] + travel_time >= - self.params.up_time2turnback - self.params.down_time2turnback + 1)
                # 站前折返
                else:
                    self.model += (self.x[self.get_idx(a - 1, pre)] - self.x[
                        idx_b] + travel_time >= self.params.min_dep_arr_delta)

    def _add_up_direction_constraints(self):
        """方向通用约束添加"""
        for i in range(1, self.params.trip_num[self.r]):
            a, b = self.r, self.r
            c1 = i
            c2 = i - 1
            # 构建约束
            idx_a = self.get_idx(a, c1)
            idx_b = self.get_idx(b, c2)
            # print(a, c1, b, c2, "up")

            # 正向约束
            expr = self.x[idx_a] - self.x[idx_b]

            if self.params.the_pre_variable[a][c1] == -1 and self.params.the_pre_variable[b][c2] == -1:
                self.model += (expr >= self.params.min_shared_interval)
            elif self.params.the_pre_variable[a][c1] == -1 and self.params.the_pre_variable[b][c2] != -1:
                self.model += (expr >= self.params.min_shared_interval)
            elif self.params.the_pre_variable[a][c1] != -1 and self.params.the_pre_variable[b][c2] == -1:
                self.model += (expr >= self.params.min_shared_interval)
            else:
                self.model += (expr >= self.params.min_shared_interval)
                pre = self.params.the_pre_variable[a][c1]
                if a == 0:
                    travel_time = self.params.down_time1
                elif a == 2:
                    travel_time = self.params.down_time2
                if self.params.isBackTurnbackStation[self.params.jiaolu_start[a // 2] - 1]:
                    # if 1:
                    self.model += (self.x[self.get_idx(a + 1, pre)] - self.x[
                        idx_b] + travel_time >= -self.params.up_time2turnback - self.params.down_time2turnback + 1)
                else:
                    self.model += (self.x[self.get_idx(a + 1, pre)] - self.x[
                        idx_b] + travel_time >= self.params.min_dep_arr_delta)

    def _add_first_last_trip_constraints(self):
        if self.r == 0:
            self.model += (
                    self.y[0] >= self.x[self.get_idx(self.r, self.params.initial_trip_num[self.r])] - self.params.t[
                self.st1])
            self.model += (
                    -self.y[0] <= self.x[self.get_idx(self.r, self.params.initial_trip_num[self.r])] - self.params.t[
                self.st1])
            self.model += (
                    self.y[1] >= self.x[self.get_idx(self.r, self.params.trip_num[self.r] - 1)] - self.params.t[-1])
            self.model += (
                    -self.y[1] <= self.x[self.get_idx(self.r, self.params.trip_num[self.r] - 1)] - self.params.t[-1])
            self.model += (
                    self.y[2] >= self.x[self.get_idx(self.r + 1, self.params.initial_trip_num[self.r + 1])] -
                    self.params.t[
                        self.st1])
            self.model += (
                    -self.y[2] <= self.x[self.get_idx(self.r + 1, self.params.initial_trip_num[self.r + 1])] -
                    self.params.t[
                        self.st1])
            self.model += (
                    self.y[3] >= self.x[self.get_idx(self.r + 1, self.params.trip_num[self.r + 1] - 1)] - self.params.t[
                -1])
            self.model += (
                    -self.y[3] <= self.x[self.get_idx(self.r + 1, self.params.trip_num[self.r + 1] - 1)] -
                    self.params.t[-1])
        else:
            self.model += (
                    self.y[0] >= self.x[self.get_idx(self.r, self.params.initial_trip_num[self.r])] - self.params.t[
                self.st2])
            self.model += (
                    -self.y[0] <= self.x[self.get_idx(self.r, self.params.initial_trip_num[self.r])] - self.params.t[
                self.st2])
            self.model += (
                    self.y[1] >= self.x[self.get_idx(self.r, self.params.trip_num[self.r] - 1)] - self.params.t[-1])
            self.model += (
                    -self.y[1] <= self.x[self.get_idx(self.r, self.params.trip_num[self.r] - 1)] - self.params.t[-1])
            self.model += (
                    self.y[2] >= self.x[self.get_idx(self.r + 1, self.params.initial_trip_num[self.r + 1])] -
                    self.params.t[
                        self.st2])
            self.model += (
                    -self.y[2] <= self.x[self.get_idx(self.r + 1, self.params.initial_trip_num[self.r + 1])] -
                    self.params.t[
                        self.st2])
            self.model += (
                    self.y[3] >= self.x[self.get_idx(self.r + 1, self.params.trip_num[self.r + 1] - 1)] - self.params.t[
                -1])
            self.model += (
                    -self.y[3] <= self.x[self.get_idx(self.r + 1, self.params.trip_num[self.r + 1] - 1)] -
                    self.params.t[-1])

    def _add_return_constraints(self):
        if self.r != 0 or self.fast_mod == 1: return
        cnt = 0
        turn_over_constant = 2 * self.v_num + self.params.trip_num[0] * self.params.trip_num[0]
        for i in range(self.params.trip_num[0]):
            if self.params.the_aft_variable[0][i] == -1:
                for j in range(i):
                    if self.params.the_aft_variable[0][j] != -1:
                        idx = self.params.the_aft_variable[0][j]
                        self.model += (
                                self.x[self.get_idx(0, i)] - self.x[self.get_idx(1, idx)] - self.M * self.x[
                            turn_over_constant + cnt * self.params.trip_num[
                                0] + j] >= 1 - self.M - self.params.up_time1)
                        self.model += (
                                self.x[self.get_idx(0, i)] - self.x[self.get_idx(0, j)] - self.M * self.x[
                            turn_over_constant + cnt * self.params.trip_num[0] + j] <= -1)
                cnt += 1

    def check_feasibility(self, mod=-1):
        """双向不同时到达约束"""
        # 统一参数计算格式
        if len(self.params.key_stations) == 0 or self.r == 2 or self.fast_mod == 1:
            return []
        res = []
        t1 = self.get_travel_time(self.params.jiaolu_start[0], self.params.key_stations[0]) + self.get_stop_time(
            self.params.jiaolu_start[0], self.params.key_stations[0])
        t2 = self.get_travel_time(self.params.jiaolu_end[0], self.params.key_stations[0]) + self.get_stop_time(
            self.params.jiaolu_end[0], self.params.key_stations[0])

        # 示例：大交路上行与下行耦合
        if mod == -1:
            for i in range(self.params.trip_num[0]):
                for j in range(self.params.trip_num[1]):
                    # 正向约束
                    a = self.x[self.get_idx(0, i)].varValue + t1 - self.x[self.get_idx(1, j)].varValue - t2
                    # warning，这里就是取个整数就行，因为有时候会有29.999999999985448 < 30的情况发生
                    check1 = (a + 0.0001 < self.params.same_arrive_delta + self.get_stop_time(
                        self.params.key_stations[0],
                        self.params.key_stations[0]))
                    # 反向约束
                    check2 = (a - 0.0001 > -self.params.same_arrive_delta - self.get_stop_time(
                        self.params.key_stations[0],
                        self.params.key_stations[0]))
                    if check1 and check2:
                        res.append([i, j, a])
        else:
            for i in range(self.params.trip_num[0]):
                for j in range(self.params.trip_num[1]):
                    # 正向约束
                    a = self.x[self.get_idx(0, i)].varValue + t1 - self.x[self.get_idx(1, j)].varValue - t2
                    # warning，这里就是取个整数就行，因为有时候会有29.999999999985448 < 30的情况发生
                    check1 = (a + 0.0001 < mod + self.get_stop_time(self.params.key_stations[0],
                                                                    self.params.key_stations[0]))
                    # 反向约束
                    check2 = (a - 0.0001 > -mod - self.get_stop_time(self.params.key_stations[0],
                                                                     self.params.key_stations[0]))
                    if check1 and check2:
                        res.append([i, j, a])
        return res

    def _process_solution(self):
        """处理优化结果"""
        temp = 0
        for i in range(self.interval_constant, self.n_vars - 1):
            temp += self.x[i].varValue

        print("峰期最大偏移量：", self.x[-1].varValue)

        for v_cnt in range(2 * self.v_num):
            if v_cnt < 2 * self.v_num:
                route = v_cnt // self.v_num
                trip = v_cnt % self.v_num
                if self.r == 0:
                    self.solution[route, trip] = self.x[v_cnt].varValue
                else:
                    self.solution[route + 2, trip] = self.x[v_cnt].varValue

    def _add_turnback_constraints(self):
        for i in range(1, self.params.trip_num[self.r + 1]):
            b = self.params.the_pre_variable[self.r + 1][i]
            if self.r == 0:
                travel_time = self.params.up_time1
            else:
                travel_time = self.params.up_time2
            if b != -1:
                idx_pre = self.get_idx(self.r, b)
                idx_curr = self.get_idx(self.r + 1, i - 1)
                idx_now = self.get_idx(self.r + 1, i)
                self.model += (
                        self.x[idx_pre] - self.x[idx_curr] + travel_time >= self.params.min_dep_arr_delta)
                self.model += (
                        self.x[idx_now] - self.x[idx_pre] - travel_time >= self.params.min_turnback_time)

        for i in range(1, self.params.trip_num[self.r]):
            b = self.params.the_pre_variable[self.r][i]
            if self.r == 0:
                travel_time = self.params.down_time1
            else:
                travel_time = self.params.down_time2
            if b != -1:
                idx_pre = self.get_idx(self.r + 1, b)
                idx_curr = self.get_idx(self.r, i - 1)
                idx_now = self.get_idx(self.r, i)
                self.model += (
                        self.x[idx_pre] - self.x[idx_curr] + travel_time >= self.params.min_dep_arr_delta)
                self.model += (
                        self.x[idx_now] - self.x[idx_pre] - travel_time >= self.params.min_turnback_time)

    def _add_peak_period_constraints(self):
        # print("peak peak")
        # print(self.params.trip_num)
        # print(self.params.n_r)
        # print(self.params.f_real)
        # print(self.params.f_accumulated)
        # print(self.params.t)
        if self.r == 0:
            for p in range(self.st1 + 1, self.params.period_num):
                for i in range(2):
                    a = self.params.f_accumulated[i][p]
                    b = self.params.f_accumulated[i][p + 1] - 1
                    for j in range(a, b + 1):
                        idx = self.get_idx(i, j)
                        self.model += (self.x[idx] + self.x[self.n_vars - 1] >= self.params.t[p])
                        self.model += (self.x[idx] - self.x[self.n_vars - 1] <= self.params.t[p + 1])

        else:
            for p in range(self.st2 + 1, self.params.period_num):
                for i in range(2, 4):
                    a = self.params.f_accumulated[i][p]
                    b = self.params.f_accumulated[i][p + 1] - 1
                    for j in range(a, b + 1):
                        idx = self.get_idx(i, j)
                        self.model += (self.x[idx] + self.x[self.n_vars - 1] >= self.params.t[p])
                        self.model += (self.x[idx] - self.x[self.n_vars - 1] <= self.params.t[p + 1])

        self.model += (self.w >= self.x[self.n_vars - 1])
        self.model += (self.w >= -self.x[self.n_vars - 1])
