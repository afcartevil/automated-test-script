# TAHP — TECNO AI Harness Platform

传音 Android 底软集成部 AI 辅助开发平台。通过 **Hermes Agent 执行**、**Skill 承载业务规则**、**Console 提供可视化入口**，支撑智能诊断（Bug 分析）、AI 适配调试、知识库管理与任务报告。

> 生产路径：`tahp-console` → Hermes Agent Bridge → `skills/` / `knowledge-base/` / `reports/`  
> 不再依赖 MCP stdio 桥或 YAML 约束引擎作为日常入口。

---

## 目录

- [架构概览](#架构概览)
- [仓库结构](#仓库结构)
- [业务模块](#业务模块)
- [快速开始](#快速开始)
- [使用指南](#使用指南)
- [开发与扩展](#开发与扩展)
- [使用规则与安全红线](#使用规则与安全红线)
- [验证与测试](#验证与测试)
- [相关文档](#相关文档)

---

## 架构概览

```
浏览器 (Vue 3 + Pinia)
    │  HTTP REST + Socket.IO
    ▼
tahp-console BFF (Koa 2, :8650)
    ├── /api/tahp/*        TAHP 业务 REST（诊断、适配、知识库、报告）
    ├── /api/hermes/*      Hermes 原生能力（对话、模型、Skills 库）
    └── Socket.IO /tahp-run   Agent 任务实时进度流
           │
           ▼
    Hermes Agent Bridge → hermes-agent-main/
           │
           ├── skills/.claude/skills/   业务 Skill（规则与执行规范）
           ├── knowledge-base/          知识库（BM25 检索 + 条目管理）
           └── reports/                 Bug 分析 / 适配 Agent 报告
```

### 双引擎定位

| 引擎 | 场景 | Console 入口 | 产出 |
|------|------|--------------|------|
| **诊断引擎** | Bug 根因分析 | `/tahp/bug-analysis` | `reports/bug-analysis/*.json` |
| **适配引擎** | 版本升级 / 特性移植 / 驱动适配 | `/tahp/adapt-debug` | `reports/adapt-agent/*.json` |
| **知识库** | 经验沉淀与检索 | `/tahp/knowledge` | `knowledge-base/.kb-data/` |

### 任务执行流程

**智能诊断（Bug 分析）**

1. 用户在 Console 输入 JIRA Key / URL 或描述
2. BFF 创建任务，通过 Agent Bridge 投递给 Hermes Agent
3. Agent 按 Skill 链执行（如 `transsion-harness` → `harness-jira`、领域 Bug 分析 Skill）
4. TaskStream 经 Socket.IO 推送 `task.started` / `task.phase` / `task.message` 等事件
5. 报告落盘 `reports/bug-analysis/<task-id>.json`

**AI 适配调试**

1. 用户选择适配域、填写表单参数
2. BFF 注入关联 Skill 与工程上下文，启动 Agent 运行
3. 实时展示 Skill 调用、文件变更、计划步骤
4. 完成后可选触发 `transsion-coding-standards-review` 自检
5. 报告落盘 `reports/adapt-agent/<task-id>.json`

---

## 仓库结构

```
tahp/
├── tahp-console/          Web 控制台（Vue 3 前端 + Koa BFF，fork 自 Hermes Web UI）
├── hermes-agent-main/     Hermes Agent 运行时（Python，含 venv）
├── skills/                Agent Skills
│   └── .claude/skills/    各业务 Skill 目录（每目录含 SKILL.md）
├── knowledge-base/        知识库数据与配置
│   ├── config.yaml        检索与自动沉淀配置
│   ├── .kb-data/          条目、草稿、文档（Console 管理）
│   └── {module}/          按模块组织的参考文档
├── reports/               任务报告输出
│   ├── bug-analysis/
│   └── adapt-agent/
├── docs/                  方案设计、控制台指南、约束规范
├── scripts/               开发脚本（pre-commit 等）
└── AGENTS.md              Agent / 协作者导航（精简版）
```

---

## 业务模块

模块由 `tahp-console` 静态常量维护，用于仪表盘、知识库筛选与适配域分组：

| 模块 ID | 显示名 | 能力域 |
|---------|--------|--------|
| `telephony` | 通信 | bug_analysis, code_adaptation, version_adaptation, carrier_porting |
| `kernel-driver` | 内核驱动 | bug_analysis, code_adaptation |
| `power-mgmt` | 功耗管理 | bug_analysis |
| `shared` | 共享 | code_adaptation |

Skill 数量约 190+，覆盖通信、充电/功耗、触控、振动、USB、传感器等子领域。总入口 Skill 为 `transsion-harness`，负责将任务路由到 `harness-*` 子 Skill。

---

## 快速开始

### 前置要求

- **Node.js** >= 20
- **Python** 3.11+（`hermes-agent-main` 使用，可通过 `TAHP_PYTHON` 指定）
- 仓库根目录包含 `hermes-agent-main/` 与 `skills/.claude/skills/`

### 安装与启动

```bash
cd tahp-console
npm install
npm run setup      # 检查 Node / Python / TAHP 根目录 / Hermes Agent venv
npm run dev
```

- 前端：http://localhost:5173  
- BFF：http://localhost:8650  

生产模式：

```bash
npm run build
npm run start
# 或
node bin/tahp-console.mjs start
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` | `8650` | 服务端口 |
| `AUTH_DISABLED` | `1` | `1` = 内网免鉴权，`0` = 启用令牌验证 |
| `AUTH_TOKEN` | — | 设置后自动启用令牌模式 |
| `TAHP_PROJECT_ROOT` | 自动探测 | 含 `skills/.claude/skills` 或 `knowledge-base/` 的目录 |
| `TAHP_PYTHON` | `python` / `python3` | Python 可执行路径 |
| `HERMES_AGENT_ROOT` | 自动 | 内置 `hermes-agent-main` 路径 |
| `LOG_LEVEL` | `info` | 日志级别 |

路径解析优先级：`TAHP_PROJECT_ROOT` 环境变量 → 自动推断 `tahp-console` 上级目录。

---

## 使用指南

### Console 面板

| 路由 | 功能 |
|------|------|
| `/tahp/dashboard` | 仪表盘：任务统计、近 7 天趋势、模块快捷入口 |
| `/tahp/bug-analysis` | 智能诊断：JIRA / 描述输入，Agent + Skill 分析 |
| `/tahp/adapt-debug` | AI 适配调试：选域、填表、启动 Agent 适配 |
| `/tahp/knowledge` | 知识库：条目 CRUD、BM25 搜索、草稿审核、文档导入 |
| `/tahp/reports` | 浏览 Bug 分析与适配 Agent 报告 |
| `/tahp/self-check` | 环境自检 |
| `/hermeses/chat` | Hermes 原生对话 |
| `/hermes/skills` | Skills 库浏览 |
| `/hermes/models` | 模型与 Provider 配置 |

详细说明见 [docs/tahp-console.md](docs/tahp-console.md)。

### 智能诊断

- 输入 JIRA Key（如 `USICPRO-12345`）或 Bug 描述
- 支持 JQL 批量分析、补充信息继续分析
- **所有 Bug 分析必须走 Agent**；Agent 不可用时任务直接失败，不降级为 BFF 直连 LLM
- JIRA 预览与 JQL 枚举由 BFF `jira.ts` 提供；正式分析由 Agent 通过 Skill 拉取

### AI 适配调试

- 按模块与适配域选择关联 Skill
- 填写动态表单（布局由 `adapt-layout` 服务解析）
- 实时查看 Skill 调用、工具执行、文件变更
- 报告含 prompt 日志（`reports/adapt-agent/prompts/`）

### 知识库

- 数据存储：`knowledge-base/.kb-data/`
- 支持语义搜索（BM25）、文档导入（URL / 文件夹）、Skill 草稿生成与审核
- 任务完成后可通过 feedback API 反哺知识库

### 报告

| 类型 | 路径 |
|------|------|
| Bug 分析 | `reports/bug-analysis/<task-id>.json` |
| 适配 Agent | `reports/adapt-agent/<task-id>.json` |
| 适配 Prompt 日志 | `reports/adapt-agent/prompts/<task-id>/` |

Console「报告」页与上述目录内容对应。

### Hermes 配置

模型与 API Key 通过 Hermes Profile 管理（`~/.hermes/auth.json`、`~/.hermes/config.yaml`）。首次使用需在 Console「模型管理」或 Hermes 设置中配置 Provider。

---

## 开发与扩展

### 核心原则

1. **Skill 优先**：业务规则写在 `skills/.claude/skills/<skill-name>/SKILL.md`，不在 BFF 硬编码流程
2. **防幻觉**：代码产出须有据可查；禁止编造 API / 类名 / 行为
3. **最小变更**：只修改与任务直接相关的代码
4. **Console 入口**：同事日常使用 `tahp-console`，而非独立 CLI

### 新增 Skill

1. 在 `skills/.claude/skills/<skill-name>/` 创建 `SKILL.md`
2. YAML frontmatter 建议包含：`name`、`description`、`module`、`funcType`、`version`
3. 在 Console Skills 库或 Agent 配置中引用；适配域可通过知识库 metadata 关联

示例结构参考 `skills/.claude/skills/telephony-bug-analyzer/SKILL.md`。

### TAHP REST API 概览

挂载于 `/api/tahp/*`：

- `bug-analysis` — 启动 / 查询 Bug 分析任务
- `adapt` — 适配 Agent 运行与 prompt 预览
- `knowledge` — 知识库 CRUD、搜索、导入、草稿审核
- `reports` — 报告列表与详情
- `skills` — 动态适配域与 Skill 元数据
- `self-check` — 环境自检

实时事件：前端订阅 Socket.IO 命名空间 `/tahp-run`。

### 文件操作范围（协作者）

- **可操作**：`skills/`、`knowledge-base/`、`tahp-console/`、`scripts/`、`docs/`、`reports/`
- **避免大范围改动**：`hermes-agent-main/` 第三方子模块、`.git/`、`.env`

---

## 使用规则与安全红线

### 平台级（所有 Agent / 协作者）

1. 不在未验证 API 存在性的情况下生成代码
2. 不硬编码密钥、Token、设备标识
3. 涉及安全相关的 Bug 必须标记为 **Critical**
4. 代码修改须经过编译或团队约定的验证流程

### AI 代码生成（详见 [docs/TAHP-AI代码生成约束规范.md](docs/TAHP-AI代码生成约束规范.md)）

- **不跑偏**：在 Skill / 约束定义的 scope 内操作
- **不幻觉**：引用须来自代码、日志、知识库或 MCP 结构化数据
- **不反复**：一次性产出可验证结果
- 弱证据推断须标注 `[SPECULATIVE]`

### Skill 编写要点

- 明确触发条件、前置检查、分析协议、安全红线
- Harness 类任务优先走 `harness --json <command>`，不凭记忆猜参数
- Bug 分析 Skill 应规定缺失关键信息时的停止条件

---

## 验证与测试

```bash
cd tahp-console
npm run setup
npm test

# 开发模式
npm run dev
```

可选 Pre-commit（Windows）：

```powershell
powershell -File scripts/pre-commit-check.ps1
```

### 常见问题

| 现象 | 处理 |
|------|------|
| Agent Bridge 不可用 | 执行 `npm run setup:agent -- --force`，检查 `hermes-agent-main/.venv` |
| 端口 8650 被占用 | `PORT=8651 npm run start` |
| 知识库搜索无结果 | 确认 `knowledge-base/.kb-data` 有条目，或在 Console 创建/导入 |
| 找不到 TAHP 根目录 | 设置 `TAHP_PROJECT_ROOT` 指向含 `skills/` 的仓库根 |

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [AGENTS.md](AGENTS.md) | 协作者 / Agent 快速导航 |
| [docs/tahp-console.md](docs/tahp-console.md) | Console 使用指南 |
| [docs/TECNO-AI-Harness-Platform-方案设计.md](docs/TECNO-AI-Harness-Platform-方案设计.md) | 方案设计与架构评估 |
| [docs/TAHP-Architecture-Overview.html](docs/TAHP-Architecture-Overview.html) | 可视化架构总览 |
| [docs/TAHP-AI代码生成约束规范.md](docs/TAHP-AI代码生成约束规范.md) | AI 代码生成约束 |
| [docs/TAHP-评估与质量门禁规范.md](docs/TAHP-评估与质量门禁规范.md) | Skill 质量与门禁 |
| [tahp-console/README_zh.md](tahp-console/README_zh.md) | Hermes Web UI 功能说明（含 TAHP 叠加面板） |

---

## 许可证

`tahp-console` 基于 Hermes Web UI，许可证为 [BSL-1.1](tahp-console/LICENSE)。
