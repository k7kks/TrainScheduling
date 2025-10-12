# Scripts 目录说明

本目录包含各种实用脚本，用于运行、测试、调试和验证程序。

---

## 📋 脚本列表

### 1. run.py - 运行脚本

**功能**：快速启动主程序

**使用方法**：
```bash
python scripts/run.py
```

**说明**：封装了main.py的启动逻辑，提供更简洁的运行接口。

---

### 2. check_output.py - 输出检查脚本

**功能**：检查和验证输出文件的正确性

**使用方法**：
```bash
python scripts/check_output.py
```

**检查内容**：
- Excel文件是否生成
- 数据格式是否正确
- 基本统计信息

---

### 3. check_connection.py - 勾连检查脚本 🆕

**功能**：验证车次勾连结果

**使用方法**：
```bash
# 先运行主程序生成Excel
python main.py

# 然后检查勾连结果
python scripts/check_connection.py
```

**检查内容**：
- 表号分布
- 勾连链长度
- 勾连统计信息
- 快慢车分离情况

**输出示例**：
```
========== 勾连检查报告 ==========

总车次数: 70
表号数量: 30

表号分布:
  [OK] 发现 23 组勾连：
    表号 1: 4 个车次勾连在一起
    表号 2: 4 个车次勾连在一起
    ...

快慢车勾连情况:
  快车数量: 35
  慢车数量: 35
  [OK] 快车和慢车分开勾连（正确）
```

---

### 4. debug_connection.py - 勾连调试脚本 🆕

**功能**：深入分析勾连过程，用于调试和优化

**使用方法**：
```bash
python scripts/debug_connection.py
```

**功能详情**：
1. 显示所有车次的时间分布
2. 分析勾连可能性
3. 查找最佳勾连配对
4. 输出详细调试信息

**输出示例**：
```
车次时间调试信息
==================
车次ID     类型   方向   交路   发车时间    首站到达   末站离开
E001      快车   上行   大交路  23340      23340      26166
L002      慢车   下行   大交路  23760      23760      26453

勾连可能性分析
==================
上行车 1:
  首站到达: 23340秒 (389分)
  末站离开: 26166秒 (436分)
  站台: 111 -> 333
  最佳匹配下行车 10:
    首站到达: 26640秒 (444分)
    站台: 333 -> 111
    折返时间: 474秒 (7分54秒) ✓
```

---

### 5. analyze_times.py - 时间分析脚本 🆕

**功能**：分析生成的Excel文件中的时间数据

**使用方法**：
```bash
# 先运行主程序生成Excel
python main.py

# 然后分析时间数据
python scripts/analyze_times.py
```

**分析内容**：
- 任务线数据（每站到发时间）
- 计划线数据（车次概要）
- 勾连可能性分析
- 时间统计

**输出示例**：
```
任务线数据分析
==================
总行数: 1750
列名: ['表号', '车次号', '站台目的地码', '到站时间', '离站时间', ...]

前10个车次的时间信息:
表号     首站时间        末站时间
1        23340          26166
2        23760          26453
...
```

---

## 🎯 使用场景

### 场景1：日常运行

```bash
# 1. 运行主程序
python main.py

# 2. 检查输出
python scripts/check_output.py

# 3. 验证勾连
python scripts/check_connection.py
```

### 场景2：勾连调试

```bash
# 1. 详细调试模式运行
python main.py --debug

# 2. 深入分析勾连
python scripts/debug_connection.py

# 3. 分析时间数据
python scripts/analyze_times.py

# 4. 验证结果
python scripts/check_connection.py
```

### 场景3：快速验证

```bash
# 一键运行和验证
python scripts/run.py && python scripts/check_connection.py
```

---

## 📝 开发指南

### 添加新脚本

1. **创建脚本文件**：在`scripts/`目录下创建新文件
2. **添加文档字符串**：说明脚本功能和用法
3. **更新README**：在本文件中添加说明
4. **添加到索引**：更新`docs/INDEX.md`

### 脚本模板

```python
"""
脚本名称 - 功能描述

使用方法：
    python scripts/script_name.py [参数]

作者：XXX
日期：YYYY-MM-DD
"""

import sys
import os

# 添加项目路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

def main():
    """主函数"""
    print("脚本功能...")
    # 实现逻辑

if __name__ == "__main__":
    main()
```

---

## 🔧 依赖说明

### 通用依赖

所有脚本依赖的包已在`requirements.txt`中定义：

```
pandas
openpyxl
numpy
pulp
```

### 特殊依赖

- `debug_connection.py`：需要先运行一次`main.py`生成数据
- `check_connection.py`：需要Excel文件存在
- `analyze_times.py`：需要Excel文件存在

---

## ✅ 最佳实践

1. **运行顺序**：先运行`main.py`，再运行验证脚本
2. **调试模式**：使用`--debug`参数获取详细日志
3. **结果验证**：每次修改后运行`check_connection.py`验证
4. **性能分析**：使用`analyze_times.py`分析时间分布

---

**最后更新**: 2025-10-12  
**维护者**: AI Assistant
