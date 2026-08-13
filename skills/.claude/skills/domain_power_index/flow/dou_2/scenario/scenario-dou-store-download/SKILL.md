---
name: flow_power_dou_store_download
description: >-
  DOU 应用商店浏览与应用下载功耗分析。定位浏览负载与下载/安装流量。
  用于 Google Play「主界面浏览+应用下载」；下载判定可复用 dou_2/app_download。
scenario_id: scenario-dou-store-download
category: download
keywords: [Google Play, 应用下载, 应用商店, Play商店]
example_scenes:
  - Google Play主界面浏览+应用下载
related_flow: flow/dou_2
related_skills:
  - app_download
related_base: [base_cpuinfo]
---

# DOU · 商店浏览 + 应用下载（store-download）

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

- 场景名含 Play/应用下载，含商店浏览与下载安装。
- 需区分「浏览 UI」与「下载传输」两段贡献。
- 下载判定详见 [`../../app_download/SKILL.md`](../../app_download/SKILL.md)。

**排除**：非商店的纯网页下载 → `scenario-dou-web-browse`。

## YAML 业务步（实样）

每行 = **一个操作**；用时为该步 `actual_time`（非场景总时长；禁止只写场景总时长）。Setup 标 setup↓，不当主因。

### Google Play主界面浏览 + 应用下载-WIFI（suffix=00646）

| # | 操作 step_name | sub_step | [t0,t1) s | **用时 actual_time** | expect | 角色 | op_kind |
|---|---------------|----------|-----------|---------------------|--------|------|---------|
| 1 | 确保退到桌面 | — | [0.0, 5.0) | **5.0s** | 3.0s | setup↓ | setup |
| 2 | 识别黑屏解锁 | — | [5.0, 12.2) | **7.2s** | 4.0s | setup↓ | setup |
| 3 | 左右滑桌面 | — | [12.2, 16.1) | **3.9s** | 3.0s | setup↓ | setup |
| 4 | 搜索打开GooglePlay | — | [16.1, 32.4) | **16.3s** | 15.0s | setup↓ | app_launch |
| 5 | 上下滑动 | 上下滑动 | [32.4, 51.4) | **19.0s** | 18.8s | 业务 | feed_scroll |
| 6 | 上下滑动 | — | [51.4, 71.5) | **20.1s** | 20.0s | 业务 | feed_scroll |
| 7 | 搜索ab_journey | — | [71.5, 87.5) | **16.0s** | 10.0s | 业务 | unknown |
| 8 | 下载ab_journey | — | [87.5, 120.9) | **33.3s** | 32.6s | 业务 | store_download |
| 9 | 退到桌面且卸載软件 | — | [120.9, 152.9) | **32.0s** | 15.0s | 业务 | unknown |
| 10 | 单用例结束机械手回轴 | — | [152.9, 156.5) | **3.7s** | 3.0s | setup↓ | setup |

必须拆：浏览滑动 vs 下载段；下载段再对 pp_download 日志。


## 2. 分析侧重点

| 优先级 | 查什么 |
|--------|--------|
| P0 | 下载时段是否与电流抬升对齐（复用 `run_app_download.py`） |
| P0 | Play 主进程 / `vending` / download 相关进程 CPU |
| P1 | 安装阶段 `installd` / PackageManager |
| P1 | 浏览段推荐页预加载是否异常 |
| P2 | 多任务并行下载 |

## 3. Log / 数据锚点

- 产物：`app_download_result.json` / `.txt`（`dou_2` §10）
- main：`state:DOWNLOADING`、包名、uid/pid
- sys：`Usf_Hiber/importantScene`（灭屏 speed 规则见 app_download skill）
- CPU：`com.android.vending` 等

## 4. 步骤

1. `dou_2` CPU + spike + AI。
2. 全流程末跑 `run_app_download.py`，读取 narrative。
3. 分段：浏览 vs DOWNLOADING vs 安装完成。
4. 若下载证据弱但电流高 → 回到浏览/预加载侧。
5. 结论写清下载包名与时段。

## 5. 结论模板

- **现象**：Play 浏览+下载功耗偏高 Δ=
- **主因**：浏览预加载 / 下载传输 / 安装
- **下载证据**：包名、uid、时段（来自 app_download）
- **建议**：
