"""
详细调试车次勾连问题

分析车次的时间分布、排序情况、折返可能性
"""

import sys
import os

# 添加项目路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

src_dir = os.path.join(project_root, 'src')
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from DataReader import DataReader
from algorithms.express_local_generator import ExpressLocalGenerator, ExpressLocalConfig
from algorithms.timetable_builder import TimetableBuilder
from models.train import Train

def debug_train_times(scheduler):
    """调试车次时间信息"""
    print("\n" + "="*80)
    print("车次时间调试信息")
    print("="*80)
    
    # 获取所有车次
    all_trains = scheduler.timetable.express_trains + scheduler.timetable.local_trains
    
    # 按发车时间排序
    all_trains_sorted = sorted(all_trains, key=lambda t: t.departure_time)
    
    print(f"\n总车次数: {len(all_trains_sorted)}")
    print(f"快车: {len(scheduler.timetable.express_trains)}")
    print(f"慢车: {len(scheduler.timetable.local_trains)}")
    
    # 分析前20个车次
    print(f"\n前20个车次的时间分布:")
    print("-" * 80)
    print(f"{'车次ID':<10} {'类型':<6} {'方向':<6} {'交路':<6} {'发车时间':<12} {'首站到达':<12} {'末站离开':<12}")
    print("-" * 80)
    
    for i, train in enumerate(all_trains_sorted[:20]):
        train_type = "快车" if hasattr(train, 'skip_stations') and train.skip_stations else "慢车"
        train_dir = train.direction
        train_xroad = "小交路" if train.is_short_route else "大交路"
        
        # 获取时刻表条目
        entries = scheduler.timetable.train_schedules.get(train.train_id, [])
        
        first_arrival = entries[0].arrival_time if entries else 0
        last_departure = entries[-1].departure_time if entries else 0
        
        print(f"{train.train_id:<10} {train_type:<6} {train_dir:<6} {train_xroad:<6} "
              f"{train.departure_time:<12} {first_arrival:<12} {last_departure:<12}")
    
    print("-" * 80)

def analyze_connection_possibilities(scheduler):
    """分析勾连可能性"""
    print("\n" + "="*80)
    print("勾连可能性分析")
    print("="*80)
    
    # 获取所有车次并转换为RouteSolution
    peak = scheduler.user_setting.peaks[0]
    all_trains = scheduler.timetable.express_trains + scheduler.timetable.local_trains
    
    route_solutions = []
    for train in all_trains:
        route_id = scheduler._get_route_id_for_train(train, peak)
        if not route_id or route_id not in scheduler.rail_info.pathList:
            continue
        path = scheduler.rail_info.pathList[route_id]
        rs = scheduler._create_route_solution_from_path(train, route_id, path)
        if rs:
            route_solutions.append(rs)
    
    # 按方向和快慢分组
    express_up = [rs for rs in route_solutions if rs.is_express and rs.dir == 0]
    express_down = [rs for rs in route_solutions if rs.is_express and rs.dir == 1]
    local_up = [rs for rs in route_solutions if not rs.is_express and rs.dir == 0]
    local_down = [rs for rs in route_solutions if not rs.is_express and rs.dir == 1]
    
    print(f"\n分组统计:")
    print(f"  快车上行: {len(express_up)}")
    print(f"  快车下行: {len(express_down)}")
    print(f"  慢车上行: {len(local_up)}")
    print(f"  慢车下行: {len(local_down)}")
    
    # 分析快车的勾连可能性
    if express_up and express_down:
        print(f"\n快车勾连分析（前5对）:")
        print("-" * 80)
        
        # 按首站到达时间排序
        express_up_sorted = sorted(express_up, key=lambda x: x.arr_time[0])
        express_down_sorted = sorted(express_down, key=lambda x: x.arr_time[0])
        
        for i in range(min(5, len(express_up_sorted))):
            up_train = express_up_sorted[i]
            
            # 找最近的下行车
            up_end_time = up_train.dep_time[-1]
            
            print(f"\n上行车 {up_train.car_info.table_num}:")
            print(f"  首站到达: {up_train.arr_time[0]}秒 ({up_train.arr_time[0]//60}分)")
            print(f"  末站离开: {up_end_time}秒 ({up_end_time//60}分)")
            print(f"  站台: {up_train.stopped_platforms[0]} -> {up_train.stopped_platforms[-1]}")
            
            # 找所有可能的下行车
            candidates = []
            for down_train in express_down_sorted:
                down_start_time = down_train.arr_time[0]
                turnback = down_start_time - up_end_time
                
                if turnback > -3600 and turnback < 3600:  # 在±1小时内
                    candidates.append((down_train, turnback))
            
            if candidates:
                # 按折返时间排序
                candidates.sort(key=lambda x: abs(x[1]))
                best = candidates[0]
                
                print(f"  最佳匹配下行车 {best[0].car_info.table_num}:")
                print(f"    首站到达: {best[0].arr_time[0]}秒 ({best[0].arr_time[0]//60}分)")
                print(f"    站台: {best[0].stopped_platforms[0]} -> {best[0].stopped_platforms[-1]}")
                print(f"    折返时间: {best[1]}秒 ({best[1]//60}分) {'✓' if best[1] >= 60 else '✗ 太短'}")
            else:
                print(f"  未找到合适的下行车")

def main():
    """主函数"""
    # 导入调度器
    current_module_dir = os.path.dirname(os.path.abspath(__file__))
    if current_module_dir not in sys.path:
        sys.path.insert(0, current_module_dir)
    
    import main as scheduler_module
    ExpressLocalSchedulerV3 = scheduler_module.ExpressLocalSchedulerV3
    
    print("初始化调度器...")
    scheduler = ExpressLocalSchedulerV3(
        rail_info_file="../data/input_data_new/RailwayInfo/Schedule-cs2.xml",
        user_setting_file="../data/input_data_new/UserSettingInfoNew/cs2_real_28.xml",
        output_dir="../data/output_data/results_express_local_v3",
        express_ratio=0.5,
        target_headway=180,
        debug=False
    )
    
    print("读取数据...")
    scheduler.read_data()
    
    print("生成快慢车运行图...")
    scheduler.generate_express_local_timetable()
    
    # 执行调试分析
    debug_train_times(scheduler)
    analyze_connection_possibilities(scheduler)

if __name__ == "__main__":
    main()

