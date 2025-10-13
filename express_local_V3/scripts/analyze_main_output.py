"""
分析主程序生成的Excel文件
提取慢车的详细时刻，查看越行站的停站时间
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

from DataReader import DataReader
from Solution import Solution
import pickle

def analyze_solution_pkl():
    """分析Solution对象（如果有保存）"""
    
    print("="*80)
    print("分析主程序输出的Solution对象")
    print("="*80)
    
    # 方法：直接从main.py的逻辑中提取
    # 1. 读取输入数据
    rail_info_file = os.path.join(project_root, "data/input_data_new/RailwayInfo/Schedule-cs2.xml")
    user_setting_file = os.path.join(project_root, "data/input_data_new/UserSettingInfoNew/cs2_real_28.xml")
    
    rail_info = DataReader.read_file(rail_info_file)
    
    # 2. 读取生成的Excel，提取RouteSolution
    # 这比较复杂，因为需要解析Excel
    
    # 简化方案：直接运行一次主程序，在convert_timetable_to_solution后打印信息
    
    print("\n[方案] 重新运行主程序并提取RouteSolution信息")
    print("  需要在main.py中添加调试输出")
    
    # 或者，分析已生成的Excel文件
    excel_file = os.path.join(project_root, "data/output_data/results_express_local_v3/result.xls")
    
    if not os.path.exists(excel_file):
        print(f"[ERROR] Excel文件不存在: {excel_file}")
        return
    
    # 使用xlrd读取xls文件
    try:
        import xlrd
        workbook = xlrd.open_workbook(excel_file)
        
        print(f"\n[Excel文件信息]")
        print(f"  文件: {excel_file}")
        print(f"  Sheet数: {workbook.nsheets}")
        
        for i, sheet in enumerate(workbook.sheets()):
            print(f"\n  Sheet {i}: {sheet.name}")
            print(f"    行数: {sheet.nrows}")
            print(f"    列数: {sheet.ncols}")
            
            # 显示前几行
            if sheet.nrows > 0:
                print(f"    前5行数据:")
                for row_idx in range(min(5, sheet.nrows)):
                    row_data = sheet.row_values(row_idx)
                    print(f"      行{row_idx}: {row_data[:10]}")  # 只显示前10列
    
    except ImportError:
        print("\n[提示] 需要安装xlrd库: pip install xlrd")
    except Exception as e:
        print(f"\n[ERROR] 读取Excel失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    analyze_solution_pkl()

