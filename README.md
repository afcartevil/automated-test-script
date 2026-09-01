# TAHP — TECNO AI Harness Platform

传音 Android 底软集成部 AI 辅助开发平台。通过 **Hermes Agent 执行**、**Skill 承载业务规则**、**Console 提供可视化入口**，支撑智能诊断（Bug 分析）、AI 适配调试、知识库管理、AI 自检与任务报告。

> **生产路径**：`tahp-console` → Hermes Agent Bridge → `skills/` / `knowledge-base/` / `reports/`  
> 日常入口为 Web Console，不再依赖 MCP stdio 桥或 YAML 约束引擎。

---

## 目录

- [架构概览](#架构概览)
- [技术栈](#技术栈)
- [仓库结构](#仓库结构)
- [基本功能](#基本功能)
- [业务模块](#业务模块)
- [快速开始](#快速开始)
- [使用指南](#使用指南)
- [配置与数据存储](#配置与数据存储)
- [开发与扩展](#开发与扩展)
- [使用规则与安全红线](#使用规则与安全红线)
- [验证与测试](#验证与测试)
- [相关文档](#相关文档)

---

## 架构概览

```
浏览器 (Vue 3 + Pinia + Naive UI)
    │  HTTP REST + Socket.IO
    ▼
tahp-console BFF (Koa 2, :8650)
    ├── /api/tahp/*        TAHP 业务 REST
    ├── /api/hermes/*      Hermes 原生能力（对话、模型、Skills 库）
    └── Socket.IO /tahp-run   Agent 任务实时进度流
           │
           ▼
    Hermes Agent Bridge → hermes-agent-main/
           │
           ├── skills/.claude/skills/   业务 Skill（规则与执行规范）
           ├── knowledge-base/          知识库（BM25 检索 + 条目管理）
           └── reports/                 任务报告（Bug / 适配 / Gerrit 等）
```

### 能力分层

| 层级 | 说明 | 典型场景 |
|------|------|----------|
| **Agent + Skill** | Hermes Agent 按 Skill 链执行，Socket.IO 推送进度 | Bug 分析、AI 适配、Gerrit Code Review |
| **BFF 直连** | Koa 服务读写本地文件 / 调用 Python / 解析表格 | 知识库、设备自检、测试自规划 |
| **Hermes 原生** | 复用 Hermes Web UI 对话、模型、终端等 | 自由对话、Skills 浏览、模型配置 |

### 任务执行流程（Agent 类）

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
4. 完成后可选触发编码规范自检
5. 报告落盘 `reports/adapt-agent/<task-id>.json`

**Gerrit Code Review（AI 自检内）**

1. 用户在 AI 自检页输入 Gerrit 链接或 topic
2. BFF 校验 Gerrit 账号配置后，通过 Agent 执行 Code Review Skill
3. 右侧自动提取 P0「必须测试」建议

---

## 技术栈

| 层次 | 技术 |
|------|------|
| 前端 | Vue 3、TypeScript、Pinia、Vue Router、Naive UI、Vite |
| BFF | Node.js ≥ 20、Koa 2、TypeScript、Socket.IO |
| Agent | Python 3.11+、`hermes-agent-main`（内置 venv） |
| 检索 | BM25（知识库）、文件存储 |
| 设备自检 | ADB + Python 用例脚本（`device-self-check` 服务） |
| 表格解析 | SheetJS（`xlsx`，项目节点同步） |
| 测试 | Vitest（单元）、Playwright（E2E） |
| 许可证 | BSL-1.1（基于 Hermes Web UI fork） |

### tahp-console 工程结构

```
tahp-console/
├── packages/
│   ├── client/          Vue 3 前端（views、components、stores、api）
│   └── server/          Koa BFF（routes、services、controllers）
├── tests/               Vitest + Playwright
├── scripts/             开发 / 构建 / setup 脚本
└── bin/tahp-console.mjs 生产启动入口
```

---

## 仓库结构

```
tahp/
├── tahp-console/          Web 控制台（Vue 3 前端 + Koa BFF）
├── hermes-agent-main/     Hermes Agent 运行时（Python，含 venv）
├── skills/
│   └── .claude/skills/    各业务 Skill 目录（每目录含 SKILL.md，约 190+）
├── knowledge-base/        知识库数据与配置
│   ├── config.yaml        检索与自动沉淀配置
│   ├── .kb-data/          条目、草稿、文档（Console 管理）
│   └── {module}/          按模块组织的参考文档
├── reports/               任务报告输出
│   ├── bug-analysis/
│   ├── adapt-agent/
│   └── gerrit-review/
├── docs/                  方案设计、控制台指南、约束规范（部分本地文件 gitignore）
├── scripts/               开发脚本（pre-commit 等）
├── .tahp-config/          运行时本地配置（gitignore，Gerrit 凭证、项目节点等）
└── AGENTS.md              Agent / 协作者导航（精简版）
```

---

## 基本功能

| 功能 | 路由 | 说明 |
|------|------|------|
| 仪表盘 | `/tahp/dashboard` | 任务统计、近 7 天趋势、模块快捷入口 |
| 智能诊断 | `/tahp/bug-analysis` | JIRA / 描述输入，Agent + Skill Bug 根因分析 |
| AI 适配调试 | `/tahp/adapt-debug` | 选域、填表、启动 Agent 适配，实时任务流 |
| **AI 自检** | `/tahp/self-check` | 多设备并行自动化测试 + Gerrit Code Review + AI 测试自规划 |
| 知识库 | `/tahp/knowledge` | 条目 CRUD、BM25 搜索、草稿审核、文档导入 |
| 报告 | `/tahp/reports` | 浏览 Bug 分析、适配 Agent、Gerrit 评审等报告 |
| 一键配置 | `/tahp/config?tab=form` | 填表后保存并启动 Skill 配置检查 |
| 对话 | `/hermes/chat` | Hermes 原生多轮对话 |
| Skills 库 | `/hermes/skills` | Skill 浏览与管理 |
| 模型管理 | `/hermes/models` | Provider 与模型配置 |
| 设置 | `/hermes/settings` | Hermes 设置 + **Gerrit 账号**（`?tab=gerrit`） |

### AI 自检（`/tahp/self-check`）子能力

概览页包含三个工作区：

1. **多设备自动化测试**
   - ADB 设备发现与并行测试（STR4 转测 / 周版本等）
   - 模块：TDD、驱动器件、驱动硬测等 Python 用例
   - 设备详情：用例树、执行进度、结果复用

2. **Gerrit Code Review**
   - 输入 Gerrit 链接或 topic，Agent 执行 Code Review
   - 右侧展示 AI 测试建议（P0 必须测试项）
   - 需先在设置中配置 Gerrit HTTP 账号

3. **AI 测试自规划**
   - 从 `docs/升级项目关键信息表.xlsx` 同步「升级中」项目节点（STR4 / STR4A / STR5 / STR6）
   - 可配置各节点前后 14 天内的测试项（如 STR4A 前 10 天启动 GMS 测试）
   - 左栏展示下一节点，右栏展示待执行测试计划

---

## 业务模块

模块由 `tahp-console` 静态常量维护，用于仪表盘、知识库筛选与适配域分组：

| 模块 ID | 显示名 | 能力域 |
|---------|--------|--------|
| `telephony` | 通信 | bug_analysis, code_adaptation, version_adaptation, carrier_porting |
| `kernel-driver` | 内核驱动 | bug_analysis, code_adaptation |
| `power-mgmt` | 功耗管理 | bug_analysis |
| `shared` | 共享 | code_adaptation |

Skill 覆盖通信、充电/功耗、触控、振动、USB、传感器等子领域。总入口 Skill 为 `transsion-harness`，负责将任务路由到 `harness-*` 子 Skill。

---

## 快速开始

### 前置要求

- **Node.js** >= 20
- **Python** 3.11+（`hermes-agent-main` 使用，可通过 `TAHP_PYTHON` 指定）
- 仓库根目录包含 `hermes-agent-main/`；业务 Skill 目录 `skills/.claude/skills/` 由 Console 同步中心拉取（Git 不跟踪正文）
- AI 测试自规划可选：本地放置 `docs/升级项目关键信息表.xlsx`

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
| `TAHP_PROJECT_INFO_XLSX` | `docs/升级项目关键信息表.xlsx` | 项目节点 Excel 路径（可覆盖） |
| `TAHP_GERRIT_CONFIG_DIR` | `.tahp-config/` | Gerrit 凭证存储目录 |
| `TAHP_TEST_PLANNING_CONFIG_DIR` | `.tahp-config/` | 测试自规划配置目录 |
| `LOG_LEVEL` | `info` | 日志级别 |

路径解析优先级：`TAHP_PROJECT_ROOT` 环境变量 → 自动推断 `tahp-console` 上级目录。

---

## 使用指南

### 智能诊断

- 输入 JIRA Key（如 `USICPRO-12345`）或 Bug 描述
- 支持 JQL 批量分析、补充信息继续分析
- **所有 Bug 分析必须走 Agent**；Agent 不可用时任务直接失败，不降级为 BFF 直连 LLM
- JIRA 预览与 JQL 枚举由 BFF 提供；正式分析由 Agent 通过 Skill 拉取

### AI 适配调试

- 按模块与适配域选择关联 Skill
- 填写动态表单（布局由 `adapt-layout` 服务解析）
- 实时查看 Skill 调用、工具执行、文件变更
- 报告含 prompt 日志（`reports/adapt-agent/prompts/`）

### 知识库

- 数据存储：`knowledge-base/.kb-data/`
- 支持 BM25 语义搜索、文档导入（URL / 文件夹）、Skill 草稿生成与审核
- 任务完成后可通过 feedback API 反哺知识库

### 报告

| 类型 | 路径 |
|------|------|
| Bug 分析 | `reports/bug-analysis/<task-id>.json` |
| 适配 Agent | `reports/adapt-agent/<task-id>.json` |
| 适配 Prompt 日志 | `reports/adapt-agent/prompts/<task-id>/` |
| Gerrit Code Review | `reports/gerrit-review/<task-id>.json` |

Console「报告」页与上述目录内容对应。

### Hermes 与 Gerrit 配置

- **模型与 API Key**：通过 Hermes Profile 管理（`~/.hermes/auth.json`、`~/.hermes/config.yaml`）
- **Gerrit 账号**：Console → 设置 → Gerrit 账号，或访问 `/hermes/settings?tab=gerrit`  
  凭证存于 `.tahp-config/gerrit.json`（gitignore），供 Gerrit Code Review Agent 使用

详细说明见 [docs/tahp-console.md](docs/tahp-console.md)。

---

## 配置与数据存储

| 路径 | 用途 | Git 跟踪 |
|------|------|----------|
| `.tahp-config/gerrit.json` | Gerrit 账号配置 | 否 |
| `.tahp-config/project-nodes.json` | AI 测试自规划：项目节点缓存 | 否 |
| `.tahp-config/test-plan-rules.json` | AI 测试自规划：节点测试规则 | 否 |
| `.adapt-config/` | AI 适配调试布局与配置 | 是 |
| `.tahp/required-skills.json` | 必选 Skill 清单（团队共享） | 是 |
| `.tahp/skill-config-state.json` | 本机 Skill 配置完成状态 | 否 |
| `.tahp/jira-user-config.json` | 智能诊断同步的 Jira 凭据 | 否 |
| `.tahp/central-user-session.json` | 中心用户 session（无密码，含 token） | 否 |
| `knowledge-base/.kb-data/` | 知识库条目与文档 | 否（本机/同步重建） |
| `skills/.claude/skills/` | 业务 Skill（Console 同步中心落盘） | 否 |
| `docs/升级项目关键信息表.xlsx` | 升级项目节点源表（飞书导出） | 否（`docs/` gitignore） |

---

## 开发与扩展

### 核心原则

1. **Skill 优先**：业务规则写在 `skills/.claude/skills/<skill-name>/SKILL.md`，不在 BFF 硬编码流程
2. **防幻觉**：代码产出须有据可查；禁止编造 API / 类名 / 行为
3. **最小变更**：只修改与任务直接相关的代码
4. **Console 入口**：同事日常使用 `tahp-console`，而非独立 CLI

### 新增 / 更新 Skill

业务 Skill **不通过 Git 分发**。本机目录仍是 `skills/.claude/skills/<skill-name>/`，入库与同事同步只走 Console「同步中心」：

1. 在该目录创建或修改 `SKILL.md`（YAML：`name`、`description`、`module`、`funcType`、`version`；目录名仅字母数字与 `_` `-`）
2. Console → 同步中心 → **提交服务器**（待审）
3. 中心审核通过后，同事 **同步全部 / 同步此包** → **应用到 Agent**

详见 `.cursor/skill-sync/`。

### TAHP REST API 概览

挂载于 `/api/tahp/*`：

| 前缀 | 说明 |
|------|------|
| `bug-analysis` | Bug 分析任务启动 / 查询 / JIRA 预览 |
| `adapt` | 适配 Agent 运行、布局与配置 |
| `knowledge` | 知识库 CRUD、搜索、导入、草稿审核 |
| `reports` | 报告列表与详情 |
| `skills` | 动态适配域与 Skill 元数据 |
| `skill-config` | 必选 Skill 配置与验证 |
| `self-check` | 环境自检 |
| `device-self-check` | 多设备自动化测试（ADB、用例执行、SSE 事件） |
| `gerrit-review` | Gerrit Code Review Agent 对话 |
| `gerrit-config` | Gerrit 账号配置读写 |
| `test-planning` | 项目节点同步、测试规则、待执行计划 |

实时事件：前端订阅 Socket.IO 命名空间 `/tahp-run`（Agent 任务）。

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

# E2E（Playwright）
npm run test:e2e

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
| Gerrit Review 无法开始 | 在设置 → Gerrit 账号中配置 host / 用户名 / HTTP Password |
| 项目节点更新失败 | 确认 `docs/升级项目关键信息表.xlsx` 存在且未被 Excel 占用；可设置 `TAHP_PROJECT_INFO_XLSX` |

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
