# V3架构改造设计文档 - PathStationIndex核心方案

**创建日期**: 2025-10-13  
**版本**: V3.0  
**状态**: 实施完成（阶段1-4）

---

## 1. 改造背景

### 问题症结

1. **站台码与路径脱节**: `convert_timetable_to_solution` 在 `timetable_entries` 比 `path.nodeList` 少时走回退分支，忽略越行对停站时间的改写
2. **虚拟节点站台码混用**: `_adjust_entries_to_path` 用 `dest_code` 充当 `station_id` 的占位 entry，导致 TimetableBuilder 在按 `station_id` 查找越行配对时失配
3. **索引对齐失效**: 一旦改成按 `station_id` 映射，站台码又会和 path 顺序脱节

### 根因分析

| 问题 | 根因 | 影响 |
|------|------|------|
| 站台码错误 | 中心里程排序 vs path.nodeList顺序不一致 | RouteSolution站台序列与XML不符 |
| 越行失配 | 虚拟节点用dest_code作station_id，但越行检测用station_id匹配 | 越行调整无法精确应用到对应entry |
| 时刻丢失 | 回退分支重新计算时间，覆盖越行调整结果 | 越行等待时间未透传到Excel |

---

## 2. 设计目标

| 目标 | 验收标准 |
|------|----------|
| 站台码100%对齐 | `rs.stopped_platforms == path.nodeList` |
| 越行调整完整保留 | Excel中 `is_overtaking=是` 且 `waiting_time>0` |
| 列控约束兼容 | 到通间隔≥120s，通发间隔≥120s，总停站≥240s |
| 增量实施 | 仅在express_local_V3目录改造，保持其余模块无感 |

---

## 3. 核心架构设计

### 3.1 PathStationIndex - 路径站点索引系统

**数据模型**：

```python
@dataclass
class PathStationNode:
    path_index: int                # 路径顺序（0-based）【主键】
    dest_code: str                 # 站台目的地码【输出标识】
    station_id: Optional[str]      # 真实车站ID（虚拟节点可为None）
    station_name: Optional[str]    # 车站名称
    direction: Optional[str]       # 方向标记
    is_virtual: bool = False       # 是否为虚拟节点（折返轨等）

class PathStationIndex:
    route_id: str
    nodes: List[PathStationNode]
    _path_index_to_node: Dict[int, PathStationNode]
    _dest_code_to_node: Dict[str, PathStationNode]
    _station_id_to_nodes: Dict[str, List[PathStationNode]]
```

**核心功能**：

1. **精确映射**: 提供 `path_index <-> dest_code <-> station_id` 三维映射
2. **虚拟节点标记**: 区分真实车站与折返轨/出入库
3. **顺序保证**: `path_index` 严格对应 `path.nodeList` 的顺序
4. **验证机制**: 检查 `path_index` 连续性、`dest_code` 唯一性

**构建流程**：

```
rail_info.pathList
  └─> build_path_station_index_from_path()
      ├─ 遍历 path.nodeList
      ├─ 通过 platform_station_map 查找 station_id
      ├─ 标记虚拟节点（station_id为None）
      └─ 构建索引缓存 {route_id: PathStationIndex}
```

### 3.2 TimetableEntry扩展

**新增字段**：

```python
@dataclass
class TimetableEntry:
    # 原有字段...
    
    # 【NEW】路径索引对齐字段
    path_index: Optional[int] = None        # 在路径中的顺序索引
    direction_hint: Optional[str] = None    # 方向提示
```

**作用**：

- `path_index`: 作为与 PathStationIndex 对齐的主键
- `direction_hint`: 辅助越行检测方向匹配

### 3.3 TimetableBuilder改造

#### 3.3.1 初始化阶段

```python
class TimetableBuilder:
    def __init__(self, rail_info, enable_overtaking=True):
        # ... 原有初始化 ...
        
        # 【NEW】构建PathStationIndex缓存
        self.path_station_indexes: Dict[str, PathStationIndex] = {}
        self._build_path_station_indexes()
```

#### 3.3.2 时刻表构建

**改造前**：

```python
def _build_train_schedule(self, train):
    train_stations = self._get_train_stations(train)  # 按center_mileage排序
    for i, station in enumerate(train_stations):
        # ... 逐站计算
```

**改造后**：

```python
def _build_train_schedule(self, train):
    path_index = self.path_station_indexes.get(train.route_id)
    
    for node in path_index.nodes:  # 【关键】按path_index顺序遍历
        entry = TimetableEntry(
            # ... 时刻计算 ...
            path_index=node.path_index,  # 【NEW】记录索引
            dest_code=node.dest_code,
            station_id=node.station_id or node.dest_code
        )
```

**优势**：

1. 生成的 entries 顺序与 path.nodeList 严格一致
2. 虚拟节点自动处理（`station_id=None` 时用 `dest_code`）
3. 每个 entry 携带 `path_index`，便于后续索引

#### 3.3.3 越行检测改造

**改造前**：

```python
def _apply_overtaking(self, local_entries, express_entries, ...):
    local_entry = local_entries[overtaking_station_idx]
    
    # 通过station_id匹配（失配风险）
    for e in express_entries:
        if e.station_id == local_entry.station_id:
            express_entry = e
            break
```

**改造后**：

```python
def _apply_overtaking(self, local_entries, express_entries, ...):
    local_entry = local_entries[overtaking_station_idx]
    
    # 【关键】通过path_index精确匹配
    if local_entry.path_index is not None:
        for e in express_entries:
            if e.path_index == local_entry.path_index:
                express_entry = e
                break
```

**优势**：

1. 避免虚拟节点 `station_id=dest_code` 导致的失配
2. 确保快慢车在路径同一位置进行越行调整
3. 兼容旧逻辑（`path_index=None` 时回退到 `station_id` 匹配）

### 3.4 RouteSolution改造

#### 3.4.1 严格索引模式

**改造前**：

```python
for i, dest_code in enumerate(path_destcodes):
    if i < len(timetable_entries):
        entry = timetable_entries[i]
        # ... 使用entry时刻
    else:
        # 【问题】回退计算，忽略越行调整
        arrival_time = current_time + running_time
```

**改造后**：

```python
# 【V3架构】强制对齐检查
if len(timetable_entries) != len(path_destcodes):
    print(f"[错误] 禁止自动补齐，请检查TimetableBuilder逻辑！")
    return None

# 严格按索引遍历
for i, dest_code in enumerate(path_destcodes):
    entry = timetable_entries[i]  # 必定存在
    rs.addStop(
        platform=dest_code,  # 使用path的dest_code
        current_time=entry.arrival_time,  # 使用entry的时刻（含越行调整）
        # ...
    )
```

**关键原则**：

1. **禁止回退计算**: 一旦数量不一致立即报错
2. **倒逼数据对齐**: 强制 TimetableBuilder 生成完整 entries
3. **保留越行调整**: 完整使用 entry 中的时刻信息

#### 3.4.2 验证机制

```python
# 严格验证站台码
if rs.stopped_platforms != path_destcodes:
    print(f"[FATAL] 车次{train.train_id}站台码验证失败！")
    return None
```

### 3.5 废弃的旧逻辑

| 方法 | 废弃原因 | 替代方案 |
|------|----------|----------|
| `_adjust_entries_to_path` | 自动补齐破坏越行时刻 | PathStationIndex预生成完整entries |
| `_get_train_stations` (center_mileage排序) | 顺序与path脱节 | PathStationIndex.nodes顺序 |
| station_id越行匹配 | 虚拟节点失配 | path_index精确匹配 |

---

## 4. 数据流示意图

```
┌─────────────────────────────────────────────────────────────────┐
│ 启动阶段                                                          │
└─────────────────────────────────────────────────────────────────┘
    rail_info.pathList
         │
         ├─> build_path_station_index_from_path()
         │
    PathStationIndex Cache
    {route_id: PathStationIndex}

┌─────────────────────────────────────────────────────────────────┐
│ 时刻表构建阶段                                                     │
└─────────────────────────────────────────────────────────────────┘
    TimetableBuilder
         │
         ├─> _build_train_schedule(train)
         │       │
         │       ├─ 获取 path_station_indexes[train.route_id]
         │       │
         │       └─ 按 PathStationIndex.nodes 顺序遍历
         │           └─> 生成 TimetableEntry (含 path_index)
         │
         ├─> _apply_overtaking(...)
         │       │
         │       └─ 通过 path_index 精确匹配快慢车entry
         │           └─> 调整 departure_time, dwell_time, waiting_time
         │
    ExpressLocalTimetable (entries按path_index顺序)

┌─────────────────────────────────────────────────────────────────┐
│ RouteSolution转换阶段                                             │
└─────────────────────────────────────────────────────────────────┘
    convert_timetable_to_solution
         │
         ├─> 严格检查 len(entries) == len(path.nodeList)
         │
         ├─> 按索引遍历:
         │   for i, dest_code in enumerate(path.nodeList):
         │       entry = entries[i]  # 必定存在
         │       rs.addStop(dest_code, entry.arrival_time, ...)
         │
         └─> 验证 rs.stopped_platforms == path.nodeList
         
    RouteSolution (站台码100%对齐，越行时刻完整保留)

┌─────────────────────────────────────────────────────────────────┐
│ Excel输出阶段                                                      │
└─────────────────────────────────────────────────────────────────┘
    ExcelExporter
         │
         └─> 列车时刻表工作表
             ├─ 站台目的地码: entry.dest_code
             ├─ 是否越行: entry.is_overtaking
             ├─ 被越行车次: entry.overtaken_by
             └─ 等待时间(秒): entry.waiting_time
```

---

## 5. 实施状态

### 已完成阶段（✅）

#### 阶段1：数据基座重建

- ✅ 创建 `PathStationIndex` 和 `PathStationNode` 模型
- ✅ 实现 `build_path_station_index_from_path()` 构建函数
- ✅ 扩展 `TimetableEntry` 新增 `path_index` 和 `direction_hint` 字段
- ✅ 更新 `models/__init__.py` 导出新模型

#### 阶段2：TimetableBuilder改造

- ✅ 在 `__init__` 中构建 `path_station_indexes` 缓存
- ✅ 重写 `_build_train_schedule` 按 PathStationIndex 遍历
- ✅ 新增 `_get_section_running_time_by_destcode` 方法
- ✅ 改造 `_apply_overtaking` 使用 `path_index` 精确匹配

#### 阶段3：RouteSolution改造

- ✅ 重写 `convert_timetable_to_solution` 为严格索引模式
- ✅ 禁止回退计算，强制 entries 与 path 数量一致
- ✅ 增加站台码验证 `rs.stopped_platforms == path.nodeList`
- ✅ 废弃 `_adjust_entries_to_path` 方法

#### 阶段4：输出层验证

- ✅ 确认 ExcelExporter 已支持越行字段输出
  - `is_overtaking`: 是否越行
  - `overtaken_by`: 被越行车次
  - `waiting_time`: 等待时间（秒）

### 待完成阶段（⏳）

#### 阶段5：单元测试

- ⏳ 创建 `tests/test_path_station_index.py`
  - 测试 PathStationIndex 构建
  - 测试虚拟节点标记
  - 测试索引验证

- ⏳ 创建 `tests/test_timetable_builder_v3.py`
  - 测试 path 顺序生成
  - 测试越行 path_index 匹配
  - 测试回退逻辑兼容性

- ⏳ 创建 `tests/test_route_solution_v3.py`
  - 测试站台码对齐
  - 测试越行时刻保留
  - 测试数量不一致报错

#### 阶段6：集成测试

- ⏳ 运行典型线路（1086/1088）
- ⏳ 对比改造前后 Excel 输出
  - 站台序列一致性
  - 越行等待字段完整性
- ⏳ 日志分析确认无 `[WARNING]` 或 `[ERROR]`

---

## 6. 风险与缓解措施

### 风险1：旧数据不兼容

**症状**: path 中含虚拟 dest_code，无法匹配到 station

**缓解**:
- PathStationIndex 自动标记为虚拟节点（`is_virtual=True`）
- TimetableBuilder 在虚拟节点使用 `dest_code` 作为 `station_id`

### 风险2：path数据质量问题

**症状**: path.nodeList 与实际车站不一致

**缓解**:
- PathStationIndex.validate() 验证连续性和唯一性
- convert_timetable_to_solution 强制对齐检查，禁止自动补齐

### 风险3：性能影响

**症状**: 构建 PathStationIndex 缓存增加启动时间

**缓解**:
- 只在 TimetableBuilder 初始化时构建一次
- 索引使用 Dict 加速查询（O(1)复杂度）

---

## 7. 验证清单

### 功能验证

- [ ] 运行 `main.py` 无报错
- [ ] Excel 中所有列车的站台序列 == path.nodeList
- [ ] 越行事件工作表中有数据
- [ ] 列车时刻表中 `is_overtaking=是` 的行 `waiting_time>0`

### 性能验证

- [ ] 启动时间增加 < 10%
- [ ] 内存占用增加 < 20%

### 兼容性验证

- [ ] 旧版测试用例通过（回退逻辑）
- [ ] 新增测试用例通过（path_index逻辑）

---

## 8. 后续优化建议

1. **区间运行时间优化**: `_get_section_running_time_by_destcode` 从 rail_info 查询实际值
2. **可视化增强**: 运行图中标注越行事件
3. **配置化越行站**: 允许用户在配置文件中指定越行站
4. **多线程构建**: PathStationIndex 构建可并行化

---

## 9. 参考文档

| 文档 | 位置 | 说明 |
|------|------|------|
| 站台码修复 | `docs/fixes/DESTCODE_PATH_FIX.md:64-96` | 原站台码问题分析 |
| 越行集成指南 | `docs/OVERTAKING_INTEGRATION_GUIDE.md:374-460` | 越行约束和测试框架 |
| 模型设计 | `docs/EXPRESS_LOCAL_MODEL_DESIGN.md:358-413` | TimetableBuilder设计原则 |

---

**版本历史**:
- V3.0 (2025-10-13): 初始版本，完成阶段1-4

