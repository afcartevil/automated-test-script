---
name: android-bootup-issue-log-analysis
description: "Android-不开机: 分析Bootup Issue(不开机/卡Logo/开机循环重启)，按启动阶段(Preloader/LK/Kernel/init-Framework/Recovery)完成阶段判定 | dm-verity/fs_mgr_mount_all/reboot_longkey/卡logo/不开机/bootup | 当用户报告Android设备不开机、卡Logo、开机循环重启时使用"
funcType: "AI故障分析"
category: "内核"
---

# Bootup Issue 问题分析 Skill

来源 SOP: [不开机问题分析 SOP](https://transsioner.feishu.cn/docx/OJ2WdDyP3ojuXsxz3vtclO95nAh)

## 适用范围

- 问题类型: Android 不开机、卡 Logo、开机循环重启、黑屏无振动
- 适用场景:
  - 长按电源无响应
  - 仅显示 Logo/动画后重启
  - 可进 Recovery/Fastboot 但无法进入系统
  - 低电、温度、按键、分区完整性相关开机失败
- 平台: MTK（方法可扩展到 SPRD/QCOM）

## 所需文档与优先级

| 日志文件 | 必需性 | 用途 |
|---|---|---|
| 串口日志 | 必需 | BootROM/Preloader/LK/Kernel 阶段判定 |
| `pl_lk` | 必需 | LK 里程碑与交界问题定位 |
| `kernel_log*` | 必需 | panic/watchdog/mount 等失败点 |
| `main_log*` | 高优先级 | init/framework 首个失败点 |
| `SYS_LAST_KMSG` / pstore | 高优先级 | 重启前最后异常 |
| `SYS_KERNEL_LOG` | 高优先级 | 内核证据与时间线 |
| `SYS_REBOOT_REASON` | 高优先级 | 复位原因线索 |
| `SYS_CUR_PLLK` | 场景化 | PMIC/电源路径线索 |
| `__exp_main.txt` / `_分析报告.txt` | 场景化 | 异常摘要与初判参考 |
| `vmlinux` + 相关 `ko` | 场景化 | Kernel 栈符号映射 |

## 分析工作流

执行顺序:
1. 先判阶段: 上电前期 / LK(ABL) / Kernel / init-Framework / Recovery 分支。
2. 锁失败点: 提取第一条致命日志或最后一个里程碑日志。
3. 分支深挖: 电源、存储、文件系统、framework、按键、热路径。
4. 证据闭环: 至少 2 条日志 + 1 个文件/截图 + 版本一致性说明。
5. Jira 输出: 结论置信度 + owner + 验证动作。

详细步骤见: [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)

## 关键字速查

详见: [KEYWORDS.md](KEYWORDS.md)

核心检索串:
`BOOTPROF|check_low_battery|shutdown,thermal|fs_mgr_mount_all|dm-verity device corrupted|androidboot.bootreason=reboot_longkey|Kernel panic|watchdog`

## 输出格式

按以下模板输出:

# [Bootup Issue] 日志分析报告

## 问题概述
- 现象: [无反应/卡Logo/循环重启/可进Recovery不可进系统]
- 复现条件: [稳定复现/概率复现/首次出现版本]

## 平台信息
- 项目/机型: [build 指纹]
- SoC/版本: [平台与软件版本]
- 版本一致性: [日志与符号是否同版本]

## 阶段判定
- 失败阶段: [Preloader/LK/Kernel/init-Framework/Recovery]
- 判定依据: [最后里程碑日志 + 首个失败日志]

## 关键证据
- [文件名 + 关键日志1]
- [文件名 + 关键日志2]
- [文件名/截图 + 辅助证据]

## 初步结论
- 根因方向: [软件配置/驱动时序/分区一致性/硬件电路]
- 置信度: [高/中/低]
- 待验证项: [若证据不足需明确]

## 建议行动项
- [owner + 优先级 + 动作]
- [验证方式与回归建议]

## 参考资源

- [KEYWORDS.md](KEYWORDS.md)
- [COMMON_ISSUES.md](COMMON_ISSUES.md)
- [CASES.md](CASES.md)
