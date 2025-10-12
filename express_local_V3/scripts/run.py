"""
快速启动脚本 - express_local_V3

直接运行main.py的便捷脚本
使用默认参数快速测试程序
"""

import subprocess
import sys
import os

def main():
    """运行express_local_V3主程序"""
    
    # 获取当前脚本所在目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # main.py在上一级目录（express_local_V3根目录）
    express_local_v3_dir = os.path.dirname(current_dir)
    main_py = os.path.join(express_local_v3_dir, "main.py")
    
    # 数据文件在项目根目录（express_local_V3的上一级）
    project_root = os.path.dirname(express_local_v3_dir)
    
    # 构建命令
    cmd = [
        sys.executable,  # Python解释器路径
        main_py,
        "--rail_info", os.path.join(project_root, "data/input_data_new/RailwayInfo/Schedule-cs2.xml"),
        "--user_setting", os.path.join(project_root, "data/input_data_new/UserSettingInfoNew/cs2_real_28.xml"),
        "--output", os.path.join(project_root, "data/output_data/results_express_local_v3"),
        "--express_ratio", "0.5",
        "--target_headway", "180",
        "--speed_level", "1",
        "--dwell_time", "30"
    ]
    
    print("="*60)
    print("运行 express_local_V3...")
    print("="*60)
    print(f"命令: {' '.join(cmd)}")
    print()
    
    # 运行命令
    try:
        result = subprocess.run(cmd, check=True)
        sys.exit(result.returncode)
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] 程序执行失败，退出代码: {e.returncode}")
        sys.exit(e.returncode)
    except Exception as e:
        print(f"\n[ERROR] 执行过程中发生错误: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
