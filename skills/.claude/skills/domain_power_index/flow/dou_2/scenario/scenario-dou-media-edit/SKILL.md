---
name: flow_power_dou_media_edit
description: >-
  DOU 本地图片/视频剪辑功耗分析。定位预览、特效、编解码与导出负载。
  用于 CapCut「图片视频剪辑」等场景。
scenario_id: scenario-dou-media-edit
category: edit
keywords: [剪辑, CapCut, 视频编辑, 图片编辑, 导出]
example_scenes:
  - CapCut图片视频剪辑
related_flow: flow/dou_2
related_base: [base_cpuinfo]
---

# DOU · 图片视频剪辑（media-edit）

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

- 场景名含剪辑/CapCut/视频编辑，本地时间线预览与特效为主。
- 负载通常远高于 Feed 浏览：GPU、多路解码、实时特效。

**排除**：社交一键发布（轻量转码）→ `scenario-dou-content-publish`。

## YAML 业务步（实样）

每行 = **一个操作**；用时为该步 `actual_time`（非场景总时长；禁止只写场景总时长）。Setup 标 setup↓，不当主因。

### CapCut图片视频剪辑-WIFI（suffix=00673）

| # | 操作 step_name | sub_step | [t0,t1) s | **用时 actual_time** | expect | 角色 | op_kind |
|---|---------------|----------|-----------|---------------------|--------|------|---------|
| 1 | 确保退到桌面 | — | [0.0, 4.9) | **4.9s** | 3.0s | setup↓ | setup |
| 2 | 识别黑屏解锁 | — | [4.9, 17.6) | **12.7s** | 4.0s | setup↓ | setup |
| 3 | 左右滑桌面 | — | [17.6, 21.1) | **3.5s** | 3.0s | setup↓ | setup |
| 4 | 搜索打开CapCut | — | [21.1, 30.5) | **9.4s** | 15.0s | setup↓ | app_launch |
| 5 | 主界面待机150s | — | [30.5, 160.7) | **130.1s** | 130.1s | 业务 | app_idle |
| 6 | 回到桌面 | — | [160.7, 167.3) | **6.7s** | 7.0s | setup↓ | setup |
| 7 | 单用例结束机械手回轴 | — | [167.3, 170.7) | **3.4s** | 3.0s | setup↓ | setup |

硬规则：case_desc 写剪辑，但本样例 YAML 只有待机 → 按待机平台分析；若当次 YAML 出现剪辑/导出步，再按 media_edit 高平台深挖。


## 2. 分析侧重点

| 优先级 | 查什么 |
|--------|--------|
| P0 | 预览播放时多路 decode + GPU 合成 |
| P0 | 特效/AI 美颜相关进程或库 CPU |
| P1 | 导出/编码段是否被计入场景（脚本是否含导出） |
| P1 | 素材分辨率/帧率两边是否一致 |
| P2 | 后台自动保存、云草稿同步 |

## 3. Log / 数据锚点

- CPU：CapCut 包名、`media.codec`、`surfaceflinger` 相关高占用线程
- main：`MediaCodec`、`OpenGL`/`Vulkan`、导出/`export`、特效模块名
- 电流：预览持续高平台；导出段更高

## 4. 步骤

1. `dou_2` CPU + spike + AI；确认场景是否含导出。
2. 分段预览 vs 导出。
3. 对比特效开关与素材规格（防脚本不公平）。
4. 查 codec 实例数与 GPU 相关线程。
5. 结论写清预览特效 vs 导出编码。

## 5. 结论模板

- **现象**：剪辑功耗偏高 Δ=（主段：预览/导出）
- **主因**：多路解码 / GPU 特效 / 导出编码
- **证据**：
- **建议**：特效降级、预览分辨率、导出参数
