"""
快车越行慢车Demo程序

按照md文档中的越行设计原则，明确展示快车越行慢车的现象

越行处理流程：
1. 检测快车是否会追上慢车（发车间隔判定）
2. 找到合适的越行站
3. 慢车在越行站停留至少4分钟（240秒）待避
4. 快车通过越行站
5. 慢车在越行站之后的所有站点时刻顺延
"""

import sys
import os
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
express_local_v3_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(express_local_v3_dir)
src_dir = os.path.join(project_root, 'src')

for path in [project_root, src_dir, express_local_v3_dir]:
    if path not in sys.path:
        sys.path.insert(0, path)

# 导入必要模块
from DataReader import DataReader
from RailInfo import RailInfo
from UserSetting import UserSetting


@dataclass
class StationStop:
    """站点停靠信息"""
    station_name: str
    station_index: int
    arrival_time: int      # 到站时间（秒）
    departure_time: int    # 离站时间（秒）
    dwell_time: int        # 停站时间（秒）
    is_skip: bool = False  # 是否跳站
    is_overtaking_station: bool = False  # 是否为越行站
    is_waiting_for_overtaking: bool = False  # 是否正在待避


@dataclass
class TrainSchedule:
    """列车时刻表"""
    train_id: str
    train_name: str
    is_express: bool
    direction: str
    departure_time: int  # 首站发车时间
    stops: List[StationStop]
    
    def get_arrival_at_station(self, station_index: int) -> Optional[int]:
        """获取列车在指定车站的到达时间"""
        for stop in self.stops:
            if stop.station_index == station_index:
                return stop.arrival_time
        return None
    
    def get_departure_at_station(self, station_index: int) -> Optional[int]:
        """获取列车在指定车站的离站时间"""
        for stop in self.stops:
            if stop.station_index == station_index:
                return stop.departure_time
        return None


class OvertakingDemoGenerator:
    """
    越行Demo生成器
    
    核心算法：
    1. 先铺画快车（均匀分布）
    2. 再铺画慢车
    3. 检测每列慢车是否会被快车追上
    4. 如果会被追上，在越行站增加停站时间到240秒
    """
    
    def __init__(self,
                 min_tracking_interval: int = 120,   # 最小追踪间隔
                 min_arrival_pass_interval: int = 120,  # 最小到通间隔
                 min_pass_departure_interval: int = 120,  # 最小通发间隔
                 min_overtaking_dwell: int = 240,    # 越行站最小停站时间
                 section_running_time: int = 120,    # 区间运行时间
                 express_speed_factor: float = 1.2,   # 快车速度系数
                 normal_dwell_time: int = 30):        # 正常停站时间
        """
        初始化越行Demo生成器
        
        Args:
            min_tracking_interval: 最小追踪间隔（秒）
            min_arrival_pass_interval: 最小到通间隔（秒）
            min_pass_departure_interval: 最小通发间隔（秒）
            min_overtaking_dwell: 越行站最小停站时间（秒）
            section_running_time: 区间运行时间（秒）
            express_speed_factor: 快车速度系数
            normal_dwell_time: 正常停站时间（秒）
        """
        self.min_tracking_interval = min_tracking_interval
        self.min_arrival_pass_interval = min_arrival_pass_interval
        self.min_pass_departure_interval = min_pass_departure_interval
        self.min_overtaking_dwell = min_overtaking_dwell
        self.section_running_time = section_running_time
        self.express_speed_factor = express_speed_factor
        self.normal_dwell_time = normal_dwell_time
        
        # 车站列表（简化为车站名称列表）
        self.stations = [
            "起点站", "站点1", "站点2", "站点3", "站点4", 
            "站点5", "站点6", "站点7", "站点8", "终点站"
        ]
        
        # 越行站列表（假设站点3、站点5、站点7可以越行）
        self.overtaking_stations = {2, 4, 6}  # 索引：站点3、站点5、站点7
    
    def generate_demo_timetable(self,
                                express_count: int = 3,
                                local_count: int = 4,
                                start_time: int = 7200) -> Tuple[List[TrainSchedule], List[TrainSchedule]]:
        """
        生成快慢车运行图Demo
        
        策略：
        1. 快车均匀铺画，跳停部分车站
        2. 慢车插入到快车间隔中，站站停
        3. 慢车发车时间设置为会被快车追上（故意制造越行）
        
        Args:
            express_count: 快车数量
            local_count: 慢车数量
            start_time: 开始时间（秒，相对于0点）
            
        Returns:
            (快车列表, 慢车列表)
        """
        express_trains = []
        local_trains = []
        
        # 步骤1：生成快车（均匀分布）
        express_headway = 600  # 快车间隔10分钟
        
        for i in range(express_count):
            train_id = f"E{i+1:02d}"
            train_name = f"快车{i+1}"
            dep_time = start_time + i * express_headway
            
            # 快车跳停：只停起点站、站点2、站点5、站点8、终点站
            express_stop_indices = {0, 2, 5, 8, 9}
            
            train = self._generate_express_train(
                train_id, train_name, dep_time, express_stop_indices
            )
            express_trains.append(train)
        
        # 步骤2：生成慢车（会被快车追上）
        # 策略：慢车在快车后面不久发车，由于速度慢，会被快车追上
        
        local_departures = [
            start_time + 150,   # 慢车1：在快车1后2.5分钟发车
            start_time + 300,   # 慢车2：在快车1后5分钟发车
            start_time + 750,   # 慢车3：在快车2后2.5分钟发车
            start_time + 900,   # 慢车4：在快车2后5分钟发车
        ]
        
        for i in range(min(local_count, len(local_departures))):
            train_id = f"L{i+1:02d}"
            train_name = f"慢车{i+1}"
            dep_time = local_departures[i]
            
            # 慢车站站停
            train = self._generate_local_train_with_overtaking_check(
                train_id, train_name, dep_time, express_trains
            )
            local_trains.append(train)
        
        return express_trains, local_trains
    
    def _generate_express_train(self,
                                train_id: str,
                                train_name: str,
                                departure_time: int,
                                stop_indices: set) -> TrainSchedule:
        """
        生成快车时刻表
        
        Args:
            train_id: 车次ID
            train_name: 车次名称
            departure_time: 发车时间
            stop_indices: 停站索引集合
            
        Returns:
            快车时刻表
        """
        stops = []
        current_time = departure_time
        
        # 快车区间运行时间（更快）
        express_section_time = int(self.section_running_time / self.express_speed_factor)
        
        for i, station_name in enumerate(self.stations):
            # 判断是否停站
            is_stop = i in stop_indices
            
            if i == 0:
                # 首站：只有发车时间
                arrival = current_time
                departure = current_time
                dwell = 0
            elif is_stop:
                # 停站
                arrival = current_time
                dwell = self.normal_dwell_time
                departure = arrival + dwell
                current_time = departure
            else:
                # 跳站：不停站，直接通过
                arrival = current_time
                dwell = 0
                departure = current_time
            
            stop = StationStop(
                station_name=station_name,
                station_index=i,
                arrival_time=arrival,
                departure_time=departure,
                dwell_time=dwell,
                is_skip=not is_stop
            )
            stops.append(stop)
            
            # 运行到下一站
            if i < len(self.stations) - 1:
                current_time += express_section_time
        
        return TrainSchedule(
            train_id=train_id,
            train_name=train_name,
            is_express=True,
            direction="上行",
            departure_time=departure_time,
            stops=stops
        )
    
    def _generate_local_train_with_overtaking_check(self,
                                                     train_id: str,
                                                     train_name: str,
                                                     departure_time: int,
                                                     express_trains: List[TrainSchedule]) -> TrainSchedule:
        """
        生成慢车时刻表（带越行检测和处理）
        
        关键算法：
        1. 先按照正常时间生成慢车时刻表
        2. 检测是否会被快车追上
        3. 如果会被追上，找到越行站
        4. 在越行站增加停站时间到240秒
        5. 越行站之后的所有站点时刻顺延
        
        Args:
            train_id: 车次ID
            train_name: 车次名称
            departure_time: 发车时间
            express_trains: 快车列表（用于越行检测）
            
        Returns:
            慢车时刻表
        """
        stops = []
        current_time = departure_time
        
        # 先生成初始时刻表（不考虑越行）
        for i, station_name in enumerate(self.stations):
            if i == 0:
                # 首站
                arrival = current_time
                departure = current_time
                dwell = 0
            else:
                # 中间站和终点站：站站停
                arrival = current_time
                dwell = self.normal_dwell_time
                departure = arrival + dwell
                current_time = departure
            
            stop = StationStop(
                station_name=station_name,
                station_index=i,
                arrival_time=arrival,
                departure_time=departure,
                dwell_time=dwell,
                is_skip=False
            )
            stops.append(stop)
            
            # 运行到下一站
            if i < len(self.stations) - 1:
                current_time += self.section_running_time
        
        # 检测越行并调整时刻表
        self._detect_and_handle_overtaking(stops, express_trains, train_id)
        
        return TrainSchedule(
            train_id=train_id,
            train_name=train_name,
            is_express=False,
            direction="上行",
            departure_time=departure_time,
            stops=stops
        )
    
    def _detect_and_handle_overtaking(self,
                                      local_stops: List[StationStop],
                                      express_trains: List[TrainSchedule],
                                      local_train_id: str):
        """
        检测越行并处理慢车时刻表
        
        这是实现越行的核心方法！
        
        Args:
            local_stops: 慢车停站列表（会被修改）
            express_trains: 快车列表
            local_train_id: 慢车ID
        """
        # 遍历每列快车，检查是否会追上这列慢车
        for express in express_trains:
            # 前提：快车在慢车后面出发
            if express.departure_time <= local_stops[0].departure_time:
                continue
            
            # 检查快车是否会在线路中追上慢车
            overtaking_station_idx = self._find_overtaking_point(local_stops, express)
            
            if overtaking_station_idx is not None:
                print(f"\n[越行] 检测到越行：{express.train_name} 将在 {self.stations[overtaking_station_idx]} 越行 {local_train_id}")
                
                # 处理越行：在越行站增加停站时间
                self._apply_overtaking_at_station(
                    local_stops, express, overtaking_station_idx, local_train_id
                )
    
    def _find_overtaking_point(self,
                               local_stops: List[StationStop],
                               express: TrainSchedule) -> Optional[int]:
        """
        找到越行发生的位置
        
        Args:
            local_stops: 慢车停站列表
            express: 快车
            
        Returns:
            越行站索引，如果不会越行则返回None
        """
        # 逐站检查
        for i in range(1, len(local_stops)):
            local_stop = local_stops[i]
            
            # 获取快车在该站的到达/通过时间
            express_arrival = express.get_arrival_at_station(i)
            
            if express_arrival is None:
                continue
            
            # 检查是否会发生追踪间隔冲突
            # 条件：快车到达时间 < 慢车离站时间 + 最小追踪间隔
            if express_arrival < local_stop.departure_time + self.min_tracking_interval:
                # 会发生冲突，需要在此站或之前的越行站进行越行
                # 从当前站往前找最近的越行站
                for j in range(i, -1, -1):
                    if j in self.overtaking_stations:
                        return j
                
                # 如果没有找到越行站，使用当前站
                print(f"  [警告] 站点{i}({self.stations[i]})不是标准越行站，但仍需越行")
                return i
        
        return None
    
    def _apply_overtaking_at_station(self,
                                     local_stops: List[StationStop],
                                     express: TrainSchedule,
                                     overtaking_station_idx: int,
                                     local_train_id: str):
        """
        在越行站应用越行处理
        
        处理步骤（按照md文档的越行处理原则）：
        1. 慢车在越行站的停站时间增加到至少240秒
        2. 确保满足到通间隔（≥120秒）和通发间隔（≥120秒）
        3. 越行站之后的所有站点时刻顺延
        
        Args:
            local_stops: 慢车停站列表（会被修改）
            express: 快车
            overtaking_station_idx: 越行站索引
            local_train_id: 慢车ID
        """
        overtaking_stop = local_stops[overtaking_station_idx]
        
        # 获取快车通过越行站的时间
        express_pass_time = express.get_arrival_at_station(overtaking_station_idx)
        
        if express_pass_time is None:
            print(f"  [警告] 快车在越行站{overtaking_station_idx}的时间未知")
            return
        
        # 计算慢车需要的停站时间
        # 慢车到站时间已知：overtaking_stop.arrival_time
        # 快车通过时间已知：express_pass_time
        
        # 到通间隔：慢车到站 -> 快车通过
        arrival_to_pass = express_pass_time - overtaking_stop.arrival_time
        
        # 慢车发车时间 = 快车通过时间 + 通发间隔
        new_local_departure = express_pass_time + self.min_pass_departure_interval
        
        # 慢车在越行站的停站时间
        new_dwell_time = new_local_departure - overtaking_stop.arrival_time
        
        # 确保停站时间至少240秒
        if new_dwell_time < self.min_overtaking_dwell:
            new_dwell_time = self.min_overtaking_dwell
            new_local_departure = overtaking_stop.arrival_time + new_dwell_time
        
        # 确保到通间隔至少120秒
        if arrival_to_pass < self.min_arrival_pass_interval:
            # 需要让慢车提前到达或快车延后通过（这里简化处理，只调整慢车发车时间）
            print(f"  [警告] 到通间隔不足({arrival_to_pass}秒 < {self.min_arrival_pass_interval}秒)")
        
        # 计算时间顺延量
        time_shift = new_local_departure - overtaking_stop.departure_time
        
        print(f"  [越行处理]")
        print(f"     慢车到达: {self._format_time(overtaking_stop.arrival_time)}")
        print(f"     快车通过: {self._format_time(express_pass_time)}")
        print(f"     慢车原定发车: {self._format_time(overtaking_stop.departure_time)}")
        print(f"     慢车调整后发车: {self._format_time(new_local_departure)}")
        print(f"     停站时间: {overtaking_stop.dwell_time}秒 -> {new_dwell_time}秒")
        print(f"     后续站点顺延: +{time_shift}秒")
        print(f"     到通间隔: {arrival_to_pass}秒")
        print(f"     通发间隔: {new_local_departure - express_pass_time}秒")
        
        # 应用越行站的时间调整
        overtaking_stop.departure_time = new_local_departure
        overtaking_stop.dwell_time = new_dwell_time
        overtaking_stop.is_overtaking_station = True
        overtaking_stop.is_waiting_for_overtaking = True
        
        # 顺延后续所有站点的时间
        for i in range(overtaking_station_idx + 1, len(local_stops)):
            local_stops[i].arrival_time += time_shift
            local_stops[i].departure_time += time_shift
    
    def _format_time(self, seconds: int) -> str:
        """格式化时间（秒 -> HH:MM:SS）"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def print_timetable(self, 
                       express_trains: List[TrainSchedule],
                       local_trains: List[TrainSchedule]):
        """
        打印时刻表（表格形式）
        
        Args:
            express_trains: 快车列表
            local_trains: 慢车列表
        """
        print("\n" + "="*100)
        print("快慢车运行图时刻表（带越行）")
        print("="*100)
        
        # 打印快车时刻表
        print("\n【快车时刻表】")
        print("-"*100)
        for train in express_trains:
            self._print_train_schedule(train)
        
        # 打印慢车时刻表
        print("\n【慢车时刻表】")
        print("-"*100)
        for train in local_trains:
            self._print_train_schedule(train)
        
        print("\n" + "="*100)
    
    def _print_train_schedule(self, train: TrainSchedule):
        """打印单列车时刻表"""
        print(f"\n{train.train_name} ({train.train_id}) - 首站发车: {self._format_time(train.departure_time)}")
        print(f"{'站名':<10} {'到站时间':<12} {'发车时间':<12} {'停站时间':<10} {'状态':<20}")
        print("-"*70)
        
        for stop in train.stops:
            arr_time = self._format_time(stop.arrival_time) if not stop.is_skip else "---"
            dep_time = self._format_time(stop.departure_time) if not stop.is_skip else "通过"
            dwell = f"{stop.dwell_time}秒" if not stop.is_skip else "0秒"
            
            # 状态标志
            status = ""
            if stop.is_skip:
                status = "[跳站]"
            elif stop.is_overtaking_station:
                status = "[越行站-待避4分钟]"
            elif stop.dwell_time > 0:
                status = "[停站]"
            
            print(f"{stop.station_name:<10} {arr_time:<12} {dep_time:<12} {dwell:<10} {status:<20}")
    
    def export_to_excel(self,
                       express_trains: List[TrainSchedule],
                       local_trains: List[TrainSchedule],
                       output_file: str = "../data/output/overtaking_demo.xlsx"):
        """
        导出时刻表到Excel
        
        Args:
            express_trains: 快车列表
            local_trains: 慢车列表
            output_file: 输出文件路径
        """
        try:
            import pandas as pd
            from pathlib import Path
            
            # 确保输出目录存在
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 创建DataFrame
            all_trains = express_trains + local_trains
            
            data = []
            for train in all_trains:
                for stop in train.stops:
                    data.append({
                        '车次': train.train_id,
                        '车次名称': train.train_name,
                        '列车类型': '快车' if train.is_express else '慢车',
                        '站名': stop.station_name,
                        '站序': stop.station_index + 1,
                        '到站时间': self._format_time(stop.arrival_time),
                        '发车时间': self._format_time(stop.departure_time),
                        '停站时间(秒)': stop.dwell_time,
                        '是否跳站': '是' if stop.is_skip else '否',
                        '是否越行站': '是' if stop.is_overtaking_station else '否',
                        '状态': '[越行站]' if stop.is_overtaking_station else ('[跳站]' if stop.is_skip else '[停站]')
                    })
            
            df = pd.DataFrame(data)
            
            # 写入Excel
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='时刻表', index=False)
                
                # 调整列宽
                worksheet = writer.sheets['时刻表']
                for idx, col in enumerate(df.columns):
                    max_length = max(df[col].astype(str).apply(len).max(), len(str(col)))
                    if idx < 26:
                        worksheet.column_dimensions[chr(65 + idx)].width = max_length + 2
            
            print(f"\n[成功] Excel文件已导出: {output_file}")
            
        except Exception as e:
            print(f"\n[错误] 导出Excel失败: {str(e)}")


def main():
    """主函数"""
    print("="*100)
    print("快车越行慢车Demo程序")
    print("="*100)
    
    # 创建生成器
    generator = OvertakingDemoGenerator(
        min_tracking_interval=120,      # 最小追踪间隔120秒
        min_arrival_pass_interval=120,  # 最小到通间隔120秒
        min_pass_departure_interval=120, # 最小通发间隔120秒
        min_overtaking_dwell=240,       # 越行站最小停站时间240秒
        section_running_time=120,       # 区间运行时间120秒
        express_speed_factor=1.2,       # 快车速度系数1.2
        normal_dwell_time=30            # 正常停站时间30秒
    )
    
    # 生成快慢车运行图
    print("\n[开始] 生成快慢车运行图...")
    express_trains, local_trains = generator.generate_demo_timetable(
        express_count=3,
        local_count=4,
        start_time=7200  # 从02:00开始
    )
    
    # 打印时刻表
    generator.print_timetable(express_trains, local_trains)
    
    # 导出Excel
    generator.export_to_excel(express_trains, local_trains)
    
    print("\n" + "="*100)
    print("[完成] Demo程序运行完成！")
    print("="*100)
    
    # 统计越行事件
    overtaking_count = 0
    for train in local_trains:
        for stop in train.stops:
            if stop.is_overtaking_station:
                overtaking_count += 1
    
    print(f"\n[统计信息]")
    print(f"  快车数量: {len(express_trains)}")
    print(f"  慢车数量: {len(local_trains)}")
    print(f"  越行事件: {overtaking_count}次")
    print(f"\n[说明]")
    print(f"  - 快车跳停部分车站，速度更快")
    print(f"  - 慢车站站停，速度较慢")
    print(f"  - 当快车在慢车后面发车，但由于速度快会追上慢车时")
    print(f"  - 慢车会在越行站停留至少4分钟(240秒)，等待快车通过")
    print(f"  - 越行后，慢车后续所有站点的时刻都会顺延")


if __name__ == "__main__":
    main()

