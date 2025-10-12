"""
快慢车运行图自动编制程序V3 - 简单测试

用于快速验证程序是否正常工作
"""

import sys
import os

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from express_local_V3.main import ExpressLocalSchedulerV3


def test_basic():
    """基本功能测试"""
    print("=" * 60)
    print("快慢车运行图自动编制程序V3 - 基本功能测试")
    print("=" * 60)
    
    # 测试参数
    rail_info_file = "../data/input_data_new/RailwayInfo/Schedule-cs2.xml"
    user_setting_file = "../data/input_data_new/UserSettingInfoNew/cs2_real_28.xml"
    output_dir = "../data/output_data/results"
    
    print("\n检查输入文件是否存在...")
    
    # 检查文件是否存在
    rail_info_path = os.path.join(project_root, rail_info_file.replace("../", ""))
    user_setting_path = os.path.join(project_root, user_setting_file.replace("../", ""))
    
    if not os.path.exists(rail_info_path):
        print(f"[ERROR] 线路信息文件不存在: {rail_info_path}")
        print("请确保文件路径正确，或者使用你自己的输入文件")
        return False
    
    if not os.path.exists(user_setting_path):
        print(f"[ERROR] 用户设置文件不存在: {user_setting_path}")
        print("请确保文件路径正确，或者使用你自己的输入文件")
        return False
    
    print("[OK] 输入文件检查通过")
    
    try:
        print("\n创建调度器...")
        scheduler = ExpressLocalSchedulerV3(
            rail_info_file=rail_info_file,
            user_setting_file=user_setting_file,
            output_dir=output_dir,
            express_ratio=0.5,
            target_headway=180,
            debug=True
        )
        print("[OK] 调度器创建成功")
        
        print("\n开始运行...")
        result = scheduler.run()
        
        if result["success"]:
            print("\n" + "=" * 60)
            print("[SUCCESS] 测试成功！运行图编制完成！")
            print("=" * 60)
            print(f"输出文件: {result['output_file']}")
            print(f"总耗时: {result['total_time']:.2f}秒")
            
            timetable = result["timetable"]
            print(f"\n运行图统计:")
            print(f"  总列车数: {timetable.total_trains}")
            print(f"  快车数: {timetable.express_trains_count}")
            print(f"  慢车数: {timetable.local_trains_count}")
            print(f"  越行次数: {timetable.total_overtaking_events}")
            
            return True
        else:
            print(f"\n[ERROR] 测试失败: {result['error']}")
            return False
            
    except Exception as e:
        print(f"\n[ERROR] 测试过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_imports():
    """测试导入是否正常"""
    print("=" * 60)
    print("测试模块导入...")
    print("=" * 60)
    
    try:
        print("导入数据模型...")
        from express_local_V3.models.train import ExpressTrain, LocalTrain
        from express_local_V3.models.express_local_timetable import ExpressLocalTimetable
        print("[OK] 数据模型导入成功")
        
        print("导入算法模块...")
        from express_local_V3.algorithms.express_local_generator import ExpressLocalGenerator
        from express_local_V3.algorithms.headway_optimizer import HeadwayOptimizer
        from express_local_V3.algorithms.overtaking_detector import OvertakingDetector
        print("[OK] 算法模块导入成功")
        
        print("导入输出模块...")
        from express_local_V3.output.excel_exporter import ExcelExporter
        print("[OK] 输出模块导入成功")
        
        print("\n" + "=" * 60)
        print("[SUCCESS] 所有模块导入成功！")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] 模块导入失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════╗
║   快慢车运行图自动编制程序V3 - 测试脚本                    ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    # 测试1：导入测试
    print("\n【测试1】模块导入测试")
    imports_ok = test_imports()
    
    if not imports_ok:
        print("\n模块导入失败，请检查代码")
        sys.exit(1)
    
    # 测试2：基本功能测试
    print("\n\n【测试2】基本功能测试")
    print("注意：此测试需要真实的输入文件")
    
    response = input("\n是否运行完整功能测试？(y/n): ")
    
    if response.lower() == 'y':
        basic_ok = test_basic()
        
        if basic_ok:
            print("\n[SUCCESS] 所有测试通过！程序运行正常！")
            sys.exit(0)
        else:
            print("\n[ERROR] 功能测试失败")
            sys.exit(1)
    else:
        print("\n跳过完整功能测试")
        print("如需测试完整功能，请使用: python test_simple.py")

