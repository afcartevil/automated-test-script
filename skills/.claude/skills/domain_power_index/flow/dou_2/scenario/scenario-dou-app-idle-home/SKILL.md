---
name: flow_power_dou_idle_home
description: >-
  DOU 主页/首页待机功耗分析。App 前台亮屏但操作极少时定位空闲 CPU、wakelock、
  保活心跳、定位/推送。用于 GCash/Grab 等「主页待机」场景。
scenario_id: scenario-dou-app-idle-home
category: idle
keywords: [主页待机, 首页待机, 待机, GCash, Grab]
example_scenes:
  - GCash主页待机
  - Grab主页待机
related_flow: flow/dou_2
related_base: [base_cpuinfo, base_batteryinfo, base_kernel_standby]
---

# DOU · 主页待机（app-idle-home）

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

- 场景名含「主页待机 / 首页待机」，前台 App 亮屏、几乎无滑动/点击。
- 差异主要来自空闲态：进程常驻、心跳、定位、推送、动画。

**排除**：Feed 滑动 → `scenario-dou-feed-scroll`；灭屏长待机 → `flow/standby_long`。

## YAML 业务步（实样）

每行 = **一个操作**；用时为该步 `actual_time`（非场景总时长；禁止只写场景总时长）。Setup 标 setup↓，不当主因。

### GCash主页待机-DATA（suffix=00547）

| # | 操作 step_name | sub_step | [t0,t1) s | **用时 actual_time** | expect | 角色 | op_kind |
|---|---------------|----------|-----------|---------------------|--------|------|---------|
| 1 | 确保退到桌面 | — | [0.0, 4.3) | **4.3s** | 3.0s | setup↓ | setup |
| 2 | 识别黑屏解锁 | — | [4.3, 12.5) | **8.2s** | 4.0s | setup↓ | setup |
| 3 | 左右滑桌面 | — | [12.5, 16.1) | **3.5s** | 3.0s | setup↓ | setup |
| 4 | 搜索打开GCash | — | [16.1, 26.0) | **10.0s** | 15.0s | setup↓ | app_launch |
| 5 | GCash应用界面待机 | — | [26.0, 76.2) | **50.2s** | 50.2s | 业务 | app_idle |
| 6 | 退到桌面 | — | [76.2, 77.4) | **1.2s** | 5.0s | setup↓ | setup |
| 7 | 单用例结束机械手回轴 | — | [77.4, 80.8) | **3.4s** | 3.0s | setup↓ | setup |

### Grab主页待机-DATA（suffix=00565）

| # | 操作 step_name | sub_step | [t0,t1) s | **用时 actual_time** | expect | 角色 | op_kind |
|---|---------------|----------|-----------|---------------------|--------|------|---------|
| 1 | 确保退到桌面 | — | [0.0, 4.5) | **4.5s** | 3.0s | setup↓ | setup |
| 2 | 识别黑屏解锁 | — | [4.5, 12.7) | **8.2s** | 4.0s | setup↓ | setup |
| 3 | 左右滑桌面 | — | [12.7, 16.1) | **3.5s** | 3.0s | setup↓ | setup |
| 4 | 搜索打开Grab | — | [16.1, 25.4) | **9.3s** | 15.0s | setup↓ | app_launch |
| 5 | 主页待机70s | — | [25.4, 25.5) | **0.1s** | 0.1s | 业务 | app_idle |
| 6 | 退到桌面 | — | [25.5, 26.7) | **1.2s** | 5.0s | setup↓ | setup |
| 7 | 单用例结束机械手回轴 | — | [26.7, 30.1) | **3.4s** | 3.0s | setup↓ | setup |

> Grab 样例中业务步 `主页待机70s` 的 YAML `actual_time=0.1s` 异常（与步名不符）；分析当次跑数时以该次 YAML 为准，并核对 high/low 公平性。

## 2. 分析侧重点

| 优先级 | 查什么 |
|--------|--------|
| P0 | YAML 待机步 `[t0,t1)` 内：底电平台高且尖峰稀疏 → 常驻；密尖峰 → 心跳/定位 |
| P0 | 高功耗侧 Top 进程是否为业务主进程 / 关联沙箱（对照 KI-001） |
| P0 | wakelock / Alarm / JobScheduler / FGS 是否异常偏多 |
| P1 | 定位（GPS/FLP）、推送长连接是否持续活跃 |
| P1 | 首页 Lottie/广告/轮播动画导致持续 GPU/CPU |
| P2 | 网络心跳周期是否显著密于低功耗版 |

## 3. Log / 数据锚点

- CPU：`cpu_analysis_*.json` Top 进程、`large_diff_processes`
- 电流：`current_cpu_spike_*.json` 底电高、尖峰稀疏 → 偏常驻；尖峰密 → 偏心跳/定位
- main/sys：`WakeLock`、`AlarmManager`、`JobScheduler`、`FusedLocation`、`Going to sleep`（应少见）
- 包名关键词：`gcash`、`grab`（随场景替换）

## 4. 步骤

1. 确认场景时长与亮屏标签（`dou_2` Excel / report）。
2. 跑通 CPU + 电流 + 综合 AI（`dou_2` §4–§5）。
3. 对比高低版：主进程平均 CPU、wakelock 持有时长。
4. 若电流平台抬高且尖峰少 → 查动画/渲染/常驻线程；尖峰周期明显 → 查定位/心跳。
5. 结论写清：常驻负载 vs 周期唤醒，并给出包名+进程名。

## 5. 结论模板

- **现象**：主页待机电流/mAh 偏高 Δ=
- **主因进程**：
- **机制**：常驻 / 周期唤醒 / 定位 / 推送 / 动画（择一或组合）
- **建议验证**：冻结可疑组件 / 关定位 / 对比心跳间隔
