---
name: flow_power_dou_camera_gallery
description: >-
  DOU 相机连拍与图库浏览功耗分析。定位 Camera HAL/ISP、JPEG 编码、图库解码与存储 IO。
  用于 Gallery「拍照 N 张+浏览图片」场景。
scenario_id: scenario-dou-camera-gallery
category: camera
keywords: [Gallery, 拍照, 浏览图片, 相机, 图库]
example_scenes:
  - Gallery拍照5张+浏览图片
related_flow: flow/dou_2
related_base: [base_cpuinfo]
---

# DOU · 拍照 + 图库浏览（camera-gallery）

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

- 场景名含 Gallery/拍照/浏览图片，**或以 YAML 业务步为准**（常见：`给5张照片换滤镜`）。
- **硬规则**：`case_desc` 写「拍照」但 `step_time_datas` 为「换滤镜」时，电流按 **滤镜编辑脉冲** 分析，不要只查 Camera 快门 HAL。
- 差异常在滤镜/后处理、图库解码、存储写放大。

**排除**：纯剪辑导出（CapCut 等）→ `scenario-dou-media-edit`。

## YAML 业务步（实样）

每行 = **一个操作**；用时为该步 `actual_time`（非场景总时长；禁止只写场景总时长）。Setup 标 setup↓，不当主因。

### Gallery拍照5张+浏览图片-DATA（suffix=00545）

| # | 操作 step_name | sub_step | [t0,t1) s | **用时 actual_time** | expect | 角色 | op_kind |
|---|---------------|----------|-----------|---------------------|--------|------|---------|
| 1 | 确保退到桌面 | — | [0.0, 4.5) | **4.5s** | 3.0s | setup↓ | setup |
| 2 | 识别黑屏解锁 | — | [4.5, 18.1) | **13.6s** | 4.0s | setup↓ | setup |
| 3 | 左右滑桌面 | — | [18.1, 21.7) | **3.5s** | 3.0s | setup↓ | setup |
| 4 | 搜索打开AiGallery | — | [21.7, 31.2) | **9.5s** | 10.0s | setup↓ | app_launch |
| 5 | 给5张照片换滤镜 | 循环图片滤镜编辑 | [31.2, 156.3) | **125.2s** | 124.6s | 业务 | media_filter_edit |
| 6 | 给5张照片换滤镜 | — | [156.3, 293.5) | **137.2s** | 136.6s | 业务 | media_filter_edit |
| 7 | 退到桌面 | — | [293.5, 309.5) | **15.9s** | 10.0s | setup↓ | setup |
| 8 | 单用例结束机械手回轴 | — | [309.5, 312.9) | **3.4s** | 3.0s | setup↓ | setup |

case_desc 写「拍照」；YAML **没有**快门连拍步，按滤镜脉冲簇对齐电流。


## 2. 分析侧重点

| 优先级 | 查什么 |
|--------|--------|
| P0 | 用 `read_scene_yaml_ops.py` 取出业务步 `[t0,t1)`，与 `diff_segments` 重叠 |
| P0 | 滤镜步：每次操作是否对应一簇电流脉冲；无操作时段平台是否虚高 |
| P0 | 若确有拍照步：拍照段 vs 浏览段哪段贡献主差异 |
| P1 | `cameraserver` / HAL / 滤镜算法进程 CPU |
| P2 | 存储 IO、缩略图重复生成 |

## 3. Log / 数据锚点

- CPU：`cameraserver`、Gallery/Photos 包名、`media.codec`
- main：`Camera2`、`CaptureResult`、`JPEG`、`provider`、图库 `ImageLoader`
- 电流：快门附近尖峰；浏览段中高平台

## 4. 步骤

1. `dou_2` CPU + spike + AI；按差异分段标出「拍照」与「浏览」。
2. 拍照段：对比 HAL 打开时长、每张 shot 后处理耗时。
3. 浏览段：对比解码进程 CPU 与滑动尖峰。
4. 排除仅因张数/分辨率脚本差异导致的假差异。
5. 结论写清主段（拍/看）+ 进程。

## 5. 结论模板

- **现象**：拍照+浏览功耗偏高 Δ=（主贡献段：拍/看）
- **主因**：Camera HAL/后处理 / 图库解码 / IO
- **证据**：分段时刻 + 进程
- **建议**：核对算法开关、缩略图策略、分辨率
