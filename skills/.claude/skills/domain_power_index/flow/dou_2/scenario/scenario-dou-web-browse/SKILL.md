---
name: flow_power_dou_web_browse
description: >-
  DOU 浏览器网页浏览功耗分析。定位 Chrome 渲染、多进程沙箱与页面脚本负载。
  用于 Chrome「浏览网页」场景。
scenario_id: scenario-dou-web-browse
category: browser
keywords: [Chrome, 浏览网页, 浏览器, WebView]
example_scenes:
  - Chrome浏览网页
related_flow: flow/dou_2
related_base: [base_cpuinfo]
known_issues: [KI-001]
---

# DOU · 浏览器网页浏览（web-browse）

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

- 场景名含 Chrome/浏览网页，以多页面滚动、站点脚本为主。
- 沙箱进程高 CPU 极常见（KI-001），必须锚定标签页/宿主。

**排除**：Drive 文档 → `scenario-dou-document-browse`；App 内 Feed → `scenario-dou-feed-scroll`。

## YAML 业务步（实样）

每行 = **一个操作**；用时为该步 `actual_time`（非场景总时长；禁止只写场景总时长）。Setup 标 setup↓，不当主因。

### Chrome浏览网页视频-DATA（suffix=00576）

| # | 操作 step_name | sub_step | [t0,t1) s | **用时 actual_time** | expect | 角色 | op_kind |
|---|---------------|----------|-----------|---------------------|--------|------|---------|
| 1 | 确保退到桌面 | — | [0.0, 4.4) | **4.4s** | 3.0s | setup↓ | setup |
| 2 | 识别黑屏解锁 | — | [4.4, 16.9) | **12.5s** | 4.0s | setup↓ | setup |
| 3 | 左右滑桌面 | — | [16.9, 20.4) | **3.5s** | 3.0s | setup↓ | setup |
| 4 | 搜索打开Chrome | — | [20.4, 28.8) | **8.4s** | 15.0s | setup↓ | app_launch |
| 5 | 进入Transsion网页 | — | [28.8, 64.3) | **35.6s** | 18.0s | 业务 | unknown |
| 6 | 循环滑动 | 循环滑动 | [64.3, 104.6) | **40.3s** | 40.2s | 业务 | feed_scroll |
| 7 | 循环滑动 | — | [104.6, 144.9) | **40.3s** | 40.2s | 业务 | feed_scroll |
| 8 | 单用例结束机械手回轴 | — | [144.9, 148.4) | **3.5s** | 3.0s | setup↓ | setup |

### Chrome浏览网页-WIFI（suffix=00671）

| # | 操作 step_name | sub_step | [t0,t1) s | **用时 actual_time** | expect | 角色 | op_kind |
|---|---------------|----------|-----------|---------------------|--------|------|---------|
| 1 | 确保退到桌面 | — | [0.0, 6.3) | **6.3s** | 3.0s | setup↓ | setup |
| 2 | 识别黑屏解锁 | — | [6.3, 14.0) | **7.7s** | 4.0s | setup↓ | setup |
| 3 | 左右滑桌面 | — | [14.0, 17.6) | **3.5s** | 3.0s | setup↓ | setup |
| 4 | 搜索打开Chrome | — | [17.6, 26.0) | **8.4s** | 15.0s | setup↓ | app_launch |
| 5 | 进入Transsion网页 | — | [26.0, 61.3) | **35.3s** | 18.0s | 业务 | unknown |
| 6 | 循环滑动 | 循环滑动 | [61.3, 104.7) | **43.3s** | 43.3s | 业务 | feed_scroll |
| 7 | 循环滑动 | — | [104.7, 148.0) | **43.3s** | 43.3s | 业务 | feed_scroll |
| 8 | 单用例结束机械手回轴 | — | [148.0, 151.4) | **3.4s** | 3.0s | setup↓ | setup |


## 2. 分析侧重点

| 优先级 | 查什么 |
|--------|--------|
| P0 | `chrome` 主进程 vs `sandboxed_process`/`ocessService`（KI-001） |
| P0 | 渲染进程 CPU、GPU/合成 |
| P1 | 后台标签、自动播放媒体 |
| P2 | 扩展/同步（若有） |

## 3. Log / 数据锚点

- CPU：`com.android.chrome`、`sandboxed_process`、`gpu-process`
- main：`Chromium`、`Render`、`Aura`、媒体自动播放相关
- 电流：滚动尖峰 + 页面脚本导致的抬升平台

## 4. 步骤

1. `dou_2` CPU + spike + AI。
2. 列出高 CPU 沙箱并找同时段宿主/标签关联（KI-001）。
3. 对比高低版打开站点是否一致（脚本公平性）。
4. 查是否有后台音视频未停。
5. 结论禁止只报 `ocessService0:0`。

## 5. 结论模板

- **现象**：Chrome 浏览功耗偏高 Δ=
- **主因**：渲染/脚本 / 沙箱伴随宿主 / 媒体自动播放
- **宿主与沙箱关系**：
- **建议**：
