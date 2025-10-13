"""检查所有路径1088的车次"""
import sys, os
import pandas as pd

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(project_root, 'src'))

from DataReader import DataReader

# 读取XML获取Path 1088的正确站台码
rail_info_file = os.path.join(project_root, "data/input_data_new/RailwayInfo/Schedule-cs2.xml")
rail_info = DataReader.read_file(rail_info_file)

path_1088 = rail_info.pathList['1088']
correct_codes = path_1088.nodeList

print("="*80)
print("Path 1088的正确站台码序列")
print("="*80)
print(f"共{len(correct_codes)}个站台:")
print(', '.join(correct_codes))

# 读取Excel
excel_file = os.path.join(project_root, "data/output_data/results_express_local_v3/result.xls")
df_plan = pd.read_excel(excel_file, sheet_name=1)
df_mission = pd.read_excel(excel_file, sheet_name=2)

trains_1088 = df_plan[df_plan['路径编号'] == 1088]

print(f"\n路径1088的车次数: {len(trains_1088)}")
print(f"车次号: {trains_1088['车次号'].tolist()}")

# 检查第一个车次的站台码
if len(trains_1088) > 0:
    first_round = trains_1088['车次号'].iloc[0]
    print(f"\n检查车次{first_round}:")
    
    train_detail = df_mission[df_mission['车次号'] == first_round]
    platforms = train_detail['站台目的地码'].tolist()
    
    print(f"  站台数: {len(platforms)}")
    print(f"  站台码: {', '.join(map(str, platforms))}")
    
    # 转换为字符串进行比较
    platforms_str = [str(p) for p in platforms]
    
    if platforms_str == correct_codes:
        print(f"  [OK] 站台码序列100%正确！")
    else:
        print(f"  [ERROR] 站台码序列错误！")
        print(f"  platforms类型: {type(platforms[0]) if platforms else 'empty'}")
        print(f"  correct_codes类型: {type(correct_codes[0]) if correct_codes else 'empty'}")
        print(f"\n  对比:")
        print(f"    应该: {', '.join(correct_codes)}")
        print(f"    实际: {', '.join(map(str, platforms))}")
        
        # 查找第一个不匹配的位置
        for i, (expected, actual) in enumerate(zip(correct_codes, platforms)):
            if str(expected) != str(actual):
                print(f"\n  第{i+1}个站台不匹配: 应该是{expected}，实际是{actual}")
                break

