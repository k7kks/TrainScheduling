# V3架构改造 - 快速上手指南

**版本**: V3.0  
**更新日期**: 2025-10-13

---

## 🚀 快速开始

### 1. 环境要求

确保已安装所需依赖：

```bash
cd express_local_V3
pip install -r requirements.txt
```

### 2. 运行系统

```bash
python main.py
```

### 3. 检查输出

运行成功后会生成：

- **Excel文件**: `data/output/快慢车运行图_YYYYMMDD_HHMMSS.xlsx`
- **日志文件**: `logs/express_local_scheduler.log`

---

## ✅ 快速验证

### 检查点1：启动日志

查找以下关键日志（表示V3架构正常工作）：

```bash
# 在 logs/express_local_scheduler.log 中查找

[PathStationIndex] 开始构建路径索引缓存...
  [√] 路径1086: 25个节点 (虚拟节点=2)
  [√] 路径1088: 23个节点 (虚拟节点=1)
[PathStationIndex] 完成！共构建X个路径索引
```

### 检查点2：无错误日志

**不应该出现**以下日志：

```
❌ [警告] 列车XXX的路径YYY未找到PathStationIndex
❌ [错误] 列车XXX的时刻表条目数与路径节点数不一致
❌ [FATAL] 车次XXX站台码验证失败
```

如果出现上述错误，请查看 [故障排查](#-故障排查)

### 检查点3：Excel输出验证

打开生成的Excel文件，检查以下工作表：

#### 工作表1：列车时刻表

| 检查项 | 预期结果 |
|--------|----------|
| 站台目的地码列 | 每列车的站台码顺序与该交路的path.nodeList一致 |
| 是否越行列 | 有值为"是"的行 |
| 等待时间(秒)列 | "是否越行=是"的行，等待时间>0 |

**示例数据**：

| 车次 | 车站名称 | 站台目的地码 | 是否越行 | 等待时间(秒) |
|------|----------|--------------|----------|--------------|
| L001 | 金星路站 | 1086 | 是 | 240 |

#### 工作表2：越行事件

| 检查项 | 预期结果 |
|--------|----------|
| 有数据行 | 至少有1条越行事件 |
| 慢车等待时间(秒) | ≥240秒 |
| 到通间隔(秒) | ≥60秒 |
| 通发间隔(秒) | ≥60秒 |

---

## 📋 V3架构关键特性

### 特性1：PathStationIndex

**作用**: 建立路径顺序与车站的精确映射

**查看方式**:

```python
from algorithms.timetable_builder import TimetableBuilder
from src.RailInfo import RailInfo

rail_info = RailInfo()
# ... 读取数据 ...

builder = TimetableBuilder(rail_info)

# 查看某条路径的索引
path_index = builder.path_station_indexes['1086']
path_index.debug_print()
```

**输出示例**:

```
=== PathStationIndex(route=1086, nodes=25, virtual=2) ===
  Node[0][虚拟] T01 (折返轨)
  Node[1] 1086 (金星路站)
  Node[2] 1087 (人民东路站)
  ...
```

### 特性2：path_index精确匹配

**原理**: 每个TimetableEntry携带 `path_index` 字段

**验证方式**:

```python
from models.express_local_timetable import ExpressLocalTimetable

timetable = ExpressLocalTimetable()
# ... 构建时刻表 ...

entries = timetable.get_train_schedule('TRAIN_001')
for entry in entries:
    print(f"path_index={entry.path_index}, dest_code={entry.dest_code}")
```

**输出示例**:

```
path_index=0, dest_code=T01
path_index=1, dest_code=1086
path_index=2, dest_code=1087
...
```

### 特性3：严格索引验证

**位置**: `main.py:586-620`

**验证逻辑**:

```python
if len(timetable_entries) != len(path_destcodes):
    print(f"[错误] 禁止自动补齐！")
    return None
```

**意义**: 确保时刻表与路径完全对齐，避免数据不一致

---

## 🔍 故障排查

### 问题1：`[警告] 路径XXX未找到PathStationIndex`

**可能原因**:
- `train.route_id` 与 `path.routeID` 不匹配
- `rail_info.pathList` 中缺失该路径

**排查步骤**:

1. 检查列车的route_id:
   ```python
   print(f"Train route_id: {train.route_id}")
   ```

2. 检查pathList中的路径:
   ```python
   print(f"Available paths: {list(rail_info.pathList.keys())}")
   ```

3. 如果route_id不在pathList中，检查数据源XML文件

### 问题2：`[错误] 时刻表条目数与路径节点数不一致`

**可能原因**:
- PathStationIndex构建时遗漏了某些节点
- TimetableBuilder生成entries时跳过了某些节点

**排查步骤**:

1. 查看PathStationIndex节点数:
   ```python
   path_index = builder.path_station_indexes[train.route_id]
   print(f"PathStationIndex nodes: {path_index.total_nodes}")
   print(f"Path nodeList length: {len(path.nodeList)}")
   ```

2. 查看生成的entries数:
   ```python
   entries = timetable.get_train_schedule(train.train_id)
   print(f"Timetable entries: {len(entries)}")
   ```

3. 对比差异:
   ```python
   path_index.debug_print()
   for i, entry in enumerate(entries):
       print(f"Entry[{i}]: path_index={entry.path_index}, dest={entry.dest_code}")
   ```

### 问题3：越行标记缺失

**可能原因**:
- `entry.path_index` 为 `None`，导致越行匹配失败
- 越行检测逻辑未触发

**排查步骤**:

1. 检查entry是否有path_index:
   ```python
   entries = timetable.get_train_schedule(train.train_id)
   for entry in entries:
       if entry.path_index is None:
           print(f"[警告] Entry缺少path_index: {entry}")
   ```

2. 检查越行事件:
   ```python
   print(f"Total overtaking events: {len(timetable.overtaking_events)}")
   for event in timetable.overtaking_events:
       print(f"  {event.overtaking_train_id} 越行 {event.overtaken_train_id}")
   ```

3. 检查越行站配置:
   ```python
   builder = TimetableBuilder(rail_info)
   print(f"上行越行站: {builder.overtaking_station_name_up} (ID={builder.overtaking_station_id_up})")
   print(f"下行越行站: {builder.overtaking_station_name_down} (ID={builder.overtaking_station_id_down})")
   ```

---

## 📚 相关文档

| 文档 | 说明 |
|------|------|
| [V3_PATH_INDEX_ARCHITECTURE.md](V3_PATH_INDEX_ARCHITECTURE.md) | 架构设计详解 |
| [V3_IMPLEMENTATION_SUMMARY.md](V3_IMPLEMENTATION_SUMMARY.md) | 实施总结 |
| [OVERTAKING_INTEGRATION_GUIDE.md](OVERTAKING_INTEGRATION_GUIDE.md) | 越行功能集成指南 |
| [fixes/DESTCODE_PATH_FIX.md](fixes/DESTCODE_PATH_FIX.md) | 站台码修复文档 |

---

## 🧪 进阶测试

### 手动验证站台码对齐

```python
from src.RailInfo import RailInfo
from algorithms.timetable_builder import TimetableBuilder
from models.express_local_timetable import ExpressLocalTimetable

# 读取数据
rail_info = RailInfo()
# ... 读取数据 ...

# 构建时刻表
builder = TimetableBuilder(rail_info)
timetable = ExpressLocalTimetable()
# ... 添加列车 ...
timetable = builder.build_timetable(timetable)

# 验证对齐
def verify_alignment(train, rail_info, timetable):
    path = rail_info.pathList[train.route_id]
    entries = timetable.get_train_schedule(train.train_id)
    
    assert len(entries) == len(path.nodeList), \
        f"数量不一致: entries={len(entries)}, path={len(path.nodeList)}"
    
    for i, (entry, dest_code) in enumerate(zip(entries, path.nodeList)):
        assert entry.path_index == i, f"path_index不一致: {entry.path_index} != {i}"
        assert entry.dest_code == dest_code, f"dest_code不一致: {entry.dest_code} != {dest_code}"
    
    print(f"✅ 列车{train.train_id}站台码对齐验证通过")

# 对所有列车验证
for train in timetable.get_all_trains():
    verify_alignment(train, rail_info, timetable)
```

### 验证越行传播

```python
def verify_overtaking_propagation(timetable):
    """验证越行调整已正确传播到entries"""
    
    for event in timetable.overtaking_events:
        # 获取被越行慢车的时刻表
        local_entries = timetable.get_train_schedule(event.overtaken_train_id)
        
        # 找到越行站的entry
        overtaking_entry = None
        for entry in local_entries:
            if entry.station_id == event.overtaking_station_id:
                overtaking_entry = entry
                break
        
        assert overtaking_entry is not None, \
            f"未找到{event.overtaken_train_id}在{event.overtaking_station_name}的entry"
        
        assert overtaking_entry.is_overtaking, \
            f"{event.overtaken_train_id}在{event.overtaking_station_name}未标记越行"
        
        assert overtaking_entry.waiting_time >= 240, \
            f"等待时间不足: {overtaking_entry.waiting_time}秒 < 240秒"
        
        assert overtaking_entry.overtaken_by == event.overtaking_train_id, \
            f"越行车次不匹配: {overtaking_entry.overtaken_by} != {event.overtaking_train_id}"
        
        print(f"✅ 越行事件验证通过: {event.overtaking_train_id} 越行 {event.overtaken_train_id}")

verify_overtaking_propagation(timetable)
```

---

## 💡 常见问题

**Q1: V3架构改造后性能有影响吗？**

A: 启动阶段增加了PathStationIndex构建时间（~1-2秒），但运行时通过索引加速查询（O(1)），整体性能无明显下降。

**Q2: 如何确认系统使用的是V3架构？**

A: 查看启动日志，如果有 `[PathStationIndex] 完成！` 表示V3架构已启用。

**Q3: 旧版数据是否兼容？**

A: 兼容。V3设计了回退机制，当PathStationIndex不可用时会回退到旧版逻辑。

**Q4: 如果发现站台码错误怎么办？**

A: 不会发生。V3架构在convert_timetable_to_solution阶段有严格验证，一旦检测到不一致会报错并拒绝生成RouteSolution。

**Q5: 如何调试PathStationIndex？**

A: 使用 `path_index.debug_print()` 方法打印详细信息。

---

## 🎯 下一步建议

1. **基础验证**: 运行系统 → 检查日志 → 查看Excel输出
2. **深度验证**: 运行"进阶测试"脚本，确认对齐和越行传播
3. **集成测试**: 测试1086/1088等典型线路，对比改造前后差异

---

**需要帮助？** 请查看 [V3_IMPLEMENTATION_SUMMARY.md](V3_IMPLEMENTATION_SUMMARY.md) 的"问题排查清单"部分。

