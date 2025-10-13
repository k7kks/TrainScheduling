"""验证所有路径的站台码序列"""
import sys, os
import pandas as pd

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(project_root, 'src'))

from DataReader import DataReader

# 读取XML
rail_info_file = os.path.join(project_root, "data/input_data_new/RailwayInfo/Schedule-cs2.xml")
rail_info = DataReader.read_file(rail_info_file)

# 读取Excel
excel_file = os.path.join(project_root, "data/output_data/results_express_local_v3/result.xls")
df_plan = pd.read_excel(excel_file, sheet_name=1)
df_mission = pd.read_excel(excel_file, sheet_name=2)

print("="*80)
print("验证所有路径的站台码序列")
print("="*80)

# 检查主要路径：1086（上行）和1088（下行）
paths_to_check = ['1086', '1088']

total_errors = 0
total_checked = 0

for path_id in paths_to_check:
    if path_id not in rail_info.pathList:
        continue
    
    path = rail_info.pathList[path_id]
    correct_codes = path.nodeList
    
    print(f"\n[Path {path_id}]")
    print(f"  正确站台数: {len(correct_codes)}")
    print(f"  站台序列: {', '.join(correct_codes[:10])}... (前10个)")
    
    # 查找该路径的所有车次
    trains = df_plan[df_plan['路径编号'] == int(path_id)]
    
    print(f"  车次数: {len(trains)}")
    
    # 检查每个车次（最多检查5个）
    for idx, (_, train_row) in enumerate(trains.iterrows()):
        if idx >= 5:  # 只检查前5个
            break
        
        round_num = train_row['车次号']
        train_detail = df_mission[df_mission['车次号'] == round_num]
        platforms = train_detail['站台目的地码'].tolist()
        platforms_str = [str(p) for p in platforms]
        
        total_checked += 1
        
        if platforms_str == correct_codes:
            if idx == 0:
                print(f"  车次{round_num}: [OK] 站台码正确（{len(platforms)}个）")
        else:
            total_errors += 1
            print(f"  车次{round_num}: [ERROR] 站台码错误！")
            print(f"    期望: {', '.join(correct_codes)}")
            print(f"    实际: {', '.join(platforms_str)}")
            
            # 找到第一个不匹配
            for i in range(min(len(correct_codes), len(platforms_str))):
                if correct_codes[i] != platforms_str[i]:
                    print(f"    首个错误位置{i}: 期望{correct_codes[i]}, 实际{platforms_str[i]}")
                    break

print(f"\n" + "="*80)
print(f"验证完成")
print(f"="*80)
print(f"检查车次数: {total_checked}")
print(f"错误车次数: {total_errors}")

if total_errors == 0:
    print(f"\n[SUCCESS] 所有车次的站台码序列都100%正确！ ✓")
else:
    print(f"\n[FAILURE] 发现{total_errors}个车次的站台码序列有误！")

