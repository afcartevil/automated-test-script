---
name: android-hwr-hwt-log-analysis
description: "Android-HWR/HWT: 分析HWR(HW reboot)与HWT升级复位，通过WDT喂狗链路、CPU栈、总线超时定位根因 | HWR/HWT/wdt/timeout/lastpc/systracker/硬复位 | 当用户提供HWR/HWT日志包、hw_reboot/wdt_timeout分析时使用"
funcType: "AI故障分析"
category: "内核"
---

# HWR/HWT 问题分析 Skill

来源 SOP: [HWR问题分析SOP](https://transsioner.feishu.cn/docx/EQqzdm3UCoI1bfxBXQKcOpOenUh)

## 适用范围

- 问题类型: Android HWR/HWT 重启离线日志分析
- 适用场景:
  - WDT Stage1 超时后升级到 HW reboot
  - 运行期 CPU 卡死导致硬复位
  - 总线访问超时、存储超时、硬件不稳定引发复位
- 适用芯片平台: MTK（兼容同类平台）

## 前置条件

分析前优先确认以下文件可用:

| 日志文件 | 必需性 | 用途 |
|---|---|---|
| `_分析报告.txt` | 必需 | 异常摘要、平台信息、初判方向 |
| `__exp_main.txt` | 必需 | 异常分类、时间与基础信息 |
| `SYS_REBOOT_REASON` | 必需 | 识别 HWT/HWR 与关键寄存器 |
| `SYS_KERNEL_LOG` | 必需 | WDT 喂狗日志、timeout/error、调用栈 |
| `SYS_LAST_CPU_BUS` | 高优先级 | lastpc/systracker/总线超时线索 |
| `SYS_ATF_LAST` / `SYS_TFA_CRASH_REPORT` | 可选 | ATF 侧最后 PC 与上下文 |
| `SYS_LAST_KMSG` / `sys_pstore_raw` | 可选 | 重启前最后日志片段 |
| `vmlinux` / `ko` | 高优先级 | 地址解析与代码定位 |

## 分析工作流

执行顺序:
1. 归类异常: 确认 HWT 还是 HWR，是否处于升级复位路径。
2. 查喂狗链路: 核对各 CPU 喂狗状态，定位缺失 CPU/卡点 CPU。
3. 查总线与硬件线索: 解析 lastpc/systracker、timeout/error。
4. 栈与符号映射: 对关键 PC/栈做 addr2line 或 gdb 映射。
5. 根因收敛: 区分软件阻塞、总线访问问题、硬件不稳定。
6. Jira 输出: 提交证据链、结论置信度与行动项。

详细步骤见: [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)

## 关键字速查

详见: [KEYWORDS.md](KEYWORDS.md)

核心检索串:
`HWT|HW reboot|wdt|wdtk|kick|timeout|failed|error|lastpc|systracker|bus timeout|oops_in_progress|addr2line`

## 输出格式

按以下模板输出:

# [HWR/HWT问题] 日志分析报告

## 问题概述
- 问题现象: [用户描述]
- 异常分类: [HWT | HWR | HWT->HWR 升级]

## 平台信息
- 项目/机型: [build 指纹提取]
- SoC 平台: [如 MT6895]
- 软件版本: [build 版本]

## 异常时间信息
- 日志时间: [关键时间]
- 时间线: [异常前操作 -> WDT超时 -> 复位]

## 关键证据
- 喂狗链路: [哪个 CPU 未喂狗/最后一次喂狗时间]
- 总线线索: [lastpc/systracker/timeout]
- 调用栈与映射: [关键 PC -> 函数]

## 初步结论
- 根因方向: [软件阻塞 | 总线/存储超时 | 硬件异常]
- 置信度: [高/中/低]
- 结论说明: [一句话 + 限制条件]

## 建议行动项
- [模块 owner 排查动作]
- [补日志/复现动作]
- [是否升级硬件或 MTK 协同]

## 参考资源

- [KEYWORDS.md](KEYWORDS.md)
- [COMMON_ISSUES.md](COMMON_ISSUES.md)
- [CASES.md](CASES.md)
