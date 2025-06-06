import os
import pulp
import numpy as np
import math
from AdjRcd_Rule import *
from AdjRcd_infeasible import *
from time import time
from copy import deepcopy
from get_opt_rcd import *

class TrainScheduler:
    def __init__(self, params):
        self.params = params
        self.params.up_time2turnback = 30
        self.params.down_time2turnback = 30
        self.M = 1e5  # 大常数
        self.start_time = time()
        self.time_limit = 100 + self.start_time
        self.fast_mod = 0
        # 变量索引计算函数
        self.get_idx = lambda route, trip: route * self.params.v_num + trip

        # 初始化模型
        self.model = None

    def initialize_params(self):
        self.params.f_tag = [[] for _ in range(self.params.n_r)]
        self.params.f_real = [[] for _ in range(self.params.n_r)]
        # 初始化累计值
        self.params.f_real[0] = self.params.f1_real[:]
        self.params.f_real[1] = self.params.f1_real[:]
        self.params.f_real[2] = self.params.f2_real[:]
        self.params.f_real[3] = self.params.f2_real[:]

        self.params.f_accumulated[0] = [0] * (self.params.period_num + 1)
        self.params.f_accumulated[1] = [0] * (self.params.period_num + 1)
        self.params.f_accumulated[2] = [0] * (self.params.period_num + 1)
        self.params.f_accumulated[3] = [0] * (self.params.period_num + 1)

        self.params.trip_num = [0] * self.params.n_r
        self.params.trip_num[0] = self.params.trip_num1
        self.params.trip_num[1] = self.params.trip_num1
        self.params.trip_num[2] = self.params.trip_num2
        self.params.trip_num[3] = self.params.trip_num2

        self.st1 = -1
        self.st2 = -1
        for i in range(self.params.period_num):
            if self.params.N1[i] != 0 and self.st1 == -1:
                self.st1 = i
            if self.params.N2[i] != 0 and self.st2 == -1:
                self.st2 = i

        self.params.initial_trip_num = [0] * self.params.n_r

        # 初始化大交路
        dt = self.params.N1[self.st1]
        dt1 = int(np.ceil(dt / 2))
        self.params.initial_trip_num[0] = dt1
        dt2 = int(np.floor(dt / 2))
        self.params.initial_trip_num[1] = dt2

        self.params.f_real[0][self.st1] += dt1
        self.params.trip_num[0] += dt1
        self.params.f_real[1][self.st1] += dt2
        self.params.trip_num[1] += dt2

        # 初始化小交路标签
        dt = self.params.N2[self.st2]
        dt1 = int(np.ceil(dt / 2))
        self.params.initial_trip_num[2] = dt1
        dt2 = int(np.floor(dt / 2))
        self.params.initial_trip_num[3] = dt2
        for i in range(4):
            print(f"self.params.initial_trip_num[{i}] = {self.params.initial_trip_num[i]}")

        self.params.f_real[2][self.st2] += dt1
        self.params.trip_num[2] += dt1
        self.params.f_real[3][self.st2] += dt2
        self.params.trip_num[3] += dt2

        for p in range(self.st1, self.params.period_num - 1):
            dt = self.params.N1[p + 1] - self.params.N1[p]
            dt1 = int(np.ceil(dt / 2))
            dt2 = int(np.floor(dt / 2))
            if dt <= 0:
                dt1, dt2 = dt2, dt1
                # self.params.f_real[0][p] += abs(dt1)
                # self.params.f_real[0][p + 1] -= abs(dt1)
                self.params.f_tag[0].extend([0] * self.params.f_real[0][p])
                for i in range(-dt1):
                    self.params.f_tag[0][-i - 1] = -1

                # self.params.f_real[1][p] += abs(dt2)
                # self.params.f_real[1][p + 1] -= abs(dt2)
                self.params.f_tag[1].extend([0] * self.params.f_real[1][p])
                for i in range(-dt2):
                    self.params.f_tag[1][-i - 1] = -1
            else:
                # print(p, dt1, dt2, self.params.f_real[0][p], self.params.f_real[0][p + 1], "weisha")
                self.params.f_real[0][p] += dt1
                self.params.f_real[0][p + 1] -= dt1
                self.params.f_tag[0].extend([0] * self.params.f_real[0][p])
                for i in range(dt1):
                    self.params.f_tag[0][-i - 1] = 1

                self.params.f_real[1][p] += dt2
                self.params.f_real[1][p + 1] -= dt2
                self.params.f_tag[1].extend([0] * self.params.f_real[1][p])
                for i in range(dt2):
                    self.params.f_tag[1][-i - 1] = 1
            if p == self.st1:
                dt1 = int(np.ceil(self.params.N1[self.st1] / 2))
                dt2 = int(np.floor(self.params.N1[self.st1] / 2))
                for i in range(dt1):
                    self.params.f_tag[0][i] = 1
                for i in range(dt2):
                    self.params.f_tag[1][i] = 1

        self.params.f_tag[0].extend([0] * self.params.f_real[0][-1])
        self.params.f_tag[1].extend([0] * self.params.f_real[1][-1])

        for p in range(self.st2, self.params.period_num - 1):
            dt = self.params.N2[p + 1] - self.params.N2[p]
            dt1 = int(np.ceil(dt / 2))
            dt2 = int(np.floor(dt / 2))
            if dt <= 0:
                dt1, dt2 = dt1, dt2
                # self.params.f_real[2][p] += abs(dt1)
                # if self.params.f_real[2][p + 1] >= abs(dt1):
                #     self.params.f_real[2][p + 1] -= abs(dt1)
                # else:
                #     self.params.trip_num[2] += (abs(dt1) - self.params.f_real[2][p + 1])
                #     self.params.f_real[2][p + 1] = 0
                self.params.f_tag[2].extend([0] * self.params.f_real[2][p])
                for i in range(-dt1):
                    self.params.f_tag[2][-i - 1] = -1

                # self.params.f_real[3][p] += abs(dt2)
                # if self.params.f_real[3][p + 1] >= abs(dt2):
                #     self.params.f_real[3][p + 1] -= abs(dt2)
                # else:
                #     self.params.trip_num[3] += (abs(dt2) - self.params.f_real[3][p + 1])
                #     self.params.f_real[3][p + 1] = 0
                self.params.f_tag[3].extend([0] * self.params.f_real[3][p])
                for i in range(-dt2):
                    self.params.f_tag[3][-i - 1] = -1

            else:
                self.params.f_real[2][p] += dt1
                self.params.f_real[2][p + 1] -= dt1
                self.params.f_tag[2].extend([0] * self.params.f_real[2][p])
                for i in range(dt1):
                    self.params.f_tag[2][-i - 1] = 1

                self.params.f_real[3][p] += dt2
                self.params.f_real[3][p + 1] -= dt2
                self.params.f_tag[3].extend([0] * self.params.f_real[3][p])
                for i in range(dt2):
                    self.params.f_tag[3][-i - 1] = 1

            if p == self.st2:
                dt1 = int(np.ceil(self.params.N2[self.st2] / 2))
                dt2 = int(np.floor(self.params.N2[self.st2] / 2))
                for i in range(dt1):
                    self.params.f_tag[2][i] = 1
                for i in range(dt2):
                    self.params.f_tag[3][i] = 1

        self.params.f_tag[2].extend([0] * self.params.f_real[2][-1])
        self.params.f_tag[3].extend([0] * self.params.f_real[3][-1])

        for i in range(self.params.n_r):
            self.params.the_aft_variable[i] = [-1] * self.params.trip_num[i]
            self.params.the_pre_variable[i] = [-1] * self.params.trip_num[i]

        p = 0
        for i in range(self.params.trip_num[0]):
            if self.params.f_tag[0][i] == -1:
                continue
            while p < self.params.trip_num[1]:
                if self.params.f_tag[1][p] != 1:
                    self.params.the_aft_variable[0][i] = p
                    self.params.the_pre_variable[1][p] = i
                    p += 1
                    break
                p += 1
        p = 0
        for i in range(self.params.trip_num[1]):
            if self.params.f_tag[1][i] == -1:
                continue
            while p < self.params.trip_num[0]:
                if self.params.f_tag[0][p] != 1:
                    self.params.the_aft_variable[1][i] = p
                    self.params.the_pre_variable[0][p] = i
                    p += 1
                    break
                p += 1
        p = 0
        for i in range(self.params.trip_num[2]):
            if self.params.f_tag[2][i] == -1:
                continue
            while p < self.params.trip_num[3]:
                if self.params.f_tag[3][p] != 1:
                    self.params.the_aft_variable[2][i] = p
                    self.params.the_pre_variable[3][p] = i
                    p += 1
                    break
                p += 1
        p = 0
        for i in range(self.params.trip_num[3]):
            if self.params.f_tag[3][i] == -1:
                continue
            while p < self.params.trip_num[2]:
                if self.params.f_tag[2][p] != 1:
                    self.params.the_aft_variable[3][i] = p
                    self.params.the_pre_variable[2][p] = i
                    p += 1
                    break
                p += 1

        self.params.rcd = [[0] * (self.params.trip_num[0] + self.params.trip_num[2]),
                           [0] * (self.params.trip_num[1] + self.params.trip_num[3])]

        for r in range(2):
            rcd_idx = 0
            for i in range(self.params.period_num):
                pre = rcd_idx
                a, b = self.params.OperaRate1[i], self.params.OperaRate2[i]
                if self.st1 != self.st2:
                    if i + 1 == self.st2:
                        trip_num1 = self.params.f_real[r][i]
                        trip_num2 = self.params.initial_trip_num[r + 2]
                        self.params.f_real[r + 2][i] += trip_num2
                        self.params.f_real[r + 2][i + 1] -= trip_num2
                        a, b = self.params.OperaRate1[i + 1], self.params.OperaRate2[i + 1]
                        c = min(trip_num1 // a, trip_num2 // b)
                        ra = trip_num1 - c * a
                        rb = trip_num2 - c * b
                        for j in range(ra):
                            self.params.rcd[r][rcd_idx] = r
                            rcd_idx += 1
                        for j in range(rb):
                            self.params.rcd[r][rcd_idx] = r + 2
                            rcd_idx += 1
                        for j in range(c):
                            for j1 in range(a):
                                self.params.rcd[r][rcd_idx] = r
                                rcd_idx += 1
                            for j2 in range(b):
                                self.params.rcd[r][rcd_idx] = r + 2
                                rcd_idx += 1
                        continue
                    if i + 1 == self.st1:
                        trip_num1 = self.params.initial_trip_num[r]
                        trip_num2 = self.params.f_real[r + 2][i]
                        self.params.f_real[r][i] += trip_num1
                        self.params.f_real[r][i + 1] -= trip_num1
                        a, b = self.params.OperaRate1[i + 1], self.params.OperaRate2[i + 1]
                        c = min(trip_num1 // a, trip_num2 // b)
                        ra = trip_num1 - c * a
                        rb = trip_num2 - c * b
                        for j in range(rb):
                            self.params.rcd[r][rcd_idx] = r + 2
                            rcd_idx += 1
                        for j in range(ra):
                            self.params.rcd[r][rcd_idx] = r
                            rcd_idx += 1
                        for j in range(c):
                            for j2 in range(b):
                                self.params.rcd[r][rcd_idx] = r + 2
                                rcd_idx += 1
                            for j1 in range(a):
                                self.params.rcd[r][rcd_idx] = r
                                rcd_idx += 1
                        continue
                if a != -1 and b != -1:
                    trip_num1 = self.params.f_real[r][i]
                    trip_num2 = self.params.f_real[r + 2][i]
                    c = min(trip_num1 // a, trip_num2 // b)
                    r1 = trip_num1 - c * a
                    r2 = trip_num2 - c * b
                    rr1 = r1 // 2
                    rr2 = r2 // 2
                    for j in range(rr1):
                        self.params.rcd[r][rcd_idx] = r
                        rcd_idx += 1
                    for j in range(rr2):
                        self.params.rcd[r][rcd_idx] = r + 2
                        rcd_idx += 1
                    for j in range(c):
                        for j1 in range(a):
                            self.params.rcd[r][rcd_idx] = r
                            rcd_idx += 1
                        for j2 in range(b):
                            self.params.rcd[r][rcd_idx] = r + 2
                            rcd_idx += 1
                    for j in range(r1 - rr1):
                        self.params.rcd[r][rcd_idx] = r
                        rcd_idx += 1
                    for j in range(r2 - rr2):
                        self.params.rcd[r][rcd_idx] = r + 2
                        rcd_idx += 1
                else:
                    if self.params.f_real[r][i] != 0:
                        for k1 in range(self.params.f_real[r][i]):
                            self.params.rcd[r][rcd_idx] = r
                            rcd_idx += 1
                    if self.params.f_real[r + 2][i] != 0:
                        for k1 in range(self.params.f_real[r + 2][i]):
                            self.params.rcd[r][rcd_idx] = r + 2
                            rcd_idx += 1

        for j in range(self.params.n_r):
            self.params.trip_num[j] = sum(self.params.f_real[j])
            for i in range(self.params.period_num):
                self.params.f_accumulated[j][i + 1] = self.params.f_accumulated[j][i] + self.params.f_real[j][i]

        self.params.rcd[0] = self.params.rcd[0][:self.params.trip_num[0] + self.params.trip_num[2]]
        self.params.rcd[1] = self.params.rcd[1][:self.params.trip_num[1] + self.params.trip_num[3]]

        self.params.v_num = max(self.params.trip_num)

        # for i in range(len(self.params.rcd[0])):
        #     self.params.rcd[1][i] = self.params.rcd[0][i] + 1

    def _init_variables(self):
        """初始化决策变量"""
        n_r = self.params.n_r
        v_num = self.params.v_num
        trip_num1 = self.params.trip_num[0]
        # 计算辅助变量维度
        cnt = sum(1 for i in range(trip_num1) if self.params.the_aft_variable[0][i] == -1)
        self.aux_num = cnt * trip_num1

        # 总变量数（主变量+辅助变量+其他）
        self.n_vars = (n_r * v_num +
                       self.params.trip_num[0] * self.params.trip_num[1] + self.aux_num +
                       len(self.params.rcd[0]) - 1 + len(self.params.rcd[1]) - 1 + 1)

        self.x = []
        self.y = []
        # z 是相邻两个发车间隔的差值
        self.z1 = []
        self.z2 = []

        x_cnt = 0
        for i in range(n_r * v_num):
            self.x.append(pulp.LpVariable('x' + str(x_cnt), cat='Continuous'))
            x_cnt += 1

        for i in range(self.params.trip_num[0] * self.params.trip_num[1] + self.aux_num):
            self.x.append(pulp.LpVariable('x' + str(x_cnt), cat='Binary'))
            x_cnt += 1

        for i in range(len(self.params.rcd[0]) - 1 + len(self.params.rcd[1]) - 1 + 1):
            self.x.append(pulp.LpVariable('x' + str(x_cnt), cat='Continuous'))
            x_cnt += 1

        for i in range(4):
            self.y.append(pulp.LpVariable('y' + str(i), cat='Continuous'))

        for i in range(len(self.params.rcd[0]) - 2):
            self.z1.append(pulp.LpVariable('z1_' + str(i), cat='Continuous'))

        for i in range(len(self.params.rcd[1]) - 2):
            self.z2.append(pulp.LpVariable('z2_' + str(i), cat='Continuous'))

        self.w = pulp.LpVariable('w', cat='Continuous')


    def solve(self):
        self.initialize_params()
        self._init_variables()

        """构建并求解模型"""
        self._add_objective()
        self._add_constraints()

        # 参数设置
        self.model.solve()
        # self.model.solve(solver=pulp.GUROBI())
        print("Status:", pulp.LpStatus[self.model.status])
        # 输出每个变量的最优值
        return self._process_solution()

    def solve_smart(self):
        max_try = 30
        max_no_improvement = 15
        history_sol = None
        if self.params.jiaolu_start[0] == self.params.jiaolu_start[1] or self.params.jiaolu_end[0] == \
                self.params.jiaolu_end[1]:
            no_improvement_cnt = 0
            pre_conflict = -1
            self.initialize_params()
            test = RcdGenerator(self.params, self.st1, self.st2)
            divide_res, self.params = test.solve_smart()
            initial_params = deepcopy(self.params)
            self.model = pulp.LpProblem("TrainScheduling", sense=pulp.LpMinimize)
            self._init_variables()
            self.params = adj_rcd(self.params)
            success = 0
            val = math.inf
            best_params = None
            best_conflict = math.inf
            for i in range(max_try):
                s, temp_res, v = self._solve_smart()
                if s == 1:
                    success = 1
                    res = temp_res
                    history_sol = res
                    best_params = deepcopy(self.params)
                    print("succ1", self.params.rcd[0])
                    print("succ1", self.params.rcd[1])
                    break
                else:
                    pre_params = deepcopy(self.params)
                    conflict_value, self.params = adj_rcd_infeasible(self.params, temp_res)
                    if conflict_value == 0:
                        success = 1
                        if val > v:
                            val = v
                            print("succ2", self.params.rcd[0])
                            print("succ2", self.params.rcd[1])
                            res = temp_res
                        break
                    if conflict_value < best_conflict:
                        best_params = pre_params
                        best_conflict = conflict_value
                        no_improvement_cnt = 0
                    else:
                        no_improvement_cnt += 1
                        if no_improvement_cnt == max_no_improvement:
                            break
                    self.model = pulp.LpProblem("TrainScheduling", sense=pulp.LpMinimize)
                    self._init_variables()
            self.fast_mod = 0
            self.params = best_params
            print(success, best_conflict, "however")
            if success == 1:
                s, res, v = self._solve_smart()
            else:
                s, t_res = self.last_solve()
                if s == 1 or history_sol is None:
                    res = t_res
                else:
                    res = history_sol
        else:
            # 取 -1，0，1
            success = 0
            self.initialize_params()
            test = RcdGenerator(self.params, self.st1, self.st2)
            divide_res, self.params = test.solve_smart()
            initial_params = deepcopy(self.params)
            val = math.inf
            best_params = None
            best_conflict = math.inf
            for adj_idx in range(-1, 2):
                no_improvement_cnt = 0
                pre_conflict = -1
                self.params = deepcopy(initial_params)
                self.params = adj_rcd(self.params, adj_idx)
                self.model = pulp.LpProblem("TrainScheduling", sense=pulp.LpMinimize)
                self._init_variables()
                for i in range(max_try):
                    print("model management", adj_idx, i)
                    s, temp_res, v = self._solve_smart()
                    if s == 1:
                        success = 1
                        if val > v:
                            val = v
                            res = temp_res
                            history_sol = res
                        best_params = deepcopy(self.params)
                        break
                    else:
                        pre_params = self.params
                        conflict_value, self.params = adj_rcd_infeasible(self.params, temp_res)
                        pre_conflict = conflict_value
                        if conflict_value == 0:
                            success = 1
                            if val > v:
                                val = v
                                res = temp_res
                                history_sol = res
                            # print("conflict", best_conflict, adj_idx, i)
                            break
                        if conflict_value < best_conflict:
                            best_params = pre_params
                            best_conflict = conflict_value
                            no_improvement_cnt = 0
                        else:
                            no_improvement_cnt += 1
                            if no_improvement_cnt == max_no_improvement:
                                break
                        self.model = pulp.LpProblem("TrainScheduling", sense=pulp.LpMinimize)
                        self._init_variables()
                    print("conflict", best_conflict, adj_idx, i)
            self.fast_mod = 1
            self.params = best_params
            print(success, best_conflict, "however")
            if success == 1:
                self.model = pulp.LpProblem("TrainScheduling", sense=pulp.LpMinimize)
                s, res, v = self._solve_smart()
            else:
                s, t_res = self.last_solve()
                if s == 1 or history_sol is None:
                    res = t_res
                else:
                    res = history_sol
        print("修改前参数，rcd0", initial_params.rcd[0])
        print("修改后参数，rcd0", self.params.rcd[0])
        print("修改前参数，rcd1", initial_params.rcd[1])
        print("修改后参数，rcd1", self.params.rcd[1])

        print("检查一下")
        adj_rcd_infeasible(best_params, res)
        return res, divide_res

    def last_solve(self):
        """构建并求解模型"""
        self.model = pulp.LpProblem("TrainScheduling", sense=pulp.LpMinimize)

        same_arrive_delta = self.params.same_arrive_delta
        min_dep_arr_delta = self.params.min_dep_arr_delta
        min_shared_interval = self.params.min_shared_interval
        min_turnback_time = self.params.min_turnback_time

        self.params.same_arrive_delta = pulp.LpVariable('same_arrive_delta', cat='Continuous')
        self.params.min_dep_arr_delta = pulp.LpVariable('min_dep_arr_delta', cat='Continuous')
        self.params.min_shared_interval = pulp.LpVariable('min_shared_interval', cat='Continuous')
        self.params.min_turnback_time = pulp.LpVariable('min_turnback_time', cat='Continuous')

        aux_same_arrive_delta = pulp.LpVariable('aux_same_arrive_delt', cat='Continuous')
        aux_min_dep_arr_delta = pulp.LpVariable('aux_min_dep_arr_delta', cat='Continuous')
        aux_min_shared_interval = pulp.LpVariable('aux_min_shared_interval', cat='Continuous')
        aux_min_turnback_time = pulp.LpVariable('aux_min_turnback_time', cat='Continuous')

        # 主变量惩罚项
        temp = 0
        for r in range(self.params.n_r):
            idx = self.get_idx(r, self.params.trip_num[r] - 1)
            temp += 0.001 * self.x[idx]

        # 辅助变量惩罚项
        self.interval_constant = self.params.n_r * self.params.v_num + self.params.trip_num[0] * self.params.trip_num[
            1] + self.aux_num

        for i in range(self.interval_constant, self.n_vars - 1):
            temp += 10 * self.x[i]

        for i in range(len(self.z1)):
            temp += 10 * self.z1[i]

        for i in range(len(self.z2)):
            temp += 10 * self.z2[i]

        for i in range(4):
            temp += 10 * self.y[i]

        temp += 1000 * aux_same_arrive_delta
        temp += 1000 * aux_min_dep_arr_delta
        temp += 1000 * aux_min_shared_interval
        temp += 1000 * aux_min_turnback_time
        temp + 1000 * self.w

        self.model += temp

        self.model += (aux_same_arrive_delta >= 0)
        self.model += (aux_same_arrive_delta >= same_arrive_delta - self.params.same_arrive_delta)
        self.model += (aux_min_dep_arr_delta >= 0)
        self.model += (aux_min_dep_arr_delta >= min_dep_arr_delta - self.params.min_dep_arr_delta)
        self.model += (aux_min_shared_interval >= 0)
        self.model += (aux_min_shared_interval >= min_shared_interval - self.params.min_shared_interval)
        self.model += (aux_min_turnback_time >= 0)
        self.model += (aux_min_turnback_time >= min_turnback_time - self.params.min_turnback_time)

        self._add_obj_constraints()
        self._add_first_last_trip_constraints()
        self._add_return_constraints()
        self._add_shared_track_constraints()
        self._add_turnback_constraints()
        self._add_peak_period_constraints()
        # self.model.solve(solver=pulp.GUROBI())
        res_time = self.start_time + self.time_limit - time()
        self.model.solve(pulp.PULP_CBC_CMD(timeLimit=res_time))
        print("Status_last:", pulp.LpStatus[self.model.status])
        if pulp.LpStatus[self.model.status] == "Infeasible":
            res_schedule = self._process_solution()
            return 0, res_schedule

        st = time()
        while pulp.LpStatus[self.model.status] != "Infeasible":
            the_set = self.check_feasibility(same_arrive_delta)
            res_time = self.start_time + self.time_limit - time()
            if res_time < 0: break
            if len(the_set) == 0: break
            for i, j, k in the_set:
                self._add_coupling_constraints_smart(i, j, k)
            # 参数设置
            self.model.solve(pulp.PULP_CBC_CMD(timeLimit=res_time))
            print("Status_last:", pulp.LpStatus[self.model.status])
            et = time()
            if et > st + 60: break

        res_schedule = self._process_solution()

        print("back", self.params.same_arrive_delta.varValue)
        print("back", self.params.min_dep_arr_delta.varValue)
        print("back", self.params.min_shared_interval.varValue)
        print("back", self.params.min_turnback_time.varValue)

        if pulp.LpStatus[self.model.status] == "Infeasible":
            return 0, res_schedule
        # 输出每个变量的最优值
        return 1, res_schedule

    def _solve_smart(self):
        """构建并求解模型"""
        self._add_objective()
        self._add_obj_constraints()
        self._add_first_last_trip_constraints()
        self._add_return_constraints()
        self._add_shared_track_constraints()
        self._add_turnback_constraints()
        self._add_peak_period_constraints()
        # self.model.solve(solver=pulp.GUROBI())
        res_time = self.start_time + self.time_limit - time()
        self.model.solve(pulp.PULP_CBC_CMD(timeLimit=res_time))
        print("Status:", pulp.LpStatus[self.model.status])
        if pulp.LpStatus[self.model.status] == "Infeasible":
            res_schedule = self._process_solution()
            return 0, res_schedule, pulp.value(self.model.objective)

        while pulp.LpStatus[self.model.status] != "Infeasible":
            the_set = self.check_feasibility()
            res_time = self.start_time + self.time_limit - time()
            if res_time < 0: break
            if len(the_set) == 0: break
            for i, j, k in the_set:
                self._add_coupling_constraints_smart(i, j, k)
            # 参数设置
            self.model.solve(pulp.PULP_CBC_CMD(timeLimit=res_time))
            print("Status:", pulp.LpStatus[self.model.status])

        res_schedule = self._process_solution()
        if pulp.LpStatus[self.model.status] == "Infeasible":
            return 0, res_schedule, pulp.value(self.model.objective)
        # 输出每个变量的最优值
        return 1, res_schedule, pulp.value(self.model.objective)

    def _add_objective(self):
        """设置目标函数"""
        # 主变量惩罚项
        temp = 0
        for r in range(self.params.n_r):
            idx = self.get_idx(r, self.params.trip_num[r] - 1)
            temp += 0.001 * self.x[idx]

        # 辅助变量惩罚项
        self.interval_constant = self.params.n_r * self.params.v_num + self.params.trip_num[0] * self.params.trip_num[
            1] + self.aux_num

        for i in range(self.interval_constant, self.n_vars - 1):
            temp += 10 * self.x[i]

        for i in range(len(self.z1)):
            temp += 10 * self.z1[i]

        for i in range(len(self.z2)):
            temp += 10 * self.z2[i]

        for i in range(4):
            temp += 10 * self.y[i]

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
        # 统一参数计算格式

        # 下行
        cnt = [0, 0]
        a = self.params.rcd[1][0]
        l1 = (a - 1) // 2
        cnt[l1] += 1
        down_first = self.get_idx(a, 0)
        if self.params.rcd[1][-1] == 1:
            down_last = self.get_idx(1, self.params.trip_num[1] - 1)
        else:
            down_last = self.get_idx(3, self.params.trip_num[3] - 1)

        interval_delta = 0
        pre = -1
        cons = 1 / (len(self.params.rcd[1]) - 1)
        for i in range(1, len(self.params.rcd[1])):
            a = self.params.rcd[1][i]
            b = self.params.rcd[1][i - 1]
            l1 = (a - 1) // 2
            l2 = (b - 1) // 2
            c1 = cnt[l1]
            c2 = cnt[l2] - 1
            r1 = r2 = 0
            if a == 1:
                r1 = self.get_travel_time(self.params.jiaolu_end[0], self.params.jiaolu_end[1]) + self.get_stop_time(
                    self.params.jiaolu_end[0] - 1, self.params.jiaolu_end[1])
            if b == 1:
                r2 = self.get_travel_time(self.params.jiaolu_end[0], self.params.jiaolu_end[1]) + self.get_stop_time(
                    self.params.jiaolu_end[0] - 1, self.params.jiaolu_end[1])
            # print(r1, r2, self.params.jiaolu_start[0], self.params.jiaolu_start[1], self.params.jiaolu_end[0], self.params.jiaolu_end[1], "wrong wrong1")
            ex = self.x[self.get_idx(a, c1)] + r1 - self.x[self.get_idx(b, c2)] - r2
            expr = ex - cons * self.x[down_last] + cons * self.x[down_first]
            self.model += (expr <= self.x[self.interval_constant + i - 1])
            self.model += (-expr <= self.x[self.interval_constant + i - 1])
            if pre != -1:
                self.model += (ex - pre <= self.z2[interval_delta])
                self.model += (-(ex - pre) <= self.z2[interval_delta])
                interval_delta += 1
            pre = ex
            cnt[l1] += 1

        # 上行
        interval_delta = 0
        pre = -1
        cnt = [0, 0]
        a = self.params.rcd[0][0]
        l1 = a // 2
        cnt[l1] += 1
        up_first = self.get_idx(a, 0)
        if self.params.rcd[0][-1] == 0:
            up_last = self.get_idx(0, self.params.trip_num[0] - 1)
        else:
            up_last = self.get_idx(2, self.params.trip_num[2] - 1)
        cons = 1 / (len(self.params.rcd[0]) - 1)
        for i in range(1, len(self.params.rcd[0])):
            a = self.params.rcd[0][i]
            b = self.params.rcd[0][i - 1]
            l1 = a // 2
            l2 = b // 2
            c1 = cnt[l1]
            c2 = cnt[l2] - 1
            r1 = r2 = 0
            if a == 0:
                r1 = self.get_travel_time(self.params.jiaolu_start[0],
                                          self.params.jiaolu_start[1]) + self.get_stop_time(
                    self.params.jiaolu_start[0] + 1, self.params.jiaolu_start[1])
            if b == 0:
                r2 = self.get_travel_time(self.params.jiaolu_start[0],
                                          self.params.jiaolu_start[1]) + self.get_stop_time(
                    self.params.jiaolu_start[0] + 1, self.params.jiaolu_start[1])

            # print(r1, r2, self.params.jiaolu_start[0], self.params.jiaolu_start[1], self.params.jiaolu_end[0], self.params.jiaolu_end[1], "wrong wrong2")

            ex = self.x[self.get_idx(a, c1)] + r1 - self.x[self.get_idx(b, c2)] - r2
            expr = ex - cons * self.x[
                up_last] + cons * self.x[up_first]
            self.model += (expr <= self.x[self.interval_constant + len(self.params.rcd[1]) + i - 2])
            self.model += (-expr <= self.x[self.interval_constant + len(self.params.rcd[1]) + i - 2])
            if pre != -1:
                self.model += (ex - pre <= self.z1[interval_delta])
                self.model += (-(ex - pre) <= self.z1[interval_delta])
                interval_delta += 1
            pre = ex
            cnt[l1] += 1

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
        if self.fast_mod == 1:
            return
        if len(self.params.key_stations) == 0:
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
        aux_idx = (self.params.n_r * self.params.v_num + i * self.params.trip_num[1] + j)
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
        if len(self.params.key_stations) == 0:
            return
        t1 = self.get_travel_time(self.params.jiaolu_start[0], self.params.key_stations[0]) + self.get_stop_time(
            self.params.jiaolu_start[0], self.params.key_stations[0])
        t2 = self.get_travel_time(self.params.jiaolu_end[0], self.params.key_stations[0]) + self.get_stop_time(
            self.params.jiaolu_end[0], self.params.key_stations[0])

        # 示例：大交路上行与下行耦合
        for i in range(self.params.trip_num[0]):
            for j in range(self.params.trip_num[1]):
                aux_idx = (self.params.n_r * self.params.v_num +
                           i * self.params.trip_num[1] + j)
                # 正向约束
                expr = (self.x[self.get_idx(0, i)] + t1 -
                        self.x[self.get_idx(1, j)] - t2 +
                        self.M * self.x[aux_idx])
                self.model += (expr >= self.params.same_arrive_delta + self.get_stop_time(self.params.key_stations[0],
                                                                                          self.params.key_stations[0]))
                # 反向约束
                self.model += (-expr >= -self.M + self.params.same_arrive_delta + self.get_stop_time(
                    self.params.key_stations[0], self.params.key_stations[0]))

    def _add_shared_track_constraints(self):
        """添加共线段约束"""
        # 下行方向约束
        self._add_down_direction_constraints(
            rcd_line=self.params.rcd[1],
        )

        # 上行方向约束
        self._add_up_direction_constraints(
            rcd_line=self.params.rcd[0],
        )

    def _add_down_direction_constraints(self, rcd_line):
        """下行约束添加"""
        cnt = [0, 0]
        a = rcd_line[0]
        line_type = (a - 1) // 2
        cnt[line_type] += 1
        for i in range(1, len(rcd_line)):
            a, b = rcd_line[i], rcd_line[i - 1]
            line_type = (a - 1) // 2
            prev_line_type = (b - 1) // 2

            c1 = cnt[line_type]
            c2 = cnt[prev_line_type] - 1

            # 时间差计算
            r1 = r2 = 0
            if a == 1:
                r1 = self.get_travel_time(self.params.jiaolu_end[0], self.params.jiaolu_end[1]) + self.get_stop_time(
                    self.params.jiaolu_end[0] - 1, self.params.jiaolu_end[1])
            if b == 1:
                r2 = self.get_travel_time(self.params.jiaolu_end[0], self.params.jiaolu_end[1]) + self.get_stop_time(
                    self.params.jiaolu_end[0] - 1, self.params.jiaolu_end[1])
            print(f"r1 = {r1}")
            print(f"r2 = {r2}")
            # 构建约束
            idx_a = self.get_idx(a, c1)
            idx_b = self.get_idx(b, c2)

            # 正向约束
            expr = self.x[idx_a] + r1 - self.x[idx_b] - r2
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
                if self.params.jiaolu_end[line_type] == self.params.jiaolu_end[prev_line_type]:
                    pre = self.params.the_pre_variable[a][c1]
                    if a == 1:
                        travel_time = self.params.up_time1
                    elif a == 3:
                        travel_time = self.params.up_time2
                    # 判断是否能够站后折返
                    if self.params.isBackTurnbackStation[self.params.jiaolu_end[line_type] - 1]:
                        # if 0:
                        self.model += (self.x[self.get_idx(a - 1, pre)] - self.x[
                            idx_b] + travel_time >= - self.params.up_time2turnback - self.params.down_time2turnback + 1)
                    # 站前折返
                    else:
                        self.model += (self.x[self.get_idx(a - 1, pre)] - self.x[
                            idx_b] + travel_time >= self.params.min_dep_arr_delta)
            cnt[line_type] += 1

    def _add_up_direction_constraints(self, rcd_line):
        """方向通用约束添加"""
        cnt = [0, 0]
        a = rcd_line[0]
        line_type = a // 2
        cnt[line_type] += 1

        for i in range(1, len(rcd_line)):
            a, b = rcd_line[i], rcd_line[i - 1]
            line_type = a // 2
            prev_line_type = b // 2

            c1 = cnt[line_type]
            c2 = cnt[prev_line_type] - 1

            # 时间差计算
            r1 = r2 = 0
            if a == 0:
                r1 = self.get_travel_time(self.params.jiaolu_start[0],
                                          self.params.jiaolu_start[1]) + self.get_stop_time(
                    self.params.jiaolu_start[0] + 1, self.params.jiaolu_start[1])
            if b == 0:
                r2 = self.get_travel_time(self.params.jiaolu_start[0],
                                          self.params.jiaolu_start[1]) + self.get_stop_time(
                    self.params.jiaolu_start[0] + 1, self.params.jiaolu_start[1])
            # 构建约束
            idx_a = self.get_idx(a, c1)
            idx_b = self.get_idx(b, c2)
            # print(a, c1, b, c2, "up")

            # 正向约束
            expr = self.x[idx_a] + r1 - self.x[idx_b] - r2

            if self.params.the_pre_variable[a][c1] == -1 and self.params.the_pre_variable[b][c2] == -1:
                self.model += (expr >= self.params.min_shared_interval)
            elif self.params.the_pre_variable[a][c1] == -1 and self.params.the_pre_variable[b][c2] != -1:
                self.model += (expr >= self.params.min_shared_interval)
            elif self.params.the_pre_variable[a][c1] != -1 and self.params.the_pre_variable[b][c2] == -1:
                self.model += (expr >= self.params.min_shared_interval)
            else:
                self.model += (expr >= self.params.min_shared_interval)
                if self.params.jiaolu_start[line_type] == self.params.jiaolu_start[prev_line_type]:
                    pre = self.params.the_pre_variable[a][c1]
                    if a == 0:
                        travel_time = self.params.down_time1
                    elif a == 2:
                        travel_time = self.params.down_time2
                    if self.params.isBackTurnbackStation[self.params.jiaolu_start[line_type] - 1]:
                        # if 1:
                        self.model += (self.x[self.get_idx(a + 1, pre)] - self.x[
                            idx_b] + travel_time >= -self.params.up_time2turnback - self.params.down_time2turnback + 1)
                    else:
                        self.model += (self.x[self.get_idx(a + 1, pre)] - self.x[
                            idx_b] + travel_time >= self.params.min_dep_arr_delta)
            cnt[line_type] += 1

    def _add_first_last_trip_constraints(self):
        for r in range(2):
            self.model += (self.y[0 + 2 * r] >= self.x[self.get_idx(r, self.params.initial_trip_num[r])] - self.params.t[self.st1])
            self.model += (-self.y[0 + 2 * r] <= self.x[self.get_idx(r, self.params.initial_trip_num[r])] - self.params.t[self.st1])
            self.model += (self.y[1 + 2 * r] >= self.x[self.get_idx(r, self.params.trip_num[r] - 1)] - self.params.t[-1])
            self.model += (-self.y[1 + 2 * r] <= self.x[self.get_idx(r, self.params.trip_num[r] - 1)] - self.params.t[-1])
            # self.model += (self.x[self.get_idx(r, self.params.f1_accumulated[1] - 1)] == self.params.t[0])
            # self.model += (self.x[self.get_idx(r, self.params.trip_num1 - 1)] == self.params.t[-1])

    def _add_return_constraints(self):
        cnt = 0
        if self.fast_mod == 1:
            return
        turn_over_constant = self.params.n_r * self.params.v_num + self.params.trip_num[0] * self.params.trip_num[0]
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
        if len(self.params.key_stations) == 0 or self.fast_mod == 1:
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
        print(res, "双向不同时到达")
        return res

    def _process_solution(self):
        """处理优化结果"""
        solution = np.zeros((4, self.params.v_num))

        temp = 0
        for i in range(self.interval_constant, self.n_vars - 1):
            temp += self.x[i].varValue

        print("峰期最大偏移量：", self.x[-1].varValue)

        for v_cnt in range(4*self.params.v_num):
            if v_cnt < 4 * self.params.v_num:
                route = v_cnt // self.params.v_num
                trip = v_cnt % self.params.v_num
                solution[route, trip] = self.x[v_cnt].varValue

        # 生成时刻表逻辑

        return solution

    def _add_turnback_constraints(self):
        for i in range(1, self.params.trip_num[1]):
            b = self.params.the_pre_variable[1][i]
            if b != -1:
                idx_pre = self.get_idx(0, b)
                idx_curr = self.get_idx(1, i - 1)
                idx_now = self.get_idx(1, i)
                self.model += (
                        self.x[idx_pre] - self.x[idx_curr] + self.params.up_time1 >= self.params.min_dep_arr_delta)
                self.model += (
                        self.x[idx_now] - self.x[idx_pre] - self.params.up_time1 >= self.params.min_turnback_time)

        for i in range(1, self.params.trip_num[0]):
            b = self.params.the_pre_variable[0][i]
            if b != -1:
                idx_pre = self.get_idx(1, b)
                idx_curr = self.get_idx(0, i - 1)
                idx_now = self.get_idx(0, i)
                self.model += (
                        self.x[idx_pre] - self.x[idx_curr] + self.params.down_time1 >= self.params.min_dep_arr_delta)
                self.model += (
                        self.x[idx_now] - self.x[idx_pre] - self.params.down_time1 >= self.params.min_turnback_time)

        for i in range(1, self.params.trip_num[3]):
            b = self.params.the_pre_variable[3][i]
            if b != -1:
                idx_pre = self.get_idx(2, b)
                idx_curr = self.get_idx(3, i - 1)
                idx_now = self.get_idx(3, i)
                self.model += (
                        self.x[idx_pre] - self.x[idx_curr] + self.params.up_time2 >= self.params.min_dep_arr_delta)
                self.model += (
                        self.x[idx_now] - self.x[idx_pre] - self.params.up_time2 >= self.params.min_turnback_time)

        for i in range(1, self.params.trip_num[2]):
            b = self.params.the_pre_variable[2][i]
            if b != -1:
                idx_pre = self.get_idx(3, b)
                idx_curr = self.get_idx(2, i - 1)
                idx_now = self.get_idx(2, i)
                self.model += (
                        self.x[idx_pre] - self.x[idx_curr] + self.params.down_time2 >= self.params.min_dep_arr_delta)
                self.model += (
                        self.x[idx_now] - self.x[idx_pre] - self.params.down_time2 >= self.params.min_turnback_time)

    def _add_peak_period_constraints(self):
        # print("peak peak")
        # print(self.params.trip_num)
        # print(self.params.n_r)
        # print(self.params.f_real)
        # print(self.params.f_accumulated)
        # print(self.params.t)
        for p in range(self.st1 + 1, self.params.period_num):
            for i in range(2):
                a = self.params.f_accumulated[i][p]
                b = self.params.f_accumulated[i][p + 1] - 1
                for j in range(a, b + 1):
                    idx = self.get_idx(i, j)
                    self.model += (self.x[idx] + self.x[self.n_vars - 1] >= self.params.t[p])
                    self.model += (self.x[idx] - self.x[self.n_vars - 1] <= self.params.t[p + 1])

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