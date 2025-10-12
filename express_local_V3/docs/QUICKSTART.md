# 快速入门指南

## 5分钟快速开始

### 步骤1：检查环境

确保已安装Python 3.9+：
```bash
python --version
```

### 步骤2：安装依赖

```bash
cd express_local_V3
pip install -r requirements.txt
```

### 步骤3：运行程序

#### 方式A：使用启动脚本（最简单）

```bash
# 使用默认配置运行
python run.py
```

#### 方式B：使用测试脚本（验证功能）

```bash
# 先测试导入，再决定是否运行完整功能
python test_simple.py
```

#### 方式C：作为模块运行（从项目根目录）

```bash
# 返回项目根目录
cd ..

# 作为模块运行
python -m express_local_V3.main
```

### 步骤4：查看结果

程序运行完成后，会在 `../data/output_data/results/` 目录下生成Excel文件：
```
express_local_V3_YYYYMMDD_HHMMSS.xlsx
```

打开Excel文件，可以看到：
- 列车时刻表
- 车站时刻表
- 交路统计
- 越行事件
- 统计信息
- 车辆运用

## 常见运行方式

### 1. 默认配置运行

```bash
python run.py
```

使用默认参数：
- 快车比例：50%
- 目标发车间隔：180秒（3分钟）
- 输入文件：默认的长沙2号线数据

### 2. 自定义快车比例

```bash
# 快车占60%
python run.py --express_ratio 0.6

# 快车占30%
python run.py --express_ratio 0.3
```

### 3. 自定义发车间隔

```bash
# 2分钟发车间隔
python run.py --target_headway 120

# 4分钟发车间隔
python run.py --target_headway 240
```

### 4. 使用自己的输入文件

```bash
python run.py \
  -r "../data/input_data_new/RailwayInfo/Schedule-cs4.xml" \
  -u "../data/input_data_new/UserSettingInfoNew/cs4_test.xml"
```

### 5. 指定输出目录

```bash
python run.py -o "../my_results"
```

### 6. 开启调试模式

```bash
python run.py -d
```

## 解决常见问题

### 问题1：ImportError错误

```
ImportError: attempted relative import with no known parent package
```

**解决**：不要直接运行 `python main.py`，而是使用：
```bash
python run.py
```

### 问题2：找不到输入文件

```
FileNotFoundError: [Errno 2] No such file or directory: '...'
```

**解决**：
1. 检查文件路径是否正确
2. 使用绝对路径：
```bash
python run.py \
  -r "D:/data/Schedule-cs2.xml" \
  -u "D:/data/cs2_real_28.xml"
```

### 问题3：模块导入失败

```
ModuleNotFoundError: No module named 'pulp'
```

**解决**：安装缺失的依赖
```bash
pip install pulp numpy pandas openpyxl
```

### 问题4：程序运行很慢

**解决**：
1. 减少列车数量（增大发车间隔）
2. 减小快车比例
3. 检查输入数据规模

## 验证程序是否正常工作

运行测试脚本：
```bash
python test_simple.py
```

这个脚本会：
1. 测试所有模块是否能正常导入
2. （可选）运行完整功能测试

如果所有测试通过，说明程序工作正常！

## 下一步

- 查看 [README.md](README.md) 了解详细功能
- 查看 [example_usage.py](example_usage.py) 学习更多用法
- 查看 [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) 了解技术细节

## 需要帮助？

如果遇到问题：
1. 查看 [README.md 的常见问题部分](README.md#常见问题)
2. 检查输入文件格式是否正确
3. 查看程序输出的错误信息
4. 使用 `-d` 参数开启调试模式获取更多信息

---

祝使用愉快！ 🚄

