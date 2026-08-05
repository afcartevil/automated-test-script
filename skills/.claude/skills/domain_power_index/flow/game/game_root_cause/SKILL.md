---
name: flow_power_game_root_cause
description: 游戏功耗澄清原因判断：基于步骤 12 汇总数据，按归因 YAML 规则输出 JSON 与澄清报告 HTML。
---
## 功能描述
flow **步骤 13**（须在步骤 12 之后）。读取 `analysis/game_power_compare_summary.json` 与各 `game_*.json`，按 `references/cause-judgment-rules.yaml` 做原因判断，并生成澄清报告。

步骤 → 归因对标见 `references/cause-attribution-mapping.yaml`。

## 归因类别
| 类别 | 说明 |
|------|------|
| 1. 测试手法不符 | **日志不全**（监测不完整 / 无场景时段 / 时长&lt;3min）+ 前置条件不符 + 亮度/音量不符 + 温控降背光 + thermal 限频 + 后台下载 |
| 2. 器件差异 | 屏、喇叭、CPU 平台、WiFi/Modem（报告拆解表；初步诊断四类之外） |
| 3. 软件策略差异 | 背光2.0（仅最大亮度）、AAL、触发 thermal（如 gameMode）、滑动提频/DDR/提频锁屏/帧率与竞品差 |
| 4. 功能差异 | 游戏助手、灵动岛、灯效、电梯模式、游戏 AI、沉浸音效、录屏投屏 |
| 5. 异常问题 | 异常进程 CPU、自启动/内存/GC、弱网/WiFi 共存/驻网频段/大流量 |

### 测试手法不符 · 日志不全
| 规则要点 | 数据来源 |
|----------|----------|
| 监测日志不完整：mobile 核心或缺 bugreport | 步骤1 `log_inventory`；mobile=`events/main/sys/kernel/radio` |
| 无测试场景时间段 / 场景覆盖不全 | [game_time_window](../game_time_window/SKILL.md) |
| 测试时长 &lt;3min | `game_window.duration_seconds` |

规则阈值与路径见 `references/cause-judgment-rules.yaml`；报告展示见 `references/report-defaults.yaml`。

## 输入参数
1. **log_path**（可选）：默认 `flow/game/mobilelog/<APLog_*>`
2. **--analysis-dir**（可选）：默认 `<log_path>/analysis`
3. **--meta-json** / CLI 元数据：`jira_key`、`device_model`、`competitor_power_ma`、`test_power_ma` 等（器件/竞品策略类需补充）
4. **--expected-network**：`wifi` 或 `data`（前置网络场景，默认 wifi）

## 输出结果
- `analysis/game_root_cause.json`：结构化判断与证据摘要
- `analysis/game_power_clarify_report.html`：澄清报告

完整「确认功耗差 + AI 建议」请走步骤 13 [game_diagnosis_report](../game_diagnosis_report/SKILL.md)。

## 使用方法
```bash
python analysis/domain/power/flow/game/game_root_cause/scripts/game_root_cause.py

python analysis/domain/power/flow/game/game_root_cause/scripts/game_root_cause.py \
  --jira-key PROJ-12345 \
  --device-model "测试机 / 竞品机" \
  --competitor-power-ma 850 --test-power-ma 920 --delta-power-ma 70
```

## 注意事项
- 步骤 12 未跑时，会回退合并已有 `game_*.json` 做判断
- 器件差异、竞品策略对比等需 `--meta-json` 或 CLI 传入，否则相关规则不命中
- 功能差异类通过日志关键词扫描，命中后建议人工复核
- 「日志不全」不把 ged/pmic/dramc 等可选日志算作核心缺失
