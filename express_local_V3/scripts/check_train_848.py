"""检查车次848的数据"""
import sys, os
import pandas as pd

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
excel_file = os.path.join(project_root, "data/output_data/results_express_local_v3/result.xls")

print("="*80)
print("检查车次848")
print("="*80)

df = pd.read_excel(excel_file, sheet_name=2)
train_848 = df[df['车次号'] == 848]

print(f"车次848记录数: {len(train_848)}")
if len(train_848) > 0:
    print(f"表号: {train_848['表号'].iloc[0]}")
    platforms = train_848['站台目的地码'].tolist()
    print(f"站台数: {len(platforms)}")
    print(f"站台序列: {', '.join(map(str, platforms))}")
    
    # 检查是否有重复
    unique = list(dict.fromkeys(platforms))
    if len(unique) != len(platforms):
        print(f"[ERROR] 发现重复站台！去重后{len(unique)}个")
    
    # 读取计划线获取路径
    df_plan = pd.read_excel(excel_file, sheet_name=1)
    plan_848 = df_plan[df_plan['车次号'] == 848]
    if len(plan_848) > 0:
        print(f"路径编号: {plan_848['路径编号'].iloc[0]}")

