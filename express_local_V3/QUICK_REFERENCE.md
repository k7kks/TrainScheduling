# 快速参考卡片 🚀

## 📁 目录结构（一目了然）

```
express_local_V3/
├── 📄 main.py              → 主程序
├── 📖 README.md            → 主文档
├── 📦 requirements.txt     → 依赖库
│
├── 🧩 models/              → 数据模型（Train, Timetable...）
├── 🔬 algorithms/          → 核心算法（Generator, Optimizer...）
├── 📊 output/              → 输出处理（Excel导出）
│
├── 🛠️  scripts/            → 工具脚本
│   ├── run.py             → 快速启动 ⭐
│   └── check_output.py    → 输出检查
│
├── 🧪 tests/               → 测试文件
│   ├── test_imports.py    → 导入测试
│   ├── test_read_data.py  → 数据测试
│   └── test_simple.py     → 功能测试
│
├── 📝 examples/            → 使用示例
│   └── example_usage.py   → API示例
│
└── 📚 docs/                → 项目文档
    ├── INDEX.md           → 文档索引 ⭐
    ├── QUICKSTART.md      → 快速入门 ⭐
    ├── PROJECT_SUMMARY.md → 技术摘要
    └── ...                → 其他文档
```

## 🚀 常用命令

### 运行程序

```bash
# 方式1：快速启动（推荐）
cd express_local_V3
python scripts/run.py

# 方式2：作为模块运行
python -m express_local_V3.main

# 方式3：自定义参数
python scripts/run.py --express_ratio 0.6 --target_headway 180
```

### 运行测试

```bash
cd express_local_V3

# 测试导入
python tests/test_imports.py

# 测试数据读取
python tests/test_read_data.py

# 完整功能测试
python tests/test_simple.py
```

### 查看文档

```bash
# 主文档
cat README.md

# 文档索引
cat docs/INDEX.md

# 快速入门
cat docs/QUICKSTART.md
```

## 📖 文档快速导航

| 我想... | 应该看... |
|---------|-----------|
| 快速运行程序 | [docs/QUICKSTART.md](docs/QUICKSTART.md) |
| 了解算法原理 | [docs/PROJECT_SUMMARY.md](docs/PROJECT_SUMMARY.md) |
| 查看所有文档 | [docs/INDEX.md](docs/INDEX.md) |
| 使用Python API | [examples/example_usage.py](examples/example_usage.py) |
| 了解项目架构 | [docs/INTEGRATION_SUMMARY.md](docs/INTEGRATION_SUMMARY.md) |
| 运行测试 | [tests/README.md](tests/README.md) |
| 使用工具脚本 | [scripts/README.md](scripts/README.md) |
| 查看更新记录 | [docs/CHANGELOG.md](docs/CHANGELOG.md) |

## ⚙️ 常用参数

| 参数 | 说明 | 默认值 | 示例 |
|------|------|--------|------|
| `--express_ratio` | 快车比例 | 0.5 | `0.3` - `0.7` |
| `--target_headway` | 发车间隔(秒) | 180 | `120` / `240` |
| `--rail_info` | 线路文件 | Schedule-cs2.xml | 路径 |
| `--user_setting` | 设置文件 | cs2_real_28.xml | 路径 |
| `--output` | 输出目录 | ../data/output_data/... | 路径 |
| `--debug` | 调试模式 | False | 加上 `-d` |

## 🎯 快速示例

### 例子1：默认配置
```bash
python scripts/run.py
```

### 例子2：快车比例60%
```bash
python scripts/run.py --express_ratio 0.6
```

### 例子3：发车间隔2分钟
```bash
python scripts/run.py --target_headway 120
```

### 例子4：自定义输入输出
```bash
python scripts/run.py \
  -r ../data/input_data_new/RailwayInfo/Schedule-cs4.xml \
  -u ../data/input_data_new/UserSettingInfoNew/cs4_test.xml \
  -o ../data/output_data/my_results
```

## 🔍 故障排查

| 问题 | 解决方案 |
|------|----------|
| ImportError | 用 `python scripts/run.py` 而不是直接运行 |
| 找不到文件 | 检查路径，使用绝对路径 |
| 模块缺失 | `pip install -r requirements.txt` |
| 结果不符合预期 | 调整 `express_ratio` 和 `target_headway` |

## 📞 获取帮助

1. 查看 [README.md](README.md) 的"常见问题"部分
2. 查看 [docs/INDEX.md](docs/INDEX.md) 找到相关文档
3. 查看 [docs/QUICKSTART.md](docs/QUICKSTART.md) 的故障排查
4. 使用 `--help` 查看命令行帮助

```bash
python scripts/run.py --help
```

## 🎓 学习路径

**初学者**:
```
QUICK_REFERENCE.md → docs/QUICKSTART.md → 运行程序
```

**开发者**:
```
README.md → docs/PROJECT_SUMMARY.md → docs/INTEGRATION_SUMMARY.md → 源代码
```

**研究者**:
```
docs/PROJECT_SUMMARY.md → algorithms/*.py → 论文参考
```

---

💡 **提示**: 将此文件加入书签，随时查阅！

