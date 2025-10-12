# express_local_V3 更新说明

## 🔄 最新更新（2025-10-11）

### ✅ 已完成的修复

#### 1. **快车标志位修复**
- **问题**：计划线数据sheet中，"快车"列（F列）全部为0
- **要求**：快车应为1，慢车应为0
- **解决方案**：
  - 在`create_route_solution()`中为每个RouteSolution添加`is_express`属性
  - 在`write_output()`中调用`_patch_express_flag()`方法
  - 动态覆盖`retCSVStringPlanned_num()`方法，根据`is_express`返回正确的快车标志位

**实现代码：**
```python
# 在生成RouteSolution时标记
rs.is_express = is_express  # True为快车，False为慢车

# 在写Excel前动态修改返回值
def new_retCSVStringPlanned_num():
    components = [
        str(ci.table_num),
        str(ci.round_num),
        str(ci.route_num),
        str(dt[0]),
        "1",  # 自动车次号
        "1" if is_exp else "0",  # 快车标志：快车=1，慢车=0
        "1 1" if op else "0 1"
    ]
    return " ".join(components)
```

#### 2. **XLSX格式转换**
- **问题**：只生成xls文件，需要xlsx格式
- **要求**：参考src/main.py的convert_to_xlsx方法
- **解决方案**：
  - 从src/Engineering.py复制`convert_to_xlsx()`方法
  - 在`write_output()`中，生成xls后自动转换为xlsx
  - 使用pandas读取xls并用openpyxl写入xlsx

**实现流程：**
```python
1. 生成result.xls（调用Solution.writeExcel）
2. 读取result.xls的所有sheet
3. 写入result.xlsx（保持格式和列宽）
```

### 📊 输出文件

现在会生成两个文件：
- `result.xls` (117KB) - 原始格式
- `result.xlsx` (118KB) - 转换格式（推荐使用）

### 📋 计划线数据格式

| 列 | 字段名 | 说明 |
|----|--------|------|
| A | 表号 | 车辆编号 |
| B | 车次号 | 车次编号 |
| C | 路径编号 | 1086（大交路） |
| D | 发车时间 | 秒为单位 |
| E | 自动车次号 | 固定为1 |
| **F** | **快车** | **快车=1，慢车=0** ✅ |
| G | 载客 | 固定为1 |
| H | 列车编号 | 固定为1 |

### 🔍 验证结果

以50%快车比例为例（express_ratio=0.5）：
- 总车次：140列（上行70 + 下行70）
- 快车：70列（F列=1）
- 慢车：70列（F列=0）

**快车列车示例：**
```
表号  车次号  路径编号  发车时间  自动车次号  快车  载客  列车编号
1     101     1086      23400     1          1     1     1
2     202     1086      23760     1          1     1     1
3     303     1086      24120     1          1     1     1
...
```

**慢车列车示例：**
```
表号  车次号  路径编号  发车时间  自动车次号  快车  载客  列车编号
36    3636    1086      23580     1          0     1     1
37    3737    1086      23940     1          0     1     1
38    3838    1086      24300     1          0     1     1
...
```

### 🎯 技术实现亮点

1. **动态方法覆盖**：
   - 不修改src源代码
   - 通过Python的动态特性覆盖方法
   - 保持与src完全兼容

2. **闭包技术**：
   - 使用`make_method`工厂函数创建闭包
   - 确保每个RouteSolution有独立的方法实例
   - 正确捕获is_express、car_info等变量

3. **格式转换**：
   - 使用pandas+openpyxl实现xls→xlsx转换
   - 保持所有sheet页和列宽
   - 转换失败不影响主流程

### 📝 使用方法

```bash
# 运行程序（默认参数）
python express_local_V3/run.py

# 自定义快车比例
python express_local_V3/main.py --express_ratio 0.6

# 查看生成的文件
ls data/output_data/results_express_local_v3/
# result.xls   - 原始格式
# result.xlsx  - 推荐使用（可用Excel直接打开）
```

### ⚠️ 注意事项

1. **快车停站逻辑**：
   - 快车通过`time_early=30`参数控制停站
   - 只在停站时间>30秒的站停车
   - 慢车`time_early=0`，所有站都停

2. **快车判定**：
   - 根据生成顺序判定：先生成的35列为快车
   - 后生成的35列为慢车
   - 保证快慢车均匀分布

3. **文件格式**：
   - xls格式兼容性更好（老版本Excel）
   - xlsx格式更现代（推荐使用）
   - 两个文件内容完全一致

### 🔧 相关代码

修改的文件：
- `express_local_V3/main.py`（添加约100行代码）
  - `create_route_solution()`: 添加is_express标记（第269行）
  - `_patch_express_flag()`: 动态修改方法（第316-345行）
  - `convert_to_xlsx()`: XLS转XLSX（第347-387行）
  - `write_output()`: 增加转换调用（第305-306行）

### 📈 性能影响

- 生成时间：0.66秒 → 2.34秒
- 增加时间主要来自xlsx转换（约1.7秒）
- 对于140个车次的规模，性能完全可接受

### ✅ 测试结果

```
✅ 生成140个车次
✅ 快车70列（F列=1）
✅ 慢车70列（F列=0）
✅ 同时生成xls和xlsx
✅ 格式与大小交路完全一致
✅ 所有sheet页正常
```

## 🎉 完成状态

所有用户需求已完成：
- ✅ 复用src输入输出接口
- ✅ Excel格式与大小交路一致
- ✅ 快车标志位正确设置（快车=1，慢车=0）
- ✅ 生成xlsx格式文件
- ✅ 发车时间均衡分布
- ✅ 独立程序，易于使用

**程序已就绪，可以投入使用！** 🚀

