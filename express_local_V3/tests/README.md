# 测试文件说明

本目录包含快慢车运行图自动编制程序的测试文件。

## 测试列表

### 1. test_imports.py - 导入测试

**功能**: 验证所有模块是否能正常导入。

**使用方法**:
```bash
cd express_local_V3
python tests/test_imports.py
```

**测试内容**:
- src模块导入（DataReader, RailInfo等）
- models模块导入（Train, ExpressLocalTimetable等）
- algorithms模块导入（ExpressLocalGenerator等）

**预期输出**:
```
✓ 所有模块导入成功
```

### 2. test_read_data.py - 数据读取测试

**功能**: 测试输入数据是否能正确读取。

**使用方法**:
```bash
cd express_local_V3
python tests/test_read_data.py
```

**测试内容**:
- XML文件读取
- RailInfo对象解析
- UserSetting对象解析
- 数据完整性验证

**预期输出**:
```
✓ 线路信息读取成功
✓ 用户设置读取成功
✓ 数据验证通过
```

### 3. test_simple.py - 简单功能测试

**功能**: 端到端的功能测试，运行完整流程。

**使用方法**:
```bash
cd express_local_V3
python tests/test_simple.py
```

**测试内容**:
- 完整的运行图生成流程
- 算法执行
- 输出文件生成
- 结果验证

**预期输出**:
```
✓ 数据读取成功
✓ 快慢车生成成功
✓ 输出文件生成成功
✓ 所有测试通过
```

## 运行所有测试

```bash
cd express_local_V3

# 依次运行所有测试
python tests/test_imports.py
python tests/test_read_data.py
python tests/test_simple.py
```

## 添加新的测试

如果需要添加新的测试文件，请遵循以下规范：

1. **命名规范**: `test_*.py`
2. **独立性**: 每个测试应该独立运行
3. **清晰的输出**: 使用 ✓ 和 ✗ 标记成功/失败
4. **异常处理**: 捕获并报告所有异常
5. **返回值**: 使用 `sys.exit(0/1)` 表示通过/失败

**测试模板**:
```python
"""
测试说明
"""
import sys

def test_something():
    """测试某个功能"""
    try:
        # 测试逻辑
        assert condition, "断言失败"
        print("✓ 测试通过")
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False

def main():
    print("开始测试...")
    
    success = True
    success &= test_something()
    # 添加更多测试...
    
    if success:
        print("\n所有测试通过！")
        return 0
    else:
        print("\n部分测试失败！")
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

## 持续集成

未来可以将这些测试集成到CI/CD流程中：
- GitHub Actions
- Jenkins
- GitLab CI

## 返回

返回 [主目录](../README.md)

