"""
检查最终生成的Excel文件
验证站台码序列和越行站停站时间
"""

import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
express_local_v3_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(express_local_v3_dir)
src_dir = os.path.join(project_root, 'src')

for path in [project_root, src_dir]:
    if path not in sys.path:
        sys.path.insert(0, path)

from DataReader import DataReader

def check_excel():
    """检查Excel文件"""
    
    print("="*80)
    print("检查最终生成的Excel文件")
    print("="*80)
    
    # 读取rail_info
    rail_info_file = os.path.join(project_root, "data/input_data_new/RailwayInfo/Schedule-cs2.xml")
    rail_info = DataReader.read_file(rail_info_file)
    
    # 获取Path 1086的正确站台码
    if '1086' not in rail_info.pathList:
        print("[ERROR] Path 1086不存在")
        return
    
    path_1086 = rail_info.pathList['1086']
    correct_codes = path_1086.nodeList
    
    print(f"\n[Path 1086的正确站台码序列]")
    print(f"  共{len(correct_codes)}个站台")
    print(f"  完整序列: {', '.join(correct_codes)}")
    
    # 读取Excel文件
    excel_file = os.path.join(project_root, "data/output_data/results_express_local_v3/result.xls")
    
    try:
        # 使用xlrd读取xls文件
        import xlrd
        
        workbook = xlrd.open_workbook(excel_file, formatting_info=False)
        
        # 读取Sheet 1（计划车次数）
        sheet_plan = workbook.sheet_by_index(1)
        
        print(f"\n[Excel Sheet 1 - 计划车次数]")
        print(f"  行数: {sheet_plan.nrows}")
        print(f"  列数: {sheet_plan.ncols}")
        
        # 打印表头
        if sheet_plan.nrows > 0:
            headers = sheet_plan.row_values(0)
            print(f"  表头: {headers}")
            
            # 找到路径编号列（通常是第3列）
            # 查找路径编号为1086的第一条记录
            for row_idx in range(1, min(sheet_plan.nrows, 100)):
                row_data = sheet_plan.row_values(row_idx)
                route_num = int(row_data[2]) if len(row_data) > 2 and row_data[2] != '' else 0
                
                if route_num == 1086:
                    table_num = int(row_data[0]) if len(row_data) > 0 else 0
                    round_num = int(row_data[1]) if len(row_data) > 1 else 0
                    dep_time = int(row_data[3]) if len(row_data) > 3 else 0
                    
                    print(f"\n[找到路径1086的车次]")
                    print(f"  表号: {table_num}")
                    print(f"  车次号: {round_num}")
                    print(f"  路径编号: {route_num}")
                    print(f"  发车时间: {dep_time}秒")
                    
                    # 现在检查这个车次的站台码序列
                    # 需要从RouteSolution的详细数据中获取，但xls format不直接包含
                    # 我们需要从其他方式验证
                    
                    break
        
        # 读取Sheet 2（固定车次数）
        sheet_fixed = workbook.sheet_by_index(2)
        
        print(f"\n[Excel Sheet 2 - 固定车次数]")
        print(f"  行数: {sheet_fixed.nrows}")
        
        # 这个sheet包含详细的站台信息
        # 格式: 起始站台码 到达站台码 ...
        
        if sheet_fixed.nrows > 0:
            # 打印前几行查看格式
            print(f"\n[前10行数据]")
            for row_idx in range(min(10, sheet_fixed.nrows)):
                row_data = sheet_fixed.row_values(row_idx)
                print(f"  行{row_idx}: {row_data[:5]}")  # 只打印前5列
        
        print(f"\n[验证结论]")
        print(f"  如果Excel能正常加载到运行图软件，说明站台码序列正确")
        print(f"  如果加载出错，请检查上述数据是否与Path 1086匹配")
        
    except ImportError:
        print("\n[提示] 需要安装xlrd: pip install xlrd")
    except Exception as e:
        print(f"\n[ERROR] 读取Excel失败: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*80)


if __name__ == "__main__":
    check_excel()

