---
name: flow_power_game_current_log_correlate
description: 电流波形(pt5)与日志关联：定位抬高窗口并归因（flow 步骤 13，无 pt5 可跳过）。
---
## 功能描述
flow **步骤 13**（须在步骤 12 `game_summary` 之后、步骤 14 `game_diagnosis_report` 之前）。

单机 A 模式：从 pt5（或 CSV/JSON 电流序列）找相对底电流抬高 ≥ 阈值的 Top-N 窗口，按 `T_game.start + t_sec` 对齐日志，依次关联：

1. kernel_cpu → 2. brightness → 3. background → 4. network → 5. thermal

无 pt5 时输出 `status=skipped`，**不阻断**后续诊断。

## 输入参数
1. **log_path**（可选）：默认 `flow/game/mobilelog/<APLog_*>`
2. **--pt5**（可选）：`.pt5` / `.csv` / `.json` 电流文件
3. **--pt5-dir**（可选）：在目录内自动搜索 `.pt5`/电流 CSV
4. **--jira-key**（可选）：在 `analysis`、下载目录等处按单号旁路查找附件
5. **--threshold-ma**（默认 20）、**--window-sec**（默认 10）、**--step-sec**（默认 2）、**--top-n**（默认 3）
6. **--pt5-offset-sec**（默认 0）：pt5 相对 `T_game.start` 的偏移

## 输出结果
写入 `<log_path>/analysis/`：
- `game_current_log_correlate.json`
- `game_current_log_correlate_report.html`（可选摘要）

JSON 含 `raised_windows[]`（主因、证据、对均值贡献）与 `waveform_analysis`（供步骤 14 功耗差确认）。

## 使用方法
```bash
LOG="analysis/domain/power/flow/game/mobilelog/APLog_2026_0622_201151__6"

# 有 pt5
python analysis/domain/power/flow/game/game_current_log_correlate/scripts/game_current_log_correlate.py \
  "$LOG" --pt5 "D:/path/scene.pt5"

# 无 pt5 → skipped，继续 flow
python analysis/domain/power/flow/game/game_current_log_correlate/scripts/game_current_log_correlate.py "$LOG"
```

## 注意事项
- MVP 仅单机相对底电抬高；双机 diff 后续扩展
- 二进制 `.pt5` 优先走本机 `pt5_reader`；不可用时请导出 CSV（`t_sec,current_ma`）
