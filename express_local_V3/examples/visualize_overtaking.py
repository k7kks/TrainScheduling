"""
越行现象可视化脚本

使用matplotlib生成运行图图表，直观展示快车越行慢车的现象
"""

import sys
import os

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
express_local_v3_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(express_local_v3_dir)

for path in [project_root, express_local_v3_dir]:
    if path not in sys.path:
        sys.path.insert(0, path)

from overtaking_demo import OvertakingDemoGenerator, TrainSchedule
from typing import List
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.font_manager import FontProperties


def visualize_overtaking(express_trains: List[TrainSchedule],
                        local_trains: List[TrainSchedule],
                        output_file: str = "../data/output/overtaking_diagram.png"):
    """
    可视化越行现象
    
    生成运行图图表：
    - X轴：时间（分钟）
    - Y轴：车站（从起点到终点）
    - 快车线：红色实线
    - 慢车线：蓝色实线
    - 越行点：绿色圆圈标注
    
    Args:
        express_trains: 快车列表
        local_trains: 慢车列表
        output_file: 输出文件路径
    """
    try:
        # 设置中文字体（尝试常见的中文字体）
        try:
            # Windows系统
            plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'SimSun']
        except:
            # Linux系统
            plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'DejaVu Sans']
        
        plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
        
        # 创建图表
        fig, ax = plt.subplots(figsize=(16, 10))
        
        # 获取车站列表
        if express_trains:
            stations = [stop.station_name for stop in express_trains[0].stops]
        elif local_trains:
            stations = [stop.station_name for stop in local_trains[0].stops]
        else:
            print("[Error] No trains to visualize")
            return
        
        station_count = len(stations)
        
        # 绘制快车运行线
        for train in express_trains:
            times = []
            positions = []
            
            for stop in train.stops:
                if not stop.is_skip:
                    # 到站时间
                    times.append(stop.arrival_time / 60)  # 转换为分钟
                    positions.append(stop.station_index)
                    
                    # 离站时间（如果停站）
                    if stop.dwell_time > 0:
                        times.append(stop.departure_time / 60)
                        positions.append(stop.station_index)
            
            # 绘制运行线
            ax.plot(times, positions, 'r-', linewidth=2, label=train.train_name if train == express_trains[0] else "")
        
        # 绘制慢车运行线
        for train in local_trains:
            times = []
            positions = []
            overtaking_times = []
            overtaking_positions = []
            
            for stop in train.stops:
                # 到站时间
                times.append(stop.arrival_time / 60)
                positions.append(stop.station_index)
                
                # 离站时间
                times.append(stop.departure_time / 60)
                positions.append(stop.station_index)
                
                # 标记越行站
                if stop.is_overtaking_station:
                    overtaking_times.append((stop.arrival_time + stop.departure_time) / 2 / 60)
                    overtaking_positions.append(stop.station_index)
            
            # 绘制运行线
            ax.plot(times, positions, 'b-', linewidth=2, label=train.train_name if train == local_trains[0] else "")
            
            # 绘制越行点
            if overtaking_times:
                ax.scatter(overtaking_times, overtaking_positions, 
                          c='green', s=200, marker='o', zorder=5,
                          label='Overtaking Point' if train == local_trains[0] else "")
        
        # 设置坐标轴
        ax.set_xlabel('Time (minutes from 02:00)', fontsize=12, fontweight='bold')
        ax.set_ylabel('Station', fontsize=12, fontweight='bold')
        ax.set_title('Express-Local Train Timetable with Overtaking', fontsize=14, fontweight='bold')
        
        # 设置Y轴刻度（车站）
        ax.set_yticks(range(station_count))
        ax.set_yticklabels(stations)
        ax.set_ylim(-0.5, station_count - 0.5)
        
        # 设置X轴刻度（时间，每5分钟一个刻度）
        min_time = min(train.departure_time for train in express_trains + local_trains) / 60
        max_time = max(stop.departure_time / 60 for train in express_trains + local_trains for stop in train.stops)
        
        x_ticks = range(int(min_time), int(max_time) + 5, 5)
        ax.set_xticks(x_ticks)
        ax.set_xlim(min_time - 2, max_time + 2)
        
        # 添加网格
        ax.grid(True, linestyle='--', alpha=0.6)
        
        # 添加图例
        # 创建自定义图例
        express_patch = mpatches.Patch(color='red', label='Express Train')
        local_patch = mpatches.Patch(color='blue', label='Local Train')
        overtaking_patch = mpatches.Patch(color='green', label='Overtaking Point')
        
        ax.legend(handles=[express_patch, local_patch, overtaking_patch], 
                 loc='upper left', fontsize=10)
        
        # 调整布局
        plt.tight_layout()
        
        # 保存图片
        from pathlib import Path
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"\n[Success] Overtaking diagram saved: {output_file}")
        
        # 显示图表（可选）
        # plt.show()
        
    except Exception as e:
        print(f"\n[Error] Visualization failed: {str(e)}")
        import traceback
        traceback.print_exc()


def main():
    """主函数"""
    print("="*100)
    print("Overtaking Visualization Script")
    print("="*100)
    
    # 创建生成器
    generator = OvertakingDemoGenerator()
    
    # 生成快慢车运行图
    print("\n[Start] Generating timetable...")
    express_trains, local_trains = generator.generate_demo_timetable(
        express_count=3,
        local_count=4,
        start_time=7200
    )
    
    # 可视化
    print("\n[Start] Visualizing overtaking...")
    visualize_overtaking(express_trains, local_trains)
    
    print("\n" + "="*100)
    print("[Done] Visualization complete!")
    print("="*100)


if __name__ == "__main__":
    main()

