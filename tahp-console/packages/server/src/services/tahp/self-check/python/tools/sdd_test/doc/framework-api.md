# 框架 API 说明

本文件聚焦“框架层”可直接复用的入口、fixture、hook 与输出约定。

## 1. 命令行入口 API

文件：`si_run.py`

### 支持参数

- `--serial` / `-serial`：设备序列号
- `--test-type`：`baseline` 或 `performance`
- `--testcase`：单文件或单节点路径
- `--tb`：栈显示模式（`line|short|no|native`）
- `--reruns`：失败重跑次数
- `--reruns-delay`：失败重跑间隔（秒）

### 运行策略

- 同时未指定 `--test-type` 与 `--testcase` 时，默认执行 `src/`
- 未传 `--serial` 时，自动调用 `get_first_sn()`

## 2. pytest 插件 API

文件：`src/conftest.py`

### 2.1 `pytest_addoption(parser)`

新增参数：

- `--report-path`：报告输出路径
- `--device-serial`：设备序列号（供内部 fixture 使用）

### 2.2 `pytest_configure(config)`

初始化：

- `ReportCollector`
- 设备能力 marker 注册
- 等级 marker 注册（L2/L3）

### 2.3 `pytest_collection_modifyitems(config, items)`

按顺序执行：

1. 等级过滤（L1/L2/L3 + 周/日版本）
2. 设备能力 marker 判定（`CHECKER_LIST`）

### 2.4 `pytest_runtest_makereport(item, call)`

收集执行结果，写入报告缓存：

- 测试名
- 执行时间
- 失败原因或跳过原因

## 3. fixture API

### 来自 `src/conftest.py`

- `device_serial`：读取 `--device-serial`
- `file_puller`：返回文件导出函数，签名：

```text
file_puller(file_name="", cmd="") -> bool
```

### 来自 `src/conftests/device.py`

- `phone_info`：返回手机属性字典
- `pms_info`：返回本地 pms JSON 信息
- `execution_environment`：返回 `windows` / `linux` / 其他

## 4. 设备能力判定 API

文件：`src/conftests/marker_check.py`

- `CHECKER_LIST`：所有设备 marker 的判定函数集合
- `register_device_markers(config)`：注册 marker 描述到 pytest

每个判定函数统一风格：

```text
checker(required_info, device_info) -> skip_marker or None
```

## 5. 等级判定 API

文件：`src/conftests/test_level.py`

- `register_test_level_markers(config)`
- `get_is_weekly_build(device_serial) -> bool`
- `get_test_level_skip_marker(item, is_weekly_build) -> skip_marker or None`

## 6. 报告输出 API

文件：`src/conftests/report.py`

- `ReportCollector(output_path)`：初始化报告结构
- `pytest_unconfigure(config)`：结束时落盘 JSON 报告
