---
name: flow_power_game_brightness
description: 游戏场景显示：六步亮度排查（测试亮度/自动背光/背光2.0/AAL/温控/刷新率）及变光阶段分析。
---
## 功能描述
flow 步骤 6。输入为步骤 2 转换后的 **kernel log**、**main log**、**sys log**，按下列六步顺序排查显示相关功耗因素；并保留启动 20s / 游戏内背光变光阶段汇总（`brightness_analysis`）。

## 2. 分析流程

| 步骤 | 名称 | 主日志源 | 关键词 / 判定 |
|------|------|----------|----------------|
| 1 | 获取测试设置亮度 | main | 基础场景：`TAB.BrightnessCollector: brightness: N` ↔ 表「350nit」列等级 |
| | | sys | NPS：`DisplayPowerController` `BrightnessEvent` 的 `nits` ↔ 表「最大亮度」列 nit |
| | | sys（备用） | `BrightnessSynchronizer: Swallowing update of N`（基础场景） |
| 2 | 检测自动背光 | main | `SensorService` + `AutomaticBrightnessController`，`activate = true/false` |
| | | kernel（备用） | `[K]` 含 `mtk_drm_cwb`；或 `cwb_work_func` 含 `cwb enable` |
| | | | **开启 → 测试条件未对齐** |
| 3 | 背光 2.0（仅最大亮度场景） | main/sys | 搜 `DisplayPowerController` `BrightnessEvent`：`nits=`=实时亮度，`brt=(XX%)`=下降比例；对照 `references/backlight-2.0-games.yaml` |
| | | | main 优先、sys 补充；结果输出到澄清报告「软件策略差异」 |
| | | | 不在名单 → 输出「场景未添加背光2.0策略」 |
| 4 | AAL / 降背光策略 | main | `calculateBrightness` / `brightness_val`（关键词 `brightness`）：`brightness(ratio)`=打折率，`brightness_val`=曲线(0-4095/5119)；**连续变光停止后的最后一行为准确值** |
| | | main | `AALService` `BL=`/`EL=`：与 HWC 停止点对齐 |
| | | sys | `DisplayPowerController` `BrightnessEvent`：`brt=(XX%)` 打折率，`nits=` 实时 nit |
| | | | 时间线示例：`4095 700nit → 2881 450nit → 4095 700nit`；快照只保留各段停止末行（main+AAL+sys） |
| | | | 进游戏前 `brightness_val` 达曲线最大值且无 0-255 level → 认定测试亮度=255 |
| 5 | 温控降亮 | main/sys | `thermalLightController`：`Level-N`、触发 app、`temp`、`brightnessNits` |
| | | | **测试前或测试中触发 → 测试手法问题** |
| 6 | 屏幕刷新率 | main/sys | `PowerHalWrapper: updateFps(): N`（支持刷新率） |
| | | main/sys | `hwcomposer` `fps:N`（实际送显刷新率） |
| | | | 结果输出到澄清报告「软件策略差异」：曲线（点标 Hz）+ 默认折叠日志快照 |

最大亮度场景：CLI `--max-brightness-scenario`，或测试前 `BrightnessCollector` 等级 = 255 自动推断（仅影响背光 2.0 步骤）。

测试亮度设定（飞书 [亮度和音量表](https://transsioner.feishu.cn/wiki/TTAVwmmIrif4uoknp1rcqRatn2V?sheet=4258R0)）：
- 表：`game_precondition/references/brightness-volume-by-project.yaml`
- `--project` + `--test-case basic|nps`
- **基础场景**：日志等级 ↔ `brightness_level`（350nit 列，例：项目1=140）
- **NPS场景**：sys `DisplayPowerController` nits ↔ `brightness_nits`（最大亮度列）
- 350nit / 72dB：物理标定说明

## 日志来源（变光阶段）

| 来源 | 日志 | 关键词 | 字段 | 范围 |
|------|------|--------|------|------|
| BrightnessCollector | main | `TAB.BrightnessCollector: brightness:` | level | 0–255 |
| BrightnessSynchronizer | sys | `Swallowing update of` | level | 0–255 |
| HWC | main | `brightness_val` | curve, ratio=val/4095 | 0–4095 |
| LCM | kernel | `lcm_setbacklight` | level | 0–4095 |
| AAL | main | `AALService` + `BL=`（兼容 `EL=`） | curve；有日志=生效；代表值=末次或 ≥2s 稳定 | 0–4095 |

## 配置文件
- `references/keyword-patterns.yaml`：关键词与正则
- `references/analysis-standards.yaml`：阈值（`merge_burst_seconds=2` 等）
- `references/backlight-2.0-games.yaml`：背光 2.0 游戏名单与下降比例

## 输入参数
1. **log_path**（可选）：默认 `flow/game/mobilelog/<APLog_*>`，示例 `.../flow/game/mobilelog/APLog_2026_0622_201151__6`
2. **--window-json**（可选）：默认 `<log_path>/analysis/game_time_window.json`（含 `T_game` 与 `game_package`）
3. **--game-package**（可选）：覆盖场景识别包名
4. **--max-brightness-scenario**（可选）：JIRA 标注最大亮度时指定
5. **--launch-seconds**（可选）：启动变光窗秒数，默认 20

## 输出结果
`analysis/game_brightness.json`：
- **`brightness_investigation`**：六步结构化结论（`step1_test_setting` … `step6_refresh_rate`）
- **`brightness_analysis`**：`pre_game_setting`、`launch_window`、`in_game_changes`
- **`thermal_brightness`**、`refresh_rate`、`pre_test_brightness`

## 使用方法
```bash
python analysis/domain/power/flow/game/game_brightness/scripts/game_brightness.py
```
