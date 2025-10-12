# 快车跳站功能修复

## 问题描述

用户反馈：修复后的版本所有车次都变成慢车了，所有车次都在每个站停靠，没有实现快车的效果。

## 根本原因

在`_should_stop_at_destcode`方法中，快车的跳站逻辑只是简单返回`True`：

```python
# 对于快车，检查跳站设置
if isinstance(train, ExpressTrain):
    # 暂时简化处理：假设中间站都停
    return True  # ← 问题：快车所有站都停！
```

**结果**：快车不跳站，所有站都停 = 变成慢车

---

## 修复方案

### 实现真正的跳站逻辑

```python
def _should_stop_at_destcode(self, train: Train, dest_code: str, index: int, total: int) -> bool:
    """判断列车是否在指定站台码停站"""
    
    # 首末站（折返轨）不停站
    if index == 0 or index == total - 1:
        if dest_code.endswith('1') or dest_code.endswith('2') or dest_code.endswith('3'):
            if len(dest_code) == 3:
                return False
    
    # 对于快车，检查跳站设置
    if isinstance(train, ExpressTrain):
        # 【关键修复】根据dest_code查找对应的车站ID
        station_id = self._get_station_id_from_destcode(dest_code)
        
        if station_id:
            # 检查该车站是否在跳站列表中
            if station_id in train.skip_stations:
                return False  # 快车跳过该站
            else:
                return True  # 快车停靠该站
        else:
            # 找不到对应车站，默认停站
            return True
    
    # 慢车全部停站（除了折返轨）
    return True
```

### 新增辅助方法

```python
def _get_station_id_from_destcode(self, dest_code: str) -> Optional[str]:
    """
    根据站台目的地码查找对应的车站ID
    
    建立dest_code到station_id的映射
    """
    # 遍历所有车站，查找包含该dest_code的站台
    for station_id, station in self.rail_info.stationList.items():
        for platform in station.platformList:
            if hasattr(platform, 'dest_code') and platform.dest_code == dest_code:
                return station.id
    
    # 找不到对应的车站
    return None
```

---

## 执行逻辑

### 示例：快车E001，跳站列表 = {12, 13, 15, 16, ...}

```
遍历path.nodeList:
  ├─ 111（折返轨I道）
  │   └─ index=0 → 折返轨，不停站 ✓
  │
  ├─ 114（梅溪湖西站上行，车站11）
  │   ├─ _get_station_id_from_destcode("114") → "11"
  │   ├─ "11" in skip_stations? → No
  │   └─ 停站 ✓
  │
  ├─ 122（麓云路站上行，车站12）
  │   ├─ _get_station_id_from_destcode("122") → "12"
  │   ├─ "12" in skip_stations? → Yes
  │   └─ 跳站！✓ （快车效果）
  │
  ├─ 132（文化艺术中心站上行，车站13）
  │   ├─ _get_station_id_from_destcode("132") → "13"
  │   ├─ "13" in skip_stations? → Yes
  │   └─ 跳站！✓
  │
  ├─ 142（梅溪湖东站上行，车站14）
  │   ├─ _get_station_id_from_destcode("142") → "14"
  │   ├─ "14" in skip_stations? → No
  │   └─ 停站 ✓
  │
  └─ ... 以此类推
```

---

## 关键设计

### 设计1：dest_code到station_id的映射

**问题**：path.nodeList是站台码（如114, 122, 132），train.skip_stations是车站ID（如11, 12, 13）

**解决**：通过`_get_station_id_from_destcode`建立映射
- 遍历所有车站的所有站台
- 找到dest_code匹配的站台
- 返回该站台所属的车站ID

### 设计2：快车跳站时的处理

**关键**：快车跳站时，仍然要调用`rs.addStop()`，但停站时间=0

```python
if is_stop:
    dwell_time = self.default_dwell_time  # 停站30秒
else:
    dwell_time = 0  # 跳站，停站时间=0

rs.addStop(
    platform=dest_code,  # 站台码仍然要添加
    stop_time=dwell_time,  # 跳站时=0
    ...
)
```

**原因**：
- Excel要求：所有站台码必须存在（与path.nodeList一致）
- 跳站表示：停站时间=0，到站时间=离站时间

---

## 预期结果

### 慢车（LocalTrain）

```
| 车次 | 站台码 | 到站时间 | 离站时间 | 停站时间 | 是否停站 |
|------|--------|----------|----------|----------|----------|
| L001 | 111    | 23400    | 23400    | 0        | 否（折返轨）|
| L001 | 114    | 23400    | 23430    | 30       | 是       |
| L001 | 122    | 23550    | 23580    | 30       | 是       |
| L001 | 132    | 23700    | 23730    | 30       | 是       |
| L001 | 142    | 23850    | 23880    | 30       | 是       |
| ...  | ...    | ...      | ...      | ...      | ...      |
```

### 快车（ExpressTrain）

```
| 车次 | 站台码 | 到站时间 | 离站时间 | 停站时间 | 是否停站 |
|------|--------|----------|----------|----------|----------|
| E001 | 111    | 23400    | 23400    | 0        | 否（折返轨）|
| E001 | 114    | 23400    | 23430    | 30       | 是       |
| E001 | 122    | 23530    | 23530    | 0        | 否（跳站）✓ |
| E001 | 132    | 23630    | 23630    | 0        | 否（跳站）✓ |
| E001 | 142    | 23730    | 23760    | 30       | 是       |
| ...  | ...    | ...      | ...      | ...      | ...      |
```

**关键差异**：
- ✅ 快车跳站时，停站时间=0
- ✅ 快车跳站时，到站时间=离站时间
- ✅ 快车跳站的站台码仍然存在（与path.nodeList一致）

---

## 文件修改清单

1. ✅ `express_local_V3/main.py`
   - 修改`_should_stop_at_destcode`：实现真正的跳站逻辑（第520-556行）
   - 新增`_get_station_id_from_destcode`：建立dest_code到station_id映射（第558-575行）

2. ✅ 创建本文档
   - 记录跳站功能修复
   - 说明执行逻辑

---

## 验证方法

### 方法1：检查Excel输出

1. 查找快车车次（E001, E002...）
2. 检查停站时间列
3. 应该有部分站台停站时间=0（跳站）

### 方法2：统计停站数

```python
# 慢车停站数（除去首末站折返轨）
慢车停站数 = 路径站台数 - 2（折返轨）= 25 - 2 = 23

# 快车停站数（除去首末站折返轨和跳站）
快车停站数 = 慢车停站数 - 跳站数
```

### 方法3：查看日志

运行时应该输出：
```
[DEBUG] 车次E001，站台122，跳站
[DEBUG] 车次E001，站台132，跳站
[DEBUG] 车次E001，站台142，停站
```

---

## 修复日期

2025-10-12

## 修复人员

AI Assistant (Claude Sonnet 4.5)

