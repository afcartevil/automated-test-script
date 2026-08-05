---
name: flow_power_dou_maps_nav
description: >-
  DOU 地图导航功耗分析。定位 GPS/FLP、地图瓦片、导航常亮与算路负载。
  用于 Google Maps「导航目的地」等场景。
scenario_id: scenario-dou-maps-nav
category: location
keywords: [导航, Maps, 目的地, GPS, 地图]
example_scenes:
  - Google Maps导航目的地
related_flow: flow/dou_2
related_base: [base_cpuinfo, base_batteryinfo]
---

# DOU · 地图导航（maps-nav）

## 适用场景

见下文 §1 / §2。

## 输入

- `cpu_analysis_<suffix>.json`、`current_cpu_spike_<suffix>.json`（`flow_power_dou` 主流程产出）
- `meta_report` 场景 YAML（`read_scene_yaml_ops.py`）

## 执行流程

见 §4 步骤。

## 输出

见 §5 结论模板。

## 门禁

须已完成 TopN + CPU + spike + AI；对照 [`known_issues.md`](../../known_issues.md) KI-001/KI-002。

## 1. 适用

- 场景名含 Maps/导航/目的地，前台导航态（定位持续、地图刷新）。
- 差异常在 GNSS、瓦片下载渲染、屏幕策略。

**排除**：主页待机类地图 App 闲置 → `scenario-dou-app-idle-home`。

## YAML 业务步（实样）

每行 = **一个操作**；用时为该步 `actual_time`（非场景总时长；禁止只写场景总时长）。Setup 标 setup↓，不当主因。

### Google Maps 导航目的地-DATA（suffix=00611）

| # | 操作 step_name | sub_step | [t0,t1) s | **用时 actual_time** | expect | 角色 | op_kind |
|---|---------------|----------|-----------|---------------------|--------|------|---------|
| 1 | 确保退到桌面 | — | [0.0, 4.4) | **4.4s** | 3.0s | setup↓ | setup |
| 2 | 识别黑屏解锁 | — | [4.4, 17.0) | **12.6s** | 4.0s | setup↓ | setup |
| 3 | 左右滑桌面 | — | [17.0, 20.5) | **3.5s** | 3.0s | setup↓ | setup |
| 4 | 搜索打开GoogleMaps | — | [20.5, 31.9) | **11.4s** | 15.0s | setup↓ | app_launch |
| 5 | 点出导航到导航结束 | — | [31.9, 106.4) | **74.5s** | 74.5s | 业务 | maps_nav |
| 6 | 退到桌面 | — | [106.4, 116.4) | **9.9s** | 6.0s | setup↓ | setup |
| 7 | 单用例结束机械手回轴 | — | [116.4, 119.7) | **3.4s** | 3.0s | setup↓ | setup |


## 2. 分析侧重点

| 优先级 | 查什么 |
|--------|--------|
| P0 | 定位模式（GPS vs 网络）、定位上报频率 |
| P0 | Maps 主进程 + 渲染 CPU |
| P1 | 导航中屏幕常亮 / 亮度策略差异 |
| P1 | 语音导航 `audioserver` 是否额外偏高 |
| P2 | 瓦片缓存未命中导致重复下载渲染 |

## 3. Log / 数据锚点

- CPU：`com.google.android.apps.maps`、`com.google.android.gms`（位置相关）
- main/sys：`FusedLocation`、`GpsLocationProvider`、`Navigation`、`WakeLock`（导航）
- 电流：持续高平台（定位+渲染），少见纯尖峰形态

## 4. 步骤

1. `dou_2` CPU + spike + AI；确认整段均为导航态。
2. 对比定位 provider 与 fix 频率。
3. 对比主进程/GMS 位置相关 CPU。
4. 核对亮屏与语音是否两边一致（脚本公平性）。
5. 结论区分定位 vs 渲染 vs 屏幕。

## 5. 结论模板

- **现象**：导航功耗偏高 Δ=
- **主因**：GNSS/FLP 频率 / 地图渲染 / 常亮或语音
- **证据**：
- **建议**：核对定位模式、缓存、屏幕策略
