---
name: android-hang-log-analysis
description: "Android-HangDetect: 分析Hang detect场景(关机/重启卡死、system_server/watchdog无响应、运行期阻塞)，定位死锁、IO阻塞、内存压力、硬件超时 | Hang_detect/watchdog/D状态/死锁/IO阻塞/AEE/DEC | 当用户提供Hang日志包、查看watchdog/线程阻塞/系统卡死根因时使用"
funcType: "AI故障分析"
category: "内核"
---

# Hang 问题分析 Skill

来源 SOP: [Hang问题分析SOP](https://transsioner.feishu.cn/docx/F3Coddmfyoc4y9xIEKtc8K6onqe)

## 适用范围

- 问题类型: Android Hang detect / 系统卡死 / 无响应离线日志分析
- 适用场景:
  - 关机或重启阶段卡死（init/debuggerd/watchdog）
  - system_server 或关键服务无响应
  - 运行期线程长期阻塞（锁等待、缺页、I-O、服务链路阻塞）
- 适用芯片平台: MTK（兼容同类平台）

## 前置条件

分析前优先确认以下文件可用:

| 日志文件 | 必需性 | 用途 |
|---|---|---|
| `_分析报告.txt` | 必需 | 工具初判、平台与异常描述 |
| `__exp_main.txt` | 必需 | 进程与调用栈基础信息 |
| `SYS_KERNEL_LOG` | 必需 | 内核错误、等待点、上下文日志 |
| `SYS_HANG_DETECT_RAW` | 必需 | Hang 核心调用栈、D 状态线程 |
| `SYS_TFA_CRASH_REPORT` | 可选 | 交叉排除 ATF 路径 |
| 其他相关日志 | 可选 | 辅助证明（如 blockio、android log） |

## 分析工作流

执行顺序:
1. 先分型: 判断关机/重启卡死、服务无响应、资源枯竭等路径。
2. 看线程: 在 Thread info 与 hang 栈中确定关键线程状态与等待对象。
3. 建链路: 构建 `被阻塞线程 -> 等待资源 -> owner` 因果链。
4. 查等待点: 按锁/内存/文件系统-I-O/Binder 分支判断根因方向。
5. 汇总结论: 输出证据三件套、置信度和行动项。

详细步骤见: [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)

## 关键字速查

详见: [KEYWORDS.md](KEYWORDS.md)

核心检索串:
`hang_detect|watchdog|D state|Uninterruptible|__mutex_lock|ww_mutex_lock|rwsem|futex|do_translation_fault|folio_wait_bit_common|kswapd|ion|slab|blockio|timeout|binder`

## 输出格式

按以下模板输出:

# [Hang问题类型] 日志分析报告

## 问题概述
- 问题现象: [用户描述]
- 场景分型: [关机/重启卡死 | 服务无响应 | 资源枯竭]

## 平台信息
- 项目/机型: [build 指纹提取]
- SoC 平台: [如 MT6895]
- 软件版本: [build 版本]

## 异常时间信息
- 日志时间: [Exception/关键时间]
- 时间线: [异常前操作 -> hang 触发 -> 重启/恢复]

## 关键线程与等待点
- 线程: [name/tid/cpu/state]
- 等待点函数: [符号/调用栈]
- owner/资源关系: [阻塞因果链]

## 关键证据
- [文件名 + 关键日志行]
- [文件名 + 调用栈片段]
- [文件名 + 辅助指标(内存/I-O/中断)]

## 初步结论
- 根因方向: [高/中/低置信度]
- 结论说明: [一句话 + 约束条件]

## 建议行动项
- [研发修复动作]
- [测试复现/补日志动作]
- [跨模块协同动作]

## 参考资源

- [KEYWORDS.md](KEYWORDS.md)
- [COMMON_ISSUES.md](COMMON_ISSUES.md)
- [CASES.md](CASES.md)
