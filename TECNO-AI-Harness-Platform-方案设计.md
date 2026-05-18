# 传音Android底软集成部 — AI提效 Harness 系统架构评估与方案设计

> **日期**: 2026-05-18 (Updated)
> **版本**: v2.1
> **编制**: Software Architect
> **状态**: Approved
>
> **v2.1 变更**: 新增适配引擎完整设计 — 版本升级适配、Feature特性移植、运营商需求移植三大Pipeline
>
> **配套文档**:
> - [可视化架构总览](TAHP-Architecture-Overview.html) — 8幅专业架构图
> - [可视化架构总览（中文）](TAHP-Architecture-Overview-CN.html) — 8幅专业架构图（中文版）
> - [约束文件编写规范](TAHP-约束文件编写规范.md) — Owner编写约束的强制性标准
> - [AI代码生成约束规范](TAHP-AI代码生成约束规范.md) — 防幻觉、防反复修改的核心规范
> - [评估与质量门禁规范](TAHP-评估与质量门禁规范.md) — Skill质量评估与代码门禁标准
> - [版本适配约束规范](TAHP-版本适配约束规范.md) — 版本升级/特性移植/运营商移植约束标准 `NEW`

---

## 目录

1. [执行摘要](#1-执行摘要)
2. [现状评估](#2-现状评估)
3. [行业调研](#3-行业调研)
4. [Harness范式解读](#4-harness范式解读)
5. [推荐系统方案](#5-推荐系统方案)
6. [技术选型与架构设计](#6-技术选型与架构设计)
7. [适配引擎详细设计](#7-适配引擎详细设计) `NEW`
8. [系统边界与接口规范](#8-系统边界与接口规范)
9. [数据模型设计](#9-数据模型设计)
10. [安全设计](#10-安全设计)
11. [实施路线图](#11-实施路线图)
12. [风险与应对](#12-风险与应对)
13. [附录：参考资源](#13-附录参考资源)

---

## 1. 执行摘要

### 1.1 核心结论

你们部门经理提出的**Harness-based系统**方向**完全正确**，且恰逢其时。2026年业界已形成成熟的方法论 —— **Agent = Model + Harness**，其中Harness就是将状态、工具、反馈、约束和执行环境串联起来的"操作系统"。核心范式转变是：**从"人写SOP→转Skill"升级为"模块出约束→系统自动生成/调用/迭代Skill"**。

### 1.1.1 双引擎定位

TAHP 服务于部门两大核心工作场景：

| 引擎 | 场景 | 现有方案 | TAHP 优化方向 |
|------|------|---------|-------------|
| **诊断引擎** | Bug 分析 | 人工排查 + AI 辅助 | 约束驱动 + EvoSkill 自动进化 |
| **适配引擎** | 版本升级 / 特性移植 / 运营商需求移植 | **各业务自己梳理 SOP → 转 Skill → AI 按Skill执行** | 约束驱动 + Skill 自动生成/进化 + 跨版本经验复用 |

**适配引擎是当前最大的工作量来源**。每次 Android 大版本升级（A15→A16、A16→A17...），各业务模块都要独立梳理适配 SOP、转成 Skill、让 AI 工具执行。TAHP 的核心价值在于：

1. **降低 Owner 门槛**：从写完整适配 SOP 降级到写约束条件（YAML），工作量从数天降到 2-4 小时
2. **自动 Skill 生成**：系统基于约束自动生成适配 Skill，无需人工编写
3. **跨版本经验复用**：A15→A16 积累的适配规则和进化 Skill，可直接复用于 A16→A17
4. **质量统一管控**：所有适配通过统一的质量门禁（编译通过 + 回归验证），而非各模块各自为战

### 1.2 推荐方案概览

```
┌─────────────────────────────────────────────────────────┐
│                    TECNO AI Harness Platform              │
│                                                          │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌────────┐ │
│  │ 约束管理层 │→│ Skill引擎层 │→│ 执行编排层 │→│ 评估迭代 │ │
│  │          │  │           │  │           │  │        │ │
│  │ 各模块    │  │ EvoSkill  │  │ 诊断Pipeline│ │ 自动   │ │
│  │ 只需输出  │  │ + Agent   │  │ 适配Pipeline│ │ 评估   │ │
│  │ 约束条件  │  │ Skills   │  │ + MCP工具  │  │ + 进化 │ │
│  └──────────┘  └───────────┘  └──────────┘  └────────┘ │
│                                                          │
│  双引擎: 诊断引擎(Bug分析) + 适配引擎(版本/特性/运营商)    │
│  底层: Git + Claude Code/Codex CLI + 本地LLM (可选)      │
└─────────────────────────────────────────────────────────┘
```

**关键优势**：
- **零服务器成本**：纯本地运行，基于Git版本控制
- **低入门门槛**：业务模块只需写约束条件（YAML/Markdown）
- **自动Skill生成**：基于EvoSkill自动从失败案例中发现和进化Skill
- **跨模块复用**：Skill遵循AgentSkills开放标准，可跨Agent/跨模块共享
- **渐进式成熟**：可从Level 1逐步演进到Level 4

---

## 2. 现状评估

### 2.1 当前方案分析

```
当前方案流程（诊断）:

业务Owner → [梳理SOP] → [手动转Skill] → [人工测试] → [人工迭代]
     ↑                                              │
     └──────────────── 完全依赖人 ───────────────────┘

当前方案流程（适配 — 已在执行）:

业务Owner → [梳理适配SOP] → [转成Skill] → [AI工具按Skill执行适配]
     ↑                                              │
     └────── 每版本重复，经验不积累 ──────────────────┘
```

#### 优势
| 项目 | 评价 |
|------|------|
| 业务理解深 | Owner对自身模块最了解，SOP质量有保障 |
| 质量可控 | 人工审核，Skill质量相对可靠 |
| 风险低 | 不依赖额外基础设施 |
| **适配已落地** | **各业务已有"SOP→Skill→AI执行"的适配流程在跑** |

#### 核心问题

| # | 问题 | 影响 | 严重度 |
|---|------|------|--------|
| 1 | **规模化瓶颈** | 每个模块Owner都要从零开始，人力投入巨大 | 🔴 高 |
| 2 | **质量不一致** | 不同Owner对SOP的梳理深度和Skill编写能力差异大 | 🔴 高 |
| 3 | **迭代成本高** | 每次迭代都要人工更新SOP→Skill，响应慢 | 🟡 中 |
| 4 | **缺乏关联调用** | 各模块Skill孤立，无法自动协调跨模块任务 | 🟡 中 |
| 5 | **知识不可积累** | 一个Owner的经验无法有效传递给另一个模块 | 🟡 中 |
| 6 | **无量化评估** | 不知道Skill到底提升了多少效率，缺乏数据驱动 | 🟠 中高 |
| 7 | **适配经验不跨版本复用** | A15→A16积累的适配知识无法直接用于A16→A17 | 🔴 高 |
| 8 | **适配SOP重复编写** | 每次大版本升级，每个业务都要重新梳理适配SOP | 🔴 高 |

### 2.2 当前方案的Harness成熟度评估

根据业界Harness成熟度模型：

| 阶段 | 特征 | 你们当前所在位置 |
|------|------|-----------------|
| Level 0 | 直接给Agent Prompt | — |
| **Level 1** | **AGENTS.md + 基础Linter + 手动测试** | **← 你们在这里** |
| Level 2 | CI/CD集成 + 自动化测试 + 进度追踪 | 目标一 |
| Level 3 | 多Agent分工 + 分层上下文 + 持久化记忆 | 目标二 |
| Level 4 | 无人值守并行化 + 自动清理 + 自修复 | 远期愿景 |

---

## 3. 行业调研

### 3.1 标杆案例分析

#### 案例1: OpenAI — 三人团队五个月约100万行代码

| 指标 | 数值 |
|------|------|
| 团队规模 | 3名工程师（后扩至7人） |
| 代码规模 | ~100万行 |
| 手写代码 | 0行（只有设计约束） |
| 合并PR | ~1,500个 |
| 效率提升 | ~10倍 |

**关键实践（与你们直接相关）**：
- **架构约束机械化**：每个业务域定义固定分层，Linter实时检测违反，错误消息直接告诉Agent怎么改
- **知识仓库化**：把Slack、Wiki、Docs里的知识放进Git仓库，作为版本控制的制品
- **熵管理**：后台Agent定期扫描文档不一致、架构违规和冗余代码

> **对你们的启示**：你们不需要让Owner写完整SOP，只需要让Owner定义**架构约束和业务规则**（类似Linter规则），其余由系统完成。

#### 案例2: Anthropic — 16个并行Agent写C编译器

| 指标 | 数值 |
|------|------|
| 时间 | ~2周 |
| 并行Agent | 16个Claude实例 |
| 会话数 | ~2,000个 |
| 产出 | 10万行Rust代码 |
| GCC torture test | 99%通过率 |

**关键实践**：
- **角色专业化**：核心开发、去重、优化、文档各有专职Agent
- **测试子采样**：每个Agent只跑随机1-10%测试子集，保证覆盖且不卡死
- **日志设计**：全部写文件，使用grep友好的单行格式

> **对你们的启示**：Android底软涉及通信、驱动、内核等多个子系统，可以设计专业化Agent分工（如Bug分析Agent、代码适配Agent、合规检查Agent）。

#### 案例3: Stripe Minions — 每周1300+个PR的无人值守模式

| 组件 | 作用 | 与你们的关系 |
|------|------|-------------|
| Devbox | 预装环境启动~10秒 | Android编译环境可预置 |
| 编排状态机 | 确定性+Agent混合节点 | Bug分析流水线 |
| Toolshed MCP | ~500个工具按需分发 | Android工具链MCP化 |

#### 案例4: Mitchell Hashimoto — 单Agent深度参与模式

**核心方法论**（适合资源有限时起步）：
1. 放弃聊天模式，让Agent在能读文件、跑程序的环境里直接干活
2. 每件事做两次：一次自己做，一次让Agent做
3. **Agent每犯一次错，就工程化一个方案，避免同类错误**
4. 始终有Agent在后台运行

### 3.2 开源项目对比

| 项目 | Stars | 许可证 | 核心能力 | 本地部署 | 适用度 |
|------|-------|--------|---------|---------|--------|
| **EvoSkill** | 749⭐ | Apache 2.0 | 从失败案例自动发现/生成/进化Skill | ✅ 纯本地 | ⭐⭐⭐⭐⭐ |
| **Dify** | 100k+⭐ | Apache 2.0 | 可视化Agent工作流编排+RAG | ✅ Docker | ⭐⭐⭐⭐ |
| **LangGraph** | 12k+⭐ | MIT | 状态机式Agent编排 | ✅ | ⭐⭐⭐ |
| **CrewAI** | 40k+⭐ | MIT | 角色化多Agent协作 | ✅ | ⭐⭐⭐ |
| **OpenClaw** | — | — | AgentSkills兼容运行时+MCP支持 | ✅ | ⭐⭐⭐ |
| **Claude Code** | — | 商业 | Agent Skills + CLAUDE.md | ✅ | ⭐⭐⭐⭐⭐ |

### 3.3 最关键的开源发现：EvoSkill

**EvoSkill**是本次调研中发现的与你们需求**匹配度最高**的项目：

| 维度 | 说明 |
|------|------|
| **核心能力** | 从Agent执行失败中自动发现非平凡、结构化、可复用的Skill |
| **进化循环** | Base Agent → Proposer（分析失败）→ Generator（创建Skill）→ Evaluator（评估）→ Frontier（保留最优） |
| **自进化** | 可配置迭代次数，自动收敛到更强Agent配置 |
| **跨Agent兼容** | Skills兼容Claude Code、Codex CLI、OpenCode、OpenHands、Goose等 |
| **跨模型迁移** | 用固定LLM进化的Skills可将性能提升迁移到其他LLM |
| **实测提升** | OfficeQA +7.3pp，SealQA +12.1pp，零样本跨任务迁移+5.3pp |
| **使用门槛** | Python 3.12+，`pip install -e .`，纯本地运行 |

---

## 4. Harness范式解读

### 4.1 Agent = Model + Harness

2026年业界的核心公式：**模型是CPU，Harness是操作系统**。CPU再强，OS如果天天崩，体验也不会好。

### 4.2 Harness六层架构

| 层级 | 名称 | 解决什么问题 | 实施优先级 |
|------|------|-------------|-----------|
| **L1** | **信息边界层** | Agent该知道什么、不该知道什么 | **P0** ← 先做这个 |
| L2 | 工具系统层 | Agent怎么和外部世界交互 | P0 |
| L3 | 执行编排层 | 多步骤任务怎么串起来 | P1 |
| L4 | 记忆与状态层 | 长任务中间结果怎么管理 | P1 |
| L5 | 评估与观测层 | Agent怎么知道自己做对了没有 | P1 |
| **L6** | **约束、校验与恢复层** | 出错了怎么办 | **P0** ← 和L1一起先做 |

> **实施建议**：不要一上来搭建全部六层。更现实的做法是**先做L1和L6**——先让Agent知道自己该干什么（约束），再设置出错后的拦截和恢复机制。这两层投入不高，但最容易见效。

### 4.3 AGENTS.md 规范

`AGENTS.md`**不是超级System Prompt**，而是一个~100行的**目录/地图**，指向更深层的子文档：

```
AGENTS.md (~100行)
  ├── docs/constraints/     # 各模块约束条件
  ├── docs/architecture/    # 系统架构
  ├── docs/playbooks/       # 执行剧本
  ├── skills/               # 自动生成/手动维护的Skills
  └── docs/quality/         # 质量评估标准
```

**核心原则**："给Agent一张地图，不要塞一本千页手册"

### 4.4 约束驱动的Skill生成

这正是你们部门经理想要的方向：

```
传统模式: Owner → [完整SOP] → [手动Skill] → [人工迭代]
Harness模式: Owner → [约束条件] → [系统自动生成Skill] → [自动评估迭代]
                                    ↑ EvoSkill核心能力
```

**OpenAI的实践经验**：
- 为每个业务域定义固定分层，依赖方向不能反过来
- 自定义Linter实时检测违反
- 错误消息直接告诉Agent怎么改
- **核心原则**：If it cannot be enforced mechanically, agents will deviate.

### 4.5 Skill开放标准：AgentSkills协议

2026年已形成跨Agent兼容的Skill标准：

```markdown
# Skill标准结构
skill-name/
├── SKILL.md           # 唯一必需文件（YAML frontmatter + Markdown指令）
├── references/        # 深度参考文档（按需加载）
└── scripts/           # 辅助脚本（按需执行）
```

```yaml
# SKILL.md 示例
---
name: telephony-bug-analyzer
description: "分析Android telephony模块的Bug，包括通话、短信、数据连接问题的根因定位"
---

# Telephony Bug分析Skill

## 触发条件
当用户提到telephony bug、通话异常、短信失败、数据连接问题时使用。

## 执行步骤
...
```

**跨Agent兼容矩阵**：

| Agent | Skill目录 | 配置文件 |
|-------|----------|---------|
| Claude Code | `.claude/skills/` | `CLAUDE.md` |
| OpenAI Codex | `.codex/skills/` | `AGENTS.md` |
| OpenClaw | `.openclaw/skills/` | `AGENTS.md` |
| KiloCode | `.kilocode/skills/` | `AGENTS.md` |

---

## 5. 推荐系统方案

### 5.1 方案对比

| 维度 | 当前方案 | 部门经理Harness愿景 | 本报告推荐方案 |
|------|---------|-------------------|--------------|
| Skill来源 | Owner手写SOP转Skill | 系统自动生成 | **约束+自动发现双引擎** |
| 入门门槛 | 高（需写完整SOP） | 中（需写约束） | **低（YAML/Markdown约束）** |
| 迭代方式 | 人工更新 | 系统自动 | **EvoSkill自动进化循环** |
| 关联调用 | 无 | 愿景中 | **AgentSkills标准+MCP工具链** |
| 评估机制 | 无 | 未定义 | **自动评估+Frontier追踪** |
| 跨模块复用 | 无 | 愿景中 | **开放Skill仓库+跨Agent兼容** |
| 服务器需求 | 无 | 可能需要 | **零服务器，纯本地Git** |
| 预算 | 人力成本 | 未知 | **仅需LLM API调用费** |

### 5.2 推荐方案：TECNO AI Harness Platform (TAHP)

#### 核心理念

```
业务Owner只需要提供:
  1. 模块约束条件（代码规范、接口协议、测试标准）
  2. 历史Bug案例（作为评估数据集）
  3. 代码适配的输入输出对（作为评估数据集）

系统自动完成:
  1. Skill初始生成（基于约束条件）
  2. Skill自动进化（基于执行失败分析）
  3. 关联Skill调用编排（基于任务类型）
  4. Skill质量评估（基于测试集打分）
  5. Skill版本管理（基于Git分支）
```

#### 架构总览 — 双引擎架构

```
┌──────────────────────────────────────────────────────────────────┐
│                   TECNO AI Harness Platform                       │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    L1: 信息边界层                            │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │  │
│  │  │ AGENTS.md   │ │ 模块约束库  │ │ 架构边界    │            │  │
│  │  │ (全局导航)  │ │ constraints/│ │ (依赖方向)  │            │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘            │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                               ↓                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    L2: 工具系统层 (MCP)                     │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │  │
│  │  │ Android  │ │ Git      │ │ BugTracker│ │ 编译构建 │       │  │
│  │  │ 日志分析 │ │ 操作     │ │ 工具     │ │ 工具     │       │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │  │
│  │  │ AOSP     │ │ Patch    │ │ API迁移  │ │ 回归测试 │       │  │
│  │  │ Diff分析 │ │ 生成器   │ │ 规则库   │ │ 运行器   │       │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                               ↓                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    L3: 执行编排层 — 双引擎                  │  │
│  │                                                              │  │
│  │  ┌─── 诊断引擎 ───────────────────────────────────────┐     │  │
│  │  │ Bug分析Pipeline: 日志收集→根因定位→报告              │     │  │
│  │  │ 单元代码适配Pipeline: 约束检查→代码生成→验证         │     │  │
│  │  └─────────────────────────────────────────────────────┘     │  │
│  │                                                              │  │
│  │  ┌─── 适配引擎 (NEW v2.1) ────────────────────────────┐     │  │
│  │  │ 版本升级Pipeline: AOSP Diff→影响评估→策略分类→       │     │  │
│  │  │                    批量适配→编译回归                  │     │  │
│  │  │ Feature移植Pipeline: 依赖分析→兼容映射→代码转换→     │     │  │
│  │  │                     集成回归                          │     │  │
│  │  │ 运营商移植Pipeline: 需求解析→源码映射→差异生成→     │     │  │
│  │  │                     合规检查                          │     │  │
│  │  └─────────────────────────────────────────────────────┘     │  │
│  │                                                              │  │
│  │  ┌─── 共性问题处理层 ────────────────────────────────┐      │  │
│  │  │ 安全补丁 / 合规修复 — 跨模块批量同步               │      │  │
│  │  └─────────────────────────────────────────────────────┘     │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                               ↓                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │              L4+L5+L6: 记忆/评估/恢复层                     │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │  │
│  │  │ EvoSkill     │ │ 评估引擎     │ │ 失败恢复     │        │  │
│  │  │ 自动进化     │ │ (编译+回归   │ │ (重试/回滚)  │        │  │
│  │  │ 跨版本复用   │ │  + 准确率)   │ │              │        │  │
│  │  └──────────────┘ └──────────────┘ └──────────────┘        │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  ═══════════════════════════════════════════════════════════════  │
│  底层基础设施: Git仓库 + Claude Code/Codex CLI + Python 3.12+     │
│  ═══════════════════════════════════════════════════════════════  │
└──────────────────────────────────────────────────────────────────┘
```

### 5.3 核心模块详解

#### 模块1：约束管理层（Owner的唯一输入端）

业务Owner**唯一需要做的事**就是为各自模块定义约束文件。TAHP v2.1 支持以下四种 domain：

| Domain | 用途 | 对应引擎 | 产出 |
|--------|------|---------|------|
| `bug_analysis` | Bug 根因分析 | 诊断引擎 | 分析报告 |
| `code_adaptation` | 单元代码适配（Bug修复等） | 诊断引擎 | 代码 Patch |
| `version_adaptation` | 大版本升级适配 | **适配引擎** | 批量 Patch 集合 |
| `carrier_porting` | 运营商需求移植 | **适配引擎** | Carrier Patch + 配置 |

> 详细的约束文件编写规范参见：
> - [TAHP-约束文件编写规范](TAHP-约束文件编写规范.md) — bug_analysis 和 code_adaptation
> - [TAHP-版本适配约束规范](TAHP-版本适配约束规范.md) — version_adaptation 和 carrier_porting `NEW`

```yaml
# constraints/telephony-bug-analysis.yaml
module:
  name: telephony
  domain: android-bug-analysis
  owner: zhangsan
  version: "1.0"

# 信息边界 — Agent需要知道什么
context:
  codebase_paths:
    - frameworks/opt/telephony/
    - frameworks/base/telephony/
  relevant_logs:
    - /data/misc/logd/logcat  # logcat路径
    - radio_log               # RIL日志
    - atcmd_log              # AT命令日志
  key_components:
    - TelephonyFramework
    - RILJ (Radio Interface Layer Java)
    - RILC (Radio Interface Layer C)
    - ModemInterface

# 架构约束 — 不能违反什么
architectural_rules:
  - "RILJ → RILC → Modem 的调用方向不能反向"
  - "Bug分析必须先确认是Framework层还是RIL层还是Modem层"
  - "修改涉及接口变更时，必须同时更新HIDL/AIDL定义"

# 评估标准 — 怎么算做好了
evaluation:
  bug_analysis_accuracy_target: 0.85  # 85%准确率
  required_artifacts:
    - root_cause_report
    - affected_components
    - fix_suggestion
  test_dataset: eval-data/telephony-bugs/

# 质量红线 — 绝对不能出错
quality_gates:
  - "不能在不知道Modem固件版本的情况下给出RIL层Bug分析"
  - "不能在未确认复现步骤的情况下给出修复方案"
  - "涉及安全相关的Bug（如通话窃听风险）必须标记为Critical"
```

```yaml
# constraints/kernel-driver-adaptation.yaml
module:
  name: kernel-driver
  domain: android-code-adaptation
  owner: lisi
  version: "1.0"

context:
  codebase_paths:
    - kernel/drivers/
    - kernel/arch/arm64/
  build_system:
    type: make
    defconfig_paths:
      - arch/arm64/configs/vendor_defconfig
  key_tools:
    - "kernel Makefile system"
    - "Kconfig"
    - "dtc (device tree compiler)"

architectural_rules:
  - "驱动代码必须遵循Linux内核编码规范 (Documentation/process/coding-style.rst)"
  - "设备树修改不能影响其他平台配置"
  - "新增Kconfig选项必须有默认值且不影响现有配置"
  - "补丁必须能通过checkpatch.pl检查"

evaluation:
  adaptation_success_target: 0.80  # 80%成功率
  test_dataset: eval-data/kernel-adaptations/

quality_gates:
  - "不能修改与目标芯片平台无关的公共代码"
  - "不能引入编译警告"
  - "设备树变更必须通过dtbs_compile验证"
```

**Owner工作量评估**：每个模块初次编写约束文件约 **2-4小时**，后续维护约 **每次30分钟**，远低于写完整SOP的数天工作量。

#### 模块2：Skill引擎层（系统自动运行）

```
约束文件 (YAML) ──→ Skill生成器 ──→ 初始SKILL.md
                                    │
                              EvoSkill进化循环
                                    │
                    ┌───────────────┤
                    ↓               ↓
              执行失败案例    反馈历史
                    │               │
                    ↓               ↓
              Proposer分析   去重+避免重复
                    │
                    ↓
              Generator生成
              新/改进Skill
                    │
                    ↓
              Evaluator打分
                    │
                    ↓
              Frontier保留
              最优N个版本
                    │
                    ↓
              ┌─────┘
              ↓ (下一轮迭代)
```

**生成的Skill示例**（系统自动产出，非人工编写）：

```markdown
# 自动生成的Telephony Bug分析Skill
# 来源: EvoSkill进化循环第3轮
# 评估分数: 0.87 (基线: 0.62)

---
name: telephony-call-drop-analyzer
description: "分析Android通话掉话问题，包括CS掉话、VoLTE掉话的根因定位和修复建议"
---

# 通话掉话分析协议

## 前置检查（必须按顺序完成）
1. 确认Modem固件版本: `getprop gsm.version.baseband`
2. 确认网络类型: 检查logcat中的 `NetworkRegistration`
3. 收集时间线: 从logcat提取通话建立→掉话的完整事件序列

## 根因定位决策树
```
通话掉话
├── 是否为VoLTE?
│   ├── YES → 检查IMS注册状态
│   │   ├── IMS已注册 → 检查RTP/RTCP统计 → 网络质量问题
│   │   └── IMS未注册 → 检查PDN连接 → EPS Fallback问题
│   └── NO → 检查CS域信令
│       ├── 正常释放 → 对端挂机，非Bug
│       └── 异常释放 → 检查RIL日志中的错误码
└── 错误码映射表 → 参见 references/error-code-mapping.md
```

## 输出格式
必须产出以下结构化报告:
- 复现概率: [必现/概率/偶发]
- 根因层级: [Framework/RIL/Modem/Network]
- 影响范围: [单机型/系列机型/全平台]
- 修复建议: [代码修改/配置修改/固件升级/网络侧]
```

#### 模块3：执行编排层（多Agent协作）

```yaml
# playbooks/bug-analysis-pipeline.yaml
name: 跨模块Bug分析Pipeline
trigger: "当Bug涉及多个子系统时自动触发"

steps:
  - agent: coordinator
    action: "解析Bug描述，识别涉及的子系统"
    output: involved_modules

  - parallel:
      - agent: telephony-analyzer
        condition: "telephony in involved_modules"
        skill: telephony-bug-analyzer
        output: telephony_analysis

      - agent: kernel-analyzer
        condition: "kernel in involved_modules"
        skill: kernel-driver-debugger
        output: kernel_analysis

      - agent: power-analyzer
        condition: "power in involved_modules"
        skill: power-consumption-tracer
        output: power_analysis

  - agent: coordinator
    action: "汇总各模块分析结果，判断根因归属"
    input: [telephony_analysis, kernel_analysis, power_analysis]
    output: unified_root_cause_report
```

#### 模块4：评估迭代层（量化效果）

```python
# 自动评估流程（EvoSkill内置）
# 1. 从eval-data/加载测试集
# 2. 在测试集上运行当前最优程序
# 3. 收集失败案例
# 4. 启动进化循环
# 5. 在验证集上评估新Skill
# 6. 保留Frontier中最优的N个版本

# evolution配置
[evolution]
mode = "skill_only"
iterations = 20
frontier_size = 3
concurrency = 4
no_improvement_limit = 5
```

---

## 6. 技术选型与架构设计

### 6.1 技术栈选择

| 层级 | 技术选型 | 选择理由 | 成本 |
|------|---------|---------|------|
| **Skill进化引擎** | **EvoSkill** | 唯一实现从失败中自动发现Skill的开源方案，Apache 2.0 | 免费 |
| **Agent运行时** | **Claude Code** (主力) + Codex CLI (备选) | 成熟度最高，EvoSkill原生支持，AgentSkills标准兼容 | API调用费 |
| **工具协议** | **MCP (Model Context Protocol)** | 2026年事实标准，工具接入标准化 | 免费 |
| **工作流编排** | **LangGraph** (轻量) 或 Python脚本 (起步) | 灵活的DAG编排，本地运行 | 免费 |
| **版本管理** | **Git** | EvoSkill原生用Git分支管理Skill版本，天然支持 | 免费 |
| **知识管理** | **Markdown + YAML + Git** | AGENTS.md标准，渐进式披露 | 免费 |
| **可选: 可视化** | **Dify** (Docker本地) | 后期如需非技术人员参与，可加Dify做可视化 | 免费 |
| **可选: 本地LLM** | **Ollama + Qwen2.5-Coder** | 降低API成本，离线可用 | 免费(GPU已有) |

### 6.2 仓库结构设计

```
tecno-ai-harness/
├── AGENTS.md                          # 全局导航（~100行）
├── CLAUDE.md                          # Claude Code配置
│
├── constraints/                       # 业务约束（Owner唯一输入端）
│   ├── telephony/
│   │   ├── bug-analysis.yaml         # 通信Bug分析约束
│   │   ├── code-adaptation.yaml      # 通信代码适配约束（Bug修复级）
│   │   ├── version-adaptation.yaml   # 通信版本升级适配约束 `NEW`
│   │   ├── carrier-porting.yaml      # 通信运营商需求移植约束 `NEW`
│   │   └── eval-data/                # 评估测试集
│   ├── kernel-driver/
│   │   ├── bug-analysis.yaml
│   │   ├── code-adaptation.yaml
│   │   ├── version-adaptation.yaml   # `NEW`
│   │   └── eval-data/
│   ├── power/
│   │   ├── bug-analysis.yaml
│   │   ├── version-adaptation.yaml   # `NEW`
│   │   └── eval-data/
│   └── shared/
│       ├── coding-standards.yaml     # 共享编码规范
│       ├── android-platform.yaml     # Android平台通用约束
│       └── api-migration-rules/      # API迁移规则库（可跨版本复用）`NEW`
│           ├── telephony-migration.yaml
│           ├── framework-migration.yaml
│           └── hal-migration.yaml
│
├── skills/                            # 自动生成的Skills（EvoSkill产出）
│   ├── .claude/skills/               # Claude Code格式
│   │   ├── telephony-call-drop/      # 自动发现的Skill
│   │   │   ├── SKILL.md
│   │   │   └── references/
│   │   ├── kernel-panic-trace/
│   │   │   ├── SKILL.md
│   │   │   └── references/
│   │   ├── power-leak-detect/
│   │   │   └── SKILL.md
│   │   ├── telephony-version-adapter/    # 版本适配Skill `NEW`
│   │   │   ├── SKILL.md
│   │   │   └── references/
│   │   └── carrier-porting-assistant/    # 运营商移植Skill `NEW`
│   │       ├── SKILL.md
│   │       └── references/
│   └── .codex/skills/                # Codex格式（自动同步）
│
├── playbooks/                         # 执行编排剧本
│   ├── bug-analysis-pipeline.yaml    # Bug分析流水线
│   ├── code-adaptation-pipeline.yaml # 代码适配流水线
│   ├── version-upgrade-pipeline.yaml # 版本升级适配流水线 `NEW`
│   ├── feature-porting-pipeline.yaml # Feature特性移植流水线 `NEW`
│   ├── carrier-porting-pipeline.yaml # 运营商需求移植流水线 `NEW`
│   └── cross-module-pipeline.yaml    # 跨模块协作流水线
│
├── tools/                             # MCP工具定义
│   ├── android-log-analyzer/         # Android日志分析工具
│   ├── git-operations/               # Git操作工具
│   ├── build-system/                 # 编译构建工具
│   ├── aosp-diff-analyzer/           # AOSP版本差异分析 `NEW`
│   ├── patch-generator/              # 适配Patch批量生成 `NEW`
│   ├── api-migration-db/             # API迁移规则管理 `NEW`
│   ├── regression-test-runner/       # 回归测试运行 `NEW`
│   └── code-review-checker/          # 代码审查规则检查
│
├── docs/                              # 深度文档（渐进式披露）
│   ├── architecture/
│   │   └── system-overview.md
│   ├── design/
│   │   └── constraint-specification-guide.md
│   └── quality/
│       └── evaluation-metrics.md
│
├── scripts/                           # 自动化脚本
│   ├── init-module.sh                # 模块初始化脚本
│   ├── run-evolution.sh              # 启动进化循环
│   ├── sync-skills.sh                # 跨Agent同步Skills
│   ├── run-version-adaptation.sh     # 执行版本升级适配 `NEW`
│   └── run-carrier-porting.sh        # 执行运营商移植 `NEW`
│
├── .claude/
│   ├── program.yaml                  # EvoSkill程序配置
│   └── feedback_history.md           # 进化反馈历史
│
├── .evoskill/
│   ├── config.toml                   # EvoSkill配置
│   └── task.md                       # 任务描述
│
└── reports/                           # 评估报告输出
    ├── evolution-reports/
    └── quality-metrics/
```

### 6.3 关键工作流

#### 工作流1：新模块接入（Owner视角）

```
Step 1: 复制模板
  $ cp -r templates/module-template/ constraints/my-module/

Step 2: 填写约束文件（~2-4小时）
  - 编辑 constraints/my-module/bug-analysis.yaml
  - 编辑 constraints/my-module/code-adaptation.yaml
  - 编辑 constraints/my-module/version-adaptation.yaml    # v2.1 新增
  - 编辑 constraints/my-module/carrier-porting.yaml       # v2.1 新增（如需）
  - 准备5-10个历史Bug案例放入 eval-data/
  - 准备上一次版本升级的适配记录放入 eval-data/           # v2.1 新增

Step 3: 提交到Git
  $ git add constraints/my-module/
  $ git commit -m "Add my-module constraints"

Step 4: 系统自动完成（无需Owner参与）
  - Skill生成器读取约束 → 生成初始SKILL.md（含诊断+适配两类）
  - EvoSkill在测试集上运行 → 收集失败案例
  - 自动启动进化循环 → 迭代优化Skill
  - 评估通过后 → 加入共享Skill仓库

Done! Owner的工作到此结束。
```

#### 工作流2：Bug分析（开发者视角）

```
开发者: "帮我分析这个通话掉话Bug: [logcat日志+复现步骤]"

系统自动:
  1. 加载 telephony-bug-analyzer Skill
  2. 读取logcat日志 → 提取关键事件
  3. 按决策树进行根因定位
  4. 如果涉及kernel → 自动加载 kernel-debugger Skill
  5. 产出结构化分析报告
  6. 记录执行轨迹 → 反馈给EvoSkill

EvoSkill自动（后台）:
  - 如果这次分析出错 → 分析失败原因
  - 生成改进的Skill变体
  - 评估后更新Skill库
```

#### 工作流3：版本升级适配（TL/开发者视角）`NEW`

```
场景: Android 16 发布，通信模块需要从 A15 适配到 A16

当前做法（各业务自己干）:
  通信Owner → [梳理 A15→A16 适配SOP] → [转成Skill] → [AI按Skill执行]
  驱动Owner → [梳理 A15→A16 适配SOP] → [转成Skill] → [AI按Skill执行]
  功耗Owner → [梳理 A15→A16 适配SOP] → [转成Skill] → [AI按Skill执行]
  ...每个模块重复上述流程，每次大版本都要重来

TAHP 优化后:
  通信Owner → [更新 version-adaptation.yaml 约束（~1小时）]
  系统自动:
    1. aosp-diff-analyzer 分析 A15→A16 framework 差异
    2. code-impact-scanner 定位受影响的定制代码点
    3. 匹配 api-migration-rules 中的已知迁移模式
    4. 适配策略分类: 全自动(~60%) / 半自动(~30%) / 人工(~10%)
    5. patch-generator 对全自动项批量生成 patch
    6. build-verifier 编译验证
    7. regression-test-runner 回归测试
    8. 输出适配报告: 完成/待审核/人工处理 清单

  EvoSkill 进化（跨版本复用）:
    - 本次适配经验 → 更新 api-migration-rules
    - 进化的 Skill → 下次 A16→A17 直接复用
    - 新发现的适配模式 → 同步到其他模块
```

### 6.4 MCP工具链设计

针对Android底软场景，建议优先实现以下MCP工具：

#### 诊断引擎工具

| 工具名 | 功能 | 优先级 |
|--------|------|--------|
| `android-log-parser` | 解析logcat/ril/atcmd日志 | P0 |
| `bugzilla-query` | 查询BugTracker | P0 |
| `git-blame-analyzer` | 代码变更历史分析 | P0 |
| `kernel-config-checker` | 检查内核配置合规性 | P1 |
| `device-tree-validator` | 设备树校验 | P1 |
| `power-profile-analyzer` | 功耗数据解析 | P1 |

#### 适配引擎工具（v2.1 新增）

| 工具名 | 功能 | 优先级 |
|--------|------|--------|
| `aosp-diff-analyzer` | 对比两个 Android 版本的 framework diff，提取 API/接口/行为变更清单 | **P0** |
| `code-impact-scanner` | 扫描定制代码，定位受 AOSP 变更影响的代码点 | **P0** |
| `patch-generator` | 根据适配规则和迁移表批量生成代码 patch | **P0** |
| `build-verifier` | 触发编译验证，检查 patch 集合能否编译通过 | **P0** |
| `api-migration-db` | 管理 API 迁移规则库（增删改查），支持跨版本积累 | **P1** |
| `regression-test-runner` | 运行冒烟测试 + 功能回归测试 | **P1** |
| `carrier-config-manager` | 管理运营商配置差异和 carrier overlay | **P2** |

#### 通用工具

| 工具名 | 功能 | 优先级 |
|--------|------|--------|
| `android-build-helper` | 编译构建辅助 | P2 |
| `code-review-checker` | 代码审查规则检查 | P2 |

---

## 7. 适配引擎详细设计

### 7.1 设计背景：现有适配流程与优化方向

#### 7.1.1 现有适配流程（已验证可行）

部门内各业务模块当前已建立了适配工作流：

```
现有流程:
  Android N 发布
       ↓
  各业务 Owner 各自梳理适配 SOP（3-7天/模块）
       ↓
  将 SOP 转换为 Skill
       ↓
  AI 工具根据 Skill 执行代码适配
       ↓
  人工验证编译 + 回归
```

**这套流程已经在跑了，关键问题在于：**

| 痛点 | 具体表现 |
|------|---------|
| SOP 编写成本高 | 每个模块每次大版本都要从零梳理，3-7天/模块 |
| 经验不跨版本复用 | A15→A16 梳理的 SOP，A16→A17 基本要从头来 |
| 经验不跨模块共享 | 通信模块踩过的坑，驱动模块可能再踩一遍 |
| SOP→Skill 转换依赖人 | Owner 的 Skill 编写能力参差不齐 |
| 适配质量评估缺失 | 不知道全自动/半自动/人工各占多少比例 |

#### 7.1.2 TAHP 优化后的适配流程

```
TAHP 优化后:
  Android N+1 发布
       ↓
  各业务 Owner 更新约束文件（1-2小时/模块）
  - 更新 api-migration-rules（如有新发现的迁移模式）
  - 更新 version-adaptation.yaml（源/目标版本）
  - 补充 eval-data（上一次适配的案例）
       ↓
  系统自动:
    1. AOSP Diff 分析 → 提取变更清单
    2. 影响面评估 → 定位受影响代码
    3. 匹配迁移规则 → 分类适配策略
    4. 批量生成 Patch → 全自动项直接完成
    5. 编译验证 → 门禁硬性要求
    6. 回归测试 → 冒烟+核心功能
    7. 输出适配报告
       ↓
  EvoSkill 进化:
    - 适配经验 → 更新 api-migration-rules
    - 失败案例 → 进化适配 Skill
    - 新模式 → 同步到其他模块
    - 下次 A(N+1)→A(N+2) 直接复用
```

**核心改进**：Owner 从"写完整 SOP"降级到"更新约束条件"，系统自动完成 SOP→Skill→执行→进化的全链路。

### 7.2 适配场景分类

TAHP 适配引擎覆盖以下四大场景：

| 场景 | 触发时机 | 特点 | 典型工作量 |
|------|---------|------|-----------|
| **大版本升级适配** | Android N → N+1 发布 | 批量、可预测、有 AOSP Diff 参考 | 持续 2-3 个月，涉及所有模块 |
| **Feature 特性移植** | 自研 Feature 迁移到新平台/新版本 | 依赖链长、需兼容性映射 | 单 Feature 1-2 周 |
| **运营商需求移植** | 运营商定制需求跨项目迁移 | 需求文档→代码映射、合规检查 | 单运营商 3-5 天 |
| **共性问题处理** | 安全补丁、合规修复 | 跨模块同步、模式统一 | 单补丁 1-2 天 |

### 7.3 Pipeline 1：版本升级适配

#### 7.3.1 详细流程

```yaml
# playbooks/version-upgrade-pipeline.yaml
name: 版本升级适配 Pipeline
trigger: "新 Android 版本发布 / Owner 更新 version-adaptation.yaml"

steps:
  - id: diff-analysis
    agent: adaptation-coordinator
    tool: aosp-diff-analyzer
    action: |
      对比 source_version 和 target_version 的 AOSP framework 差异
      输出: 变更清单（API变更/接口变更/行为变更/废弃API）
    output: aosp_change_list

  - id: impact-assessment
    agent: adaptation-coordinator
    tool: code-impact-scanner
    action: |
      将 AOSP 变更清单与定制代码交叉比对
      输出: 受影响代码文件清单 + 影响类型标注
    input: [aosp_change_list, module_constraints]
    output: impact_report

  - id: strategy-classification
    agent: adaptation-coordinator
    action: |
      对每个受影响代码点进行适配策略分类:
      - 全自动(auto): 已知迁移模式 + 置信度>95%
      - 半自动(semi-auto): AI生成patch + 人工审核
      - 人工(manual): 新场景 / 低置信度
    input: [impact_report, api_migration_rules]
    output: adaptation_plan

  - id: batch-adaptation
    parallel:
      - id: auto-adapt
        agent: code-adapter
        condition: "strategy == 'auto'"
        tool: patch-generator
        action: "根据迁移规则自动生成 patch"
        output: auto_patches

      - id: semi-auto-adapt
        agent: code-adapter
        condition: "strategy == 'semi-auto'"
        tool: patch-generator
        action: "AI生成 patch（标记为待审核）"
        output: review_patches

      - id: manual-queue
        agent: coordinator
        condition: "strategy == 'manual'"
        action: "生成交付给Owner的适配任务清单"
        output: manual_tasks

  - id: build-verification
    agent: build-verifier
    tool: build-verifier
    action: |
      对 auto_patches 执行编译验证
      对 review_patches 执行编译验证（编译通过后才提交人工审核）
    input: [auto_patches, review_patches]
    output: build_results

  - id: regression-test
    agent: test-runner
    tool: regression-test-runner
    action: |
      编译通过的 patch 运行冒烟测试 + 功能回归
    input: [build_results.passed]
    output: regression_results

  - id: report-generation
    agent: coordinator
    action: |
      生成适配报告:
      - 全自动完成: N 项
      - 待人工审核: N 项（附带 patch diff）
      - 需人工处理: N 项（附带原因和参考）
      - 编译/回归失败: N 项（附带错误日志）
    output: adaptation_report
```

#### 7.3.2 适配策略分类标准

| 策略 | 判定条件 | 处理方式 | 审核要求 |
|------|---------|---------|---------|
| 🟢 全自动 | 已知迁移模式 + API 迁移规则匹配 + 置信度 > 95% | 直接生成 patch → 编译 → 回归 | 系统自动审核 |
| 🟡 半自动 | 部分匹配迁移规则 / 置信度 70-95% / 涉及多文件联动 | AI 生成 patch → 编译 → **人工审核** → 回归 | Owner 审核通过 |
| 🔴 人工 | 全新 API / 无匹配规则 / 置信度 < 70% / 涉及架构变更 | 生成适配任务清单 + 参考建议 | Owner 手动适配 |

#### 7.3.3 版本升级约束文件示例

```yaml
# constraints/telephony/version-adaptation.yaml
module:
  name: telephony
  domain: version-adaptation
  owner: zhangsan
  version: "1.0"

source_version: "android-15.0.0_r1"
target_version: "android-16.0.0_r1"

# 信息边界
context:
  codebase_paths:
    - frameworks/opt/telephony/
    - frameworks/base/telephony/
    - packages/services/Telephony/
  build_targets:
    - TeleService
    - TelephonyProvider
  test_targets:
    - android.telephony.cts
    - com.android.phone.tests

# API 迁移规则（可逐步积累，跨版本复用）
api_migration_rules:
  - old_api: "TelephonyManager.getDataNetworkType()"
    new_api: "TelephonyManager.getServiceState().getDataNetworkType()"
    change_type: "method_signature"
    auto: true
    confidence: 0.98
    note: "Android 16 将 getDataNetworkType() 标记为 @Deprecated"

  - old_api: "PhoneFactory.getPhones()"
    new_api: "PhoneFactory.getPhoneList()"
    change_type: "method_rename"
    auto: true
    confidence: 0.92
    note: "返回类型从 Phone[] 改为 List<Phone>"

  - old_api: "IccCardConstants.INTENT_VALUE_ICC_ABSENT"
    new_api: "TelephonyManager.SIM_STATE_ABSENT"
    change_type: "constant_moved"
    auto: false
    confidence: 0.75
    note: "常量从 IccCardConstants 迁移到 TelephonyManager，需要检查上下文"

# 适配约束（红线）
adaptation_constraints:
  - "不能因为适配而删除传音自研的业务逻辑"
  - "新增的 Android 16 API 调用必须有 @RequiresApi(16) 注解"
  - "HIDL/AIDL 接口变更必须同步更新接口定义和实现"
  - "废弃 API 的迁移必须检查所有调用点，不能遗漏"
  - "不能引入新的编译警告"

# 验收标准
acceptance_criteria:
  compile_pass: true                    # 必须100%编译通过
  smoke_test_targets:                   # 冒烟测试目标
    - call_functional_smoke
    - sms_functional_smoke
    - data_connection_smoke
  regression_targets:                   # 功能回归目标
    - call_functional_test
    - sms_functional_test
    - data_connection_test
    - sim_hot_swap_test
  regression_pass_rate: 0.95            # 回归通过率 ≥ 95%

# 评估数据集（上一次适配记录）
eval_dataset: eval-data/telephony-a15-to-a16/
```

### 7.4 Pipeline 2：Feature 特性移植

#### 7.4.1 适用场景

- 传音自研 Feature（双卡定制、VoWiFi 增强、来电归属地等）迁移到新版本
- Feature 从一个芯片平台迁移到另一个芯片平台
- Feature 从 A 项目移植到 B 项目

#### 7.4.2 流程

```yaml
# playbooks/feature-porting-pipeline.yaml
name: Feature 特性移植 Pipeline
trigger: "Owner 提交 Feature 移植需求"

steps:
  - id: dependency-analysis
    agent: feature-analyzer
    action: |
      分析 Feature 源码，提取依赖链:
      - API 依赖（调用了哪些 framework API）
      - HAL 依赖（依赖哪些 HAL 接口）
      - 资源依赖（layout/string/drawable）
      - 进程间依赖（ContentProvider/Broadcast/AIDL Service）
    output: dependency_graph

  - id: compatibility-mapping
    agent: feature-analyzer
    action: |
      将依赖链与目标版本/平台进行兼容性检查:
      - API 兼容: 直接复用
      - API 变更: 需要 migration
      - API 移除: 需要替代方案
      - HAL 变更: 需要适配层
    input: [dependency_graph, api_migration_rules]
    output: compatibility_report

  - id: code-transformation
    agent: code-adapter
    tool: patch-generator
    action: |
      根据兼容性报告自动执行代码转换:
      - API 调用替换
      - Import 语句更新
      - Manifest 声明更新
      - 资源文件调整
    input: [compatibility_report]
    output: porting_patches

  - id: integration-test
    agent: test-runner
    tool: regression-test-runner
    action: |
      编译验证 + Feature 功能测试 + 回归测试
    input: [porting_patches]
    output: test_results
```

### 7.5 Pipeline 3：运营商需求移植

#### 7.5.1 适用场景

- Airtel / Vodafone / MTN 等运营商定制需求从一个项目移植到另一个项目
- 运营商更新需求（新版 RFI）的增量适配
- Generic 项目增加运营商 Flavor

#### 7.5.2 约束文件示例

```yaml
# constraints/telephony/carrier-porting.yaml
module:
  name: telephony
  domain: carrier-porting
  owner: zhangsan
  version: "1.0"

source_project: "generic"
target_carrier: "airtel-india"

# 运营商定制需求清单
carrier_specifics:
  - requirement: "VoWiFi 预置支持"
    code_paths:
      - frameworks/opt/telephony/src/java/com/mediatek/ims/vowifi/
    config_changes:
      - "carrier_config_airtel.xml"
    auto: true
    confidence: 0.90

  - requirement: "Airtel 分钟提醒"
    code_paths:
      - packages/services/Telephony/src/com/android/phone/callsettings/
    config_changes:
      - "call_feature_airtel.xml"
    auto: true
    confidence: 0.85

  - requirement: "Airtel USSD 定制"
    code_paths:
      - frameworks/base/telephony/java/android/telephony/USSD.java
    auto: false
    confidence: 0.60
    note: "涉及 Modem AT 命令定制，需要确认芯片平台差异"

# 合规标准
compliance_standards:
  - "GCF CCv3"
  - "Airtel India RFI requirements v3.2"

# 适配约束
adaptation_constraints:
  - "运营商定制不能影响 generic 基础功能"
  - "Carrier overlay 必须通过 Android 标准机制（CarrierConfigManager）"
  - "网络配置变更必须通过 AT 命令验证"
  - "不能硬编码运营商参数，必须通过 carrier_config 管理"

# 验收标准
acceptance_criteria:
  compile_pass: true
  carrier_certification:
    - "GCF 基础认证测试通过"
    - "Airtel RFI 需求项全覆盖"
  regression_targets:
    - generic_functional_test      # 确保 generic 不受影响
    - airtel_specific_test         # 运营商定制功能测试
```

### 7.6 API 迁移规则库（跨版本复用的核心）

API 迁移规则库是适配引擎**跨版本复用的核心资产**。每次版本升级积累的迁移规则，直接复用于下一次升级。

#### 存储结构

```
constraints/shared/api-migration-rules/
├── telephony-migration.yaml        # 通信模块迁移规则
├── framework-migration.yaml        # Framework 层迁移规则
├── hal-migration.yaml              # HAL 层迁移规则
├── kernel-migration.yaml           # 内核接口迁移规则
└── media-migration.yaml            # 多媒体迁移规则
```

#### 规则积累机制

```
版本升级适配过程中:
  1. aosp-diff-analyzer 提取变更清单
  2. code-impact-scanner 定位受影响代码
  3. 人工/半自动适配完成后 → 提取成功的适配模式
  4. 写入 api-migration-rules/（含置信度和适用版本范围）
  5. 下次升级时 → 规则库直接复用，全自动比例逐步提升

预期效果:
  A15→A16: 全自动 40%, 半自动 40%, 人工 20%（首次）
  A16→A17: 全自动 60%, 半自动 30%, 人工 10%（积累一次后）
  A17→A18: 全自动 75%, 半自动 20%, 人工 5%（积累两次后）
```

### 7.7 适配引擎评估指标

| 指标 | 目标 | 度量方式 |
|------|------|---------|
| 全自动适配率 | ≥ 60%（首次），逐步提升到 ≥ 75% | 全自动适配项数 / 总适配项数 |
| 半自动适配率 | ~ 30% | 半自动适配项数 / 总适配项数 |
| 人工适配率 | ≤ 10% | 人工适配项数 / 总适配项数 |
| 编译通过率 | 100% | P0 门禁，编译不通过直接 BLOCK |
| 回归通过率 | ≥ 95% | 冒烟+核心功能回归通过数 / 总回归数 |
| Owner 工作量 | 从 3-7 天/模块降到 1-2 小时/模块 | Owner 实际投入时间 |
| 适配周期缩短 | ≥ 50% | 对比纯人工适配周期 |

---

## 8. 系统边界与接口规范

### 8.1 系统边界定义

> 详细的架构图参见 [TAHP-Architecture-Overview.html](TAHP-Architecture-Overview.html)

#### 系统内部（TAHP管理）

| 组件 | 职责 | 管理方式 |
|------|------|---------|
| 约束文件 (constraints/) | 模块规则定义 | Owner编写 + Git版本控制 |
| Skill仓库 (skills/) | 自动生成的Agent能力 | EvoSkill产出 + Git版本控制 |
| MCP工具链 (tools/) | 标准化工具接口 | 工程师开发 + 测试验证 |
| 评估引擎 (scripts/) | 质量评估与门禁 | 自动化脚本 + CI集成 |
| 执行剧本 (playbooks/) | 多Agent编排 | YAML定义 + 运行时调度 |

#### 系统外部（TAHP依赖但不管理）

| 外部系统 | 依赖关系 | 接口方式 |
|---------|---------|---------|
| Android代码仓库 | 读取代码、分析结构 | Git clone / Git blame |
| Claude Code / Codex CLI | Agent运行时 | CLI调用 + Skill加载 |
| BugTracker (JIRA/Bugzilla) | 获取Bug信息、更新状态 | REST API |
| Modem/芯片厂商工具 | 固件分析、日志解码 | MCP工具封装 |
| Android编译系统 | 编译验证 | Shell命令调用 |

### 7.2 接口规范

#### 8.2.1 Owner → TAHP 接口

**唯一输入接口**: YAML约束文件

```
输入: constraints/{module}/{domain}.yaml
验证: scripts/validate-constraints.py --module {module}
反馈: 约束文件质量评分（完整性/可验证性/具体性/最小性/评估集质量）
```

#### 8.2.2 TAHP → AI Agent 接口

```
加载: AGENTS.md → 引导Agent读取约束文件和Skills
约束注入: 约束文件内容作为System Prompt的一部分
Scope控制: 通过L1信息边界层控制Agent的可访问范围
工具分发: 通过MCP协议按需分发工具
```

#### 8.2.3 AI Agent → TAHP 接口

```
产出格式: 遵循 TAHP-AI代码生成约束规范 第5节定义的输出格式
质量门禁: 所有代码修改必须通过 P0/P1/P2 三级门禁
反馈记录: 执行轨迹记录到 feedback_history.md，供EvoSkill分析
```

#### 8.2.4 TAHP → 开发者 接口

```
分析报告: 结构化Markdown，包含完整证据链和修复建议
代码修改: Git patch格式，附带门禁检查结果
交互方式: Claude Code CLI交互 / 预生成的报告文件
```

### 8.3 MCP工具接口标准

所有MCP工具必须实现以下标准接口：

```typescript
interface MCPTool {
  name: string;                    // 工具唯一标识
  description: string;             // 功能描述
  inputSchema: JSONSchema;         // 输入参数定义
  handler: (params) => Promise<{   // 处理函数
    success: boolean;
    data: any;
    error?: string;
    metadata?: {
      execution_time_ms: number;
      cache_hit?: boolean;
    }
  }>;
  validate?: (params) => string[];  // 前置验证（返回错误列表）
}
```

---

## 9. 数据模型设计

### 9.1 核心数据实体

#### 约束文件 (Constraint)

```
Constraint
├── id: string (module/domain 格式)
├── module: Module
├── domain: enum [bug_analysis, code_adaptation, test_generation, version_adaptation, carrier_porting]
├── version: semver
├── content: YAML
├── preconditions: Precondition[]     // 前置条件列表
├── rules: AnalysisRule[]             // 分析/修改规则
├── quality_gates: QualityGate[]      // 质量门禁
├── eval_dataset: TestCase[]          // 评估数据集
├── created_at: datetime
├── updated_at: datetime
└── author: string
```

#### Skill (技能)

```
Skill
├── id: string (kebab-case)
├── name: string
├── description: string
├── module: string (关联的模块)
├── source: enum [manual, evoskill_generated, hybrid]
├── version: semver
├── content: SKILL.md (Markdown)
├── references: Reference[]           // 深度参考文档
├── scripts: Script[]                 // 辅助脚本
├── metrics: SkillMetrics            // 质量指标
├── frontier_rank: int               // Frontier排名（0=不在Frontier）
├── evolution_history: Evolution[]    // 进化历史
├── status: enum [active, archived, experimental]
└── compatible_agents: string[]      // 兼容的Agent列表
```

#### 评估记录 (Evaluation)

```
Evaluation
├── id: string (uuid)
├── skill_id: string
├── test_case_ids: string[]
├── scores: {
│   accuracy: float,
│   completeness: float,
│   consistency: float,
│   efficiency: float,
│   explainability: float,
│   total: float
│ }
├── gate_result: enum [PASS, WARNING, FAIL]
├── failures: FailureAnalysis[]       // 失败案例详情
├── timestamp: datetime
└── evolution_iteration: int          // 进化轮次（如果是EvoSkill产生的）
```

### 9.2 数据流转图

```
[Owner] ──YAML约束──→ [Constraint Store] ──→ [Skill Generator]
                                                  │
                                            [EvoSkill Engine]
                                                  │
                                            [Skill Store] ──→ [Agent Runtime]
                                                  │                        │
                                                  │                   [Bug Analysis]
                                                  │                   [Code Adaptation]
                                                  │                        │
                                                  ↓                        ↓
                                            [Evaluation Engine] ←── [Feedback Logger]
                                                  │
                                            [Metrics Store]
                                                  │
                                                  ↓
                                            [Quality Dashboard]
```

### 9.3 存储方案

| 数据类型 | 存储方式 | 版本管理 | 备份 |
|---------|---------|---------|------|
| 约束文件 | Git (YAML) | Git branch + tag | Git remote |
| Skills | Git (Markdown) | Git branch + tag | Git remote |
| 评估结果 | JSON文件 | Git (按日期归档) | Git remote |
| 执行日志 | Markdown | Git (按日期归档) | Git remote |
| 进化历史 | TOML (EvoSkill原生) | EvoSkill内部管理 | Git同步 |

> 所有数据均为**纯文件存储**，无数据库依赖。Git既是版本管理工具，也是备份和协作工具。

---

## 10. 安全设计

### 10.1 威胁模型

| 威胁 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| AI生成恶意代码 | 低 | 极高 | Scope限制 + 安全红线 + 代码门禁 + 人工审核 |
| API Key泄露 | 中 | 高 | 环境变量存储 + 不写入Git + 定期轮换 |
| 约束文件被恶意篡改 | 低 | 高 | Git签名 + Owner审核 + 变更通知 |
| 敏感日志泄露 | 中 | 中 | 脱敏规则 + 访问控制 + 日志保留策略 |
| LLM Prompt注入 | 中 | 中 | 输入校验 + 系统Prompt隔离 |

### 10.2 安全架构

#### 10.2.1 Scope隔离（L1信息边界）

```
安全原则: 最小权限原则（Principle of Least Privilege）

Agent只能访问:
  ✓ scope.includes 中定义的代码路径
  ✓ MCP工具明确授权的操作
  ✓ 约束文件中列出的日志路径

Agent不能访问:
  ✗ scope.excludes 中的任何文件
  ✗ 系统级配置和密钥
  ✗ 其他模块的约束文件（除非有明确依赖）
  ✗ 用户的个人信息和凭证
```

#### 10.2.2 代码安全门禁

```
安全红线检查（P0级，任一失败即BLOCK）:

1. 权限检查
   - 不允许新增危险权限申请（SYSTEM_APP、WRITE_SECURE_SETTINGS等）
   - 不允许降低已有权限检查标准

2. 数据安全
   - 不允许硬编码密钥、Token、证书
   - 不允许明文存储敏感数据
   - 不允许绕过加密/签名验证

3. 通信安全
   - 不允许使用不安全的协议（HTTP替代HTTPS）
   - 不允许禁用SSL证书验证

4. 代码注入
   - 不允许使用Runtime.exec()执行未验证的命令
   - 不允许动态加载未签名的DEX/SO文件
```

#### 10.2.3 敏感信息处理

```
日志脱敏规则:
  - IMEI → 替换为 "IMEI:***"
  - 手机号 → 替换为 "PHONE:***"
  - ICCID → 替换为 "ICCID:***"
  - 位置信息 → 替换为 "LOCATION:[模糊化]"

日志保留策略:
  - 分析用日志: 任务完成后自动清除
  - 评估用日志: 存储在eval-data/，需Owner审核
  - 进化用日志: 匿名化后存储，不关联设备信息
```

### 10.3 访问控制

| 角色 | 权限 | 说明 |
|------|------|------|
| **Owner** | 编写约束、审核Skill、查看评估报告 | 模块负责人 |
| **开发者** | 使用Skill进行分析、提交反馈 | 日常使用者 |
| **TL** | 所有Owner权限 + 管理模块、审批变更 | 团队负责人 |
| **系统管理员** | 配置CI/CD、管理MCP工具、系统维护 | 运维角色 |
| **AI Agent** | 只读代码、按约束修改代码、生成报告 | 受约束执行 |

---

## 11. 实施路线图

### 11.1 分阶段实施（10周MVP → 持续演进）`UPDATED`

```
Phase 0: 基础搭建 (第1-2周)
├── 搭建Git仓库和目录结构
├── 安装Claude Code + EvoSkill
├── 编写AGENTS.md全局导航
├── 设计约束文件模板（含4种domain）
├── 选择1-2个试点模块（建议: telephony）
└── 设计API迁移规则库初始结构

Phase 1: 诊断引擎MVP (第3-4周)
├── 试点模块Owner填写 bug-analysis + code-adaptation 约束
├── 基于约束生成初始诊断 Skills
├── 准备评估测试集（每个模块5-10个案例）
├── 手动验证Skill效果
└── 建立效果度量基线

Phase 2: 适配引擎MVP (第5-6周) — v2.1 重点
├── 试点模块Owner填写 version-adaptation 约束
├── 实现 aosp-diff-analyzer MCP工具
├── 实现 code-impact-scanner MCP工具
├── 实现 patch-generator MCP工具
├── 建立 API 迁移规则库初始数据
├── 用上一次版本升级数据做回溯验证
└── 量化适配效果（全自动率/编译通过率/回归通过率）

Phase 3: 自动进化 + 规模化 (第7-8周)
├── 启动EvoSkill进化循环（诊断+适配双引擎）
├── 实现 build-verifier + regression-test-runner
├── 总结试点经验，完善模板
├── 向 power/kernel-driver 等模块推广
├── 建立跨模块 Skill 共享机制
└── 编写部门级使用文档

Phase 4: 持续优化 (第9周+)
├── 定期Skill质量评审
├── 每次版本升级后更新API迁移规则库
├── 量化全自动适配率提升曲线
├── 探索本地LLM降低API成本
├── 建立Skill贡献和评分机制
└── 对标业界Level 3-4成熟度
```

### 11.2 关键里程碑

| 里程碑 | 时间 | 标准 | 成功标志 |
|--------|------|------|---------|
| M0: 基础就绪 | 第2周末 | 仓库结构完整，工具安装完毕 | `evoskill init` 成功运行 |
| M1: 诊断MVP | 第4周末 | 试点模块 Bug 分析约束完成 | 初始 Skill 能正确分析测试集 |
| M2: 适配MVP | 第6周末 | 试点模块版本适配约束完成 + 核心 MCP 工具就绪 | 用历史数据回溯验证，全自动率 ≥ 40% |
| M3: 双引擎进化 | 第8周末 | EvoSkill 双引擎进化循环稳定 | Skill 准确率提升 ≥ 10pp；适配全自动率 ≥ 50% |
| M4: 规模推广 | 第10周末 | ≥ 3 个模块接入双引擎 | 开发者主动使用，反馈积极 |
| M5: 效果量化 | 第14周末 | 有完整的对比数据 | 人力投入降低 ≥ 40%；适配周期缩短 ≥ 50% |

---

## 12. 风险与应对

### 12.1 技术风险

| 风险 | 概率 | 影响 | 应对策略 |
|------|------|------|---------|
| LLM理解Android底层代码能力不足 | 中 | 高 | 增加约束条件详细度；准备高质量评估集；考虑fine-tune |
| EvoSkill进化不收敛 | 低 | 中 | 设置no_improvement_limit；人工干预调整约束 |
| MCP工具实现复杂 | 中 | 中 | 从最简单的工具开始（日志解析）；Python脚本即可 |
| Git版本管理混乱 | 低 | 中 | EvoSkill自带分支管理；制定分支策略规范 |
| AOSP Diff 过大导致分析超时 | 中 | 中 | 分模块分阶段分析；增加 diff 缓存和增量分析 |
| API迁移规则库质量不足 | 中 | 高 | 人工审核首批规则；置信度阈值动态调整 |

### 12.2 组织风险

| 风险 | 概率 | 影响 | 应对策略 |
|------|------|------|---------|
| Owner不愿写约束文件 | 中 | 高 | 约束模板化，提供示例；Demo展示效果；管理层推动 |
| 团队不信任AI分析结果 | 中 | 中 | 先做辅助工具定位，不做替代；保留人工审核环节 |
| 评估测试集质量差 | 中 | 高 | 由Owner提供历史真实案例；建立测试集评审机制 |
| 效果短期不明显导致放弃 | 中 | 高 | 2周MVP验证；选择最痛的模块做试点；小赢积累信心 |
| 适配引擎引入代码质量风险 | 中 | 高 | 编译门禁+回归门禁+人工审核三级保障；全自动项必须有历史案例支撑 |

### 12.3 成本预估

| 项目 | 初始投入 | 月度成本 | 说明 |
|------|---------|---------|------|
| Claude API | ~$300/月 | ~$300-800/月 | 适配引擎批量操作消耗更多API调用 |
| EvoSkill | 免费 | 免费 | Apache 2.0开源 |
| Git仓库 | 免费 | 免费 | 可用GitHub/GitLab免费版 |
| 人力（初期） | ~3人×2周 | ~1人×月 | 适配引擎MCP工具开发需要额外投入 |
| **总初始成本** | **~$300 + 3人周** | **~$300-800/月** | |

> **对比当前方案成本**：当前方案每次大版本升级，每个Owner梳理SOP 3-7天，6个模块 = 18-42人天。新方案Owner更新约束 1-2小时/模块 = 约1人天。每次升级节省 17-41人天。

---

## 13. 附录：参考资源

### 13.1 必读文章

| 标题 | 链接 | 重要性 |
|------|------|--------|
| Harness Engineering 六层架构完整解析 | https://javaguide.cn/ai/agent/harness-engineering.html | ⭐⭐⭐⭐⭐ |
| Harness Engineering 实践指南 (OpenAI/Stripe/Anthropic) | https://edison-a-n.github.io/2026/03/14/harness-engineering-practical-guide/ | ⭐⭐⭐⭐⭐ |
| EvoSkill: 从Agent失败中自动发现Skill | https://github.com/sentient-agi/EvoSkill | ⭐⭐⭐⭐⭐ |
| AgentSkills 协议标准 | https://github.com/anthropics/skills | ⭐⭐⭐⭐ |
| Agent Skill Architecture Guide | https://github.com/shane9coy/Agent-Skill-Architecture-Guide | ⭐⭐⭐⭐ |
| AI自进化: EvoSkill从失败中学习 | https://www.36kr.com/p/3728164375231362 | ⭐⭐⭐⭐ |
| Multi-Agent框架对比: LangGraph/CrewAI/AutoGen | https://langcopilot.com/posts/2025-11-01-top-multi-agent-ai-frameworks-2024-guide | ⭐⭐⭐ |

### 13.2 开源项目

| 项目 | GitHub | 许可证 | 用途 |
|------|--------|--------|------|
| EvoSkill | https://github.com/sentient-agi/EvoSkill | Apache 2.0 | Skill自动进化 |
| Claude Code Skills | https://github.com/anthropics/skills | MIT | Skill标准参考 |
| Dify | https://github.com/langgenius/dify | Apache 2.0 | 可选可视化平台 |
| MCP协议 | https://modelcontextprotocol.io | MIT | 工具接入标准 |

### 13.3 论文

| 标题 | 链接 |
|------|------|
| EvoSkill: Automated Skill Discovery for Multi-Agent Systems | https://arxiv.org/abs/2603.02766 |
| Voyager: An Open-Ended Embodied Agent with LLMs | https://arxiv.org/abs/2305.16291 |

---

## ADR-001: 采用Harness+约束驱动方案替代手动SOP转Skill

### Status
Approved (v2.1)

### Context
当前方案要求各业务Owner手动编写SOP并转为Skill，存在规模化瓶颈、质量不一致、迭代成本高等问题。部门经理提议搭建基于Harness规范的自动化系统。适配场景（版本升级/特性移植/运营商需求移植）占部门工作量的大头，每个模块每次大版本都要重新梳理适配SOP。

### Decision
采用 **Agent = Model + Harness** 范式，结合 **EvoSkill** 自动Skill发现和 **AgentSkills** 开放标准，搭建 TECNO AI Harness Platform (TAHP) **双引擎架构**：
1. 各模块只需输出约束条件（YAML格式），系统自动生成 Skill（诊断+适配）
2. 通过 EvoSkill 从执行失败中自动进化和优化 Skill
3. **适配经验通过 API 迁移规则库跨版本复用**（v2.1 核心）
4. 基于 Git 版本控制和 AgentSkills 标准实现 Skill 共享
5. 纯本地运行，零服务器成本
6. **通过 AI 代码生成约束规范严格管控 AI 行为**
7. **通过评估与质量门禁规范量化 Skill 效果**
8. **通过版本适配约束规范统一适配流程**（v2.1 新增）

### Consequences
- **变得更容易**: Owner 工作量从数天 SOP 降低到 2-4 小时约束编写；新模块接入标准化
- **变得更容易**: Skill 质量评估量化，效果可衡量可追踪
- **变得更容易**: AI 行为通过约束规范严格管控，减少幻觉和无效输出
- **变得更容易**: **适配经验跨版本复用，每次升级全自动率逐步提升**
- **变得更难**: 初期需要 3 周搭建期（含适配 MCP 工具）；团队需要学习约束编写思维
- **风险**: EvoSkill 对中文/Android 领域的效果需验证；LLM API 有持续成本；适配引擎代码质量风险需三级门禁保障

---

## ADR-002: 采用纯文件存储方案（无数据库）

### Status
Approved

### Context
评估数据存储方案时，考虑过SQLite、PostgreSQL等数据库方案。但考虑到零服务器成本的要求和团队现有的Git工作流。

### Decision
采用**纯文件存储**方案：YAML + Markdown + JSON，全部通过Git进行版本管理。不引入任何数据库依赖。

### Consequences
- **优势**: 零运维成本、天然版本控制、易于审查、与现有工作流无缝集成
- **劣势**: 复杂查询能力有限、大规模并发写入性能受限
- **缓解**: 评估脚本提供结构化查询能力；单用户使用场景下并发不是问题

## ADR-003: 适配引擎采用"约束+规则库+批量验证"三段式设计 `NEW`

### Status
Approved (v2.1)

### Context
部门适配工作量（版本升级/特性移植/运营商移植）远大于诊断工作量。现有各业务已有"SOP→Skill→AI执行"的适配流程在跑，但存在 SOP 重复编写、经验不跨版本复用、质量评估缺失等问题。

### Decision
适配引擎采用三段式设计：
1. **约束段**：Owner 通过 YAML 定义适配约束（版本范围、API 迁移规则、红线、验收标准）
2. **规则库段**：API 迁移规则库作为跨版本复用的核心资产，每次升级积累，逐步提升全自动比例
3. **验证段**：编译通过 + 回归测试双门禁，全自动项系统审核，半自动项人工审核

适配策略分三级：全自动（已知模式，置信度>95%）/ 半自动（AI生成+人工审核）/ 人工（新场景）。

### Consequences
- **优势**: 首次升级全自动率 ~40%，积累后逐步提升到 ~75%；Owner 工作量从 3-7 天降到 1-2 小时
- **优势**: API 迁移规则库跨版本复用，知识不会丢失
- **风险**: 规则库质量依赖首批人工输入；全自动适配的代码质量需要严格门禁保障
- **缓解**: 首批规则人工审核 + 置信度阈值 + 编译门禁 + 回归门禁 + 人工审核

---

> **下一步行动建议**: 选择通信模块（telephony）作为试点，用最近的版本升级数据做回溯验证。参照 [TAHP-版本适配约束规范](TAHP-版本适配约束规范.md) 开始编写适配约束文件。
