"""
检查Excel文件中的越行效果

读取生成的Excel文件，查看慢车在越行站的停站时间
"""

import pandas as pd
import sys
import os

def check_overtaking(excel_file):
    """
    检查Excel文件中的越行效果
    
    Args:
        excel_file: Excel文件路径
    """
    print("="*80)
    print("检查Excel文件中的越行效果")
    print("="*80)
    
    try:
        # 读取所有sheet
        xl = pd.ExcelFile(excel_file)
        print(f"\n[文件信息] {excel_file}")
        print(f"Sheet页数: {len(xl.sheet_names)}")
        print(f"Sheet名称: {xl.sheet_names}")
        
        # 尝试读取第2个sheet（计划车次数）
        print("\n[读取] 计划车次数...")
        df_plan = pd.read_excel(excel_file, sheet_name=1)
        
        print(f"\n[数据概要]")
        print(f"  总车次数: {len(df_plan)}")
        print(f"  列名: {list(df_plan.columns)}")
        
        # 检查是否有快车标志列
        if '快车' in df_plan.columns or 'is_express' in str(df_plan.columns):
            express_col = [c for c in df_plan.columns if '快车' in str(c) or 'express' in str(c).lower()][0]
            express_count = df_plan[express_col].sum() if df_plan[express_col].dtype in ['int64', 'float64'] else 0
            print(f"  快车数量: {express_count}")
            print(f"  慢车数量: {len(df_plan) - express_count}")
        
        # 显示前10个车次
        print(f"\n[前10个车次]")
        print(df_plan.head(10).to_string(index=False))
        
        # 尝试读取运行时间sheet
        print("\n[读取] 运行时间表...")
        df_time = pd.read_excel(excel_file, sheet_name=0)
        
        print(f"\n[运行时间表概要]")
        print(f"  行数: {len(df_time)}")
        print(f"  列数: {len(df_time.columns)}")
        print(f"  列名示例: {list(df_time.columns)[:5]}")
        
        # 查找停站时间异常大的记录（可能是越行站）
        print("\n[查找越行站] 检测停站时间≥200秒的站点...")
        
        # 在df_time中查找运行时间异常大的值
        # 通常运行时间在30-120秒之间，如果超过200秒，可能是越行站
        
        overtaking_found = False
        for col in df_time.columns:
            if col.startswith('起始') or col.startswith('到达'):
                continue
            
            # 检查该列是否有大于200的值
            values = df_time[col].dropna()
            if len(values) > 0:
                max_val = values.max()
                if max_val > 200:
                    rows = df_time[df_time[col] > 200]
                    if len(rows) > 0:
                        print(f"\n  在列 '{col}' 中发现 {len(rows)} 个异常大的时间值（可能是越行站）")
                        print(f"    最大值: {max_val}秒")
                        overtaking_found = True
                        # 只显示第一个
                        break
        
        if not overtaking_found:
            print("  未在运行时间表中发现明显的越行特征")
            print("  注意：越行效果可能体现在详细的列车时刻表中，而不是汇总表中")
        
    except Exception as e:
        print(f"\n[ERROR] 读取Excel文件失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    excel_file = "data/output_data/results_express_local_v3/result.xlsx"
    
    # 检查文件是否存在
    if not os.path.exists(excel_file):
        print(f"[ERROR] 文件不存在: {excel_file}")
        sys.exit(1)
    
    check_overtaking(excel_file)
    
    print("\n" + "="*80)
    print("[完成] 检查完成")
    print("="*80)
    print("\n[说明]")
    print("  如果在运行时间表中发现异常大的时间值（≥200秒），说明越行处理生效了。")
    print("  如果没有发现，可能是因为：")
    print("    1. 越行信息存储在其他格式的数据中")
    print("    2. 需要用运行图显示软件加载Excel才能看到效果")
    print("    3. 停站时间可能体现在详细时刻表中，而不是汇总表")

