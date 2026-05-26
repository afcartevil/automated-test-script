---
name: android-kernel-api-dump-log-analysis
description: "MTK-KernelAPI-dump: 分析Kernel API dump(EMI MPU Violation)，通过Plat_Parser_mpu/smpu完成master/region owner双向校验 | EMI_MPU/MPU_Violation/CRDISPATCH/SYS_KERNEL_LOG/violation_address | 当用户提供KernelAPI dump DB、EMI MPU violation分析时使用"
funcType: "AI故障分析"
category: "内核"
---

# Kernel API Dump 问题分析 Skill

来源 SOP: [KernelAPI dump问题分析SOP](https://transsioner.feishu.cn/docx/TQsFdsneGohOpkx0lhgclo33nVd)

## 适用范围

- 问题类型: MTK 平台 Kernel API dump（典型为 EMI MPU Violation）
- 适用场景: 访问受保护内存区域触发 permission deny、需定位 master 与 region owner、需与 MTK 协同权限或模块修复
- 适用芯片平台: MTK（兼容同类 AEE/DEC 包结构）

## 前置条件

| 文件/路径 | 必需性 | 用途 |
|---|---|---|
| `_分析报告.txt` | 必需 | 异常描述、平台、初判 |
| `__exp_main.txt` | 必需 | 异常类型、栈、Detail Info |
| `db.00.KernelAPI.../Plat_Parser_mpu.txt` | 必需 | EMI MPU 解析字段 |
| `Plat_Parser_smpu.txt` | 可选 | 支持 SMPU 的平台 |
| `SYS_KERNEL_LOG` | 必需 | violation address、reserved 区间 |
| `SYS_TFA_CRASH_REPORT` | 可选 | 排除 ATF 路径 |
| LK/UART 日志 | 高优先级（缺省时） | 内存区间与模块申请映射 |
| `vmlinux` / 相关 `ko` | 高优先级 | 代码路径与符号 |

## 分析工作流

1. 读取 `Plat_Parser_mpu.txt`（及 `smpu` 若适用），提取关键字段并写清结论句式。
2. 在 `SYS_KERNEL_LOG` 中按 violation address 做归属检索（完整地址与前缀）。
3. 缺 LK/UART 映射时补同平台同项目日志；在代码中按 reserved 节点名检索申请/重映射实现。
4. 做 master 与 region owner 双向校验，按根因分型收敛。
5. 按 MTK 协同边界决定是否升级 MTK，并输出 Jira 证据三件套。

详细步骤见: [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)

## 关键字速查

详见: [KEYWORDS.md](KEYWORDS.md)

核心检索串:
`CRDISPATCH_KEY|EMI MPU|violation address|Read violation|Write violation|region_id|domain_id|Plat_Parser_mpu|reserved|drdi_memory`

## 输出格式

按以下模板输出:

# [Kernel API Dump / EMI MPU] 日志分析报告

## 问题概述
- 问题现象: [用户描述]
- 异常分类: [CRDISPATCH_KEY / Exception 类型]

## 平台信息
- 项目/机型: [build 指纹]
- SoC / 软件版本: [芯片与版本]

## 异常时间信息
- 发生时刻: [绝对时间或相对开机秒数]
- 关键操作时间线: [简述]

## 关键字段（Plat_Parser）
- emi_id / port_id / axi_id / region_id / domain_id: [...]
- 访问类型: [Read/Write violation]
- violation address: [...]
- CRDISPATCH_KEY: [...]

## 关键证据
- Parser 摘录: [文件 + 关键行]
- 地址归属: [SYS_KERNEL_LOG reserved 区间与节点名]
- 代码路径: [函数/文件或检索结论]

## 初步结论
- master 侧: [合法/异常/待验证]
- region owner 侧: [权限是否覆盖/待验证]
- 置信度: [高/中/低]

## 建议行动项
- [模块 owner 自检]
- [是否需 MTK 权限对齐 / 提单材料清单]

## 参考资源

- [KEYWORDS.md](KEYWORDS.md)
- [COMMON_ISSUES.md](COMMON_ISSUES.md)
- [CASES.md](CASES.md)
