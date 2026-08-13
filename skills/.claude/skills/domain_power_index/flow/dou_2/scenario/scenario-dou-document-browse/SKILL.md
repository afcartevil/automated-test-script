---
name: flow_power_dou_document_browse
description: >-
  DOU 云文档浏览功耗分析。定位文档渲染、云同步与 WebView/沙箱负载。
  用于 Google Drive「文档浏览」等场景。
scenario_id: scenario-dou-document-browse
category: document
keywords: [文档浏览, Google Drive, Drive, Docs]
example_scenes:
  - Google Drive文档浏览
related_flow: flow/dou_2
related_base: [base_cpuinfo]
known_issues: [KI-001]
---

# DOU · 云文档浏览（document-browse）

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

- 场景名含 Drive/文档浏览，以打开与翻阅云文档为主。
- 常见 WebView/Docs 渲染、同步拉取。

**排除**：通用 Chrome 网页 → `scenario-dou-web-browse`（Drive 内嵌仍优先本 skill）。

## YAML 业务步（实样）

每行 = **一个操作**；用时为该步 `actual_time`（非场景总时长；禁止只写场景总时长）。Setup 标 setup↓，不当主因。

### Google Drive文档浏览-DATA（suffix=00598）

| # | 操作 step_name | sub_step | [t0,t1) s | **用时 actual_time** | expect | 角色 | op_kind |
|---|---------------|----------|-----------|---------------------|--------|------|---------|
| 1 | 确保退到桌面 | — | [0.0, 4.4) | **4.4s** | 3.0s | setup↓ | setup |
| 2 | 识别黑屏解锁 | — | [4.4, 13.4) | **9.0s** | 4.0s | setup↓ | setup |
| 3 | 左右滑桌面 | — | [13.4, 16.9) | **3.5s** | 3.0s | setup↓ | setup |
| 4 | 搜索打开GoogleDrive | — | [16.9, 27.0) | **10.1s** | 15.0s | setup↓ | app_launch |
| 5 | 主界面打开文件 | — | [27.0, 33.6) | **6.6s** | 5.0s | 业务 | unknown |
| 6 | 滑动查看文档 | 滑动查看文档 | [33.6, 166.2) | **132.6s** | 131.7s | 业务 | document_browse |
| 7 | 滑动查看文档 | — | [166.2, 298.8) | **132.6s** | 131.7s | 业务 | document_browse |
| 8 | 回到桌面 | — | [298.8, 303.2) | **4.4s** | 5.0s | setup↓ | setup |
| 9 | 单用例结束机械手回轴 | — | [303.2, 306.6) | **3.4s** | 3.0s | setup↓ | setup |


## 2. 分析侧重点

| 优先级 | 查什么 |
|--------|--------|
| P0 | Drive/Docs 主进程与沙箱（KI-001） |
| P0 | 翻页/滚动时渲染 CPU |
| P1 | 云同步、缩略图/预览预取 |
| P2 | 自动播放预览、多文档预加载 |

## 3. Log / 数据锚点

- CPU：`com.google.android.apps.docs` 等、沙箱进程
- main：`WebView`、`Docs`、`SyncAdapter`、`Drive`
- 电流：打开文档尖峰 + 滚动平台

## 4. 步骤

1. `dou_2` CPU + spike + AI。
2. 区分打开瞬间 vs 持续翻阅。
3. 沙箱高占用时锚定宿主（KI-001）。
4. 查同步是否在浏览期密集触发。
5. 结论写清渲染 vs 同步。

## 5. 结论模板

- **现象**：文档浏览功耗偏高 Δ=
- **主因**：渲染/WebView / 同步预取 / 沙箱伴随
- **证据**：
- **建议**：
