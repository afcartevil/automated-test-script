---
name: flow_power_game_thermal
description: 游戏场景温控：两步排查（thermal 信息/CPU 介入）与温升、降背光、限频聚合。
---
## 功能描述
flow 步骤 11。在 `T_game` 内按两步排查温控影响；并保留温升/降背光/限频聚合分析。

## 分析流程

| 步骤 | 名称 | 日志源 | 关键词 |
|------|------|--------|--------|
| 1 | 获取 thermal 信息 | main | `tran_thermal_engine`、`SKIN` |
| 2 | CPU 介入判断 | main | `ThermalEngineTypeData` / `min_cpu_freq` |

### 步骤 1 字段
- `temp`：触发温度（℃）
- `scene=scene_game`：游戏场景
- `fgAct`：前台 Activity
- `gameMode`：1=开启游戏模式
- `gameFuncMode`：1=录屏/直播
- `SKIN value`：模拟壳温

输出：**温度曲线**（vt_shell / SKIN / CPU 分源）、均值/极值统计。

### 澄清报告（thermal 策略）
- **thermal降亮度**：一句话是否生效；生效则按档列出（生效温度、亮度降至多少 nits、测试最高温度）
- **thermal限频**：一句话是否生效；生效则按档列出（生效温度、limits/状态、最高温度）
- 附 **T_game 温度曲线**（vt_shell 壳温 + SKIN；若日志有 CPU/tscpu/Tj 再叠加 CPU）
- 仅 `gameMode=1` 且 limits 全 0 **不算**降亮/限频生效

### 步骤 2 判定
`min_cpu_freq, value: 0.5,0.5` → thermal 介入，降低 CPU 下限；`unknown` 为未介入。

## 配置文件
- `references/keyword-patterns.yaml`
- `references/analysis-standards.yaml`

## 输入参数
1. **log_path**（可选）：默认 `flow/game/mobilelog/<APLog_*>`，示例 `.../flow/game/mobilelog/APLog_2026_0622_201151__6`
2. **--window-json**（可选）：默认 `<log_path>/analysis/game_time_window.json`
3. **--game-package**（可选）

## 输出结果
`analysis/game_thermal.json`：
- **`thermal_investigation`**：`step1_thermal_info`、`step2_cpu_intervention`
- `temperature`、`thermal_backlight`、`tran_thermal_engine` 等原有字段

## 使用方法
```bash
python analysis/domain/power/flow/game/game_thermal/scripts/game_thermal.py
```
