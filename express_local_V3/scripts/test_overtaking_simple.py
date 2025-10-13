"""
简单越行测试 - 最小数据集

用最简单的场景验证越行是否正确反映到Excel
场景：1列快车 + 1列慢车，确保产生越行
"""

import sys
import os

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
express_local_v3_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(express_local_v3_dir)
src_dir = os.path.join(project_root, 'src')

for path in [project_root, src_dir, express_local_v3_dir]:
    if path not in sys.path:
        sys.path.insert(0, path)

from RouteSolution import RouteSolution
from Solution import Solution
from CarInfo import CarInfo
import pandas as pd

def create_test_excel():
    """创建测试Excel：1列快车 + 1列慢车，展示越行"""
    
    print("="*80)
    print("简单越行测试 - 创建最小数据集")
    print("="*80)
    
    solution = Solution(False)  # debug_mode=False
    
    # 创建快车
    print("\n[创建快车]")
    express_dep_time = 7200  # 02:00:00
    express_rs = RouteSolution(express_dep_time, 1, 1, 1086)
    express_rs.dir = 0  # 上行
    express_rs.xroad = 0  # 大交路
    express_rs.operating = True
    express_rs.is_express = True
    
    # 快车跳停部分站，速度快
    # 简化场景：5个站点，快车跳停站点2和4
    stations = ['111', '114', '154', '202', '242']
    express_stops = [True, False, True, False, True]  # 停站模式
    
    current_time = express_dep_time
    express_section_time = 100  # 快车区间运行时间100秒
    
    for i, (platform, is_stop) in enumerate(zip(stations, express_stops)):
        if i > 0:
            current_time += express_section_time
        
        arrival = current_time
        dwell = 30 if is_stop and i > 0 and i < len(stations) - 1 else 0
        departure = arrival + dwell
        
        express_rs.addStop(
            platform=platform,
            stop_time=dwell,
            perf_level=1,
            current_time=arrival,
            dep_time=departure
        )
        
        current_time = departure
        
        status = "[跳站]" if not is_stop else "[停站]"
        print(f"  {platform}: 到{arrival}秒, 停{dwell}秒, 发{departure}秒 {status}")
    
    solution.addTrainService(express_rs)
    
    # 创建慢车（会被快车越行）
    print("\n[创建慢车 - 带越行]")
    local_dep_time = 7350  # 02:02:30（在快车后2.5分钟发车）
    local_rs = RouteSolution(local_dep_time, 2, 2, 1086)
    local_rs.dir = 0  # 上行
    local_rs.xroad = 0  # 大交路
    local_rs.operating = True
    local_rs.is_express = False
    
    # 慢车站站停
    current_time = local_dep_time
    local_section_time = 120  # 慢车区间运行时间120秒
    
    for i, platform in enumerate(stations):
        if i > 0:
            current_time += local_section_time
        
        arrival = current_time
        
        # 在站点3（索引2）发生越行，停站时间增加到240秒
        if i == 2:
            # 越行站：停站240秒
            dwell = 240
            print(f"  ** {platform}: 到{arrival}秒, 停{dwell}秒（越行站！）, 发{arrival+dwell}秒 [越行站-待避4分钟]")
        elif i == 0 or i == len(stations) - 1:
            dwell = 0
        else:
            dwell = 30
            print(f"  {platform}: 到{arrival}秒, 停{dwell}秒, 发{arrival+dwell}秒 [停站]")
        
        departure = arrival + dwell
        
        local_rs.addStop(
            platform=platform,
            stop_time=dwell,
            perf_level=1,
            current_time=arrival,
            dep_time=departure
        )
        
        current_time = departure
    
    solution.addTrainService(local_rs)
    
    # 写Excel
    print("\n[写入Excel]")
    output_dir = os.path.join(project_root, "data/output_data/test_overtaking_simple")
    os.makedirs(output_dir, exist_ok=True)
    
    # 创建假的rail_info（只用于Excel输出）
    from DataReader import DataReader
    rail_info_file = os.path.join(project_root, "data/input_data_new/RailwayInfo/Schedule-cs2.xml")
    rail_info = DataReader.read_file(rail_info_file)
    
    solution.writeExcel(output_dir, rail_info, "gbk")
    
    print(f"[OK] Excel已生成: {output_dir}/result.xls")
    
    # 读取Excel验证
    print("\n[验证Excel]")
    excel_file = os.path.join(output_dir, "result.xls")
    
    try:
        xl = pd.ExcelFile(excel_file)
        df_plan = pd.read_excel(excel_file, sheet_name=1)
        
        print(f"  总车次数: {len(df_plan)}")
        print(f"  快车数量: {df_plan['快车'].sum() if '快车' in df_plan.columns else 'N/A'}")
        
        # 检查详细数据
        print(f"\n[详细车次]")
        print(df_plan.to_string(index=False))
        
    except Exception as e:
        print(f"  [ERROR] 验证失败: {str(e)}")
    
    print("\n" + "="*80)
    print("[完成]")
    print("="*80)
    print("\n[说明]")
    print("  这个测试创建了最简单的场景：1列快车 + 1列慢车")
    print("  慢车在站点3（索引2）被快车越行，停站时间从30秒增加到240秒")
    print("  请用运行图显示软件加载Excel文件验证越行效果")
    print(f"\n[输出文件] {output_dir}/result.xls")


if __name__ == "__main__":
    create_test_excel()

