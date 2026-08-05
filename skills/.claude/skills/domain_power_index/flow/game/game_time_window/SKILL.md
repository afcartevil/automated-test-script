---
name: flow_power_game_time_window
description: 游戏场景时间窗对齐：识别测试应用与前台时段，检查 kernel/main/sys 是否在 T_game 内有日志覆盖。
---
## 功能描述
flow 步骤 3。从 event log 识别游戏前台 `T_start`~`T_end`，衍生 `T_pre`/`T_post`，并检查 kernel/main/sys 是否覆盖游戏时段。须先完成步骤 2 [mtk_kernellog_convert](../../../base/mtk_kernellog_convert/SKILL.md)。

## 分析项
- **游戏应用**：包名、游戏名（`references/game-packages.yaml`）
- **时间窗**：`T_pre`（默认前 5min）、`T_game`、`T_post`（默认后 3min）
- **日志覆盖**：mobile 核心（events/main/sys/kernel/radio）是否存在且与 `T_game` 重叠；输出 `log_coverage` + `log_inventory`
- **阶段**：`startup` / `stable` / `exit`

无满足要求的测试场景 → `status=failed|need_confirm`（澄清报告「日志无场景」）。
有场景但部分日志未覆盖 `T_game` → `log_inventory.scene_coverage_missing`（「场景日志不全」）。

## 输入参数
1. **log_path**（可选）：默认 `flow/game/mobilelog/<APLog_*>`，示例 `.../flow/game/mobilelog/APLog_2026_0622_201151__6`
2. **--game-package**（可选）
3. **--start** / **--end**（可选）
4. **--output**（可选）：默认 `<log_path>/analysis/game_time_window.json`

## 输出结果
`analysis/game_time_window.json`

## 使用方法
```bash
python analysis/domain/power/flow/game/game_time_window/scripts/game_time_window.py
```

## 注意事项
- event 缺失且未给包名与起止时间 → `status=failed`
- 优先使用步骤 2 生成的 `*_linli_666.txt`
