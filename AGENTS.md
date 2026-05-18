# TAHP — TECNO AI Harness Platform

> 双引擎AI平台: 诊断引擎(Bug分析) + 适配引擎(版本/特性/运营商移植)

## 项目概述

TAHP服务于传音Android底软集成部，覆盖通信、驱动、内核、功耗等子部门。
基于 Agent = Model + Harness 范式，通过约束驱动 + EvoSkill自动进化实现AI辅助开发。

## 快速定位

| 任务 | 导航 |
|------|------|
| 分析Bug | constraints/{module}/bug-analysis.yaml |
| 适配代码 | constraints/{module}/code-adaptation.yaml |
| 版本升级适配 | constraints/{module}/version-adaptation.yaml |
| 运营商需求移植 | constraints/{module}/carrier-porting.yaml |
| 查看执行流程 | playbooks/ |
| 了解可用工具 | tools/ |

## 仓库结构

```
constraints/     ← 业务约束（Owner输入端）
  ├── {module}/  ← 按模块组织
  └── shared/    ← 共享约束 + API迁移规则库
skills/          ← AI Skills（自动生成/手动维护）
playbooks/       ← 执行编排（Pipeline定义）
tools/           ← MCP工具接口定义
scripts/         ← 自动化脚本
templates/       ← 模块初始化模板
docs/            → 深度文档
reports/         → 评估报告输出
```

## 已接入模块

| 模块 | Domain | 状态 |
|------|--------|------|
| telephony (通信) | android-telephony | 模板就绪 |
| kernel-driver (内核驱动) | android-kernel-driver | 模板就绪 |
| power-mgmt (功耗管理) | android-power-management | 模板就绪 |

## 四种约束域(Domain)

| Domain | 引擎 | 输入 | 产出 |
|--------|------|------|------|
| bug_analysis | 诊断 | 日志/复现步骤 | 分析报告 |
| code_adaptation | 诊断 | Bug修复/代码适配 | 代码Patch |
| version_adaptation | 适配 | 版本升级/Feature移植 | 批量Patch |
| carrier_porting | 适配 | 运营商需求 | Carrier Patch |

## 安全红线（所有操作必须遵守）

1. 不修改 scope.excludes 中列出的任何文件
2. 不在未验证API存在性的情况下生成代码
3. 不硬编码密钥/Token/设备标识
4. 涉及安全相关的Bug必须标记为Critical
5. 所有代码修改必须在编译门禁中通过

## 质量门禁

| 级别 | 门禁 | 失败处理 |
|------|------|---------|
| P0 | 编译通过 + Scope合规 + 安全红线 + API真实性 | BLOCK |
| P1 | 编码风格 + Lint + 废弃API + TODO关联 | WARNING |
| P2 | 代码复杂度 + 重复率 + 注释覆盖 | 记录 |

## 新模块接入

```bash
python scripts/init_module.py --module your-module --owner your-name
```

## 相关文档

- [方案设计](TECNO-AI-Harness-Platform-方案设计.md)
- [架构总览](TAHP-Architecture-Overview.html)
- [约束编写规范](TAHP-约束文件编写规范.md)
- [版本适配规范](TAHP-版本适配约束规范.md)
- [AI代码生成约束](TAHP-AI代码生成约束规范.md)
- [评估与质量门禁](TAHP-评估与质量门禁规范.md)
