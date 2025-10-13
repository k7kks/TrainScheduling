"""
调试RouteSolution - 检查停站时间是否正确保存
"""

import sys
import os
import pickle

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
express_local_v3_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(express_local_v3_dir)
src_dir = os.path.join(project_root, 'src')

for path in [project_root, src_dir, express_local_v3_dir]:
    if path not in sys.path:
        sys.path.insert(0, path)

from RouteSolution import RouteSolution

def create_and_check_route_solution():
    """创建RouteSolution并检查停站时间"""
    
    print("="*80)
    print("调试RouteSolution - 检查停站时间")
    print("="*80)
    
    # 创建一个简单的RouteSolution
    rs = RouteSolution(7200, 1, 1, 1086)
    rs.dir = 0
    rs.operating = True
    
    # 添加5个站点，第3个站点停站240秒（越行站）
    stations = ['111', '114', '154', '202', '242']
    dwell_times = [0, 30, 240, 30, 0]  # 第3个站点停站240秒
    
    current_time = 7200
    
    for i, (platform, dwell) in enumerate(zip(stations, dwell_times)):
        if i > 0:
            current_time += 120  # 区间运行时间
        
        arrival = current_time
        departure = arrival + dwell
        
        rs.addStop(
            platform=platform,
            stop_time=dwell,
            perf_level=1,
            current_time=arrival,
            dep_time=departure
        )
        
        current_time = departure
        
        print(f"  站台{platform}: 到{arrival}, 停{dwell}秒, 发{departure}")
    
    # 检查RouteSolution对象
    print(f"\n[RouteSolution内部数据]")
    print(f"  stopped_platforms: {rs.stopped_platforms}")
    print(f"  stopped_time: {rs.stopped_time}")
    print(f"  arr_time: {rs.arr_time}")
    print(f"  dep_time: {rs.dep_time}")
    
    # 验证第3个站点的停站时间
    if len(rs.stopped_time) >= 3:
        third_station_dwell = rs.stopped_time[2]
        print(f"\n[验证] 第3个站点（索引2）的停站时间: {third_station_dwell}秒")
        
        if third_station_dwell == 240:
            print("  ✓ 越行站停站时间正确设置为240秒！")
        else:
            print(f"  ✗ 错误：应该是240秒，实际是{third_station_dwell}秒")
    
    # 检查retCSVStringPlanned方法的输出
    print(f"\n[CSV输出格式]")
    print(f"  retCSVStringPlanned():")
    print(f"    {rs.retCSVStringPlanned()}")
    
    # 检查详细的停站信息
    print(f"\n[详细停站信息]")
    for i in range(len(rs.stopped_platforms)):
        platform = rs.stopped_platforms[i]
        dwell = rs.stopped_time[i]
        arr = rs.arr_time[i]
        dep = rs.dep_time[i]
        print(f"  站{i}: {platform} - 到:{arr}, 停:{dwell}秒, 发:{dep}")
    
    print("\n" + "="*80)
    print("[结论]")
    print("="*80)
    
    if len(rs.stopped_time) >= 3 and rs.stopped_time[2] == 240:
        print("✓ RouteSolution正确保存了越行站的停站时间（240秒）")
        print("✓ 数据结构正确，应该能够写入Excel")
        print("\n下一步：确认Excel写入方法是否正确读取stopped_time")
    else:
        print("✗ RouteSolution未正确保存越行站停站时间")
        print("  需要检查addStop()方法的实现")


if __name__ == "__main__":
    create_and_check_route_solution()

