---
name: flow_power_game_network_cap
description: >
  条件步骤：日志含 networklog 且存在与 T_game 重叠的 .cap 时，解析抓包并提炼影响功耗的因子，
  写入 game_network_cap.json，供澄清报告「抓包功耗影响」区块使用。
---
## 功能描述
在 `game_network`（日志侧 RF/四步排查）之后，对 **networklog/.cap** 做抓包侧补充：

1. **门禁**：存在 `networklog`/`netlog`，且文件名粗筛有与 **T_game** 重叠的 `.cap` → 启动；否则 `status=skipped`
2. **解析**：文件名粗筛 → `capinfos` 确认重叠 → 仅解析重叠文件；默认 deep（协议/会话/`sll.ifindex`）→ `dual_channel`
3. **功耗提炼**：双通道、多接口、高包速率/高吞吐、抓包覆盖缺口等 → `power_impact`

## 触发条件
| 条件 | 说明 |
|------|------|
| networklog | APLog/设备根可解析到 `networklog` 或内含 `.cap` |
| T_game 重叠 cap | 文件名时间粗筛与 `game_time_window` 有重叠候选 |

不满足时仍写出 JSON（`skipped`），**不**调用 tshark。可用 `--force` 强制解析。

## 配置文件
- `references/power-impact-rules.yaml`：包速率 / 字节率 / 覆盖率阈值

## 输入
1. **log_path**：APLog 或含 networklog 的设备根
2. **--window-json**：默认 `<log_path>/analysis/game_time_window.json`

## 输出
`<log_path>/analysis/game_network_cap.json`：
- `gate`：门禁探测结果
- `files` / `dual_channel` / `overlapping_caps`
- **`power_impact`**：`has_impact` / `level` / `factors` / `impact_factors` / `report_rows` / `summary`

可选 `--device-label CN6`：额外写入 workspace `analysis/game_network_cap_<label>.json`。

## 使用方法
```bash
python analysis/domain/power/flow/game/game_network_cap/scripts/game_network_cap.py ^
  <APLog> --window-json <APLog>/analysis/game_time_window.json --device-label CN6
```

依赖主机 **Wireshark CLI**（`capinfos` / `tshark`）。解析库复用 `../game_network/scripts/network_cap_parse_lib.py`。

## 报告
澄清报告在「网络/RF 分析」后追加 **抓包功耗影响**（读取 ctx.`game_network_cap`.power_impact）。

## 注意事项
- 非重叠 `.cap` 不深解析
- 抓包覆盖不足时结论不可外推整局，需结合 main/radio
- 与日志侧 `game_network.dual_channel` 交叉验证
