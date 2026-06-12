# TAHP — TECNO AI Harness Platform

> Agent + Skill 专一路径：Hermes Agent 执行，Skill 承载业务规则，Console 提供可视化入口。

## 项目概述

TAHP 服务于传音 Android 底软集成部，覆盖通信、驱动、内核、功耗等子部门。
生产路径为 **tahp-console + Hermes Agent + skills**，不再依赖 MCP 桥接或 YAML 约束引擎。

## 快速定位

| 任务 | 导航 |
|------|------|
| 智能诊断 (Bug 分析) | `tahp-console` → `/tahp/bug-analysis` |
| AI 适配调试 | `tahp-console` → `/tahp/adapt-debug` |
| 知识库管理 | `knowledge-base/` + `/tahp/knowledge` |
| Skill 维护 | `skills/.claude/skills/` |
| 查看报告 | `reports/` + `/tahp/reports` |
| 控制台文档 | [docs/tahp-console.md](docs/tahp-console.md) |

## 仓库结构

```
skills/              ← Agent Skills（业务规则与执行规范）
knowledge-base/      ← 知识库（文件存储 + BM25 检索）
hermes-agent-main/   ← Hermes Agent 运行时
tahp-console/        ← Web 控制台（BFF + Vue UI）
reports/             ← Bug 分析 / 适配 Agent 报告输出
scripts/             ← 开发脚本（pre-commit 等）
docs/                ← 文档
```

## 业务模块

| 模块 | 能力域 |
|------|--------|
| telephony (通信) | bug_analysis, code_adaptation, version_adaptation, carrier_porting |
| kernel-driver (内核驱动) | bug_analysis, code_adaptation |
| power-mgmt (功耗管理) | bug_analysis |
| shared (共享) | code_adaptation |

模块列表由 `tahp-console` 静态常量维护，用于仪表盘与知识库筛选。

## 安全红线

1. 不在未验证 API 存在性的情况下生成代码
2. 不硬编码密钥 / Token / 设备标识
3. 涉及安全相关的 Bug 必须标记为 Critical
4. 代码修改须经过编译或团队约定的验证流程

## 验证命令

```bash
cd tahp-console
npm run setup
npm test

# 开发模式
npm run dev   # client:5173, server:8650
```

## 相关文档

- [控制台使用指南](docs/tahp-console.md)
- [方案设计](TECNO-AI-Harness-Platform-方案设计.md)
- [架构总览](TAHP-Architecture-Overview.html)
