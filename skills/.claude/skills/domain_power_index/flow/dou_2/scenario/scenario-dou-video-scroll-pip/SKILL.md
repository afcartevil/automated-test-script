---
name: flow_power_dou_video_pip
description: >-
  DOU 视频信息流滑动叠加长视频小窗功耗分析。定位解码、Surface、PIP、音频通路。
  用于 Youtube「滑动浏览+长视频小窗」等场景。
scenario_id: scenario-dou-video-scroll-pip
category: video
keywords: [滑动浏览, 长视频, 小窗, PIP, Youtube, 短视频划动]
example_scenes:
  - Youtube滑动浏览+长视频小窗
related_flow: flow/dou_2
related_base: [base_cpuinfo]
known_issues: [KI-002]
---

# DOU · 视频滑动 + 小窗（video-scroll-pip）

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

- 场景同时含「视频滑动/短视频划动」与「长视频小窗/PIP」。
- 关注 media codec、双路画面、音频会话是否异常常开。

**排除**：纯 Feed 图文滑动 → `scenario-dou-feed-scroll`；本地剪辑 → `scenario-dou-media-edit`。

## YAML 业务步（实样）

每行 = **一个操作**；用时为该步 `actual_time`（非场景总时长；禁止只写场景总时长）。Setup 标 setup↓，不当主因。

### Youtube滑动浏览+长视频小窗-DATA（suffix=00572）

| # | 操作 step_name | sub_step | [t0,t1) s | **用时 actual_time** | expect | 角色 | op_kind |
|---|---------------|----------|-----------|---------------------|--------|------|---------|
| 1 | 确保退到桌面 | — | [0.0, 4.5) | **4.5s** | 3.0s | setup↓ | setup |
| 2 | 识别黑屏解锁 | — | [4.5, 17.0) | **12.6s** | 4.0s | setup↓ | setup |
| 3 | 左右滑桌面 | — | [17.0, 20.5) | **3.5s** | 3.0s | setup↓ | setup |
| 4 | 搜索打开Youtube | — | [20.5, 31.7) | **11.2s** | 15.0s | setup↓ | app_launch |
| 5 | 主界面浏览 | 主界面浏览 | [31.7, 119.9) | **88.1s** | 86.2s | 业务 | unknown |
| 6 | 主界面浏览 | — | [119.9, 241.8) | **122.0s** | 120.0s | 业务 | unknown |
| 7 | 进入视频资源 | — | [241.8, 298.5) | **56.7s** | 32.0s | 业务 | unknown |
| 8 | 长视频小窗浏览 | 长视频小窗浏览 | [298.5, 486.3) | **187.8s** | 187.8s | 业务 | video_pip |
| 9 | 长视频小窗浏览 | — | [486.3, 676.4) | **190.0s** | 191.0s | 业务 | video_pip |
| 10 | 退到桌面 | — | [676.4, 683.1) | **6.7s** | 11.0s | setup↓ | setup |
| 11 | 单用例结束机械手回轴 | — | [683.1, 686.4) | **3.4s** | 3.0s | setup↓ | setup |

必须按 YAML **拆开写**：滑动段 vs 小窗段，勿混成一段。


## 2. 分析侧重点

| 优先级 | 查什么 |
|--------|--------|
| P0 | 解码器实例数（是否主窗+小窗双路同时硬解） |
| P0 | 播放器/App 主进程 CPU、mediaserver/`media.swcodec` |
| P1 | PIP Surface / 叠加层合成（HWC/GPU） |
| P1 | 音频 track 是否在划走后仍播放 |
| P2 | 划动误触导致无关进程崩溃重启（KI-002） |

## 3. Log / 数据锚点

- CPU：`youtube`/`vending` 宿主、`mediaserver`、`media.codec`、`audioserver`
- main/sys：`MediaCodec`、`PIP`、`PictureInPicture`、`AudioTrack`、`NuPlayer`/`ExoPlayer`
- 电流：平台整体抬高（解码）+ 划动尖峰；小窗段底电不应接近纯 Feed

## 4. 步骤

1. `dou_2` CPU + spike + AI。
2. 确认高功耗时段是否与「划动」或「小窗长播」对齐。
3. 查 codec start/stop 是否成对；小窗期间是否多开一路。
4. 查音频是否在划走 Feed 后仍活跃。
5. 结论区分：解码负载 vs 合成/PIP vs 音频未释放。

## 5. 结论模板

- **现象**：视频+小窗功耗偏高 Δ=
- **主因**：双路解码 / PIP 合成 / 音频未停 / 划动侧负载
- **证据**：codec 日志时刻 + CPU 进程 + 电流分段
- **建议**：核对小窗策略、codec 复用、划动预加载
