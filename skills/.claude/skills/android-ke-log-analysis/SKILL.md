---
name: android-ke-log-analysis
description: "Android-KernelException: 分析KE及其衍生重启(ATF_CRASH/HWT/HWR/Hang_detect/OCP)，完成异常分型、证据提取、符号映射 | KE/ATF_CRASH/HWT/HWR/Hang_detect/OCP/DB/DEC/重启根因 | 当用户提供KE日志包、DB/DEC、需内核异常重启根因分析时使用"
---

# KE (Kernel Exception) 问题分析 Skill

来源 SOP: [KE (Kernel Exception) 问题分析SOP](https://transsioner.feishu.cn/docx/R235djWM1oBKz7xueVmcrFNJnud)

## 适用范围

- 问题类型: Android KE/重启/异常崩溃离线日志分析
- 适用场景:
  - Kernel panic / Oops / BUG
  - ATF crash（exception/assert/panic）
  - Hang detect、HWT/HWR、OCP reboot
  - 需要输出标准 Jira 报告
- 适用芯片平台: MTK（兼容同类平台）

## 所需文档与优先级

先检查以下文件:

| 日志文件 | 必需性 | 用途 |
|---|---|---|
| `__exp_main.txt` | 必需 | 异常类型、时间、build 指纹 |
| `_分析报告.txt` | 必需 | 初判结论、建议排查方向 |
| `out.json` | 必需 | 结构化 `Exception Class/Type` |
| `SYS_KERNEL_LOG` | 必需 | backtrace、panic/oops/hang 关键日志 |
| `SYS_LAST_KMSG` / `sys_pstore_raw` | 高优先级 | 重启前最后时刻证据 |
| `SYS_REBOOT_REASON` | 高优先级 | 重启上下文、硬件记录 |
| `SYS_VERSION_INFO` | 高优先级 | 符号匹配校验 |
| `SYS_TFA_CRASH_REPORT` | 场景化 | ATF crash 分型 |
| `SYS_TFA_BL31_RAMDUMP` | 场景化 | MTK 深入分析输入 |
| `SYS_CUR_PLLK` | 场景化 | OCP/PMIC 路径寄存器证据 |
| `SYS_ANDROID_LOG_ALL` | 场景化 | 异常前后行为交叉验证 |

## 分析工作流
 
执行顺序:
1. 异常归类: 依据 `Exception Class/Type/CRDISPATCH_KEY` 先分支。
2. 时间线对齐: 明确异常前操作、触发点、重启/恢复时刻。
3. 主证据定位: 搜索 backtrace/pc/lr/kernel offset/BUG/oops/panic。
4. 符号映射: 用匹配版本 `vmlinux/ko` 做 addr2line 或 gdb/trace32。
5. 根因判断: 给出高/中/低置信度与已证实/待验证边界。
6. Jira 输出: 生成结构化报告与行动项。

详细步骤见: [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)

## 关键字速查

详见: [KEYWORDS.md](KEYWORDS.md)

核心检索串:
`Exception Class|Exception Type|CRDISPATCH_KEY|Kernel panic - not syncing|BUG|Oops|ATF crash|Unhandled Exception in EL3|assert`

## 输出格式

按以下模板输出:

# [问题类型] 日志分析报告

## 问题概述
- 问题现象: [用户描述]
- 异常分类: [Exception Class / out.json exception_type]

## 平台信息
- 项目/机型: [build 指纹提取]
- SoC 平台: [如 MT6895]
- 软件版本: [build 版本]
- 备注: [如存在平台信息不一致，需明确]

## 异常时间信息
- 日志时间: [Exception Log Time]
- 时间线: [异常前操作 -> 触发 -> 重启]

## 崩溃CPU
- [CPU 编号 / N/A(硬件 PMIC 触发复位路径)]

## 关键异常描述
- [简述触发链路与关键异常类型]
- [关键函数/线程 + 地址映射结果]

## 关键证据
- [文件名 + 关键日志/寄存器行]
- [文件名 + 关键日志/寄存器行]
- [符号文件版本与映射结果]

## 初步结论
- 根因方向: [高/中/低置信度]
- 结论说明: [一句话 + 限定条件]

## 建议行动项
- [研发动作]
- [测试复现/补日志动作]
- [跨团队协作动作，如 PMIC/硬件]

## 参考资源

- [KEYWORDS.md](KEYWORDS.md)
- [COMMON_ISSUES.md](COMMON_ISSUES.md)
- [CASES.md](CASES.md)
