def adj_rcd(params, initial_r=-1):
    r = initial_r
    if params.jiaolu_start[0] == params.jiaolu_start[1]:
        r = 1
    elif params.jiaolu_end[0] == params.jiaolu_end[1]:
        r = 0
    if r == -1: return params

    while 1:
        cnt1 = [0, 0]
        temp_dict = {}
        for i in range(len(params.rcd[1 - r])):
            a = params.rcd[1 - r][i] // 2
            temp_dict[a, cnt1[a]] = i
            cnt1[a] += 1
        pre = -1
        pre_id = -1
        cnt = [0, 0]
        flag = 0
        for i in range(len(params.rcd[r])):
            line_id = params.rcd[r][i]
            cnt_id = line_id // 2
            if params.the_aft_variable[line_id][cnt[cnt_id]] != -1:
                a = params.the_aft_variable[line_id][cnt[cnt_id]]
                the_id = temp_dict[cnt_id, a]
                if pre != -1:
                    if pre > the_id:
                        params.rcd[r][i], params.rcd[r][pre_id] = params.rcd[r][pre_id], params.rcd[r][i]
                        flag = 1
                if pre < the_id:
                    pre = the_id
                    pre_id = i
            if flag == 1:
                break
            cnt[cnt_id] += 1
        if flag == 0:
            break
    return params
