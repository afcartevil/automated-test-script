---
name: flow_power_game_kernel_cpu
description: 游戏场景 Kernel [K] CPU 与线程统计（game_cpu_gpu_ddr 子模块）。
---
## 功能描述
在 `T_game` 内解析 kernel `[K][Perf] TRAN Perf Statistic` 块。**flow 步骤 8 完整入口**为 [game_cpu_gpu_ddr](../game_cpu_gpu_ddr/SKILL.md)；本 skill 仅 CPU/[K] 子模块，可单独运行。

## 输入参数
1. **log_path**（可选）：默认 `flow/game/mobilelog/<APLog_*>`，示例 `.../flow/game/mobilelog/APLog_2026_0622_201151__6`
2. **--window-json**（可选）：默认 `<log_path>/analysis/game_time_window.json`
3. **--soc-model**（可选）

## 输出结果
`analysis/game_kernel_cpu.json`

## 使用方法
```bash
python analysis/domain/power/flow/game/game_kernel_cpu/scripts/game_kernel_cpu.py
```

## 注意事项
- 须先完成步骤 2 kernel 时间转换
- GPU/DDR/FPSGO 见 flow 步骤 8 `game_cpu_gpu_ddr`
