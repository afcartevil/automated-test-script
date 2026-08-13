---
name: flow_power_game_volume
description: 游戏场景音量：TranAuraController 确认测试音量与游戏内变音量。
---
## 功能描述
flow 步骤 7。从 **main log** 的 `TranAuraController` 提取 STREAM_MUSIC 音量，确认测试前设置档位，并检测 `T_game` 内是否有变音量。

## 1. 分析流程

**输入**：转换后的 main log（辅以 events/sys 作对照）。

在 main log 中通过关键词 **`TranAuraController`** 获取音量：

```
TranAuraController: onAudioVolumeChange: streamType=3, volume=9, device=2, packageName=null, flags=4112
```

| 字段 | 含义 |
|------|------|
| `streamType=3` | STREAM_MUSIC（媒体/游戏音量） |
| `volume=9` | 音量档位 9 |
| `device=2` | 内置扬声器（外放喇叭） |
| `device=1` | 听筒 |
| `device=4` | 有线耳机 |
| `device=8` | 蓝牙 A2DP 等 |
| `packageName=null` | **按键调音**（非应用内调音） |

**步骤 1**：取 `T_pre` 内最后一次 `streamType=3` 的 `TranAuraController` 采样 → 测试设置音量。  
**步骤 2**：统计 `T_game` 内 `TranAuraController` 档位变化 → 判断测试过程中音量是否变化。

辅助源（可选对照，见 `keyword-patterns.yaml`）：`events_log` 的 `volume_changed`、`vol.Events`、`AudioPolicyInterfaceImpl` 等。

## 配置文件
- `references/keyword-patterns.yaml`：`TranAuraController` 正则与 device 映射
- `references/analysis-standards.yaml`：变音量合并间隔等阈值

## 输入参数
1. **log_path**（可选）：默认 `flow/game/mobilelog/<APLog_*>`，示例 `.../flow/game/mobilelog/APLog_2026_0622_201151__6`
2. **--window-json**（可选）：默认 `<log_path>/analysis/game_time_window.json`

## 输出结果
`analysis/game_volume.json`：
- **`volume_investigation`**：`step1_test_setting`、`step2_in_game_changes`
- **`pre_test_volume`**、**`in_game_volume`**：多源汇总（主结论以 `volume_investigation` 为准）

## 使用方法
```bash
python analysis/domain/power/flow/game/game_volume/scripts/game_volume.py
```
