"""
检查生成的Excel文件中的勾连情况

检查表号（table_num）是否正确分配
"""

import pandas as pd
import sys
import os

# 添加src目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

def check_connection(excel_file):
    """
    检查Excel文件中的勾连情况
    
    Args:
        excel_file: Excel文件路径
    """
    try:
        # 先列出所有sheet名称
        xl_file = pd.ExcelFile(excel_file)
        print(f"\nExcel文件中的sheet列表: {xl_file.sheet_names}")
        
        # 读取"计划线数据" sheet（包含表号信息）
        sheet_name = None
        for sn in xl_file.sheet_names:
            if '计划' in sn or 'plan' in sn.lower():
                sheet_name = sn
                break
        
        if sheet_name is None:
            sheet_name = xl_file.sheet_names[1] if len(xl_file.sheet_names) > 1 else xl_file.sheet_names[0]
        
        print(f"读取sheet: {sheet_name}")
        df = pd.read_excel(excel_file, sheet_name=sheet_name)
        
        print("\n========== 勾连检查报告 ==========")
        print(f"\n总车次数: {len(df)}")
        print(f"\n列名: {list(df.columns)}")
        
        # 统计表号分布（尝试不同的列名）
        table_num_col = None
        for col in ['表号', 'table_num', 'Table Num', '车次', 'Train ID']:
            if col in df.columns:
                table_num_col = col
                break
        
        if table_num_col is None:
            print("错误: 无法找到表号列")
            return
        
        print(f"使用列名: {table_num_col}")
        table_nums = df[table_num_col].value_counts().sort_index()
        
        print(f"\n表号数量: {len(table_nums)}")
        print(f"\n表号分布:")
        
        # 找出有多个车次的表号（说明有勾连）
        connected_tables = table_nums[table_nums > 1]
        
        if len(connected_tables) == 0:
            print("  [X] 没有发现勾连！所有车次都有独立的表号。")
        else:
            print(f"  [OK] 发现 {len(connected_tables)} 组勾连：")
            for table_num, count in connected_tables.items():
                print(f"    表号 {table_num}: {count} 个车次勾连在一起")
        
        # 显示前10个车次的详细信息
        print(f"\n前10个车次的详细信息：")
        print("=" * 60)
        for idx, row in df.head(10).iterrows():
            try:
                train_id = row['车次号'] if '车次号' in row else row.get('车次', idx)
                table_num = row['表号']
                route_num = row['路径编号']
                start_time = row.get('开始时间', 'N/A')
                is_express = row.get('快车', False)
                
                print(f"  [{idx+1}] 车次号:{train_id}, 表号:{table_num}, 路径:{route_num}, 快车:{'是' if is_express else '否'}, 开始时间:{start_time}")
            except Exception as e:
                print(f"  [{idx+1}] 读取错误: {e}")
        
        # 检查快慢车分组
        if '快车标志' in df.columns or 'is_express' in df.columns:
            print(f"\n快慢车勾连情况:")
            express_flag_col = '快车标志' if '快车标志' in df.columns else 'is_express'
            
            express_trains = df[df[express_flag_col] == True]
            local_trains = df[df[express_flag_col] == False]
            
            print(f"  快车数量: {len(express_trains)}")
            print(f"  慢车数量: {len(local_trains)}")
            
            # 检查是否有快车和慢车共用表号（不应该发生）
            express_table_nums = set(express_trains['表号'].unique())
            local_table_nums = set(local_trains['表号'].unique())
            mixed_table_nums = express_table_nums & local_table_nums
            
            if mixed_table_nums:
                print(f"  [WARNING] 警告: {len(mixed_table_nums)} 个表号同时包含快车和慢车！")
                for tn in list(mixed_table_nums)[:5]:
                    print(f"    表号 {tn}")
            else:
                print(f"  [OK] 快车和慢车分开勾连（正确）")
        
        print("\n" + "=" * 60)
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    excel_file = "../data/output_data/results_express_local_v3/result.xlsx"
    check_connection(excel_file)

