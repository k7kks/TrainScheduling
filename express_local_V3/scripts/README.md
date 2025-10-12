# 工具脚本说明

本目录包含快慢车运行图自动编制程序的实用工具脚本。

## 脚本列表

### 1. run.py - 快速启动脚本

**功能**: 最简单的方式启动快慢车运行图编制程序。

**使用方法**:
```bash
# 进入express_local_V3目录
cd express_local_V3

# 使用默认配置运行
python scripts/run.py

# 使用自定义参数
python scripts/run.py --express_ratio 0.6 --target_headway 180
```

**特点**:
- 自动处理Python路径问题
- 使用默认配置，开箱即用
- 支持命令行参数

### 2. check_output.py - 输出检查工具

**功能**: 检查生成的Excel输出文件是否正确。

**使用方法**:
```bash
# 检查默认输出目录
python scripts/check_output.py

# 检查指定文件
python scripts/check_output.py --file ../data/output_data/results/result.xlsx
```

**检查内容**:
- 文件是否存在
- 数据完整性
- 关键字段验证
- 路径编号检查

## 开发自己的脚本

如果需要创建新的工具脚本，请遵循以下规范：

1. **命名规范**: 使用小写+下划线，如 `my_script.py`
2. **文档字符串**: 在文件开头添加说明
3. **命令行参数**: 使用 `argparse` 模块
4. **错误处理**: 添加适当的异常处理
5. **返回值**: 使用 `sys.exit(0/1)` 表示成功/失败

**模板示例**:
```python
"""
我的脚本说明
"""
import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description='脚本说明')
    parser.add_argument('--param', type=str, help='参数说明')
    args = parser.parse_args()
    
    try:
        # 主要逻辑
        print("执行成功")
        return 0
    except Exception as e:
        print(f"错误: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

## 返回

返回 [主目录](../README.md)

