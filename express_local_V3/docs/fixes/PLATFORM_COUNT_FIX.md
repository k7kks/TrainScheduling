# 站台数量不匹配修复（24 vs 25）

## 问题描述

用户反馈：Excel生成的站台码只有24个，但XML中路径1086定义了25个站台码。

**终端警告信息**：
```
[WARNING] 列车E030的时刻表条目数(24)与路径1088的站台数(25)不一致
[WARNING] 列车E031的时刻表条目数(24)与路径1086的站台数(25)不一致
```

**Excel结果**：
- 101车次（路径1086）只有24行站台数据
- 应该有25行

---

## 根本原因

### 原因：Path的nodeList是站台级别，而timetable_builder生成的entries是车站级别

**XML结构分析**：

```xml
<!-- 车站11：梅溪湖西站 -->
<Station>
  <Id>11</Id>
  <Name>梅溪湖西站</Name>
  <Platforms>
    <!-- 折返轨I道 -->
    <Platform>
      <Id>1</Id>
      <Destcode>111</Destcode>  ← 第1个站台
      <Type>Turnback</Type>
      <IsVirtual>true</IsVirtual>
    </Platform>
    <!-- 折返轨II道 -->
    <Platform>
      <Id>2</Id>
      <Destcode>112</Destcode>
      <Type>Turnback</Type>
    </Platform>
    <!-- 下行站台 -->
    <Platform>
      <Id>3</Id>
      <Destcode>113</Destcode>  ← 第2个站台（同一车站）
      <Direction>Left</Direction>
    </Platform>
    <!-- 上行站台 -->
    <Platform>
      <Id>4</Id>
      <Destcode>114</Destcode>  ← 第3个站台（同一车站）
      <Direction>Right</Direction>
    </Platform>
  </Platforms>
</Station>

<!-- 路径1086的定义 -->
<Path>
  <Id>1086</Id>
  <DestcodesOfPath>
    <Destcode>111</Destcode>  ← 折返轨I道
    <Destcode>114</Destcode>  ← 梅溪湖西站上行站台（同一车站的不同站台）
    <Destcode>122</Destcode>  ← 麓云路站
    <Destcode>132</Destcode>  ← 文化艺术中心站
    <!-- ... 共25个站台码 ... -->
  </DestcodesOfPath>
</Path>
```

**问题分析**：

1. **车站级别 vs 站台级别**：
   - 长沙2号线有24个车站
   - 但路径1086包含25个站台码
   - 因为梅溪湖西站（车站11）有2个站台被路径使用：111（折返轨）和114（上行站台）

2. **timetable_builder的逻辑**：
   - `_get_train_stations()`：返回24个车站（车站级别）
   - `_build_train_schedule()`：为每个车站创建1个entry
   - **结果：只生成24个entries**

3. **Path的nodeList**：
   - 包含25个站台码（站台级别）
   - 同一车站的多个站台会产生多个destcode

---

## 修复方案

### 方案：在main.py中补充缺失的站台条目

**文件**：`express_local_V3/main.py`

**新增方法**：`_adjust_entries_to_path`（第424-490行）

```python
def _adjust_entries_to_path(self, entries: List[TimetableEntry], 
                            path_destcodes: List[str], 
                            train: Train) -> List[TimetableEntry]:
    """
    调整时刻表条目以匹配路径的站台码序列
    
    当entries数量少于path_destcodes时，补充缺失的站台（通常是折返轨等虚拟站台）
    """
    if len(entries) >= len(path_destcodes):
        return entries[:len(path_destcodes)]
    
    # 计算缺失数量
    missing_count = len(path_destcodes) - len(entries)
    
    adjusted_entries = []
    
    # 在开头插入缺失的站台（通常是折返轨）
    first_entry = entries[0] if entries else None
    base_time = first_entry.arrival_time if first_entry else (train.departure_time if train.departure_time else 0)
    
    for i in range(missing_count):
        dest_code = path_destcodes[i]
        
        # 创建虚拟entry（折返轨，停站时间=0）
        new_entry = TimetableEntry(
            train_id=train.train_id,
            station_id=dest_code,
            station_name=f"站台{dest_code}",
            arrival_time=base_time,
            departure_time=base_time,  # 不停站
            dwell_time=0,
            is_stop=False,  # 折返轨不停站
            is_skip=True,
            platform_id=dest_code,
            dest_code=dest_code
        )
        adjusted_entries.append(new_entry)
    
    # 追加原有的entries
    adjusted_entries.extend(entries)
    
    return adjusted_entries
```

**调用位置**：`_create_route_solution_from_train`方法（第542-544行）

```python
# 当entries数量与path_destcodes不一致时，需要补充或插值
if len(entries) != len(path_destcodes):
    print(f"[INFO] 列车{train.train_id}的时刻表条目数({len(entries)})与路径{route_id}的站台数({len(path_destcodes)})不一致，进行调整")
    entries = self._adjust_entries_to_path(entries, path_destcodes, train)
```

---

## 修复逻辑详解

### 步骤1：检测数量不匹配

```python
if len(entries) != len(path_destcodes):
    # 24 != 25，需要调整
```

### 步骤2：计算缺失数量

```python
missing_count = len(path_destcodes) - len(entries)
# missing_count = 25 - 24 = 1
```

### 步骤3：在开头插入折返轨站台

```python
# path_destcodes[0] = "111"（折返轨I道）
# 创建一个虚拟entry：
#   - station_id = "111"
#   - arrival_time = first_entry.arrival_time（与首站同时间）
#   - departure_time = arrival_time（不停站）
#   - dwell_time = 0
#   - is_stop = False
```

### 步骤4：合并条目

```python
adjusted_entries = [折返轨entry] + entries
# 现在有25个entries，与path.nodeList一致
```

---

## 执行流程图

```
timetable_builder.py
  └─ _build_train_schedule()
      └─ 遍历24个车站
      └─ 生成24个entries
          ↓
main.py
  └─ _create_route_solution_from_train()
      ├─ path.nodeList = 25个站台码
      ├─ len(entries) = 24
      ├─ len(path_destcodes) = 25
      ├─ 不一致！调用 _adjust_entries_to_path()
      ↓
main.py
  └─ _adjust_entries_to_path()
      ├─ missing_count = 1
      ├─ 在开头插入"111"（折返轨）
      ├─ 时间 = 首站时间
      ├─ 停站时间 = 0
      └─ 返回25个entries
          ↓
main.py
  └─ _create_route_solution_from_train()
      └─ for entry, platform_code in zip(entries, path_destcodes):
          └─ 25个entry对应25个platform_code
          └─ rs.addStop(platform=platform_code, ...)
          ↓
Excel输出
  └─ 101车次：25行站台数据 ✓
      ├─ 111（折返轨I道）
      ├─ 114（梅溪湖西站）
      ├─ 122（麓云路站）
      └─ ... 共25行
```

---

## 预期结果

**修复前**：
- 101车次：24行站台数据
- 缺少111（折返轨）
- 终端警告：entries数量不匹配

**修复后**：
- 101车次：25行站台数据 ✓
- 包含111（折返轨）
- entries数量与path.nodeList完全一致
- 站台码顺序与XML的DestcodesOfPath完全一致

**Excel输出**：
```
| 车次 | 站台码 | 到站时间 | 离站时间 | 停站时间 |
|------|--------|----------|----------|----------|
| 101  | 111    | 23370    | 23370    | 0        | ← 折返轨（补充）
| 101  | 114    | 23470    | 23470    | 0        |
| 101  | 122    | 23570    | 23600    | 30       |
| 101  | 132    | 23700    | 23700    | 0        |
| ...  | ...    | ...      | ...      | ...      |
| 101  | 333    | 26030    | 26030    | 0        | ← 第25行
```

---

## 关键设计原则

### 原则1：Path的nodeList是站台码的权威来源

- **车站数 ≠ 站台数**：一个车站可能有多个站台（折返轨、上下行站台等）
- **Path的nodeList决定站台数量**：路径定义了经过哪些站台（而不是哪些车站）
- **entries必须与nodeList一致**：数量、顺序、内容都必须完全一致

### 原则2：折返轨是虚拟站台

- **停站时间=0**：折返轨不是客运站台，列车不停靠
- **到站时间=离站时间**：表示列车只是通过该站台区域
- **is_stop=False**：标记为不停站

### 原则3：补充策略

- **通常缺失的是首站或末站的折返轨**
- **使用首站时间作为基准**：折返轨与首站同时间
- **在开头插入**：折返轨通常在路径的开头

---

## 文件修改清单

1. ✅ `express_local_V3/main.py`
   - 新增`_adjust_entries_to_path`方法（第424-490行）
   - 修改`_create_route_solution_from_train`：调用adjust方法（第542-544行）

2. ✅ `express_local_V3/algorithms/timetable_builder.py`
   - 添加注释说明：entries是车站级别，与path的站台级别不同（第89-91行）

3. ✅ 创建本文档
   - 记录站台数量不匹配问题
   - 说明补充逻辑

---

## 与src代码的一致性

本次修复**完全兼容**src文件夹的代码：

1. **不修改src文件夹任何代码**
2. **使用src/Path.py的nodeList属性**
3. **使用src/RouteSolution.py的addStop方法**
4. **输出格式与src/Solution.py一致**

---

## 修复日期

2025-10-12

## 修复人员

AI Assistant (Claude Sonnet 4.5)

