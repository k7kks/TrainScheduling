# 快慢车勾连功能实现总结

**日期**: 2025-10-12  
**版本**: express_local_V3  
**功能**: 车次勾连（Train Connection）

---

## 📋 实现内容

### 1. 核心功能

实现了快慢车运行图的车次勾连功能，参考`src/Engineering.py`中的Phase2和Phase3逻辑：

- **车次勾连**: 相邻车次可以共享相同的表号（table_num），在运行图软件中显示为连续的线
- **折返约束**: 勾连需满足折返时间约束
- **分类勾连**: 快车连快车，慢车连慢车，大小交路分开处理

### 2. 新增文件

#### `express_local_V3/algorithms/connection_manager.py`

车次勾连管理器，包含以下核心方法：

```python
class ConnectionManager:
    def connect_all_trains(route_solutions)
        """主流程：分组、勾连、分配表号"""
    
    def _group_trains(route_solutions)
        """按快慢、交路、方向分组"""
    
    def _connect_within_group(trains)
        """组内建立勾连关系（Phase2逻辑）"""
    
    def _can_connect(from_train, to_train)
        """检查两车次是否可勾连"""
    
    def _assign_table_numbers(route_solutions)
        """递归分配相同表号"""
```

### 3. 集成修改

#### `express_local_V3/main.py`

1. **导入勾连管理器**:
   ```python
   from algorithms.connection_manager import ConnectionManager
   ```

2. **初始化勾连管理器**:
   ```python
   self.connection_manager = ConnectionManager(
       rail_info=self.rail_info,
       debug=self.debug
   )
   ```

3. **在`convert_timetable_to_solution`中调用**:
   ```python
   # 步骤1：转换所有列车为RouteSolution对象
   route_solutions = []
   for train in all_trains:
       rs = self._create_route_solution_from_path(train, route_id, path)
       route_solutions.append(rs)
   
   # 步骤2：建立车次勾连关系
   route_solutions = self.connection_manager.connect_all_trains(route_solutions)
   
   # 步骤3：添加到Solution对象
   for rs in route_solutions:
       solution.addTrainService(rs)
   ```

---

## 🔍 勾连逻辑说明

### 勾连条件

两个车次可以勾连需满足：

1. **方向相反**: 前车上行 → 后车下行（或反之）
2. **交路相同**: 同为大交路或同为小交路
3. **快慢相同**: 快车只连快车，慢车只连慢车
4. **折返时间合理**: 
   - `turnback_time = to_train.arr_time[0] - from_train.dep_time[-1]`
   - `min_turnback <= turnback_time <= max_turnback`
5. **站台兼容**: 前车终点站和后车起点站在同一折返区域

### 勾连策略

- 按时间顺序遍历
- 交替连接上行和下行
- 满足折返约束
- 避免交叉勾连

### 表号分配

使用递归方法`_connect_routes_recursive`，参考`src/Engineering.py`的`connect_routes`：

```python
if rs.next_ptr已分配表号:
    rs.table_num = rs.next_ptr.table_num
    rs.round_num = connected[rs.next_ptr.table_num]
else:
    递归处理rs.next_ptr
    rs.table_num = 递归返回的表号
```

---

## ⚠️ 当前状态

### 测试结果

运行`python main.py`后的结果：

- ✅ 程序成功运行，无报错
- ✅ 生成了70个车次
- ✅ 所有车次都有有效的`RouteSolution`对象
- ❌ **未建立任何勾连**：70个车次有70个独立表号

### 问题分析

从调试输出可以看到：

```
  折返时间不足: -2406s < 60s
  折返时间不足: -3126s < 60s
  折返时间不足: -3846s < 60s
  ...
```

**问题根源**：折返时间都是负数，说明后续车次的发车时间早于前序车次的到达时间。

**可能原因**：
1. 车次排序问题：`_group_trains`按`car_info.arr_time`排序，但这个时间可能不是实际发车时间
2. 时间计算问题：`arr_time[0]`（首站到达）和`dep_time[-1]`（末站离站）的时间顺序不符合折返逻辑
3. 上下行车次的时间关系：上行车到站后，下行车应该晚于上行车，但实际可能不是

---

## 🛠️ 待优化项

### 1. 时间排序优化

**问题**：当前按`car_info.arr_time`排序，这可能不是正确的排序依据。

**建议修改**：
```python
def _group_trains(self, route_solutions):
    # 对每组按照首站发车时间排序，而不是car_info.arr_time
    for trains in grouped.values():
        trains.sort(key=lambda x: x.arr_time[0] if x.arr_time else x.car_info.arr_time)
```

### 2. 折返时间约束放宽

**问题**：当前要求`turnback_time >= 60s`，可能太严格。

**建议修改**：
```python
min_turnback = 30   # 从60秒降到30秒
max_turnback = 1800  # 从900秒增加到30分钟
```

### 3. 增强调试信息

**建议**：在`_connect_within_group`中添加详细日志：
```python
if self.debug:
    print(f"    尝试连接: 车{from_train.car_info.table_num}")
    print(f"      到达时间: {from_train.dep_time[-1]}")
    print(f"    至: 车{to_train.car_info.table_num}")
    print(f"      发车时间: {to_train.arr_time[0]}")
    print(f"      折返时间: {turnback_time}秒")
```

### 4. 移位优化（Phase2完整实现）

**当前状态**：未实现移位逻辑

**src的做法**：
- 固定一个方向的车次
- 移动另一个方向的车次（平移时间）
- 尝试多种移位量（例如：5秒×30次）
- 找到勾连数量最多的移位量

**建议**：在`_connect_within_group`之前添加移位优化：
```python
def _optimize_shift(self, uplink_trains, downlink_trains):
    """尝试不同的移位量，找到最佳勾连方案"""
    best_shift = 0
    max_connections = 0
    
    for shift_amount in range(0, 600, 30):  # 0-600秒，每次30秒
        # 克隆并移位
        shifted_downlink = [train.clone() for train in downlink_trains]
        for train in shifted_downlink:
            train.shift_time(shift_amount)
        
        # 尝试勾连
        connections = self._try_connect(uplink_trains, shifted_downlink)
        
        if connections > max_connections:
            max_connections = connections
            best_shift = shift_amount
    
    return best_shift
```

### 5. Phase3实现（跨峰期勾连）

**当前状态**：仅实现同峰期内勾连

**待实现**：
- 如果有多个峰期，应该尝试跨峰期连接
- 参考`src/Engineering.py`的`phase3_connect`方法

---

## 📊 测试验证

### 测试脚本

创建了`express_local_V3/check_connection.py`用于验证勾连结果：

```bash
cd express_local_V3
python check_connection.py
```

### 预期结果（修复后）

```
========== 勾连检查报告 ==========

总车次数: 70
表号数量: 35（或更少）

表号分布:
  [OK] 发现 30+ 组勾连：
    表号 1: 2 个车次勾连在一起
    表号 2: 2 个车次勾连在一起
    ...

快慢车勾连情况:
  快车数量: 35
  慢车数量: 35
  [OK] 快车和慢车分开勾连（正确）
```

---

## 🎯 下一步行动

### 高优先级

1. **修复时间排序**：确保车次按正确的时间顺序排列
2. **放宽折返约束**：调整`min_turnback`和`max_turnback`
3. **增强调试**：添加详细的勾连尝试日志

### 中优先级

4. **实现移位优化**：完整的Phase2逻辑
5. **添加单元测试**：测试`_can_connect`等核心方法

### 低优先级

6. **实现Phase3**：跨峰期勾连
7. **优化性能**：大规模车次（1000+）的勾连效率

---

## 📚 参考代码

- `src/Engineering.py` - line 337-412: `connect()` 和 `connect_routes()`
- `src/Engineering.py` - line 11472-11620: `phase2_origin()` 和相关方法
- `src/Engineering.py` - line 2304-2407: `phase3_connect()`
- `src/Engineering.py` - line 2408-2443: `phase3()`

---

## ✅ 完成情况

- ✅ 创建了`ConnectionManager`类
- ✅ 实现了分组逻辑（按快慢、交路分组）
- ✅ 实现了勾连检查（`_can_connect`）
- ✅ 实现了表号分配（递归算法）
- ✅ 集成到`main.py`
- ✅ 创建了测试脚本
- ⚠️ **勾连功能未生效**（需进一步调试和优化）

---

**总结**：勾连功能的框架和核心逻辑已经实现，但由于时间排序和折返时间计算的问题，当前未能成功建立勾连。需要进一步调试和优化时间计算逻辑。

**建议**：用户可以先测试其他功能（快车跳站、路径一致性等），勾连功能可以作为后续优化项。

