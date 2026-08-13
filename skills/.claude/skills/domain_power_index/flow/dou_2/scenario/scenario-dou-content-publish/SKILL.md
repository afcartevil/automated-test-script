---
name: flow_power_dou_content_publish
description: >-
  DOU 社交发布视频/动态功耗分析。定位本地转码、上传与发布页预览负载。
  用于 Instagram「发布视频动态」等场景。
scenario_id: scenario-dou-content-publish
category: publish
keywords: [发布视频, 发布动态, 发帖, Instagram发布]
example_scenes:
  - Instagram发布视频动态
related_flow: flow/dou_2
related_base: [base_cpuinfo]
---

# DOU · 发布视频/动态（content-publish）

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

- 场景名含「发布视频 / 发布动态」，含编辑预览→转码→上传。
- 与纯浏览不同：编码与上行是主因候选。

**排除**：仅主界面浏览 → `scenario-dou-feed-scroll`；本地重度剪辑 → `scenario-dou-media-edit`。

## YAML 业务步（实样）

每行 = **一个操作**；用时为该步 `actual_time`（非场景总时长；禁止只写场景总时长）。Setup 标 setup↓，不当主因。

### Instagram发布视频动态-DATA（suffix=00589）

| # | 操作 step_name | sub_step | [t0,t1) s | **用时 actual_time** | expect | 角色 | op_kind |
|---|---------------|----------|-----------|---------------------|--------|------|---------|
| 1 | 确保退到桌面 | — | [0.0, 5.9) | **5.9s** | 3.0s | setup↓ | setup |
| 2 | 识别黑屏解锁 | — | [5.9, 18.6) | **12.8s** | 4.0s | setup↓ | setup |
| 3 | 左右滑桌面 | — | [18.6, 22.1) | **3.5s** | 3.0s | setup↓ | setup |
| 4 | 搜索打开Instagram | — | [22.1, 30.9) | **8.8s** | 15.0s | setup↓ | app_launch |
| 5 | 点击左上角的相机录制 | — | [30.9, 41.4) | **10.4s** | 5.0s | 业务 | content_record |
| 6 | 长按录制 | — | [41.4, 72.5) | **31.2s** | 30.0s | 业务 | content_record |
| 7 | 回放界面持续播放 | — | [72.5, 84.9) | **12.4s** | 12.4s | 业务 | unknown |
| 8 | Share发布视频 | — | [84.9, 102.9) | **18.0s** | 18.0s | 业务 | content_upload |
| 9 | 退到桌面 | — | [102.9, 110.7) | **7.8s** | 5.0s | setup↓ | setup |
| 10 | 单用例结束机械手回轴 | — | [110.7, 114.1) | **3.4s** | 3.0s | setup↓ | setup |

按 YAML 拆：录制抬升 → 回放 → Share 上传台阶。


## 2. 分析侧重点

| 优先级 | 查什么 |
|--------|--------|
| P0 | 转码/导出时段 `MediaCodec` encoder CPU/电流 |
| P0 | 上传时段网络与主进程是否持续高负载 |
| P1 | 发布页循环预览是否未暂停 |
| P2 | 草稿压缩、多清晰度重复编码 |

## 3. Log / 数据锚点

- CPU：Instagram 宿主、`media.codec`、上传相关进程
- main：`MediaCodec`（encode）、`Upload`、`RESUMABLE`、发布 Activity
- 电流：编码段高平台；上传段中高+尖峰

## 4. 步骤

1. `dou_2` CPU + spike + AI；分段「预览 / 编码 / 上传」。
2. 确认 encoder start/stop 是否成对、是否重复开编。
3. 对比高低版上传时长与主进程 CPU。
4. 结论标明主段；勿与 Feed 浏览混写。

## 5. 结论模板

- **现象**：发布动态功耗偏高 Δ=（主段：预览/编码/上传）
- **主因**：
- **证据**：
- **建议**：编码参数、预览暂停、上传并发
