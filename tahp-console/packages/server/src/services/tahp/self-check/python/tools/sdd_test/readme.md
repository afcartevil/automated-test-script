# SDD 自动化测试框架

本项目是基于 `pytest` 的 Android 设备侧自动化测试框架，核心目标是通过 ADB 拉取设备信息、执行规则校验，并输出统一 JSON 报告。

## 1. 项目简介

- 支持按模块（`baseline`/`performance`）或按单文件运行测试。
- 支持通过设备能力 `marker` 在收集阶段自动跳过不满足条件的用例。
- 支持用例等级分层：默认 `L1`、扩展 `L2`、占位 `L3`。
- 支持根据 `ro.build.display.id` 自动区分周版本和日版本。
- 输出统一结构的 JSON 报告，便于平台集成。

## 2. 目录结构

```text
sdd_test_dev/
├─ data/                          # 数据与资源
│  ├─ channel_list.py             # 渠道规则
│  ├─ res_list.py                 # 常量配置
│  └─ file/                       # 外部资源与子工程
├─ doc/                           # 项目文档（本次整理新增）
│  ├─ README.md                   # 文档导航
│  ├─ pytest-basics.md            # pytest 基础知识（从 README 拆出）
│  ├─ framework-overview.md       # 框架摘要
│  ├─ framework-api.md            # 框架 API 与执行链路
│  ├─ adb-api.md                  # ADB 工具方法说明
│  ├─ custom-markers.md           # 自定义 marker 说明
│  └─ minimal-cases/              # 最小用例（非 py）
├─ src/
│  ├─ conftest.py                 # pytest 全局插件入口
│  ├─ conftests/                  # fixture / marker / 报告 / 等级过滤
│  ├─ test_case/                  # 测试用例（baseline/performance）
│  └─ utils/                      # 工具能力（ADB、文件、装饰器等）
├─ si_run.py                      # 命令行入口
├─ pytest.ini                     # pytest 配置
└─ requirements.txt               # 依赖列表
```

## 3. 快速启动

### 3.1 环境准备

1. 安装 Python（建议 3.8+）。
2. 安装 ADB 并确保 `adb devices` 可用。
3. 安装依赖：

```bash
pip install -r requirements.txt
```

### 3.2 运行示例

- 全量执行（`src` 下所有用例）：

```bash
python si_run.py
```

未指定 `--serial` 时，框架会自动读取 `adb devices` 的第一台设备作为目标设备。

- 全量执行（显式指定设备）：

```bash
python si_run.py --serial <设备SN>
```

- 仅执行 `baseline`：

```bash
python si_run.py --serial <设备SN> --test-type baseline
```

- 仅执行 `performance`：

```bash
python si_run.py --serial <设备SN> --test-type performance
```

- 仅执行 `gmstcd`：

```bash
python si_run.py --serial <设备SN> --test-type gmstcd
```

- 执行单文件：

```bash
python si_run.py --serial <设备SN> --testcase src/test_case/baseline/config/test_channel.py
```

- 带重跑参数：

```bash
python si_run.py --serial <设备SN> --reruns 2 --reruns-delay 2
```

## 4. 用例等级与版本策略

- 默认未标记用例为 `L1`。
- 扩展用例使用 `@pytest.mark.L2`。
- `L3` 为占位（当前固定跳过）。
- 版本判定：
  - `ro.build.display.id` 以 `)` 结尾 -> 周版本
  - 否则 -> 日版本
- 执行策略：
  - 日版本执行 `L1`
  - 周版本执行 `L1 + L2`

## 5. 报告输出

- 默认报告路径：`./report/<display.id>/SDD_report.json`
- 可通过 `--report-path` 自定义
- 报告含用例总数、失败数、跳过数、通过率、失败原因等字段

### 5.1 报告字段说明

- `status`：整体状态，`ok` 或 `failed`。
- `detail`：状态说明，失败时会带失败数量说明。
- `versionNum`：设备 `ro.build.display.id`。
- `AlltestCase`：本次执行的用例列表（名称与执行时间）。
- `failed`：失败用例列表（含失败原因）。
- `ignore`：跳过用例列表（含跳过原因）。
- `summary.totalNum`：执行用例总数。
- `summary.failedCount`：失败用例数。
- `summary.ignored`：跳过用例数。
- `summary.passRate`：通过率（按 `totalNum` 计算）。
- `summary.totalTime`：总执行时长（秒）。

### 5.2 报告示例

```json
{
  "status": "failed",
  "detail": "2 tests failed",
  "versionNum": "A15-TR-XYZ(20260423)",
  "summary": {
    "totalTime": "125s",
    "totalNum": 20,
    "ignored": 3,
    "failedCount": 2,
    "passRate": "75%"
  },
  "failed": [
    {
      "testCaseName": "test_channel",
      "excuteTime": "2026-04-23 10:30:11",
      "reason": "assert xxx == yyy"
    }
  ],
  "ignore": [
    {
      "testCaseName": "test_l2_feature",
      "excuteTime": "2026-04-23 10:30:12",
      "reason": "日版本仅执行L1级用例，L2已跳过"
    }
  ]
}
```

## 6. 文档导航

- 文档入口：`doc/README.md`
- pytest 基础：`doc/pytest-basics.md`
- 框架摘要：`doc/framework-overview.md`
- 框架 API：`doc/framework-api.md`
- ADB 方法：`doc/adb-api.md`
- 自定义 marker：`doc/custom-markers.md`
- 最小用例：`doc/minimal-cases/README.md`

