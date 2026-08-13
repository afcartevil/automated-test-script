# TAHP — TECNO AI Harness Platform

> Agent + Skill 专一路径：Hermes Agent 执行，Skill 承载业务规则，Console 提供可视化入口。

## 项目概述

TAHP 服务于传音 Android 底软集成部，覆盖通信、驱动、内核、功耗等子部门。
生产路径为 **tahp-console + Hermes Agent + skills**，不再依赖 MCP 桥接或 YAML 约束引擎。

## Cursor 编码规范

所有 Agent / 研发在 Cursor 中改代码须遵守 [.cursor/rules/](.cursor/rules/)：

| 规则文件 | 作用 |
|----------|------|
| `00-change-control.mdc` | 变更范围、敏感链、禁止越界（**始终生效**） |
| `tahp-verify-commit.mdc` | 验证命令、提交与 MR 要求（**始终生效**） |
| `tahp-console-dev.mdc` | 编辑 `tahp-console/**` 时加载 |
| `tahp-paths-config.mdc` | 编辑路径/统一配置/JIRA 工作区时加载 |
| `tahp-skills-hermes.mdc` | 编辑 `skills/.claude/skills/**` 时加载 |
| `tahp-self-check.mdc` | 编辑 AI 自检相关代码时加载 |

复杂流程另见 `.cursor/skills/`（如 `device-self-check`、`self-check-test-integration`）。

---

## 快速定位

| 任务 | 导航 | Cursor 规则 / Skill |
|------|------|---------------------|
| 智能诊断 (Bug 分析) | `/tahp/bug-analysis` | `tahp-skills-hermes` |
| AI 适配调试 | `/tahp/adapt-debug` | `tahp-console-dev` |
| 知识库管理 | `knowledge-base/` + `/tahp/knowledge` | `00-change-control` |
| Skill 维护 | Console 同步中心 → 本机 `skills/.claude/skills/`（不入库） | `tahp-skills-hermes` |
| 配置 / JIRA 路径 | 配置 UI + `.tahp/` | `tahp-paths-config` |
| AI 自检 | `/tahp/self-check` | `tahp-self-check` + `device-self-check` skill |
| 查看报告 | `reports/` + `/tahp/reports` | — |
| Console 开发细则 | [tahp-console/DEVELOPMENT.md](tahp-console/DEVELOPMENT.md) | `tahp-console-dev` |
| Windows 部署 | `run_adapter.bat`、系统托盘；详见 `Windows使用说明.txt` | `00-change-control` |

## 仓库结构

```
skills/              ← 业务 Skill 运行时目录（Console 同步中心落盘，不入库）
knowledge-base/      ← 知识库（文件存储 + BM25 检索）
hermes-agent-main/   ← Hermes Agent 运行时（默认少改）
tahp-console/        ← Web 控制台（BFF + Vue UI）
jira_workspace/      ← JIRA 日志工作区（工程根，gitignore）
reports/             ← 报告输出
scripts/             ← 开发/部署脚本
.cursor/rules/       ← Cursor 编码规范
```

## 业务模块

| 模块 | 能力域 |
|------|--------|
| telephony (通信) | bug_analysis, code_adaptation, version_adaptation, carrier_porting |
| kernel-driver (内核驱动) | bug_analysis, code_adaptation |
| power-mgmt (功耗管理) | bug_analysis |
| shared (共享) | code_adaptation |

模块列表由 `tahp-console` 静态常量维护。

## 路径与配置排障

配置异常时按序检查（详见 `tahp-paths-config.mdc`）：

1. BFF 启动日志中的 `projectRoot` / `valid=`
2. `tahp-console/.env` → `TAHP_PROJECT_ROOT`
3. `{工程根}/.tahp/unified-config.json`
4. `%LOCALAPPDATA%\hermes\skills\jira-ops\.env` → `WORKSPACE_ROOT`
5. 重启服务后确认 `{工程根}/jira_workspace/<JIRA_KEY>/`

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
npm run build    # 改代码后建议执行

npm run dev      # client:5173, server:8650
```

## 相关文档

- [控制台 README（中文）](tahp-console/README_zh.md)
- [Console 开发规范](tahp-console/DEVELOPMENT.md)
- [方案设计](TECNO-AI-Harness-Platform-方案设计.md)
- [架构总览](TAHP-Architecture-Overview.html)

> `docs/` 目录若未纳入版本库，以 `tahp-console/README_zh.md` 与 `.cursor/rules/` 为准。
