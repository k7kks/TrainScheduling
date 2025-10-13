"""
检查车次125的详细数据
"""

import sys
import os
import pandas as pd

current_dir = os.path.dirname(os.path.abspath(__file__))
express_local_v3_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(express_local_v3_dir)

excel_file = os.path.join(project_root, "data/output_data/results_express_local_v3/result.xls")

print("="*80)
print("检查车次125的详细数据")
print("="*80)

try:
    # 读取任务线数据（Sheet 3）
    df_mission = pd.read_excel(excel_file, sheet_name=2)
    
    print(f"\n[任务线数据Sheet]")
    print(f"  总行数: {len(df_mission)}")
    print(f"  列名: {list(df_mission.columns)}")
    
    # 查找车次号=125的所有记录
    round_col = [c for c in df_mission.columns if '车次' in str(c) or 'round' in str(c).lower()]
    if round_col:
        round_col_name = round_col[0]
        train_125 = df_mission[df_mission[round_col_name] == 125]
        
        print(f"\n[车次125的所有记录]")
        print(f"  记录数: {len(train_125)}")
        
        if len(train_125) > 0:
            # 获取站台码列
            platform_col = [c for c in df_mission.columns if '站台' in str(c) or 'platform' in str(c).lower()]
            if platform_col:
                platform_col_name = platform_col[0]
                platforms = train_125[platform_col_name].tolist()
                
                print(f"\n  站台码序列（共{len(platforms)}个）:")
                print(f"    {', '.join(map(str, platforms))}")
                
                # 获取表号
                table_col = [c for c in df_mission.columns if '表号' in str(c) or 'table' in str(c).lower()]
                if table_col:
                    table_num = train_125[table_col[0]].iloc[0]
                    print(f"\n  表号: {table_num}")
            
            # 显示前10条记录
            print(f"\n  前10条记录:")
            print(train_125.head(10).to_string(index=False, max_colwidth=15))
    
    # 读取计划线数据（Sheet 2）
    df_plan = pd.read_excel(excel_file, sheet_name=1)
    
    print(f"\n[计划线数据Sheet]")
    
    # 查找车次号=125的记录
    round_col_plan = [c for c in df_plan.columns if '车次' in str(c) or 'round' in str(c).lower()]
    if round_col_plan:
        train_125_plan = df_plan[df_plan[round_col_plan[0]] == 125]
        
        if len(train_125_plan) > 0:
            route_col = [c for c in df_plan.columns if '路径' in str(c) or 'route' in str(c).lower()]
            if route_col:
                route_num = train_125_plan[route_col[0]].iloc[0]
                print(f"  车次125的路径编号: {route_num}")
        else:
            print(f"  计划线数据中没有车次125")
    
except Exception as e:
    print(f"\n[ERROR] 读取Excel失败: {str(e)}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80)
print("[分析]")
print("如果站台码序列超过25个或出现反向站台，说明有问题")
print("="*80)

