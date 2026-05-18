# TAHP — Claude Code 配置

## 项目
TECNO AI Harness Platform (TAHP) — 传音Android底软集成部双引擎AI平台。

## 首先阅读
执行任何任务前，必须先阅读 AGENTS.md 了解项目导航和约束体系。

## 核心规则

1. **Scope锁定**: 每次操作前先读取对应模块约束文件，只操作 scope.includes 中的路径
2. **防幻觉**: 所有代码产出必须有据可查，禁止编造
3. **一次性正确**: 分析→计划→确认→修改→验证，不允许试错式迭代
4. **最小变更**: 只修改与任务直接相关的代码

## 任务执行协议
Phase 1 分析（只读）→ Phase 2 修改（按计划）→ Phase 3 验证（自检）

## MCP工具
tools/ 目录下定义了7个MCP工具:
android-log-analyzer, aosp-diff-analyzer, patch-generator, api-migration-db, build-verifier, regression-test-runner, code-review-checker

## 文件操作范围
- 可操作: constraints/, skills/, playbooks/, scripts/, docs/, reports/
- 禁止: .git/, .env, 其他模块约束文件（除非显式授权）

## 输出格式
- Bug分析报告: TAHP-AI代码生成约束规范 §5.1
- 代码修改: TAHP-AI代码生成约束规范 §5.2
- 适配报告: TAHP-版本适配约束规范 §7.3
