---
name: flow_power_dou_feed_scroll
description: >-
  DOU 主界面/Feed/购物页滑动浏览功耗分析。定位列表滑动、图片解码、预取、
  WebView/沙箱高 CPU。用于 Instagram/Facebook/Meesho/Shopee/foodpanda/Pinterest 等。
scenario_id: scenario-dou-feed-scroll
category: feed
keywords: [主界面浏览, 浏览滑动, 购物浏览, 壁纸浏览, Instagram, Facebook, Meesho, Shopee, Flipkart, foodpanda, Pinterest]
example_scenes:
  - Instagram主界面浏览
  - foodpanda主界面浏览
  - Meesho主界面浏览
  - Pinterest主页壁纸浏览
  - Facebook主界面,浏览滑动
  - Facebook lite主界面,浏览滑动
  - Shopee 2.2MenSale购物浏览
  - Flipkart购物浏览
related_flow: flow/dou_2
related_base: [base_cpuinfo]
known_issues: [KI-001, KI-002]
---

# DOU · Feed/主界面滑动浏览（feed-scroll）

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

- 场景名含「主界面浏览 / 浏览滑动 / 购物浏览 / 壁纸浏览」等，以手指滑动信息流为主。
- 差异常见于图片解码、预加载、广告 SDK、WebView/沙箱。

**排除**：视频小窗 → `scenario-dou-video-scroll-pip`；发布动态 → `scenario-dou-content-publish`。

## YAML 业务步（实样）

每行 = **一个操作**；用时为该步 `actual_time`（非场景总时长；禁止只写场景总时长）。Setup 标 setup↓，不当主因。

### Instagram主界面浏览-DATA（suffix=00551）

| # | 操作 step_name | sub_step | [t0,t1) s | **用时 actual_time** | expect | 角色 | op_kind |
|---|---------------|----------|-----------|---------------------|--------|------|---------|
| 1 | 确保退到桌面 | — | [0.0, 4.4) | **4.4s** | 3.0s | setup↓ | setup |
| 2 | 识别黑屏解锁 | — | [4.4, 11.2) | **6.8s** | 4.0s | setup↓ | setup |
| 3 | 左右滑桌面 | — | [11.2, 14.7) | **3.5s** | 3.0s | setup↓ | setup |
| 4 | 搜索打开Instagram | — | [14.7, 23.5) | **8.7s** | 15.0s | setup↓ | app_launch |
| 5 | 主界面观看95秒 | 每3秒循环滑动 | [23.5, 92.8) | **69.4s** | 69.3s | 业务 | feed_scroll |
| 6 | 主界面观看95秒 | — | [92.8, 174.4) | **81.6s** | 81.5s | 业务 | feed_scroll |
| 7 | 退到桌面 | — | [174.4, 179.1) | **4.7s** | 5.0s | setup↓ | setup |
| 8 | 单用例结束机械手回轴 | — | [179.1, 182.5) | **3.4s** | 3.0s | setup↓ | setup |

### Meesho主界面浏览-DATA（suffix=00585）

| # | 操作 step_name | sub_step | [t0,t1) s | **用时 actual_time** | expect | 角色 | op_kind |
|---|---------------|----------|-----------|---------------------|--------|------|---------|
| 1 | 确保退到桌面 | — | [0.0, 4.6) | **4.6s** | 3.0s | setup↓ | setup |
| 2 | 识别黑屏解锁 | — | [4.6, 12.1) | **7.5s** | 4.0s | setup↓ | setup |
| 3 | 左右滑桌面 | — | [12.1, 15.5) | **3.5s** | 3.0s | setup↓ | setup |
| 4 | 搜索打开Meesho | — | [15.5, 26.2) | **10.6s** | 15.0s | setup↓ | app_launch |
| 5 | 滑动浏览 | 滑动浏览 | [26.2, 165.1) | **138.9s** | 138.8s | 业务 | video_or_feed_scroll |
| 6 | 滑动浏览 | — | [165.1, 305.8) | **140.8s** | 140.7s | 业务 | video_or_feed_scroll |
| 7 | 回到桌面 | — | [305.8, 308.6) | **2.8s** | 5.0s | setup↓ | setup |
| 8 | 单用例结束机械手回轴 | — | [308.6, 312.0) | **3.4s** | 3.0s | setup↓ | setup |

### Pinterest主页壁纸浏览-DATA（suffix=00594）

| # | 操作 step_name | sub_step | [t0,t1) s | **用时 actual_time** | expect | 角色 | op_kind |
|---|---------------|----------|-----------|---------------------|--------|------|---------|
| 1 | 确保退到桌面 | — | [0.0, 4.3) | **4.3s** | 3.0s | setup↓ | setup |
| 2 | 识别黑屏解锁 | — | [4.3, 17.2) | **12.9s** | 4.0s | setup↓ | setup |
| 3 | 左右滑桌面 | — | [17.2, 20.9) | **3.7s** | 3.0s | setup↓ | setup |
| 4 | 搜索打开Pinterest | — | [20.9, 35.6) | **14.7s** | 15.0s | setup↓ | app_launch |
| 5 | 滑动浏览 | 滑动浏览 | [35.6, 165.8) | **130.2s** | 130.1s | 业务 | video_or_feed_scroll |
| 6 | 滑动浏览 | — | [165.8, 300.7) | **135.0s** | 135.0s | 业务 | video_or_feed_scroll |
| 7 | 回到桌面 | — | [300.7, 303.5) | **2.8s** | 5.0s | setup↓ | setup |
| 8 | 单用例结束机械手回轴 | — | [303.5, 306.9) | **3.4s** | 3.0s | setup↓ | setup |

### Facebook主界面，浏览滑动-WIFI（suffix=00616）

| # | 操作 step_name | sub_step | [t0,t1) s | **用时 actual_time** | expect | 角色 | op_kind |
|---|---------------|----------|-----------|---------------------|--------|------|---------|
| 1 | 确保退到桌面 | — | [0.0, 4.4) | **4.4s** | 3.0s | setup↓ | setup |
| 2 | 识别黑屏解锁 | — | [4.4, 11.2) | **6.8s** | 4.0s | setup↓ | setup |
| 3 | 左右滑桌面 | — | [11.2, 14.6) | **3.4s** | 3.0s | setup↓ | setup |
| 4 | 搜索打开Facebook | — | [14.6, 27.2) | **12.6s** | 15.0s | setup↓ | app_launch |
| 5 | 短距离滑动150s | 循环短距离滑动 | [27.2, 139.7) | **112.4s** | 112.3s | 业务 | feed_scroll |
| 6 | 短距离滑动150s | — | [139.7, 275.1) | **135.4s** | 135.3s | 业务 | feed_scroll |
| 7 | 退到桌面 | — | [275.1, 286.2) | **11.1s** | 5.0s | setup↓ | setup |
| 8 | 单用例结束机械手回轴 | — | [286.2, 289.7) | **3.4s** | 3.0s | setup↓ | setup |

### Shopee 2.2 Men Sale购物浏览（或者巴基斯坦地区的Flipkart）-WIFI（suffix=00662）

| # | 操作 step_name | sub_step | [t0,t1) s | **用时 actual_time** | expect | 角色 | op_kind |
|---|---------------|----------|-----------|---------------------|--------|------|---------|
| 1 | 确保退到桌面 | — | [0.0, 4.5) | **4.5s** | 3.0s | setup↓ | setup |
| 2 | 识别黑屏解锁 | — | [4.5, 13.2) | **8.8s** | 4.0s | setup↓ | setup |
| 3 | 左右滑桌面 | — | [13.2, 16.8) | **3.5s** | 3.0s | setup↓ | setup |
| 4 | 搜索打开ShopApp | — | [16.8, 29.7) | **13.0s** | 15.0s | setup↓ | app_launch |
| 5 | 滑动浏览 | 滑动浏览 | [29.7, 160.2) | **130.5s** | 130.5s | 业务 | video_or_feed_scroll |
| 6 | 滑动浏览 | — | [160.2, 298.5) | **138.2s** | 138.2s | 业务 | video_or_feed_scroll |
| 7 | 回到桌面 | — | [298.5, 306.5) | **8.0s** | 6.0s | setup↓ | setup |
| 8 | 单用例结束机械手回轴 | — | [306.5, 309.9) | **3.4s** | 3.0s | setup↓ | setup |

注意：个别 case_desc 写「主界面浏览」但 YAML 实为待机（如 foodpanda 主页待机180s）→ 改走 pp-idle-home，以 YAML 为准。


## 2. 分析侧重点

| 优先级 | 查什么 |
|--------|--------|
| P0 | YAML 滑动步（如「每3秒循环滑动」）与 `diff_segments`/spike **周期是否对齐** |
| P0 | 主进程 vs 沙箱（`ocessService`/`SandboxedProcess`，KI-001）成对出现 |
| P0 | 图片库/解码相关进程或线程 CPU 是否偏高 |
| P1 | 预取/广告/推荐 SDK 额外进程 |
| P1 | 停滑后电流平台是否回落（不掉则泄漏/预取） |
| P2 | `messenger.sms` 崩溃重启（KI-002，视频划动误触类） |

## 3. Log / 数据锚点

- CPU：宿主包名 + `sandboxed_process` / `ocessService`
- 电流：滑动段连续中高平台 + 密集尖峰
- main：`Choreographer`、`HWUI`、`ImageDecoder`、`Glide`/`Coil`（若有）、WebView
- 包名随场景：`instagram`、`facebook`、`meesho`、`shopee`、`foodpanda`、`pinterest` 等

## 4. 步骤

1. `dou_2` 产出 CPU + spike + AI。
2. 在 `top_diff_processes` 中区分宿主与沙箱，沙箱高 CPU 时锚定宿主（KI-001）。
3. 对照电流差异分段：滑动段 vs 停顿段。
4. 查是否新增广告/预加载进程（仅 high 侧出现）。
5. 结论避免只报沙箱名；写清宿主包 + 行为（解码/预取/广告）。

## 5. 结论模板

- **现象**：Feed 滑动 mAh/电流偏高 Δ=
- **主因**：宿主进程 / 沙箱伴随 / 预取或广告
- **证据**：CPU Top + 电流分段时刻
- **建议**：限制预加载、核对广告 SDK、对照 KI
