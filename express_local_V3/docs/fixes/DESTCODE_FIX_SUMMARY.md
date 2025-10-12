# 站台目的地码修复总结

## 问题描述

express_local_V3生成的Excel文件中，"站台目的地码"列的数据不正确，未能从输入的轨道信息XML文件中读取正确的Destcode值。

## 根本原因

1. **TimetableEntry模型缺少dest_code字段**：原始模型没有专门的字段来存储站台目的地码
2. **Excel导出器未输出站台目的地码列**：ExcelExporter在生成Excel时没有包含"站台目的地码"列
3. **数据传递不清晰**：station_id和dest_code的职责混淆

## 修复内容

### 1. 修改TimetableEntry模型 (`models/timetable_entry.py`)

**添加dest_code字段：**
```python
dest_code: Optional[str] = None  # 站台目的地码（Destcode，用于输出）
```

**说明：**
- `station_id`: 存储车站ID（真正的车站ID）
- `dest_code`: 存储站台目的地码（Destcode，从XML读取）

### 2. 修改TimetableBuilder (`algorithms/timetable_builder.py`)

**修改时刻表条目创建逻辑：**
```python
# 获取正确的站台目的地码（根据列车方向选择站台）
dest_code = self._get_platform_code(station, train.direction)

# 创建时刻表条目
entry = TimetableEntry(
    train_id=train.train_id,
    station_id=station.id,  # 使用车站ID
    station_name=station.name,
    arrival_time=arrival_time,
    departure_time=departure_time,
    dwell_time=dwell_time,
    is_stop=is_stop,
    is_skip=is_skip,
    platform_id=dest_code,  # 站台ID（内部引用）
    dest_code=dest_code  # 站台目的地码（用于输出）
)
```

**_get_platform_code方法：**
该方法根据车站和列车方向，从Station.platformList中查找匹配的Platform，并返回其dest_code属性。

### 3. 修改main.py

**修改RouteSolution创建逻辑：**
```python
# 获取站台目的地码（使用dest_code字段）
platform_code = entry.dest_code if entry.dest_code else entry.station_id

rs.addStop(
    platform=platform_code,  # 使用站台目的地码
    stop_time=entry.dwell_time,
    perf_level=self.speed_level,
    current_time=entry.arrival_time,
    dep_time=entry.departure_time
)
```

### 4. 修改ExcelExporter (`output/excel_exporter.py`)

**在列车时刻表中添加"站台目的地码"列：**
```python
data.append({
    '车次': train.train_id,
    '车次名称': train.train_name,
    '列车类型': train.train_type.value,
    '交路ID': train.route_id,
    '方向': train.direction,
    '车站ID': entry.station_id,
    '车站名称': entry.station_name,
    '站台目的地码': entry.dest_code if entry.dest_code else '',  # 新增
    '到达时间': self._format_time(entry.arrival_time),
    '发车时间': self._format_time(entry.departure_time),
    # ... 其他字段
})
```

**在车站时刻表中添加"站台目的地码"列：**
```python
data.append({
    '车站ID': entry.station_id,
    '车站名称': entry.station_name,
    '站台目的地码': entry.dest_code if entry.dest_code else '',  # 新增
    '车次': entry.train_id,
    # ... 其他字段
})
```

## 验证结果

### 测试数据

使用长沙2号线数据（Schedule-cs2.xml）进行测试：
- 车站数：24个
- 列车数：42列（12列快车 + 30列慢车）
- 时刻表条目：1008条

### 验证结果

✅ **列车时刻表工作表**
- 包含"站台目的地码"列
- 所有1008行数据的站台目的地码都有值，无空值
- 站台目的地码正确（如113, 121, 131, 141, 153等）

✅ **车站时刻表工作表**
- 包含"站台目的地码"列
- 站台目的地码与XML文件中的Destcode完全一致

### 示例数据

```
车次    车站名称     车站ID  站台目的地码
E001   梅溪湖西站    11     113
E001   麓谷路站      12     121
E001   文化艺术中心站 13     131
E001   梅溪湖东站    14     141
E001   望城坡站      15     153
```

## 数据来源确认

站台目的地码的正确来源路径：
1. **XML文件** (`Schedule-cs2.xml`)
   ```xml
   <Platform>
     <Id>3</Id>
     <Name>梅溪湖西站上行站台</Name>
     <Type>Turnback</Type>
     <Direction>Left</Direction>
     <IsVirtual>false</IsVirtual>
     <Destcode>113</Destcode>  <!-- 这里！-->
   </Platform>
   ```

2. **DataReader** (`src/DataReader.py`)
   - `_extract_platform_data()` 方法读取 `<Destcode>` 标签
   - 返回 `dest_code` 字段

3. **Platform对象** (`src/Platform.py`)
   - 构造函数接收 `dest_code` 参数
   - 存储为 `self.dest_code` 属性

4. **TimetableBuilder** (`express_local_V3/algorithms/timetable_builder.py`)
   - `_get_platform_code()` 方法从 `Platform.dest_code` 获取
   - 赋值给 `TimetableEntry.dest_code`

5. **ExcelExporter** (`express_local_V3/output/excel_exporter.py`)
   - 从 `entry.dest_code` 读取
   - 输出到Excel的"站台目的地码"列

## 文件修改清单

1. ✅ `express_local_V3/models/timetable_entry.py` - 添加dest_code字段
2. ✅ `express_local_V3/algorithms/timetable_builder.py` - 正确获取和设置dest_code
3. ✅ `express_local_V3/main.py` - 使用dest_code创建RouteSolution
4. ✅ `express_local_V3/output/excel_exporter.py` - 输出站台目的地码列

## 兼容性说明

- 保持与src文件夹中原有代码的兼容性
- 使用与src/Solution.py相同的Excel输出格式
- 站台目的地码列的位置和命名与原有系统一致

## 后续建议

1. ✅ 已完成测试，确认Excel输出正确
2. 建议在用户实际使用时再次验证其他线路的数据
3. 如果发现某些车站没有找到合适的站台，会使用车站ID作为后备值（已有WARNING提示）

## 修复日期

2025-10-12

## 修复人员

AI Assistant (Claude Sonnet 4.5)

