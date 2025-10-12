# 更新日志

## Version 3.0.1 (2024-10-11) - 修复版本

### 修复的问题

#### 1. 导入错误修复
- ✅ 修复了 `ImportError: attempted relative import with no known parent package` 错误
- ✅ 添加了相对导入和绝对导入的兼容处理
- ✅ 创建了 `run.py` 启动脚本，简化运行方式

#### 2. 语法错误修复
- ✅ 修复了 `excel_exporter.py` 第213行的字典语法错误
  - 问题：`'数值': timetable.express_trains_count, '列'}`  缺少键名
  - 修复：`'数值': timetable.express_trains_count, '单位': '列'}`

#### 3. DataReader接口修复
- ✅ 修复了DataReader方法调用错误
  - 问题：使用了不存在的 `read_rail_info_file` 方法
  - 修复：使用正确的 `DataReader.read_file()` 静态方法

#### 4. Station属性修复
- ✅ 修复了Station对象属性名错误
  - 问题：使用了不存在的 `kilometer` 属性
  - 修复：使用正确的 `centerKp` 属性
  - 影响文件：
    - `algorithms/timetable_builder.py`
    - `algorithms/express_local_generator.py`

#### 5. Unicode编码问题修复
- ✅ 修复了Windows PowerShell中的Unicode字符显示问题
  - 问题：`'gbk' codec can't encode character '\u2713'`
  - 修复：将特殊Unicode字符（✓、❌）替换为ASCII字符（[OK]、[ERROR]）
  - 影响文件：
    - `main.py`
    - `test_simple.py`
    - `test_imports.py`

### 新增功能

#### 1. 运行脚本
- ✨ `run.py` - 简单启动脚本，解决导入问题
- ✨ `test_imports.py` - 快速测试所有模块导入
- ✨ `test_read_data.py` - 测试数据读取功能

#### 2. 文档更新
- 📚 `QUICKSTART.md` - 5分钟快速入门指南
- 📚 更新 `README.md`，添加常见问题解答
- 📚 `CHANGELOG.md` - 本文档

### 当前状态

✅ **所有核心功能已修复并验证通过**

- [x] 模块导入正常
- [x] 数据读取正常
- [x] 语法错误已修复
- [x] 接口调用正确
- [x] 字符编码兼容

### 使用方法

```bash
# 进入目录
cd express_local_V3

# 快速测试模块
python test_imports.py

# 测试数据读取
python test_read_data.py

# 运行完整程序
python run.py

# 或者查看帮助
python run.py --help
```

### 已知问题

1. **中文显示问题**: Windows PowerShell的GBK编码导致部分中文显示为乱码，但不影响功能
   - 解决方法：在输出中使用ASCII字符替代Unicode特殊字符

2. **路径问题**: 使用相对路径时需要注意当前工作目录
   - 建议：使用 `run.py` 脚本启动，自动处理路径问题

### 测试结果

#### 模块导入测试 ✅
```
[OK] 数据模型导入成功
[OK] 算法模块导入成功
[OK] 输出模块导入成功
[OK] 主程序导入成功
```

#### 数据读取测试 ✅
```
[OK] 输入文件存在
[OK] 线路信息读取成功 (车站数: 24, 路径数: 778)
[OK] 用户设置读取成功 (峰期数: 5)
```

### 下一步

程序现在可以正常运行！可以：
1. 使用默认配置运行：`python run.py`
2. 自定义参数运行：`python run.py --express_ratio 0.6`
3. 查看输出的Excel文件，验证运行图质量

---

## Version 3.0.0 (2024-10-11) - 初始版本

### 主要功能

1. **快慢车运行图自动编制**
   - 基于快慢车铺画规则的算法
   - 先铺快车，后铺慢车
   - 在均匀时间段内搜索旅行时间最短的运行线

2. **发车时间均衡性优化**
   - 基于线性规划的发车间隔优化
   - 目标函数：min Σ |h_i - h_avg|
   - 约束：最小/最大发车间隔

3. **越行检测和分析**
   - 智能检测越行事件
   - 分析越行可避免性
   - 提供优化建议

4. **完整的输入输出接口**
   - 复用src的DataReader
   - 生成与大小交路一致的Excel输出
   - 6个工作表：列车时刻表、车站时刻表、交路统计、越行事件、统计信息、车辆运用

### 技术特点

- 模块化设计
- 清晰的代码结构
- 详细的文档和注释
- 完整的测试脚本

---

**项目**: 快慢车运行图自动编制程序V3  
**团队**: CRRC城市轨道交通调度系统算法研发团队  
**最后更新**: 2024-10-11

