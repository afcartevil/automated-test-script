# Android启动证书监控系统

一个用于监控Android设备启动证书有效期的自动化工具，通过ADB日志分析实现实时监控和预警。支持完整的端到端自动化集成测试流程。

## 功能特性

- **实时监控**: 通过ADB logcat实时获取Android设备启动证书信息
- **智能预警**: 基于证书到期时间的多级预警系统（警告阈值120天，严重阈值90天）
- **多种报告**: 支持HTML、JSON、纯文本格式的监控报告
- **配置管理**: 基于YAML配置文件的灵活配置系统
- **设备管理**: 支持ADB设备连接和管理
- **自动化集成**: 完整的端到端自动化测试流程，包括APK安装、应用启动、监控和报告生成
- **时间计算**: 支持基于网络时间和ROM编译时间的双重时间计算
- **优化架构**: 监听逻辑在应用启动前全局初始化，确保不遗漏任何监控数据

## 系统要求

- Python 3.9+
- Android Debug Bridge (ADB)
- 已启用USB调试的Android设备
- PyYAML 6.0+ (用于配置文件解析)

## 安装说明

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

主要依赖：
- `pyyaml>=6.0` - YAML配置文件解析

### 2. 配置ADB
确保ADB已安装并添加到系统PATH中：
```bash
adb version
```

### 3. 连接Android设备
- 启用开发者选项和USB调试
- 连接设备并授权调试
```bash
adb devices
```

## 快速开始

### 自动化集成测试（推荐）
```bash
# 运行完整的连续监控（集成测试），默认持续60秒
python auto_integration.py

# 指定监控持续时间（秒）
python auto_integration.py --duration 30

# 仅检查前置条件
python auto_integration.py --check-only

# 仅安装APK
python auto_integration.py --install-only
```

`auto_integration.py`自动执行以下步骤：
1. 检查ADB连接和设备状态
2. **全局初始化监听逻辑**（在应用启动前准备所有监听器）
3. 安装Android测试应用（APK/app-release.apk）
4. 启动Android应用
5. 启动连续监控模式
6. 实时捕获和解析启动证书数据
7. 生成HTML、JSON、TXT格式的监控报告
8. 检测到严重警告时自动退出

**注意**: `auto_integration.py`专为连续监控设计，提供完整的端到端自动化测试体验。

### 手动操作模式

#### 单次检查
```bash
# 基本单次检查
python main.py check

# 单次检查并自动安装APK
python main.py check --install

# 单次检查并指定设备
python main.py check --device 129065546D000013
```

#### 连续监控
```bash
# 连续监控，默认间隔60秒
python main.py monitor

# 指定监控间隔（秒）
python main.py monitor --interval 30

# 指定监控持续时间（秒）
python main.py monitor --duration 3600
```

#### 查看设备列表
```bash
python main.py devices
```

#### 查看配置
```bash
python main.py config
```

## 架构优化说明

### 监听逻辑全局初始化

系统采用了优化的监听架构，确保在Android应用启动前就完成所有监听器的初始化：

#### 优化前的问题
- 监听逻辑在应用启动后才初始化
- 可能遗漏应用启动初期的关键数据
- 监控时机不够精确

#### 优化后的架构
1. **全局初始化阶段**：在应用启动前完成logcat监听器的初始化
2. **监听器准备**：确保所有监听器在应用启动前就处于就绪状态
3. **数据完整性**：从应用启动的第一刻就开始捕获数据，避免遗漏

#### 实现细节
```python
def _initialize_monitoring_system(self):
    """在APP启动前全局初始化监听系统"""
    self.logger.info("全局初始化监听逻辑...")
    
    # 启动logcat监控
    self.adb_interface.start_logcat_monitor(
        callback=self._handle_logcat_data,
        tag_filter=self.config.get('logcat', {}).get('tag_filter', 'BootDataExport')
    )
    
    self.logger.info("监听系统初始化完成，所有监听器已准备就绪")
```

#### 执行流程
1. 设备连接检查
2. **监听系统全局初始化** ← 新增优化步骤
3. 应用启动（手动或自动）
4. 数据捕获和解析
5. 监听停止和报告生成

## 配置文件

系统使用YAML格式的配置文件。默认配置文件为`config.yaml`：

```yaml
# 元数据信息
_metadata:
  created_at: '2025-09-02T11:42:54.640899'
  description: Android启动证书监控系统配置文件
  version: '1.0'

# ADB相关配置
adb_retry_count: 3
adb_retry_delay: 1.0
adb_timeout: 30

# 监控配置
logcat_tag: BootDataExport
logcat_buffer_size: 1000
logcat_timeout: 60
monitor_interval: 60
enable_continuous_monitoring: true

# 预警阈值（天数）
warning_threshold_days: 120
critical_threshold_days: 90

# 报告配置
auto_generate_report: true
report_format: html
report_output_dir: output/reports

# 其他配置
log_level: INFO
debug_mode: false
max_retry_attempts: 5
data_retention_days: 30
save_raw_data: false
```

## 项目结构

```
smoke_test_monitor/
├── main.py                 # 主程序入口（支持多种操作模式）
├── auto_integration.py     # 连续监控入口（一键启动完整监控）
├── config.yaml            # 默认配置文件
├── requirements.txt        # Python依赖
├── src/                   # 源代码目录
│   ├── core/              # 核心模块
│   │   ├── config_manager.py    # 配置管理器
│   │   ├── data_parser.py       # 数据解析模块
│   │   └── time_calculator.py   # 时间计算模块
│   ├── interfaces/        # 接口模块
│   │   └── adb_interface.py     # ADB接口模块
│   ├── monitoring/        # 监控模块
│   │   └── warning_engine.py    # 预警引擎
│   ├── reporting/         # 报告模块
│   │   └── report_generator.py  # 报告生成器
│   └── utils/             # 工具模块
│       ├── exceptions.py        # 异常定义
│       └── debug_device_connection.py  # 设备连接调试
├── APK/                   # Android应用文件
│   └── app-release.apk    # 测试用Android应用
├── output/                # 输出目录
│   ├── data/              # 数据文件
│   ├── logs/              # 日志文件
│   │   └── smoke_test_monitor.log
│   ├── reports/           # 生成的监控报告
│   │   ├── *.html         # HTML格式报告
│   │   ├── *.json         # JSON格式报告
│   │   └── *.txt          # 文本格式报告
│   └── temp/              # 临时文件
└── README.md              # 项目文档
```

## Android端集成

### 1. 添加BootDataExporter类
将`BootDataExporter.java`添加到Android项目中，用于输出启动证书信息到logcat。

### 2. 集成到MainActivity
在`MainActivity.java`中集成BootDataExporter调用：

```java
// 成功获取补丁信息后
BootDataExporter.exportBootData(this, patchInfo, remainingDays);

// 发生错误时
BootDataExporter.exportError(this, "Error message", exception);
```

### 3. 日志输出格式
Android端会输出JSON格式的日志，包含：
- 设备信息（型号、SDK版本、构建信息）
- 启动数据（原始和格式化的补丁级别）
- 计算结果（ROM构建时间、启动日期、到期日期、剩余天数）

## 使用示例

### 自动化集成测试
```bash
# 运行完整的集成测试（30秒监控）
python auto_integration.py --duration 30

# 仅检查前置条件
python auto_integration.py --check-only

# 仅安装APK
python auto_integration.py --install-only
```

执行步骤：
1. 环境检查（设备连接、ADB可用性）
2. APK安装（自动卸载旧版本并安装新版本）
3. 应用启动（启动目标Activity）
4. 连续监控（收集启动证书数据）
5. 数据分析（计算剩余天数、生成预警）
6. 报告生成（生成HTML、JSON、TXT格式报告）
7. 检测到严重警告时自动退出

### 基本监控
```bash
# 单次检查
python main.py check

# 单次检查并安装APK
python main.py check --install

# 连续监控（默认60秒间隔）
python main.py monitor
```

### 连续监控
```bash
# 指定监控间隔（30秒）
python main.py monitor --interval 30

# 指定监控持续时间（1小时）
python main.py monitor --duration 3600
```

### 设备管理
```bash
# 查看连接的设备
python main.py devices

# 指定特定设备进行监控
python main.py check --device 129065546D000013
```

### 配置查看
```bash
# 查看当前配置
python main.py config
```

## 报告格式

系统会自动生成三种格式的报告，保存在`output/reports/`目录下：

### HTML报告
- 包含完整的设备信息、证书状态、预警信息
- 显示网络时间、ROM编译时间、剩余天数等关键数据
- 包含警告级别和详细描述
- 适合人工查看和分析

### JSON报告
- 结构化数据格式，便于程序处理
- 包含所有原始数据和计算结果
- 包含时间戳、设备信息、警告详情等
- 适合自动化流程集成

### 文本报告
- 简洁的纯文本格式
- 包含关键信息摘要和警告统计
- 显示报告摘要："证书已过期，需要更新系统或重新刷机"
- 适合日志记录和快速查看

## 故障排除

### ADB连接问题
- 确保设备已开启USB调试
- 检查ADB驱动是否正确安装
- 尝试重启ADB服务：`adb kill-server && adb start-server`
- 使用`python main.py devices`查看设备连接状态

### 配置问题
- 如果出现"未知配置项"警告，检查`config.yaml`文件格式
- 确认配置项名称与实际代码中的配置项匹配
- 可以使用`python main.py config`查看当前配置

### APK安装问题
- 确保APK文件存在于`APK/app-release.apk`路径
- 检查设备是否允许安装未知来源应用
- 如果安装失败，系统会自动重试

### 日志获取失败
- 检查应用是否正确启动
- 确认logcat标签配置为`BootDataExport`
- 检查设备权限设置
- 查看`output/logs/smoke_test_monitor.log`了解详细信息

### 数据解析错误
- 检查Android应用的日志输出格式
- 确认时间戳格式正确
- 查看调试日志了解详细错误信息
- 检查网络时间获取是否成功

## 开发说明

### 项目依赖
主要依赖：
- `pyyaml>=6.0` - 配置文件解析

可选开发依赖（在requirements.txt中）：
- `pytest` - 单元测试
- `pytest-cov` - 测试覆盖率
- `black` - 代码格式化
- `flake8` - 代码检查
- `mypy` - 类型检查

### 运行测试
```bash
# 安装开发依赖
pip install pytest pytest-cov

# 运行测试
pytest tests/ -v
```

### 代码格式化
```bash
# 安装格式化工具
pip install black flake8

# 格式化代码
black .
flake8 .
```

### 类型检查
```bash
# 安装类型检查工具
pip install mypy

# 运行类型检查
mypy .
```

## 已知问题

### 配置项警告
- 系统可能会显示"未知配置项"警告，这不影响核心功能运行
- 这些警告通常是由于配置文件中的某些配置项与代码中的配置项不完全匹配

### 监控自动退出
- 当检测到严重警告（如证书已过期）时，监控系统会自动退出
- 这是设计行为，用于及时提醒用户关注严重问题

### 时间计算依赖
- 系统依赖网络时间获取来计算证书剩余天数
- 如果网络连接不稳定，可能影响时间计算的准确性

### 设备兼容性
- 系统主要针对Android设备设计
- 不同Android版本的logcat输出格式可能略有差异

## 作者信息

- 作者：LYH
- 项目：Android启动证书监控系统
- 版本：1.0

## 自动化集成功能

### auto_integration.py - 连续监控入口

`auto_integration.py`是专门的连续监控入口，提供完整的端到端自动化测试功能：

#### 核心功能
- **前置条件检查**: 验证APK文件存在、ADB工具可用
- **设备连接管理**: 自动检测和连接Android设备
- **监听系统初始化**: 在应用启动前全局初始化所有监听器
- **APK管理**: 自动安装Android测试应用
- **应用启动**: 自动启动Android测试应用
- **连续监控**: 启动连续监控模式，实时捕获数据
- **报告生成**: 自动生成HTML格式的监控报告
- **错误处理**: 完整的异常处理和日志记录

#### 使用方法
```bash
# 直接运行连续监控（推荐方式）
python auto_integration.py

# 程序会自动执行完整的连续监控流程
# 无需额外参数，开箱即用
```

#### 与main.py的区别
- `auto_integration.py`: 专为连续监控设计，自动化程度更高
- `main.py`: 提供更多手动控制选项，支持单次检查和自定义参数

#### 日志文件
- `auto_integration.log`: 详细的集成测试执行日志
- `smoke_test_monitor.log`: 监控脚本运行日志

## 集成测试报告

- **测试环境**: 硬件设备、软件版本信息
- **测试流程**: Android应用验证、Python监控脚本验证、数据流完整性验证
- **问题发现与解决**: 关键问题的识别和修复过程
- **性能指标**: 响应时间、资源使用情况
- **测试覆盖率**: 功能覆盖、数据类型覆盖、边界条件覆盖
- **质量评估**: 代码质量、可维护性评估
