---
name: flow_power_game
description: MTK 平台游戏场景功耗：按 14 步完成日志检查、分维分析、汇总、电流关联、功耗差确认/诊断并输出澄清报告。
---
## 功能描述
MTK Android 游戏场景功耗分析编排入口。步骤 1~14 中，步骤 2 调用公共 skill [mtk_kernellog_convert](../../../base/mtk_kernellog_convert/SKILL.md) 做 kernel 绝对时间转换；步骤 3~14 为 game 子 skill。

**日志路径约定**：所有需 `log_path` 的步骤，默认使用 `flow/game/mobilelog/<APLog_*>`（见 `scripts/game_log_paths.py`）。

## Agent 必做：项目与测试场景
亮度/音量「要求」来自飞书 [亮度和音量表](https://transsioner.feishu.cn/wiki/TTAVwmmIrif4uoknp1rcqRatn2V?sheet=4258R0)（本地镜像 `game_precondition/references/brightness-volume-by-project.yaml`）。

JIRA 描述中的 **Precondition / Test Result / 功耗数字 / 竞品机型** 等，优先用公共 skill [`base_jira_testcase_parse`](../../base/jira_testcase_parse/SKILL.md) 解析为 `analysis/jira_testcase_parse.json`，再填入 `--test-power-ma` / `--competitor-power-ma` / `--game-title` 等。

| 日志来源 | 项目 | 测试场景（basic / nps） |
|----------|------|-------------------------|
| **JIRA 单** | 从摘要/描述/`affect_project` 解析「项目N」等 | 从摘要/描述识别「基础场景」或「NPS/最大亮度」 |
| **本地路径** | **必须提示用户选择**表中项目（或传 `--project`） | 可一并选择；默认 `basic` |

解析结果写入 `<log_path>/analysis/game_analysis_meta.json`，步骤 4/6/14 共用。CLI：`game_project_resolve.resolve_project_context`；全流程：`run_game_flow.py --project` / `--jira-key`。

## 执行步骤
| 步骤 | 名称 | 调用 |
|------|------|------|
| 1 | 日志检查 | 本节门禁 + `discover_logs`（mobile 核心：events/main/sys/kernel/radio + bugreport → `log_inventory`） |
| 2 | kernel 时间转换 | [mtk_kernellog_convert](../../../base/mtk_kernellog_convert/SKILL.md) |
| 3 | 场景识别 | [game_time_window](./game_time_window/SKILL.md) |
| 4 | 前置条件检查 | [game_precondition](./game_precondition/SKILL.md) |
| 5 | 功耗拆解 | [game_power_model](./game_power_model/SKILL.md) |
| 6 | 显示 | [game_brightness](./game_brightness/SKILL.md) |
| 7 | 音量 | [game_volume](./game_volume/SKILL.md) |
| 8 | CPU/GPU/DDR | [game_cpu_gpu_ddr](./game_cpu_gpu_ddr/SKILL.md) |
| 9 | 后台应用 | [game_background](./game_background/SKILL.md) |
| 10 | 网络连接 | [game_network](./game_network/SKILL.md) |
| 10b | 抓包功耗影响（条件） | [game_network_cap](./game_network_cap/SKILL.md)（networklog + T_game 重叠 .cap） |
| 11 | Thermal | [game_thermal](./game_thermal/SKILL.md) |
| 12 | 数据汇总 | [game_summary](./game_summary/SKILL.md) |
| 13 | 电流↔日志关联 | [game_current_log_correlate](./game_current_log_correlate/SKILL.md) |
| 13b | 电流图对比（异常问题） | DOU [`run_current_cpu_spike.py`](../dou_2/tool1_2/run_current_cpu_spike.py)（经 [`scripts/run_game_current_cpu_spike.py`](./scripts/run_game_current_cpu_spike.py)） |
| 14 | 诊断→澄清报告 | [game_diagnosis_report](./game_diagnosis_report/SKILL.md) |

步骤 6~11 须 `--window-json`（默认 `<log_path>/analysis/game_time_window.json`）。步骤 6~11 可并行。步骤 13/13b 无 pt5 时 `status=skipped` 不阻断。步骤 14 须在步骤 12（及可选 13/13b）之后：确认功耗差、初步诊断、AI 建议，**合并写入** `game_power_clarify_report.html`（规则引擎复用 [game_root_cause](./game_root_cause/SKILL.md)；「异常问题」第 1 项嵌入 `game_current_cpu_spike.report_html`）。

**步骤 I/O 详表**：见 [references/flow-io-steps.yaml](./references/flow-io-steps.yaml)（每步输入 / 读哪些日志 / 输出哪些文件与关键字段）。
**归因对标**：见 [game_root_cause/references/cause-attribution-mapping.yaml](./game_root_cause/references/cause-attribution-mapping.yaml)（各步结果汇总进澄清报告四类诊断 + 器件拆解）。

## 输入参数
1. **log_path**（可选）：默认 `flow/game/mobilelog/<APLog_*>`，也可传 **case 根目录**；其下若有 ≥2 份 `APLog_*` 则分别分析并对比输出
2. **log_compare**（可选）：显式指定对比机 APLog；省略且仅 1 份日志时不对比
3. **game_package**（可选）
4. **project / test_case / jira_key**：见上文「项目与测试场景」
5. 时间窗由步骤 3 产出
6. 步骤 13/13b 可选 `--pt5` / `--pt5-compare` / `--pt5-dir` / `--jira-key`
7. 步骤 14 建议补充问题单功耗：`--test-power-ma` / `--competitor-power-ma` / `--delta-power-ma` 与已知差；双机时 `--compare-analysis-dir` / `--log-compare`

## 输出结果
各步 `analysis/game_*.json`；步骤 12 产出 `game_power_compare_summary.json`、`game_power_report.html`；步骤 13 产出 `game_current_log_correlate.json`；步骤 13b 产出 `game_current_cpu_spike.json` / `current_cpu_spike_game.json`（含可嵌入的 `report_html`）；步骤 14 产出 `game_power_delta.json`、`game_preliminary_diagnosis.json`、`game_ai_insights.json`、`game_root_cause.json`、各分维 `*_report.html`、**`game_power_clarify_report.html`**；步骤 2 在原目录生成 `*_linli_666.txt`

## 使用方法
```bash
LOG="analysis/domain/power/flow/game/mobilelog/APLog_2026_0622_201151__6"

# 路径模式：先选/指定项目（或 TTY 下交互）
python .../game_precondition.py "$LOG" --project 项目1 --test-case basic

# JIRA 模式：从单号解析项目与场景
python .../game_precondition.py "$LOG" --jira-key PROJ-12345

# 一键全流程（路径模式指定项目）
python .../scripts/run_game_flow.py "$LOG" --project 项目1 --test-case basic --debug-log

# 一键全流程（case 根目录：两份 APLog 自动对比）
python .../scripts/run_game_flow.py "$CASE_DIR" --project 项目1 --test-case basic --jira-key PROJ-123

# 一键全流程（显式双日志）
python .../scripts/run_game_flow.py "$LOG_DUT" --log-compare "$LOG_REF" --project 项目1 --test-case basic

# 一键全流程（JIRA）
python .../scripts/run_game_flow.py "$LOG" --jira-key PROJ-12345 --debug-log
```

## 工作原理
1. 步骤 1 检查 event/kernel/main/sys 可用性
2. 步骤 2 将 kernel_log 转为 `*_linli_666.txt` 绝对时间
3. 步骤 3 确定 `T_game`
4. 步骤 4~11 分维解析（亮度/音量要求按项目×用例查表）
5. 步骤 12 汇总各维证据
6. 步骤 13 用 pt5 找抬高窗并对齐日志归因（可跳过）；步骤 13b 接入 DOU `current_cpu_spike` 做双机电流对比（可跳过）
7. 步骤 14 确认 I1 / 排除已知差并分流，规则诊断 + AI，输出澄清 HTML

## 调试日志
各 skill CLI 支持调试开关，输出到 `flow/game/game_test.log`（可用 `GAME_SKILL_DEBUG_LOG` 改路径）：

| 开关 | 说明 |
|------|------|
| `--debug-log` | 开启：打印 skill 作用、输入、输出摘要 |
| `--no-debug-log` | 强制关闭 |
| `GAME_SKILL_DEBUG=1` | 环境变量开启（子进程可继承） |

一键全流程（默认开日志）：
```bash
python analysis/domain/power/flow/game/scripts/run_game_flow.py --debug-log
```
