---
name: flow_power_game_network
description: 游戏场景网络：四步排查（WiFi 信号/场景切换/蜂窝信号/数传）与 RF 聚合。
---
## 功能描述
flow 步骤 10。在 `T_game` 内按四步排查网络影响；并保留 `rf_stats` 聚合分析。

## 分析流程

| 步骤 | 名称 | 日志源 | 关键词 |
|------|------|--------|--------|
| 1 | WiFi 信号强度 | main | `TranWifiSmartAssistantController` / `====>>rssi` |
| 2 | WiFi 场景切换 | radio | `NetworkStatusMonitor` / `updateInterfaceNameMap` |
| 3 | 蜂窝信号强度 | radio | `RmmNwHdlr`（rsrp/rsrq/sinr/band） |
| 4 | 数据 rx/tx | kernel | `ccmni` |

### 步骤 1
- 解析 `rssi :-35`（dBm）
- 输出 **RSSI 曲线** 与 **信号质量使用率**（excellent/good/fair/poor）
- 解析 `top app … in white list` / `stop monitor`：白名单游戏停 monitor → 局内无周期性 RSSI（≠断网）

### 步骤 2
- `wifi:wlan0 , changed` → WiFi 端口变化
- `mobile:` 为空 → 未走蜂窝；非空 → 有蜂窝数据
- 搜索范围：radio / main / sys

### 双通道判定
- **是**：WiFi 活跃（SSID/RSSI/接口）且蜂窝有数传（`mobile:` 非空 或 ccmni rx+tx 增量达标）
- **否（仅信号）**：WiFi 活跃 + 有 RSRP 采样，但无蜂窝数传 → 纯 WiFi
- RSRP/band **不等于**双通道

### 步骤 3
- 统计 rsrp/rsrq/sinr **平均值**与**变化曲线**
- 检测 **band** 是否切换

### 步骤 4
- 识别 rx 增长的 `ccmniN` 接口
- 统计首尾 rx/tx **差值**（字节）

## 配置文件
- `references/keyword-patterns.yaml`
- `references/analysis-standards.yaml`

## 输入参数
1. **log_path**（可选）：默认 `flow/game/mobilelog/<APLog_*>`，示例 `.../flow/game/mobilelog/APLog_2026_0622_201151__6`
2. **--window-json**（可选）：默认 `<log_path>/analysis/game_time_window.json`

## 输出结果
`analysis/game_network.json`：
- **`network_investigation`**：`step1_wifi_rssi` … `step4_ccmni_transfer`、`dual_channel`
- **`rf_stats`** 等原有字段

## 使用方法
```bash
python analysis/domain/power/flow/game/game_network/scripts/game_network.py
```

### networklog /.cap 解析
已拆分为独立条件 skill：`../game_network_cap/SKILL.md`（门禁：networklog + T_game 重叠 .cap）。

```bash
python analysis/domain/power/flow/game/game_network_cap/scripts/game_network_cap.py <APLog>
```

输出 `game_network_cap.json`（含 `power_impact`），澄清报告追加「抓包功耗影响」。

## 注意事项
- 弱网须与步骤 8、9 交叉验证
- kernel `ccmni` 无墙钟时间戳时，step4 退化为日志文件内首尾差值
- 局内 `====>>rssi` 常停记：曲线**仅输出 T_game**；用白名单/`stop monitor` 解释空窗，不用局外点补曲线
