---
name: flow_power_game_summary
description: 游戏功耗数据汇总：合并各维 JSON，输出 compare_summary 与 HTML 报告（flow 步骤 12）。
---
## 功能描述
flow 步骤 12。封装 `game_power_parser.py` 全量解析：合并步骤 3~11 各维证据，生成主因排序与 HTML 报告。

## 输入参数
1. **log_path**（可选）：默认 `flow/game/mobilelog/<APLog_*>`，示例 `.../flow/game/mobilelog/APLog_2026_0622_201151__6`
2. **--output-dir**（可选）：默认 `<log_path>/analysis`
3. **--game-package**（可选）

## 输出结果
`game_power_compare_summary.json`、`game_power_report.html`

## 使用方法
```bash
python analysis/domain/power/flow/game/game_summary/scripts/game_summary.py
```

## 注意事项
- 建议先跑步骤 2~11 子 skill，全量 parser 亦可独立运行
