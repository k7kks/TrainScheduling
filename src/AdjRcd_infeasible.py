# 先试着平移发车时间，如果不行的话再交换大小交路的发车顺序，再不行的话，修改输入的参数
import random


def adj_rcd_infeasible(params, res_schedule):
    conflict = []
    M = 0.1
    n = max(len(params.rcd[0]), len(params.rcd[1]))

    def get_travel_time(i, j):
        if i > j:
            return params.travel_time_matrix[1][i][j]
        return params.travel_time_matrix[0][i][j]

    def get_stop_time(i, j):
        if i > j:
            return params.stop_time_matrix[1][i][j]
        return params.stop_time_matrix[0][i][j]

    def _check_turnback_constraints():
        cnt = [0, 0]
        for i in params.rcd[0]:
            l1 = i // 2
            b = params.the_pre_variable[i][cnt[l1]]
            if b == -1:
                cnt[l1] = cnt[l1] + 1
                continue
            if i == 0:
                travel_time = params.down_time1
            else:
                travel_time = params.down_time2
            if res_schedule[i, cnt[l1]] - res_schedule[i + 1][b] - travel_time < params.min_turnback_time - M:
                conflict.append(["min_turnback_time1", i, cnt[l1], i + 1, b,
                                 res_schedule[i][cnt[l1]] - res_schedule[i + 1][b] - travel_time,
                                 params.min_turnback_time])
            cnt[l1] = cnt[l1] + 1

        cnt = [0, 0]
        for i in params.rcd[1]:
            l1 = (i - 1) // 2
            b = params.the_pre_variable[i][cnt[l1]]
            if b == -1:
                cnt[l1] += 1
                continue
            if i == 1:
                travel_time = params.up_time1
            else:
                travel_time = params.up_time2
            if res_schedule[i, cnt[l1]] - res_schedule[i - 1][b] - travel_time < params.min_turnback_time - M:
                conflict.append(["min_turnback_time2", i, cnt[l1], i - 1, b,
                                 res_schedule[i][cnt[l1]] - res_schedule[i - 1, b] - travel_time,
                                 params.min_turnback_time])
            cnt[l1] = cnt[l1] + 1

        for i in range(1, params.trip_num[1]):
            b = params.the_pre_variable[1][i]
            if b != -1:
                if res_schedule[0][b] - res_schedule[1, i - 1] + params.up_time1 < params.min_dep_arr_delta - M:
                    conflict.append(["min_dep_arr_delta1", 0, b, 1, i - 1,
                                     res_schedule[0][b] - res_schedule[1, i - 1] + params.up_time1,
                                     params.min_dep_arr_delta])
        for i in range(1, params.trip_num[0]):
            b = params.the_pre_variable[0][i]
            if b != -1:
                if res_schedule[1][b] - res_schedule[0, i - 1] + params.down_time1 < params.min_dep_arr_delta - M:
                    conflict.append(["min_dep_arr_delta2", 1, b, 0, i - 1,
                                     res_schedule[1][b] - res_schedule[0, i - 1] + params.down_time1,
                                     params.min_dep_arr_delta])

        for i in range(1, params.trip_num[3]):
            b = params.the_pre_variable[3][i]
            if b != -1:
                if res_schedule[2][b] - res_schedule[3, i - 1] + params.up_time2 < params.min_dep_arr_delta - M:
                    conflict.append(["min_dep_arr_delta3", 2, b, 3, i - 1,
                                     res_schedule[2][b] - res_schedule[3, i - 1] + params.up_time2,
                                     params.min_dep_arr_delta])

        for i in range(1, params.trip_num[2]):
            b = params.the_pre_variable[2][i]
            if b != -1:
                if res_schedule[3][b] - res_schedule[2, i - 1] + params.down_time2 < params.min_dep_arr_delta - M:
                    conflict.append(["min_dep_arr_delta4", 3, b, 2, i - 1,
                                     res_schedule[3][b] - res_schedule[2, i - 1] + params.down_time2,
                                     params.min_dep_arr_delta])

    def _check_up_direction_constraints(rcd_line):
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
                r1 = get_travel_time(params.jiaolu_start[0],
                                     params.jiaolu_start[1]) + get_stop_time(
                    params.jiaolu_start[0] + 1, params.jiaolu_start[1])
            if b == 0:
                r2 = get_travel_time(params.jiaolu_start[0],
                                     params.jiaolu_start[1]) + get_stop_time(
                    params.jiaolu_start[0] + 1, params.jiaolu_start[1])
            # 构建约束
            # print(a, c1, b, c2, "up")

            # 正向约束
            expr = res_schedule[a][c1] + r1 - res_schedule[b][c2] - r2

            if params.the_pre_variable[a][c1] == -1 and params.the_pre_variable[b][c2] == -1:
                if expr < params.min_shared_interval - M:
                    conflict.append(["min_shared_interval", a, c1, b, c2, expr, params.min_shared_interval])
            elif params.the_pre_variable[a][c1] == -1 and params.the_pre_variable[b][c2] != -1:
                if expr < params.min_shared_interval - M:
                    conflict.append(["min_shared_interval", a, c1, b, c2, expr, params.min_shared_interval])
            elif params.the_pre_variable[a][c1] != -1 and params.the_pre_variable[b][c2] == -1:
                if expr < params.min_shared_interval - M:
                    conflict.append(["min_shared_interval", a, c1, b, c2, expr, params.min_shared_interval])
            else:
                if expr < params.min_shared_interval - M:
                    conflict.append(["min_shared_interval", a, c1, b, c2, expr, params.min_shared_interval])
                if params.jiaolu_start[line_type] == params.jiaolu_start[prev_line_type]:
                    pre = params.the_pre_variable[a][c1]
                    if a == 0:
                        travel_time = params.down_time1
                    elif a == 2:
                        travel_time = params.down_time2

                    if params.isBackTurnbackStation[params.jiaolu_start[line_type] - 1]:
                        # if 1:
                        if res_schedule[a + 1][pre] - res_schedule[b][
                            c2] + travel_time < -params.up_time2turnback - params.down_time2turnback + 1 - M:
                            conflict.append(
                                ["min_dep_arr_delta_backturnback", a + 1, pre, b, c2,
                                 res_schedule[a + 1][pre] - res_schedule[b][c2] + travel_time,
                                 -params.up_time2turnback - params.down_time2turnback + 1])
                    else:
                        if res_schedule[a + 1][pre] - res_schedule[b][c2] + travel_time < params.min_dep_arr_delta - M:
                            conflict.append(
                                ["min_dep_arr_delta", a + 1, pre, b, c2,
                                 res_schedule[a + 1][pre] - res_schedule[b][c2] + travel_time,
                                 params.min_dep_arr_delta])
            cnt[line_type] += 1

    def _check_down_direction_constraints(rcd_line):
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
                r1 = get_travel_time(params.jiaolu_end[0], params.jiaolu_end[1]) + get_stop_time(
                    params.jiaolu_end[0] - 1, params.jiaolu_end[1])
            if b == 1:
                r2 = get_travel_time(params.jiaolu_end[0], params.jiaolu_end[1]) + get_stop_time(
                    params.jiaolu_end[0] - 1, params.jiaolu_end[1])

            # 构建约束

            # 正向约束
            expr = res_schedule[a][c1] + r1 - res_schedule[b][c2] - r2
            # 虽然这几个判断语句都有同样的约束，但是保持这个结构便于扩展模型
            if params.the_pre_variable[a][c1] == -1 and params.the_pre_variable[b][c2] == -1:
                if expr < params.min_shared_interval - M:
                    conflict.append(["min_shared_interval", a, c1, b, c2, expr, params.min_shared_interval])
            elif params.the_pre_variable[a][c1] == -1 and params.the_pre_variable[b][c2] != -1:
                if expr < params.min_shared_interval - M:
                    conflict.append(["min_shared_interval", a, c1, b, c2, expr, params.min_shared_interval])
            elif params.the_pre_variable[a][c1] != -1 and params.the_pre_variable[b][c2] == -1:
                if expr < params.min_shared_interval - M:
                    conflict.append(["min_shared_interval", a, c1, b, c2, expr, params.min_shared_interval])
            else:
                if expr < params.min_shared_interval - M:
                    conflict.append(["min_shared_interval", a, c1, b, c2, expr, params.min_shared_interval])
                # 下行是否是共线折返，如果结束的站点不同，那么不是，如果结束的站点相同，则是共线折返
                if params.jiaolu_end[line_type] == params.jiaolu_end[prev_line_type]:
                    pre = params.the_pre_variable[a][c1]
                    if a == 1:
                        travel_time = params.up_time1
                    elif a == 3:
                        travel_time = params.up_time2
                    # 判断是否能够站后折返
                    if params.isBackTurnbackStation[params.jiaolu_end[line_type] - 1]:
                        # if 0:
                        if res_schedule[a - 1][pre] - res_schedule[b][
                            c2] + travel_time < - params.up_time2turnback - params.down_time2turnback + 1 - M:
                            conflict.append(["min_shared_interval", a - 1, pre, b, c2,
                                             res_schedule[a - 1][pre] - res_schedule[b][c2] + travel_time,
                                             - params.up_time2turnback - params.down_time2turnback + 1 - M])
                    # 站前折返
                    else:
                        if res_schedule[a - 1][pre] - res_schedule[b][c2] + travel_time < params.min_dep_arr_delta - M:
                            conflict.append(["min_dep_arr_delta", a - 1, pre, b, c2,
                                             res_schedule[a - 1][pre] - res_schedule[b][c2] + travel_time,
                                             params.min_dep_arr_delta])
            cnt[line_type] += 1

    _check_turnback_constraints()
    _check_up_direction_constraints(params.rcd[0])
    _check_down_direction_constraints(params.rcd[1])

    max_modify_num = 30
    modify_num = random.randint(1, max_modify_num)
    # modify_num = 10
    res = 0
    for i in conflict:
        res += i[-1] - i[-2]

    conflict.sort(key=lambda x: x[-1] - x[-2], reverse=True)

    for i in conflict:
        print(["conflict", i])
    if random.random() < 0.5:
        modify_num = max(modify_num, len(conflict) // 4)

    for i in conflict[:modify_num]:
        temp_dict = {}
        for r in range(2):
            cnt = [0, 0]
            for k in range(len(params.rcd[r])):
                a = params.rcd[r][k]
                aa = a // 2
                temp_dict[a, cnt[aa]] = k
                cnt[aa] += 1
        c, d, a, b = i[1], i[2], i[3], i[4]
        dis1 = dis2 = n
        st1 = temp_dict[a, b]
        st2 = temp_dict[c, d]
        line1 = a % 2
        line2 = c % 2
        for j in range(st1 - 1, 0, -1):
            if params.rcd[line1][j] != a:
                dis1 = st1 - j
                break
        for j in range(st2 + 1, len(params.rcd[line2])):
            if params.rcd[line2][j] != c:
                dis2 = j - st2
                break
        if dis1 < dis2:
            params.rcd[line1][st1 - dis1], params.rcd[line1][st1] = params.rcd[line1][st1], params.rcd[line1][
                st1 - dis1]
        else:
            params.rcd[line2][st2 + dis2], params.rcd[line2][st2] = params.rcd[line2][st2], params.rcd[line2][
                st2 + dis2]

    return res, params
