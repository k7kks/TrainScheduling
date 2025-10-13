"""完整验证所有车次的站台码序列"""
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
print("完整验证所有64个车次的站台码序列")
print("="*80)

total_trains = len(df_plan)
total_errors = 0
error_details = []

print(f"\n总车次数: {total_trains}")
print(f"\n开始逐个检查...")

for idx, (_, train_row) in enumerate(df_plan.iterrows()):
    round_num = train_row['车次号']
    route_num = train_row['路径编号']
    
    # 获取该路径的正确站台序列
    route_id_str = str(route_num)
    if route_id_str not in rail_info.pathList:
        continue
    
    path = rail_info.pathList[route_id_str]
    correct_codes = path.nodeList
    
    # 获取该车次的实际站台序列
    train_detail = df_mission[df_mission['车次号'] == round_num]
    actual_platforms = train_detail['站台目的地码'].tolist()
    actual_platforms_str = [str(p) for p in actual_platforms]
    
    # 比较
    if actual_platforms_str != correct_codes:
        total_errors += 1
        error_details.append({
            'round_num': round_num,
            'route_num': route_num,
            'expected_count': len(correct_codes),
            'actual_count': len(actual_platforms),
            'expected': correct_codes,
            'actual': actual_platforms_str
        })
        
        if total_errors <= 5:  # 只打印前5个错误
            print(f"\n[ERROR {total_errors}] 车次{round_num}（路径{route_num}）")
            print(f"  期望{len(correct_codes)}个站台: {', '.join(correct_codes[:10])}...")
            print(f"  实际{len(actual_platforms)}个站台: {', '.join(actual_platforms_str[:10])}...")
    
    if (idx + 1) % 10 == 0:
        print(f"  已检查 {idx+1}/{total_trains}...")

print(f"\n" + "="*80)
print(f"验证完成")
print(f"="*80)
print(f"总车次数: {total_trains}")
print(f"错误车次数: {total_errors}")
print(f"正确率: {(total_trains - total_errors) / total_trains * 100:.1f}%")

if total_errors == 0:
    print(f"\n[SUCCESS] 所有{total_trains}个车次的站台码序列都100%正确！")
    print(f"\n新生成的Excel文件可以正常加载到运行图显示软件。")
    print(f"文件路径: data/output_data/results_express_local_v3/result.xlsx")
else:
    print(f"\n[FAILURE] 发现{total_errors}个车次的站台码有误！")
    print(f"\n错误详情已保存，需要进一步修复。")
    
    # 保存错误详情
    if error_details:
        with open('platform_code_errors.txt', 'w', encoding='utf-8') as f:
            for err in error_details:
                f.write(f"\n车次{err['round_num']}（路径{err['route_num']}）:\n")
                f.write(f"  期望: {', '.join(err['expected'])}\n")
                f.write(f"  实际: {', '.join(err['actual'])}\n")
        print(f"错误详情已保存到: platform_code_errors.txt")

