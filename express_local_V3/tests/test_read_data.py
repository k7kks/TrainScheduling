"""
测试数据读取功能
"""

import sys
import os

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
src_dir = os.path.join(project_root, 'src')

if project_root not in sys.path:
    sys.path.insert(0, project_root)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

print("=" * 60)
print("测试数据读取功能")
print("=" * 60)

try:
    print("\n1. 导入DataReader...")
    from DataReader import DataReader
    print("   [OK] DataReader导入成功")
    
    print("\n2. 检查输入文件...")
    rail_info_file = "../data/input_data_new/RailwayInfo/Schedule-cs2.xml"
    user_setting_file = "../data/input_data_new/UserSettingInfoNew/cs2_real_28.xml"
    
    rail_info_path = os.path.join(project_root, rail_info_file.replace("../", ""))
    user_setting_path = os.path.join(project_root, user_setting_file.replace("../", ""))
    
    if not os.path.exists(rail_info_path):
        print(f"   [ERROR] 文件不存在: {rail_info_path}")
        sys.exit(1)
    
    if not os.path.exists(user_setting_path):
        print(f"   [ERROR] 文件不存在: {user_setting_path}")
        sys.exit(1)
    
    print(f"   [OK] 输入文件存在")
    print(f"        线路信息: {rail_info_path}")
    print(f"        用户设置: {user_setting_path}")
    
    print("\n3. 读取线路信息...")
    rail_info = DataReader.read_file(rail_info_file)
    print(f"   [OK] 线路信息读取成功")
    print(f"        车站数: {len(rail_info.stationList)}")
    print(f"        路径数: {len(rail_info.pathList)}")
    
    print("\n4. 读取用户设置...")
    user_setting = DataReader.read_setting_file(user_setting_file)
    print(f"   [OK] 用户设置读取成功")
    print(f"        峰期数: {len(user_setting.peaks)}")
    print(f"        首班车: {user_setting.first_car}秒")
    print(f"        末班车: {user_setting.last_car}秒")
    
    print("\n" + "=" * 60)
    print("[SUCCESS] 数据读取测试通过！")
    print("=" * 60)
    
    sys.exit(0)
    
except Exception as e:
    print(f"\n[ERROR] 测试失败: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

