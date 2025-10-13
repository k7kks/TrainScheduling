"""
验证生成的Excel中的站台码是否正确
"""

import sys
import os
import pandas as pd

current_dir = os.path.dirname(os.path.abspath(__file__))
express_local_v3_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(express_local_v3_dir)

# 添加路径
sys.path.insert(0, os.path.join(project_root, 'src'))

from DataReader import DataReader

def verify_platform_codes():
    """验证Excel中的站台码序列"""
    
    print("="*80)
    print("验证Excel中的站台码序列")
    print("="*80)
    
    # 1. 读取Rail Info，获取Path 1086的正确站台码列表
    rail_info_file = os.path.join(project_root, "data/input_data_new/RailwayInfo/Schedule-cs2.xml")
    rail_info = DataReader.read_file(rail_info_file)
    
    if '1086' in rail_info.pathList:
        path_1086 = rail_info.pathList['1086']
        correct_destcodes = path_1086.nodeList
        print(f"\n[Path 1086正确的站台码序列]")
        print(f"  共{len(correct_destcodes)}个站台:")
        print(f"  {', '.join(correct_destcodes)}")
    else:
        print("[ERROR] 找不到Path 1086")
        return
    
    # 2. 读取生成的Excel
    excel_file = os.path.join(project_root, "data/output_data/results_express_local_v3/result.xls")
    
    try:
        # 读取计划车次数sheet
        df_plan = pd.read_excel(excel_file, sheet_name=1)
        
        print(f"\n[Excel文件信息]")
        print(f"  总车次数: {len(df_plan)}")
        
        # 找到路径编号为1086的车次
        route_col = [c for c in df_plan.columns if '路径' in str(c) or 'route' in str(c).lower()]
        if route_col:
            route_col_name = route_col[0]
            train_1086 = df_plan[df_plan[route_col_name] == 1086]
            
            print(f"\n[路径1086的车次]")
            print(f"  数量: {len(train_1086)}")
            
            if len(train_1086) > 0:
                # 显示第一个车次
                first_train = train_1086.iloc[0]
                table_col = [c for c in df_plan.columns if '表号' in str(c) or 'table' in str(c).lower()][0]
                table_num = first_train[table_col]
                
                print(f"\n[检查车次 {table_num}]")
                print(f"  路径编号: {first_train[route_col_name]}")
                
                # 读取运行时间sheet，查找该车次的站台码序列
                df_time = pd.read_excel(excel_file, sheet_name=0)
                
                print(f"\n[运行时间表]")
                print(f"  总行数: {len(df_time)}")
                
                # 查找包含站台111的行
                start_col = [c for c in df_time.columns if '起始' in str(c) or 'start' in str(c).lower()]
                if start_col:
                    start_col_name = start_col[0]
                    rows_111 = df_time[df_time[start_col_name] == '111']
                    
                    print(f"\n[起始站台=111的记录]")
                    print(f"  数量: {len(rows_111)}")
                    
                    if len(rows_111) > 0:
                        # 显示到达站台列
                        arrive_col = [c for c in df_time.columns if '到达' in str(c) or 'arrive' in str(c).lower()]
                        if arrive_col:
                            arrive_col_name = arrive_col[0]
                            arrive_platforms = rows_111[arrive_col_name].tolist()
                            print(f"\n  起始站台111 -> 到达站台: {arrive_platforms[:10]}")
        
        print("\n[站台码序列对比]")
        print(f"  Path 1086应该有的站台: {len(correct_destcodes)}个")
        print(f"  前10个: {', '.join(correct_destcodes[:10])}")
        
    except Exception as e:
        print(f"\n[ERROR] 读取Excel失败: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*80)
    print("[完成]")
    print("="*80)


if __name__ == "__main__":
    verify_platform_codes()

