---
name: android-video-playback-log-analysis
description: "Android-视频播放: 分析视频播放异常(黑屏/花屏/起播失败/卡住)，覆盖MediaCodec/VPUD/C2MtkVdec解码链路 | MediaCodec/VPUD/C2MtkVdec/decoder/codec/视频播放/黑屏/花屏/起播失败 | 当用户报告Android设备视频播放黑屏、花屏、起播失败、解码失败时使用。第三方视频播放卡走bug-scenario-video-stuck-audio"
funcType: "AI故障分析"
category: "驱动"
---

# Android Video Playback Log Analysis

## 适用范围

- 问题类型：
  - 无法播放（黑屏）
  - 播放视频花屏
  - 起播失败
  - 播放一段时间后卡住或黑屏
- 适用芯片平台：通用
- 有效性确认：优先用友商同 app 验证，排除 app 自身原因

## 前置条件

### 必需日志

- `mobilelog`
  - 关键分析日志主要位于 `mainlog`

### 可选补充

- 拍屏或问题复现时间点信息
  - 用于快速定位异常发生区间

## 分析工作流

1. 先结合拍屏或复现现象，定位问题大致时间点。
2. 在 `mainlog` 中搜索 `Number of i`，判断是起播阶段还是播放中异常阶段。
3. 围绕解码器实例增加或减少附近日志，检查 `MediaCodec`、`C2MtkVdec`、`VPUD` 关键流程。
4. 搜索异常 `E` 级日志，优先判断是否存在平台、框架、片源超 spec 或应用侧问题。
5. 结合常见问题对照表完成归因。
6. 如需详细关键词、步骤与案例，分别参考：
   - [KEYWORDS.md](KEYWORDS.md)
   - [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)
   - [COMMON_ISSUES.md](COMMON_ISSUES.md)
   - [CASES.md](CASES.md)

## 输出格式

按以下模板输出分析结论：

# 视频播放异常日志分析报告

## 基本信息
- 分析时间：[时间]
- 日志来源：[文件列表]
- 问题描述：[用户提供的问题描述]
- 适用范围校验：[是否属于播放黑屏/花屏/起播失败/播放中卡住]

## 分析过程
### 步骤1：定位问题时间点
- 搜索关键字：`Number of i`
- 搜索结果：[找到/未找到，日志摘要]
- 判断结论：[起播即异常/播放过程中异常/时间点不明确]

### 步骤2：检查解码器生命周期
- 搜索关键字：`MediaCodec` `C2MtkVdec` `vpud`
- 搜索结果：[解码器创建/配置/启动/格式变化/销毁情况]
- 判断结论：[创建成功/配置失败/启动失败/播放后异常退出]

### 步骤3：检查异常错误日志
- 搜索关键字：`returned error: 0xe` `Codec reported err` `VPUD` `C2MtkVdec`
- 搜索结果：[关键异常日志]
- 判断结论：[片源超spec/解码器数量达到max/平台问题/应用问题/无明显异常]
 
## 分析结论
- 问题根因：[根因描述]
- 证据摘要：[支持结论的关键日志行]
- 责任域判断：[平台/框架/app/片源]
- 建议措施：[后续处理建议]

## 参考资源

- 关键词与日志示例：[`KEYWORDS.md`](KEYWORDS.md)
- 详细分析步骤：[`ANALYSIS_STEPS.md`](ANALYSIS_STEPS.md)
- 常见问题对照：[`COMMON_ISSUES.md`](COMMON_ISSUES.md)
- 典型案例：[`CASES.md`](CASES.md)
