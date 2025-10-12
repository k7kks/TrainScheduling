"""
Excel导出器

复用src的输出接口，生成与大小交路一致的Excel文件
"""

from typing import List, Dict, Optional
import sys
import os
from pathlib import Path
import pandas as pd
from datetime import datetime, timedelta

# 添加src到路径以复用现有接口
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'src'))

from Solution import Solution
from RouteSolution import RouteSolution

# 使用绝对导入
try:
    from models.express_local_timetable import ExpressLocalTimetable
    from models.timetable_entry import TimetableEntry
except ImportError:
    # 兼容相对导入
    from ..models.express_local_timetable import ExpressLocalTimetable
    from ..models.timetable_entry import TimetableEntry


class ExcelExporter:
    """
    Excel导出器
    
    生成与大小交路格式一致的Excel运行图文件
    """
    
    def __init__(self):
        """初始化导出器"""
        self.base_date = datetime(2024, 1, 1)  # 基准日期
    
    def export(self,
               timetable: ExpressLocalTimetable,
               output_path: str,
               rail_info=None,
               user_setting=None) -> str:
        """
        导出快慢车运行图到Excel文件
        
        Args:
            timetable: 快慢车时刻表
            output_path: 输出文件路径
            rail_info: 线路信息（可选）
            user_setting: 用户设置（可选）
            
        Returns:
            输出文件路径
        """
        # 确保输出目录存在
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建Excel写入器
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # 工作表1：列车时刻表（按列车）
            self._write_train_timetable(timetable, writer)
            
            # 工作表2：车站时刻表（按车站）
            self._write_station_timetable(timetable, writer)
            
            # 工作表3：交路统计
            self._write_route_statistics(timetable, writer)
            
            # 工作表4：越行事件
            self._write_overtaking_events(timetable, writer)
            
            # 工作表5：统计信息
            self._write_statistics(timetable, writer)
            
            # 工作表6：车辆运用（简化版）
            self._write_vehicle_utilization(timetable, writer)
        
        return output_path
    
    def _write_train_timetable(self, timetable: ExpressLocalTimetable, writer):
        """写入列车时刻表"""
        data = []
        
        all_trains = timetable.express_trains + timetable.local_trains
        
        for train in all_trains:
            entries = timetable.get_train_schedule(train.train_id)
            
            if not entries:
                continue
            
            for entry in entries:
                data.append({
                    '车次': train.train_id,
                    '车次名称': train.train_name,
                    '列车类型': train.train_type.value,
                    '交路ID': train.route_id,
                    '方向': train.direction,
                    '车站ID': entry.station_id,
                    '车站名称': entry.station_name,
                    '站台目的地码': entry.dest_code if entry.dest_code else '',
                    '到达时间': self._format_time(entry.arrival_time),
                    '发车时间': self._format_time(entry.departure_time),
                    '停站时间(秒)': entry.dwell_time,
                    '是否停车': '是' if entry.is_stop else '否',
                    '是否跳停': '是' if entry.is_skip else '否',
                    '是否越行': '是' if entry.is_overtaking else '否',
                    '被越行车次': entry.overtaken_by if entry.overtaken_by else '',
                    '等待时间(秒)': entry.waiting_time
                })
        
        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name='列车时刻表', index=False)
    
    def _write_station_timetable(self, timetable: ExpressLocalTimetable, writer):
        """写入车站时刻表"""
        data = []
        
        # 获取所有车站
        station_ids = set()
        for entry in timetable.timetable_entries:
            station_ids.add(entry.station_id)
        
        # 按车站整理时刻
        for station_id in sorted(station_ids):
            entries = timetable.get_station_schedule(station_id)
            
            for entry in entries:
                train = timetable.get_train(entry.train_id)
                if train is None:
                    continue
                
                data.append({
                    '车站ID': entry.station_id,
                    '车站名称': entry.station_name,
                    '站台目的地码': entry.dest_code if entry.dest_code else '',
                    '车次': entry.train_id,
                    '列车类型': train.train_type.value,
                    '方向': train.direction,
                    '到达时间': self._format_time(entry.arrival_time),
                    '发车时间': self._format_time(entry.departure_time),
                    '停站时间(秒)': entry.dwell_time,
                    '是否停车': '是' if entry.is_stop else '否',
                    '是否越行': '是' if entry.is_overtaking else '否'
                })
        
        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name='车站时刻表', index=False)
    
    def _write_route_statistics(self, timetable: ExpressLocalTimetable, writer):
        """写入交路统计"""
        data = []
        
        # 统计各交路的开行情况
        route_stats = {}
        
        for train in timetable.express_trains + timetable.local_trains:
            route_id = train.route_id
            if route_id not in route_stats:
                route_stats[route_id] = {
                    '交路ID': route_id,
                    '快车数': 0,
                    '慢车数': 0,
                    '小交路数': 0,
                    '大交路数': 0,
                    '总列车数': 0
                }
            
            route_stats[route_id]['总列车数'] += 1
            
            if train.train_type.value == '快车':
                route_stats[route_id]['快车数'] += 1
                route_stats[route_id]['大交路数'] += 1
            else:
                route_stats[route_id]['慢车数'] += 1
                if hasattr(train, 'is_short_route') and train.is_short_route:
                    route_stats[route_id]['小交路数'] += 1
                else:
                    route_stats[route_id]['大交路数'] += 1
        
        data = list(route_stats.values())
        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name='交路统计', index=False)
    
    def _write_overtaking_events(self, timetable: ExpressLocalTimetable, writer):
        """写入越行事件"""
        data = []
        
        for event in timetable.overtaking_events:
            data.append({
                '事件ID': event.event_id,
                '越行车次': event.overtaking_train_id,
                '被越行车次': event.overtaken_train_id,
                '越行站': event.overtaking_station_name,
                '方向': event.direction,
                '慢车到达时间': self._format_time(event.local_arrival_time),
                '快车通过时间': self._format_time(event.express_pass_time),
                '慢车发车时间': self._format_time(event.local_departure_time),
                '到通间隔(秒)': event.arrival_to_pass_interval,
                '通发间隔(秒)': event.pass_to_departure_interval,
                '慢车等待时间(秒)': event.local_waiting_time,
                '额外延误(秒)': event.total_delay,
                '是否合规': '是' if event.is_valid_overtaking else '否',
                '是否可避免': '是' if event.is_avoidable else '否',
                '优化建议': event.get_optimization_suggestion()
            })
        
        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name='越行事件', index=False)
    
    def _write_statistics(self, timetable: ExpressLocalTimetable, writer):
        """写入统计信息"""
        data = []
        
        # 基本统计
        data.append({'统计项': '总列车数', '数值': timetable.total_trains, '单位': '列'})
        data.append({'统计项': '快车数', '数值': timetable.express_trains_count, '单位': '列'})
        data.append({'统计项': '慢车数', '数值': timetable.local_trains_count, '单位': '列'})
        data.append({'统计项': '快慢车比例', '数值': f"{timetable.express_trains_count}:{timetable.local_trains_count}", '单位': ''})
        
        # 时间统计
        data.append({'统计项': '服务开始时间', '数值': self._format_time(timetable.start_time), '单位': ''})
        data.append({'统计项': '服务结束时间', '数值': self._format_time(timetable.end_time), '单位': ''})
        data.append({'统计项': '服务时长', '数值': timetable.service_duration / 3600, '单位': '小时'})
        
        # 发车间隔统计
        avg_headway_up = timetable.calculate_average_headway("上行")
        avg_headway_down = timetable.calculate_average_headway("下行")
        var_headway_up = timetable.calculate_headway_variance("上行")
        var_headway_down = timetable.calculate_headway_variance("下行")
        
        data.append({'统计项': '上行平均发车间隔', '数值': avg_headway_up / 60, '单位': '分钟'})
        data.append({'统计项': '下行平均发车间隔', '数值': avg_headway_down / 60, '单位': '分钟'})
        data.append({'统计项': '上行发车间隔方差', '数值': var_headway_up, '单位': '秒²'})
        data.append({'统计项': '下行发车间隔方差', '数值': var_headway_down, '单位': '秒²'})
        
        # 越行统计
        data.append({'统计项': '越行事件总数', '数值': timetable.total_overtaking_events, '单位': '次'})
        
        overtaken_locals = timetable.get_overtaken_local_trains()
        data.append({'统计项': '被越行慢车数', '数值': len(overtaken_locals), '单位': '列'})
        
        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name='统计信息', index=False)
    
    def _write_vehicle_utilization(self, timetable: ExpressLocalTimetable, writer):
        """写入车辆运用"""
        data = []
        
        # 简化版车辆运用：只列出车次连接关系
        for train in timetable.local_trains:
            data.append({
                '车次': train.train_id,
                '列车类型': train.train_type.value,
                '交路类型': '小交路' if hasattr(train, 'is_short_route') and train.is_short_route else '大交路',
                '发车时间': self._format_time(train.departure_time) if train.departure_time else '',
                '到达时间': self._format_time(train.arrival_time) if train.arrival_time else '',
                '前序车次': train.prev_train_id if train.prev_train_id else '',
                '后续车次': train.next_train_id if train.next_train_id else ''
            })
        
        # 快车独立运用
        for train in timetable.express_trains:
            data.append({
                '车次': train.train_id,
                '列车类型': train.train_type.value,
                '交路类型': '大交路',
                '发车时间': self._format_time(train.departure_time) if train.departure_time else '',
                '到达时间': self._format_time(train.arrival_time) if train.arrival_time else '',
                '前序车次': '',
                '后续车次': ''
            })
        
        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name='车辆运用', index=False)
    
    def _format_time(self, seconds: int) -> str:
        """
        将秒数格式化为时:分:秒字符串
        
        Args:
            seconds: 秒数
            
        Returns:
            格式化的时间字符串
        """
        if seconds is None:
            return ""
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

