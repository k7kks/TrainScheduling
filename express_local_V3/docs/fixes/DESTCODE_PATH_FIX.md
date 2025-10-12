# 站台码与Path的DestcodesOfPath一致性修复

## 问题描述

用户反馈：生成的Excel中，101车次（路径编号1086）的站台码与XML输入文件中的`DestcodesOfPath`的顺序和内容都不一致。

### XML中的定义

```xml
<Path>
  <Id>1086</Id>
  <Name>梅溪湖西站折返轨I道--光达站折返轨I道</Name>
  <RouteId>52</RouteId>
  <Direction>Right</Direction>
  <DestcodesOfPath>
    <Destcode>111</Destcode>
    <Destcode>114</Destcode>
    <Destcode>122</Destcode>
    <Destcode>132</Destcode>
    <!-- ... 共25个站台码 ... -->
    <Destcode>333</Destcode>
  </DestcodesOfPath>
</Path>
```

### 预期vs实际

- **预期**：Excel中101车次的站台码应该是：111, 114, 122, 132, 142, 154, 162, 172, 184, 192, 202, 212, 222, 232, 242, 252, 262, 274, 282, 292, 302, 312, 322, 332, 333
- **实际**：生成的Excel中站台码与上述顺序和内容不一致

---

## 根本原因分析

### 原因1：未使用Path的nodeList

**代码逻辑错误**：
1. `main.py`的`_create_route_solution_from_train`方法接收了`path`参数
2. 但在添加停站时，使用的是`entry.dest_code`（从Station的Platform获取）
3. **没有使用`path.nodeList`**（这才是XML中的`DestcodesOfPath`）

**问题**：
- `entry.dest_code`：从每个Station的Platform中根据方向单独获取
- `path.nodeList`：XML中该路径的完整站台码序列
- **两者可能不一致！**

### 原因2：下行列车的车站顺序错误

**代码逻辑错误**：
1. `timetable_builder.py`按公里标（centerKp）升序排列车站
2. 这个顺序只适用于上行列车
3. **下行列车应该按公里标降序（反向行驶）**
4. 但代码没有根据列车方向调整车站顺序

**问题**：
- 上行列车：车站1→车站2→...→车站N（按公里标升序）✓
- 下行列车：车站N→...→车站2→车站1（应按公里标降序）✗
- 结果：下行列车的entries顺序与path.nodeList相反

---

## 修复方案

### 修复1：使用Path的nodeList作为站台码序列

**文件**：`express_local_V3/main.py`

**位置**：`_create_route_solution_from_train`方法（约533-570行）

**修改内容**：

```python
# 修改前：使用entry.dest_code（从Station获取）
for entry in entries:
    platform_code = entry.dest_code if entry.dest_code else entry.station_id
    rs.addStop(platform=platform_code, ...)

# 修改后：使用path.nodeList（XML的DestcodesOfPath）
path_destcodes = path.nodeList  # 路径的完整站台码列表

# 确保entries和path_destcodes数量一致
if len(entries) != len(path_destcodes):
    print(f"[WARNING] 列车{train.train_id}的时刻表条目数({len(entries)})与路径{route_id}的站台数({len(path_destcodes)})不一致")
    min_len = min(len(entries), len(path_destcodes))
    entries = entries[:min_len]
    path_destcodes = path_destcodes[:min_len]

# 使用path.nodeList中的站台码
for i, (entry, platform_code) in enumerate(zip(entries, path_destcodes)):
    rs.addStop(platform=platform_code, ...)  # 使用path.nodeList中的站台码
```

**关键点**：
1. 直接从`path.nodeList`获取站台码序列
2. 使用`zip(entries, path_destcodes)`确保一一对应
3. 添加数量不一致的检查和对齐逻辑

### 修复2：下行列车车站顺序反转

**文件**：`express_local_V3/algorithms/timetable_builder.py`

**位置**：`_get_train_stations`方法（约152-182行）

**修改内容**：

```python
def _get_train_stations(self, train: Train) -> List[Station]:
    """
    获取列车经过的车站列表
    
    Returns:
        车站列表（按列车行驶方向排序）
    """
    # 获取基础车站列表
    stations = self.stations.copy()
    
    # 如果是小交路，只走部分站
    if isinstance(train, LocalTrain) and train.is_short_route:
        if train.turnback_station:
            turnback_idx = next(
                (i for i, s in enumerate(stations) 
                 if s.id == train.turnback_station),
                len(stations) // 2
            )
            stations = stations[:turnback_idx+1]
    
    # 【关键修复】如果是下行列车，车站顺序需要反转
    # self.stations是按公里标升序排列（上行方向）
    # 下行列车应该按公里标降序（反向行驶）
    if train.direction == "下行":
        stations = list(reversed(stations))
    
    return stations
```

**关键点**：
1. 对于下行列车，使用`reversed()`反转车站列表
2. 确保entries的顺序与path.nodeList一致

---

## 数据流图（修复后）

```
XML文件
  └─ <Path>
      └─ <DestcodesOfPath>
          └─ [111, 114, 122, ..., 333]
          ↓
src/DataReader.py
  └─ 读取DestcodesOfPath
  └─ 存储到 path.nodeList
          ↓
src/Path.py
  └─ path.nodeList = [111, 114, 122, ..., 333]
          ↓
express_local_V3/main.py
  └─ convert_timetable_to_solution()
      ├─ 获取 path = self.rail_info.pathList[route_id]
      └─ 传递给 _create_route_solution_from_train(train, entries, route_id, path)
          ↓
express_local_V3/main.py
  └─ _create_route_solution_from_train()
      ├─ path_destcodes = path.nodeList  ← 【修复点1】直接使用path.nodeList
      └─ for entry, platform_code in zip(entries, path_destcodes):
              rs.addStop(platform=platform_code, ...)
          ↓
express_local_V3/algorithms/timetable_builder.py
  └─ _get_train_stations()
      ├─ stations = self.stations.copy()
      └─ if train.direction == "下行":  ← 【修复点2】下行反转
              stations = list(reversed(stations))
          ↓
src/RouteSolution.py
  └─ platform_list = [111, 114, 122, ..., 333]  ← 与XML完全一致
          ↓
Excel输出（站台目的地码列）
  └─ 101车次：111, 114, 122, 132, 142, ...  ← 与XML一致 ✓
```

---

## 修复验证

### 验证点1：路径1086的站台码序列

**XML定义**（25个站台码）：
```
111, 114, 122, 132, 142, 154, 162, 172, 184, 192, 202, 212, 222, 232, 242, 252, 262, 274, 282, 292, 302, 312, 322, 332, 333
```

**Excel输出**（应完全一致）：
- 101车次（路径1086）的站台码应该与上述序列完全一致

### 验证点2：上下行列车使用不同路径

**上行列车**：
- 使用路径1086（或其他上行路径）
- 站台码：111, 114, 122, ...（正序）

**下行列车**：
- 使用路径1088（或其他下行路径）
- 站台码：333, 332, 322, ...（反序）

### 验证点3：快车跳站

**快车跳站时**：
- 仍然包含所有站台码（与path.nodeList一致）
- 跳站的到站时间=离站时间（停站时间=0）
- 不会遗漏任何站台码

---

## 关键设计原则

### 原则1：路径是站台码序列的唯一来源

**正确做法**：
- 列车使用某个路径时，站台码序列必须来自该路径的`nodeList`
- `path.nodeList`就是XML中的`DestcodesOfPath`

**错误做法**（之前的实现）：
- 从Station的Platform中根据方向单独获取dest_code
- 这样获取的站台码可能与path.nodeList不一致

### 原则2：车站顺序必须与路径方向一致

**正确做法**：
- 上行列车：车站按公里标升序
- 下行列车：车站按公里标降序
- 确保entries的顺序与path.nodeList一致

**错误做法**（之前的实现）：
- 所有列车都按公里标升序排列车站
- 导致下行列车的entries顺序与path.nodeList相反

### 原则3：快车和慢车使用相同路径时站台码必须一致

**要求**：
- 如果快车和慢车使用相同的路径编号
- 必须包含相同数量和顺序的站台码
- 快车跳站时，到站=离站（停站时间=0），而不是不添加该站台

---

## 文件修改清单

1. ✅ `express_local_V3/main.py`
   - 修改`_create_route_solution_from_train`方法
   - 使用`path.nodeList`作为站台码序列
   - 添加entries与path_destcodes数量一致性检查

2. ✅ `express_local_V3/algorithms/timetable_builder.py`
   - 修改`_get_train_stations`方法
   - 下行列车车站顺序反转

3. ✅ 创建本文档
   - 记录问题根因
   - 说明修复方案
   - 提供验证方法

---

## 与src代码的一致性

本次修复**完全兼容**src文件夹的代码：

1. **数据读取**：使用src/DataReader.py读取XML
2. **数据结构**：使用src/Path.py的nodeList属性
3. **输出格式**：使用src/RouteSolution.py的addStop方法
4. **Excel输出**：使用src/Solution.py的writeExcel方法

**不修改src文件夹任何代码**，只修改express_local_V3文件夹。

---

## 修复日期

2025-10-12

## 修复人员

AI Assistant (Claude Sonnet 4.5)

---

## 后续建议

1. ✅ 运行测试，验证101车次的站台码与XML一致
2. 验证上行和下行列车都使用正确的路径和站台码
3. 验证快车跳站时仍包含所有站台码
4. 如果有多条交路，验证每条交路的路径都正确

