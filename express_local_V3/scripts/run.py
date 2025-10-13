"""
快速启动脚本 - express_local_V3（支持快车越行慢车）

一键生成带越行现象的快慢车运行图Excel文件
生成的Excel可直接用运行图显示软件加载

越行功能说明：
- 程序会自动检测快车是否会追上慢车
- 如果会追上，慢车会在越行站停留≥4分钟（240秒）
- 后续站点时刻自动顺延
- Excel中可以看到慢车在某些站的停站时间明显增加（越行站）
"""

import subprocess
import sys
import os

def main():
    """运行express_local_V3主程序（启用越行处理）"""
    
    # 获取当前脚本所在目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # main.py在上一级目录（express_local_V3根目录）
    express_local_v3_dir = os.path.dirname(current_dir)
    main_py = os.path.join(express_local_v3_dir, "main.py")
    
    # 数据文件在项目根目录（express_local_V3的上一级）
    project_root = os.path.dirname(express_local_v3_dir)
    
    # 构建命令
    # 注意：快车比例0.4，目标间隔180秒，这样的参数组合更容易产生越行
    cmd = [
        sys.executable,  # Python解释器路径
        main_py,
        "--rail_info", os.path.join(project_root, "data/input_data_new/RailwayInfo/Schedule-cs2.xml"),
        "--user_setting", os.path.join(project_root, "data/input_data_new/UserSettingInfoNew/cs2_real_28.xml"),
        "--output", os.path.join(project_root, "data/output_data/results_express_local_v3"),
        "--express_ratio", "0.4",      # 快车40%，慢车60%（调整后更容易产生越行）
        "--target_headway", "180",     # 目标发车间隔3分钟
        "--speed_level", "1",
        "--dwell_time", "30"           # 正常停站30秒（越行站会自动增加到≥240秒）
    ]
    
    print("="*80)
    print("快慢车运行图自动编制程序V3 - 支持快车越行慢车")
    print("="*80)
    print("\n[参数设置]")
    print(f"  快车比例: 40%（容易产生越行）")
    print(f"  慢车比例: 60%")
    print(f"  目标发车间隔: 180秒（3分钟）")
    print(f"  正常停站时间: 30秒")
    print(f"  越行站停站时间: >=240秒（4分钟）自动调整")
    print("\n[越行处理]")
    print(f"  [OK] 自动检测快车是否会追上慢车")
    print(f"  [OK] 慢车在越行站停留>=4分钟等待快车通过")
    print(f"  [OK] 满足到通间隔>=120秒、通发间隔>=120秒")
    print(f"  [OK] 后续站点时刻自动顺延")
    print("\n[输出文件]")
    print(f"  data/output_data/results_express_local_v3/result.xlsx")
    print(f"  可用运行图显示软件加载，查看越行现象")
    print("\n" + "="*80)
    print(f"[执行命令] {' '.join(cmd[:3])} ...")
    print("="*80 + "\n")
    
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
