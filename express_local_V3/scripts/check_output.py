"""检查输出Excel文件"""

import pandas as pd
import sys

try:
    # 读取Excel文件
    file_path = '../data/output_data/results_express_local_v3/result.xls'
    
    print(f"正在读取: {file_path}")
    
    # 先获取所有sheet名称
    excel_file = pd.ExcelFile(file_path)
    print(f"\nSheet names: {excel_file.sheet_names}")
    
    # 读取"计划数据表"sheet（第2个sheet）
    sheet_name = excel_file.sheet_names[1] if len(excel_file.sheet_names) > 1 else excel_file.sheet_names[0]
    print(f"\n正在读取sheet: {sheet_name}")
    df = pd.read_excel(file_path, sheet_name=sheet_name, dtype=str)
    
    print("\n前10行数据:")
    print(df.head(10))
    
    print("\n列名:")
    print(df.columns.tolist())
    
    # 检查路径编号列
    if '路径编号' in df.columns:
        print("\n路径编号统计:")
        print(df['路径编号'].value_counts())
        
        # 检查是否有0
        zero_count = (df['路径编号'] == '0').sum()
        if zero_count > 0:
            print(f"\n[WARNING] 发现{zero_count}个路径编号为0的记录！")
        else:
            print(f"\n[OK] 路径编号正常，无0值")
    
    # 检查快车标志位
    if '是否时刻站次跳跃车次' in df.columns:
        print("\n快车标志统计:")
        print(df['是否时刻站次跳跃车次'].value_counts())
    
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

