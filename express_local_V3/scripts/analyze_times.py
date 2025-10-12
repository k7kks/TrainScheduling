"""
分析生成的Excel中的时间数据，找出勾连失败的原因
"""

import pandas as pd
import sys

def analyze_excel():
    """分析Excel文件"""
    excel_file = "../data/output_data/results_express_local_v3/result.xlsx"
    
    try:
        # 读取任务线数据（包含详细的到发时间）
        xl_file = pd.ExcelFile(excel_file)
        
        # 尝试读取任务线数据
        task_sheet = None
        for sn in xl_file.sheet_names:
            if '任务' in sn or 'task' in sn.lower():
                task_sheet = sn
                break
        
        if task_sheet:
            df_task = pd.read_excel(excel_file, sheet_name=task_sheet)
            print(f"\n{'='*80}")
            print(f"任务线数据分析（{task_sheet}）")
            print(f"{'='*80}")
            print(f"总行数: {len(df_task)}")
            print(f"列名: {list(df_task.columns)}")
            
            # 显示前20行
            print(f"\n前20行数据:")
            print(df_task.head(20).to_string())
        
        # 读取计划线数据
        plan_sheet = None
        for sn in xl_file.sheet_names:
            if '计划' in sn or 'plan' in sn.lower():
                plan_sheet = sn
                break
        
        if plan_sheet:
            df_plan = pd.read_excel(excel_file, sheet_name=plan_sheet)
            print(f"\n{'='*80}")
            print(f"计划线数据分析（{plan_sheet}）")
            print(f"{'='*80}")
            print(f"总车次数: {len(df_plan)}")
            
            # 按表号分组
            table_groups = df_plan.groupby('表号')
            
            print(f"\n前20个车次的详细信息:")
            print(f"{'表号':<8} {'车次号':<10} {'路径':<8} {'快车':<6} {'交路':<8} {'开始时间':<12}")
            print("-" * 70)
            
            for idx, row in df_plan.head(20).iterrows():
                table_num = row['表号']
                train_num = row['车次号']
                route_num = row['路径编号']
                is_express = row.get('快车', False)
                xroad = row.get('交路', 0)
                start_time = row.get('开始时间', 0)
                
                print(f"{table_num:<8} {train_num:<10} {route_num:<8} {'是' if is_express else '否':<6} "
                      f"{xroad:<8} {start_time:<12}")
            
            # 分析可能的勾连对
            print(f"\n\n{'='*80}")
            print(f"勾连可能性分析")
            print(f"{'='*80}")
            
            # 按路径分组（1086=上行，1088=下行）
            up_trains = df_plan[df_plan['路径编号'] == 1086].copy()
            down_trains = df_plan[df_plan['路径编号'] == 1088].copy()
            
            print(f"\n上行车次（路径1086）: {len(up_trains)}")
            print(f"下行车次（路径1088）: {len(down_trains)}")
            
            # 从任务线数据中获取实际的到发时间
            if task_sheet and len(df_task) > 0:
                print(f"\n从任务线数据分析实际勾连可能性...")
                
                # 任务线数据每个车次有多行（每站一行）
                # 需要找到每个车次的首末站时间
                
                # 假设任务线有"表号"列
                if '表号' in df_task.columns or '����' in df_task.columns:
                    table_col = '表号' if '表号' in df_task.columns else '����'
                    
                    # 获取每个表号的首末行
                    train_times = {}
                    for table_num in df_plan['表号'].unique()[:10]:  # 只分析前10个
                        train_rows = df_task[df_task[table_col] == table_num]
                        if len(train_rows) > 0:
                            # 获取时间列（可能是"到达时间"、"出发时间"等）
                            time_cols = [c for c in train_rows.columns if '时间' in c]
                            if time_cols:
                                first_row = train_rows.iloc[0]
                                last_row = train_rows.iloc[-1]
                                
                                train_times[table_num] = {
                                    'first_arrival': first_row.get(time_cols[0], 0) if time_cols else 0,
                                    'last_departure': last_row.get(time_cols[-1], 0) if time_cols else 0,
                                }
                    
                    if train_times:
                        print(f"\n前10个车次的时间信息:")
                        print(f"{'表号':<8} {'首站时间':<15} {'末站时间':<15}")
                        print("-" * 50)
                        for table_num, times in sorted(train_times.items())[:10]:
                            print(f"{table_num:<8} {times['first_arrival']:<15} {times['last_departure']:<15}")
            
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    analyze_excel()

