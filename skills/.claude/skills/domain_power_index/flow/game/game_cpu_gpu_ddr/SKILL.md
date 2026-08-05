---
name: flow_power_game_cpu_gpu_ddr
description: 游戏场景 CPU/GPU/DDR：五步排查（滑动提频/DDR/trace/帧率/thermal 限频）与 kernel [K] 统计。
---
## 功能描述
flow 步骤 8。输入为 **main log**、**trace**（步骤 3 待 `game_trace` skill），在游戏测试时段 `T_game` 内按五步排查 CPU/GPU/DDR 相关功耗因素；并保留 kernel `[K]` 线程统计（[game_kernel_cpu](../game_kernel_cpu/SKILL.md)）。

## 2. 分析流程

| 步骤 | 名称 | 日志源 | 关键词 / 判定 |
|------|------|--------|----------------|
| 1 | 滑动提频 | main | `touch_boost` / `MTKPOWER_HINT_UX_SCROLLING` + `[recordCPUFreqInfo]`；配对下方最近 `perfLockAcq` 的 `duration`（ms） |
| 2 | DDR | main | `setDvfsrcDevFreqOpp` → `opp`、`freq`（GHz） |
| 3 | trace 解析 | perf-statistic.html / trace | 频率分布、限频策略启发式、CPU 动态功耗估算（见 [game_trace](../game_trace/SKILL.md)；推荐 `--perf-html` + `--soc-model`） |
| 4 | 应用帧率 | main | `BufferQueueProducer` `queueBuffer: fps=`；游戏图层 avg/min/max + 分布；fps≤5 持续低帧图层排除；对比标准 UI 图层检异常多出图层 |
| 5 | thermal 限频 | main | `tran_thermal_engine` → `temp`、`fgAct`、`limits{cluster0,cluster1,...}` |

cluster 频率：`-1` = 不受限制。`duration:3000` = 滑动提频 3s。

## 配置文件
- `references/keyword-patterns.yaml`
- `references/analysis-standards.yaml`
- `references/analysis-standards.yaml`（含标准 UI 图层名单 `standard_ui_layers`）

## 输入参数
1. **log_path**（可选）：默认 `flow/game/mobilelog/<APLog_*>`，示例 `.../flow/game/mobilelog/APLog_2026_0622_201151__6`
2. **--window-json**（可选）：默认 `<log_path>/analysis/game_time_window.json`
3. **--game-package**（可选）
4. **--trace-path**（可选）：原始 Perfetto/trace；旁路有 `perf-statistic.html` 时自动解析
5. **--perf-html**（可选）：MTK 工具导出的 `perf-statistic.html`（步骤 3 推荐输入）
6. **--soc-model**（可选）

## 输出结果
`analysis/game_cpu_gpu_ddr.json`：
- **`cpu_gpu_ddr_investigation`**：`step1_touch_boost` … `step5_thermal_throttle`
- **`kernel_cpu`**、`frequency`、`cpu_perf_lock`、`frame_rate`（多源汇总，主结论以 investigation 为准）

## 使用方法
```bash
python analysis/domain/power/flow/game/game_cpu_gpu_ddr/scripts/game_cpu_gpu_ddr.py
```

## 注意事项
- 须先完成步骤 2 kernel 时间转换
- 步骤 3 推荐传 `--perf-html`（MTK 工具从 trace 转出的 `perf-statistic.html`）；详见 `game_trace/SKILL.md`
