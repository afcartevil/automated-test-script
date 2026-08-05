---
name: base_jira_testcase_parse
description: >-
  从功耗/续航类 JIRA 描述中解析 Precondition、Environment、Operation Steps、
  Expect Result、Test Result 等结构化字段，并派生机型、功耗差、游戏名、网络/开关等。
  在分析 JIRA 功耗单、需提取测试前置与实测结果数字时使用。
---

## 功能描述

解析公司标准「功耗/续航温升」JIRA 描述模板，输出结构化 JSON，供 `flow_power_game` 等下游使用（功耗数字、竞品机型、日志 SMB 路径、前置开关等）。

**不负责**：读 JIRA API（由 `base_jirainfo` 完成）；日志合规实测（由 `flow_power_game_precondition` / `base_precondition_check` 完成）。

## 输入来源（优先级）

1. `--description-file` / `--description`：原始描述文本
2. `--jira-info`：工作区 `jira_info.json`（含 `description`/`summary`/`affect_project`）
3. `--jira-key`：调用 `base_jirainfo` 同类接口拉单（需本机凭证）

## 解析字段

| 区块 | JSON 路径 |
|------|-----------|
| Precondition 条目 | `sections.precondition`（list） |
| Environment | `sections.environment` |
| Operation Steps | `sections.operation_steps` |
| Expect Result | `sections.expect_result` |
| Test Result | `sections.test_result` |
| Log And Screenshot Address | `sections.log_address` |
| Others / 版本备注 | `sections.others` |

派生（`derived`）：

| 字段 | 说明 |
|------|------|
| `test_power_ma` / `competitor_power_ma` / `delta_power_ma` | 从 Test Result / 摘要提取 |
| `dut_model` / `competitor_model` | 测试机 / 竞品机型 |
| `game_title` / `speaker_mode` | 如 PUBG、外放 |
| `test_case` | `nps` / `basic`（摘要含 NPS/最大亮度等） |
| `brightness` / `volume` / `refresh_rate` | max / unknown |
| `network` / `switches` / `logs_required` | 前置开关与日志要求 |
| `game_play` | 模式/地图/组队等操作步骤要点 |
| `expect_margin_ma` | 如标杆机 +20mA → `20` |
| `smb_log_path` | UNC 日志地址 |

## 使用方法

```bash
# 从工作区 jira_info.json
python analysis/domain/power/base/jira_testcase_parse/scripts/jira_testcase_parse.py \
  --jira-info temp/<DATE>/<KEY>/jira_info.json \
  --output temp/<DATE>/<KEY>/analysis/jira_testcase_parse.json

# 从单号（需凭证）
python .../jira_testcase_parse.py --jira-key CN6OS16-2121 -w temp/<DATE>/CN6OS16-2121

# 仅解析文本
python .../jira_testcase_parse.py --description-file desc.txt --summary "....PUBG...."
```

## 输出

默认打印 JSON；`--output` 时写入文件并只打印路径（遵守 AI-02）。

建议落盘：`<workspace>/analysis/jira_testcase_parse.json`

## 与 game flow 的关系

| 步骤 | 关系 |
|------|------|
| `orch_analyze_jira` 读单后 | 可立刻对本 skill 解析描述 |
| `flow_power_game` | 用 `derived.*_power_ma`、机型、游戏名填充澄清报告参数 |
| `flow_power_game_precondition` | 用 `derived.test_case` / 亮度音量要求作对照基准 |
