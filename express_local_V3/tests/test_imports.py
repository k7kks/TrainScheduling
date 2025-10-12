"""
快速测试所有模块是否能正常导入
"""

import sys
import os

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

print("=" * 60)
print("快慢车运行图自动编制程序V3 - 模块导入测试")
print("=" * 60)

try:
    print("\n1. 导入数据模型...")
    from express_local_V3.models.train import ExpressTrain, LocalTrain, TrainType
    from express_local_V3.models.timetable_entry import TimetableEntry
    from express_local_V3.models.overtaking_event import OvertakingEvent
    from express_local_V3.models.express_local_timetable import ExpressLocalTimetable
    print("   [OK] 数据模型导入成功")
    
    print("\n2. 导入算法模块...")
    from express_local_V3.algorithms.express_local_generator import ExpressLocalGenerator
    from express_local_V3.algorithms.headway_optimizer import HeadwayOptimizer
    from express_local_V3.algorithms.overtaking_detector import OvertakingDetector
    from express_local_V3.algorithms.timetable_builder import TimetableBuilder
    print("   [OK] 算法模块导入成功")
    
    print("\n3. 导入输出模块...")
    from express_local_V3.output.excel_exporter import ExcelExporter
    print("   [OK] 输出模块导入成功")
    
    print("\n4. 导入主程序...")
    from express_local_V3.main import ExpressLocalSchedulerV3
    print("   [OK] 主程序导入成功")
    
    print("\n" + "=" * 60)
    print("[SUCCESS] 所有模块导入测试通过！")
    print("=" * 60)
    print("\n程序已准备就绪，可以正常使用！")
    print("\n使用方法：")
    print("  python run.py                    # 使用默认配置运行")
    print("  python run.py --help             # 查看所有参数")
    print("  python run.py --express_ratio 0.6 # 自定义快车比例")
    
    sys.exit(0)
    
except Exception as e:
    print(f"\n[ERROR] 模块导入失败: {str(e)}")
    import traceback
    traceback.print_exc()
    print("\n请检查是否安装了所有依赖库:")
    print("  pip install -r requirements.txt")
    sys.exit(1)

