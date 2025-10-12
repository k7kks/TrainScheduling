"""
快慢车运行图自动编制程序V3 - 示例代码

本文件展示了如何使用Express Local V3程序
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from express_local_V3 import ExpressLocalSchedulerV3


def example_basic_usage():
    """示例1：基本用法"""
    print("=" * 60)
    print("示例1：基本用法")
    print("=" * 60)
    
    # 创建调度器（使用默认参数）
    scheduler = ExpressLocalSchedulerV3(
        rail_info_file="../data/input_data_new/RailwayInfo/Schedule-cs2.xml",
        user_setting_file="../data/input_data_new/UserSettingInfoNew/cs2_real_28.xml",
        output_dir="../data/output_data/results",
        debug=False
    )
    
    # 运行程序
    result = scheduler.run()
    
    # 检查结果
    if result["success"]:
        print("\n✓ 运行图编制成功！")
        print(f"  输出文件: {result['output_file']}")
    else:
        print(f"\n✗ 运行图编制失败: {result['error']}")


def example_custom_ratio():
    """示例2：自定义快慢车比例"""
    print("\n" + "=" * 60)
    print("示例2：自定义快慢车比例（快车60%）")
    print("=" * 60)
    
    scheduler = ExpressLocalSchedulerV3(
        rail_info_file="../data/input_data_new/RailwayInfo/Schedule-cs2.xml",
        user_setting_file="../data/input_data_new/UserSettingInfoNew/cs2_real_28.xml",
        output_dir="../data/output_data/results",
        express_ratio=0.6,      # 快车占60%
        target_headway=180,     # 目标发车间隔3分钟
        debug=False
    )
    
    result = scheduler.run()
    
    if result["success"]:
        timetable = result["timetable"]
        print(f"\n✓ 生成的运行图:")
        print(f"  总列车数: {timetable.total_trains}")
        print(f"  快车数: {timetable.express_trains_count}")
        print(f"  慢车数: {timetable.local_trains_count}")
        print(f"  实际快车比例: {timetable.express_trains_count / timetable.total_trains:.1%}")


def example_analyze_timetable():
    """示例3：生成并分析运行图"""
    print("\n" + "=" * 60)
    print("示例3：生成并分析运行图")
    print("=" * 60)
    
    scheduler = ExpressLocalSchedulerV3(
        rail_info_file="../data/input_data_new/RailwayInfo/Schedule-cs2.xml",
        user_setting_file="../data/input_data_new/UserSettingInfoNew/cs2_real_28.xml",
        output_dir="../data/output_data/results",
        express_ratio=0.5,
        target_headway=180,
        debug=False
    )
    
    result = scheduler.run()
    
    if result["success"]:
        timetable = result["timetable"]
        
        print("\n----- 运行图统计 -----")
        
        # 列车统计
        print(f"\n【列车统计】")
        print(f"  总列车数: {timetable.total_trains}")
        print(f"  快车数: {timetable.express_trains_count}")
        print(f"  慢车数: {timetable.local_trains_count}")
        
        # 发车间隔统计
        print(f"\n【发车间隔】")
        avg_headway = timetable.calculate_average_headway("上行")
        var_headway = timetable.calculate_headway_variance("上行")
        print(f"  平均发车间隔: {avg_headway:.1f}秒 ({avg_headway/60:.1f}分钟)")
        print(f"  发车间隔方差: {var_headway:.1f}秒²")
        
        # 计算变异系数（CV）
        if avg_headway > 0:
            cv = (var_headway ** 0.5) / avg_headway
            print(f"  变异系数: {cv:.3f}")
        
        # 越行统计
        print(f"\n【越行事件】")
        print(f"  越行次数: {timetable.total_overtaking_events}")
        
        if timetable.total_overtaking_events > 0:
            overtaken_locals = timetable.get_overtaken_local_trains()
            print(f"  被越行慢车数: {len(overtaken_locals)}")
            
            # 统计可避免的越行
            avoidable = [e for e in timetable.overtaking_events if e.is_avoidable]
            print(f"  可避免越行: {len(avoidable)}")
            
            # 显示前3个越行事件
            print(f"\n  前3个越行事件:")
            for i, event in enumerate(timetable.overtaking_events[:3], 1):
                print(f"    {i}. {event.overtaking_train_id} 越行 {event.overtaken_train_id} @ {event.overtaking_station_name}")
                print(f"       延误: {event.total_delay}秒, 建议: {event.get_optimization_suggestion()}")
        
        # 发车时刻表（前5列车）
        print(f"\n【前5列车发车时刻】")
        all_trains = timetable.express_trains + timetable.local_trains
        all_trains.sort(key=lambda t: t.departure_time if t.departure_time else 0)
        
        for i, train in enumerate(all_trains[:5], 1):
            dep_time = train.departure_time if train.departure_time else 0
            hours = dep_time // 3600
            minutes = (dep_time % 3600) // 60
            seconds = dep_time % 60
            print(f"    {i}. {train.train_name}: {hours:02d}:{minutes:02d}:{seconds:02d}")


def example_compare_different_ratios():
    """示例4：比较不同快慢车比例的效果"""
    print("\n" + "=" * 60)
    print("示例4：比较不同快慢车比例")
    print("=" * 60)
    
    ratios = [0.3, 0.5, 0.7]
    results = []
    
    for ratio in ratios:
        print(f"\n--- 测试快车比例 {ratio:.0%} ---")
        
        scheduler = ExpressLocalSchedulerV3(
            rail_info_file="../data/input_data_new/RailwayInfo/Schedule-cs2.xml",
            user_setting_file="../data/input_data_new/UserSettingInfoNew/cs2_real_28.xml",
            output_dir="../data/output_data/results",
            express_ratio=ratio,
            target_headway=180,
            debug=False
        )
        
        result = scheduler.run()
        
        if result["success"]:
            timetable = result["timetable"]
            avg_headway = timetable.calculate_average_headway("上行")
            var_headway = timetable.calculate_headway_variance("上行")
            
            results.append({
                "ratio": ratio,
                "total_trains": timetable.total_trains,
                "express_count": timetable.express_trains_count,
                "local_count": timetable.local_trains_count,
                "avg_headway": avg_headway,
                "var_headway": var_headway,
                "overtaking_count": timetable.total_overtaking_events
            })
    
    # 显示比较结果
    print("\n" + "=" * 60)
    print("比较结果:")
    print("=" * 60)
    print(f"{'快车比例':<10} {'总车数':<8} {'快车':<6} {'慢车':<6} {'平均间隔':<12} {'间隔方差':<12} {'越行次数':<8}")
    print("-" * 60)
    
    for r in results:
        print(f"{r['ratio']:<10.0%} {r['total_trains']:<8} {r['express_count']:<6} {r['local_count']:<6} "
              f"{r['avg_headway']/60:<12.1f} {r['var_headway']:<12.1f} {r['overtaking_count']:<8}")


def main():
    """主函数"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║   快慢车运行图自动编制程序V3 - 示例代码                    ║
║                                                           ║
║   本程序演示了如何使用Express Local V3进行                ║
║   快慢车运行图的自动编制                                   ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    try:
        # 示例1：基本用法
        example_basic_usage()
        
        # 示例2：自定义快慢车比例
        # example_custom_ratio()
        
        # 示例3：生成并分析运行图
        # example_analyze_timetable()
        
        # 示例4：比较不同快慢车比例
        # example_compare_different_ratios()
        
        print("\n" + "=" * 60)
        print("示例运行完成！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n错误: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

