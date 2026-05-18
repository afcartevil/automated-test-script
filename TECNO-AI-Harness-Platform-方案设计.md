# 传音Android底软集成部 — AI提效 Harness 系统架构评估与方案设计

> **日期**: 2026-05-18 (Updated)
> **版本**: v2.0
> **编制**: Software Architect
> **状态**: Approved
>
> **配套文档**:
> - [可视化架构总览](TAHP-Architecture-Overview.html) — 8幅专业架构图
> - [约束文件编写规范](TAHP-约束文件编写规范.md) — Owner编写约束的强制性标准
> - [AI代码生成约束规范](TAHP-AI代码生成约束规范.md) — 防幻觉、防反复修改的核心规范
> - [评估与质量门禁规范](TAHP-评估与质量门禁规范.md) — Skill质量评估与代码门禁标准

---

## 目录

1. [执行摘要](#1-执行摘要)
2. [现状评估](#2-现状评估)
3. [行业调研](#3-行业调研)
4. [Harness范式解读](#4-harness范式解读)
5. [推荐系统方案](#5-推荐系统方案)
6. [技术选型与架构设计](#6-技术选型与架构设计)
7. [系统边界与接口规范](#7-系统边界与接口规范) `NEW`
8. [数据模型设计](#8-数据模型设计) `NEW`
9. [安全设计](#9-安全设计) `NEW`
10. [实施路线图](#10-实施路线图)
11. [风险与应对](#11-风险与应对)
12. [附录：参考资源](#12-附录参考资源)

---

## 1. 执行摘要

### 1.1 核心结论

你们部门经理提出的**Harness-based系统**方向**完全正确**，且恰逢其时。2026年业界已形成成熟的方法论 —— **Agent = Model + Harness**，其中Harness就是将状态、工具、反馈、约束和执行环境串联起来的"操作系统"。核心范式转变是：**从"人写SOP→转Skill"升级为"模块出约束→系统自动生成/调用/迭代Skill"**。

### 1.2 推荐方案概览

```
┌─────────────────────────────────────────────────────────┐
│                    TECNO AI Harness Platform              │
│                                                          │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌────────┐ │
│  │ 约束管理层 │→│ Skill引擎层 │→│ 执行编排层 │→│ 评估迭代 │ │
│  │          │  │           │  │           │  │        │ │
│  │ 各模块    │  │ EvoSkill  │  │ 多Agent   │  │ 自动   │ │
│  │ 只需输出  │  │ + Agent   │  │ 编排调度   │  │ 评估   │ │
│  │ 约束条件  │  │ Skills   │  │ + MCP工具  │  │ + 进化 │ │
│  └──────────┘  └───────────┘  └──────────┘  └────────┘ │
│                                                          │
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
当前方案流程:

业务Owner → [梳理SOP] → [手动转Skill] → [人工测试] → [人工迭代]
     ↑                                              │
     └──────────────── 完全依赖人 ───────────────────┘
```

#### 优势
| 项目 | 评价 |
|------|------|
| 业务理解深 | Owner对自身模块最了解，SOP质量有保障 |
| 质量可控 | 人工审核，Skill质量相对可靠 |
| 风险低 | 不依赖额外基础设施 |

#### 核心问题

| # | 问题 | 影响 | 严重度 |
|---|------|------|--------|
| 1 | **规模化瓶颈** | 每个模块Owner都要从零开始，人力投入巨大 | 🔴 高 |
| 2 | **质量不一致** | 不同Owner对SOP的梳理深度和Skill编写能力差异大 | 🔴 高 |
| 3 | **迭代成本高** | 每次迭代都要人工更新SOP→Skill，响应慢 | 🟡 中 |
| 4 | **缺乏关联调用** | 各模块Skill孤立，无法自动协调跨模块任务 | 🟡 中 |
| 5 | **知识不可积累** | 一个Owner的经验无法有效传递给另一个模块 | 🟡 中 |
| 6 | **无量化评估** | 不知道Skill到底提升了多少效率，缺乏数据驱动 | 🟠 中高 |

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

#### 架构总览

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
│  └─────────────────────────────────────────────────────────────┘  │
│                               ↓                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                 L3: 执行编排层                              │  │
│  │  ┌──────────────────┐  ┌──────────────────┐               │  │
│  │  │ Bug分析Pipeline   │  │ 代码适配Pipeline │               │  │
│  │  │ ┌────┐ ┌────┐    │  │ ┌────┐ ┌────┐   │               │  │
│  │  │ │日志 │→│根因 │→   │  │ │约束 │→│代码 │→  │               │  │
│  │  │ │收集 │ │定位 │    │  │ │检查 │ │生成 │   │               │  │
│  │  │ └────┘ └────┘    │  │ └────┘ └────┘   │               │  │
│  │  └──────────────────┘  └──────────────────┘               │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                               ↓                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │              L4+L5+L6: 记忆/评估/恢复层                     │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │  │
│  │  │ EvoSkill     │ │ 评估引擎     │ │ 失败恢复     │        │  │
│  │  │ 自动进化     │ │ (测试集打分) │ │ (重试/回滚)  │        │  │
│  │  │ 循环         │ │              │ │              │        │  │
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

业务Owner**唯一需要做的事**就是为各自模块定义约束文件：

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
│   │   ├── code-adaptation.yaml      # 通信代码适配约束
│   │   └── eval-data/                # 评估测试集
│   ├── kernel-driver/
│   │   ├── bug-analysis.yaml
│   │   ├── code-adaptation.yaml
│   │   └── eval-data/
│   ├── power/
│   │   ├── bug-analysis.yaml
│   │   └── eval-data/
│   └── shared/
│       ├── coding-standards.yaml     # 共享编码规范
│       └── android-platform.yaml     # Android平台通用约束
│
├── skills/                            # 自动生成的Skills（EvoSkill产出）
│   ├── .claude/skills/               # Claude Code格式
│   │   ├── telephony-call-drop/      # 自动发现的Skill
│   │   │   ├── SKILL.md
│   │   │   └── references/
│   │   ├── kernel-panic-trace/
│   │   │   ├── SKILL.md
│   │   │   └── references/
│   │   └── power-leak-detect/
│   │       └── SKILL.md
│   └── .codex/skills/                # Codex格式（自动同步）
│
├── playbooks/                         # 执行编排剧本
│   ├── bug-analysis-pipeline.yaml    # Bug分析流水线
│   ├── code-adaptation-pipeline.yaml # 代码适配流水线
│   └── cross-module-pipeline.yaml    # 跨模块协作流水线
│
├── tools/                             # MCP工具定义
│   ├── android-log-analyzer/         # Android日志分析工具
│   ├── git-operations/               # Git操作工具
│   └── build-system/                 # 编译构建工具
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
│   └── sync-skills.sh                # 跨Agent同步Skills
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
  - 准备5-10个历史Bug案例放入 eval-data/

Step 3: 提交到Git
  $ git add constraints/my-module/
  $ git commit -m "Add my-module constraints"

Step 4: 系统自动完成（无需Owner参与）
  - Skill生成器读取约束 → 生成初始SKILL.md
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

### 6.4 MCP工具链设计

针对Android底软场景，建议优先实现以下MCP工具：

| 工具名 | 功能 | 优先级 |
|--------|------|--------|
| `android-log-parser` | 解析logcat/ril/atcmd日志 | P0 |
| `bugzilla-query` | 查询BugTracker | P0 |
| `git-blame-analyzer` | 代码变更历史分析 | P0 |
| `kernel-config-checker` | 检查内核配置合规性 | P1 |
| `device-tree-validator` | 设备树校验 | P1 |
| `power-profile-analyzer` | 功耗数据解析 | P1 |
| `android-build-helper` | 编译构建辅助 | P2 |
| `code-review-checker` | 代码审查规则检查 | P2 |

---

## 7. 系统边界与接口规范

### 7.1 系统边界定义

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

#### 7.2.1 Owner → TAHP 接口

**唯一输入接口**: YAML约束文件

```
输入: constraints/{module}/{domain}.yaml
验证: scripts/validate-constraints.py --module {module}
反馈: 约束文件质量评分（完整性/可验证性/具体性/最小性/评估集质量）
```

#### 7.2.2 TAHP → AI Agent 接口

```
加载: AGENTS.md → 引导Agent读取约束文件和Skills
约束注入: 约束文件内容作为System Prompt的一部分
Scope控制: 通过L1信息边界层控制Agent的可访问范围
工具分发: 通过MCP协议按需分发工具
```

#### 7.2.3 AI Agent → TAHP 接口

```
产出格式: 遵循 TAHP-AI代码生成约束规范 第5节定义的输出格式
质量门禁: 所有代码修改必须通过 P0/P1/P2 三级门禁
反馈记录: 执行轨迹记录到 feedback_history.md，供EvoSkill分析
```

#### 7.2.4 TAHP → 开发者 接口

```
分析报告: 结构化Markdown，包含完整证据链和修复建议
代码修改: Git patch格式，附带门禁检查结果
交互方式: Claude Code CLI交互 / 预生成的报告文件
```

### 7.3 MCP工具接口标准

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

## 8. 数据模型设计

### 8.1 核心数据实体

#### 约束文件 (Constraint)

```
Constraint
├── id: string (module/domain 格式)
├── module: Module
├── domain: enum [bug_analysis, code_adaptation, test_generation]
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

### 8.2 数据流转图

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

### 8.3 存储方案

| 数据类型 | 存储方式 | 版本管理 | 备份 |
|---------|---------|---------|------|
| 约束文件 | Git (YAML) | Git branch + tag | Git remote |
| Skills | Git (Markdown) | Git branch + tag | Git remote |
| 评估结果 | JSON文件 | Git (按日期归档) | Git remote |
| 执行日志 | Markdown | Git (按日期归档) | Git remote |
| 进化历史 | TOML (EvoSkill原生) | EvoSkill内部管理 | Git同步 |

> 所有数据均为**纯文件存储**，无数据库依赖。Git既是版本管理工具，也是备份和协作工具。

---

## 9. 安全设计

### 9.1 威胁模型

| 威胁 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| AI生成恶意代码 | 低 | 极高 | Scope限制 + 安全红线 + 代码门禁 + 人工审核 |
| API Key泄露 | 中 | 高 | 环境变量存储 + 不写入Git + 定期轮换 |
| 约束文件被恶意篡改 | 低 | 高 | Git签名 + Owner审核 + 变更通知 |
| 敏感日志泄露 | 中 | 中 | 脱敏规则 + 访问控制 + 日志保留策略 |
| LLM Prompt注入 | 中 | 中 | 输入校验 + 系统Prompt隔离 |

### 9.2 安全架构

#### 9.2.1 Scope隔离（L1信息边界）

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

#### 9.2.2 代码安全门禁

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

#### 9.2.3 敏感信息处理

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

### 9.3 访问控制

| 角色 | 权限 | 说明 |
|------|------|------|
| **Owner** | 编写约束、审核Skill、查看评估报告 | 模块负责人 |
| **开发者** | 使用Skill进行分析、提交反馈 | 日常使用者 |
| **TL** | 所有Owner权限 + 管理模块、审批变更 | 团队负责人 |
| **系统管理员** | 配置CI/CD、管理MCP工具、系统维护 | 运维角色 |
| **AI Agent** | 只读代码、按约束修改代码、生成报告 | 受约束执行 |

---

## 10. 实施路线图

### 7.1 分阶段实施（8周MVP → 持续演进）

```
Phase 0: 基础搭建 (第1-2周)
├── 搭建Git仓库和目录结构
├── 安装Claude Code + EvoSkill
├── 编写AGENTS.md全局导航
├── 设计约束文件模板
└── 选择1-2个试点模块（建议: telephony + kernel-driver）

Phase 1: 约束驱动MVP (第3-4周)
├── 试点模块Owner填写约束文件
├── 基于约束生成初始Skills
├── 准备评估测试集（每个模块5-10个案例）
├── 手动验证Skill效果
└── 建立效果度量基线

Phase 2: 自动进化 (第5-6周)
├── 启动EvoSkill进化循环
├── 观察Skill自动进化效果
├── 实现第一个MCP工具（android-log-parser）
├── 建立Bug分析Pipeline
└── 量化效果对比（VS人工分析）

Phase 3: 规模化推广 (第7-8周)
├── 总结试点经验，完善模板
├── 向power等其他模块推广
├── 实现跨模块协作Pipeline
├── 建立Skill共享机制
└── 编写部门级使用文档

Phase 4: 持续优化 (第9周+)
├── 定期Skill质量评审
├── 根据评估报告申请服务器资源（如需）
├── 探索本地LLM降低API成本
├── 建立Skill贡献和评分机制
└── 对标业界Level 3-4成熟度
```

### 7.2 关键里程碑

| 里程碑 | 时间 | 标准 | 成功标志 |
|--------|------|------|---------|
| M0: 基础就绪 | 第2周末 | 仓库结构完整，工具安装完毕 | `evoskill init` 成功运行 |
| M1: 约束MVP | 第4周末 | 试点模块约束文件完成 | 初始Skill能正确分析测试集 |
| M2: 自动进化 | 第6周末 | EvoSkill进化循环稳定 | Skill准确率提升≥10pp |
| M3: 规模推广 | 第8周末 | ≥3个模块接入 | 开发者主动使用，反馈积极 |
| M4: 效果量化 | 第12周末 | 有完整的对比数据 | 人力投入降低≥30% |

---

## 11. 风险与应对

### 8.1 技术风险

| 风险 | 概率 | 影响 | 应对策略 |
|------|------|------|---------|
| LLM理解Android底层代码能力不足 | 中 | 高 | 增加约束条件详细度；准备高质量评估集；考虑fine-tune |
| EvoSkill进化不收敛 | 低 | 中 | 设置no_improvement_limit；人工干预调整约束 |
| MCP工具实现复杂 | 中 | 中 | 从最简单的工具开始（日志解析）；Python脚本即可 |
| Git版本管理混乱 | 低 | 中 | EvoSkill自带分支管理；制定分支策略规范 |

### 8.2 组织风险

| 风险 | 概率 | 影响 | 应对策略 |
|------|------|------|---------|
| Owner不愿写约束文件 | 中 | 高 | 约束模板化，提供示例；Demo展示效果；管理层推动 |
| 团队不信任AI分析结果 | 中 | 中 | 先做辅助工具定位，不做替代；保留人工审核环节 |
| 评估测试集质量差 | 中 | 高 | 由Owner提供历史真实案例；建立测试集评审机制 |
| 效果短期不明显导致放弃 | 中 | 高 | 2周MVP验证；选择最痛的模块做试点；小赢积累信心 |

### 8.3 成本预估

| 项目 | 初始投入 | 月度成本 | 说明 |
|------|---------|---------|------|
| Claude API | ~$200/月 | ~$200-500/月 | 按使用量计费，EvoSkill迭代会消耗较多 |
| EvoSkill | 免费 | 免费 | Apache 2.0开源 |
| Git仓库 | 免费 | 免费 | 可用GitHub/GitLab免费版 |
| 人力（初期） | ~2人×2周 | ~0.5人×月 | 试点阶段需要工程师投入搭建 |
| **总初始成本** | **~$200 + 2人周** | **~$200-500/月** | |

> **对比当前方案成本**：当前方案每个Owner写SOP至少2天，6个模块 = 12人天 + 持续维护。新方案初始Owner投入2-4小时/模块 = 约2人天。

---

## 12. 附录：参考资源

### 9.1 必读文章

| 标题 | 链接 | 重要性 |
|------|------|--------|
| Harness Engineering 六层架构完整解析 | https://javaguide.cn/ai/agent/harness-engineering.html | ⭐⭐⭐⭐⭐ |
| Harness Engineering 实践指南 (OpenAI/Stripe/Anthropic) | https://edison-a-n.github.io/2026/03/14/harness-engineering-practical-guide/ | ⭐⭐⭐⭐⭐ |
| EvoSkill: 从Agent失败中自动发现Skill | https://github.com/sentient-agi/EvoSkill | ⭐⭐⭐⭐⭐ |
| AgentSkills 协议标准 | https://github.com/anthropics/skills | ⭐⭐⭐⭐ |
| Agent Skill Architecture Guide | https://github.com/shane9coy/Agent-Skill-Architecture-Guide | ⭐⭐⭐⭐ |
| AI自进化: EvoSkill从失败中学习 | https://www.36kr.com/p/3728164375231362 | ⭐⭐⭐⭐ |
| Multi-Agent框架对比: LangGraph/CrewAI/AutoGen | https://langcopilot.com/posts/2025-11-01-top-multi-agent-ai-frameworks-2024-guide | ⭐⭐⭐ |

### 9.2 开源项目

| 项目 | GitHub | 许可证 | 用途 |
|------|--------|--------|------|
| EvoSkill | https://github.com/sentient-agi/EvoSkill | Apache 2.0 | Skill自动进化 |
| Claude Code Skills | https://github.com/anthropics/skills | MIT | Skill标准参考 |
| Dify | https://github.com/langgenius/dify | Apache 2.0 | 可选可视化平台 |
| MCP协议 | https://modelcontextprotocol.io | MIT | 工具接入标准 |

### 9.3 论文

| 标题 | 链接 |
|------|------|
| EvoSkill: Automated Skill Discovery for Multi-Agent Systems | https://arxiv.org/abs/2603.02766 |
| Voyager: An Open-Ended Embodied Agent with LLMs | https://arxiv.org/abs/2305.16291 |

---

## ADR-001: 采用Harness+约束驱动方案替代手动SOP转Skill

### Status
Approved (v2.0)

### Context
当前方案要求各业务Owner手动编写SOP并转为Skill，存在规模化瓶颈、质量不一致、迭代成本高等问题。部门经理提议搭建基于Harness规范的自动化系统。

### Decision
采用 **Agent = Model + Harness** 范式，结合 **EvoSkill** 自动Skill发现和 **AgentSkills** 开放标准，搭建TECNO AI Harness Platform (TAHP)：
1. 各模块只需输出约束条件（YAML格式），系统自动生成Skill
2. 通过EvoSkill从执行失败中自动进化和优化Skill
3. 基于Git版本控制和AgentSkills标准实现Skill共享
4. 纯本地运行，零服务器成本
5. **通过AI代码生成约束规范严格管控AI行为**（v2.0新增）
6. **通过评估与质量门禁规范量化Skill效果**（v2.0新增）

### Consequences
- **变得更容易**: Owner工作量从数天SOP降低到2-4小时约束编写；新模块接入标准化
- **变得更容易**: Skill质量评估量化，效果可衡量可追踪
- **变得更容易**: AI行为通过约束规范严格管控，减少幻觉和无效输出
- **变得更难**: 初期需要2周搭建期；团队需要学习约束编写思维
- **风险**: EvoSkill对中文/Android领域的效果需验证；LLM API有持续成本

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

---

> **下一步行动建议**: 选择1-2个痛点最明显的模块（建议telephony Bug分析），用2周时间跑通MVP，用数据说话决定是否全面推广。参照 [TAHP-约束文件编写规范](TAHP-约束文件编写规范.md) 开始编写约束文件。
