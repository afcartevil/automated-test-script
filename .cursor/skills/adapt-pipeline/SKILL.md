---
name: adapt-pipeline
description: >-
  TAHP「AI 适配流水线」（适配 → 编译 → 烧录 → 自检 → 故障分析 → 人工审核 → 提交 Gerrit）
  的编排层设计与开发规范。核心是可插拔阶段注册表 + 数据化流程定义 + 能力未就绪时自动降级为人工门，
  使各业务节点可动态增删且互不耦合。在实现/修改流水线编排、阶段插件、实时进度 UI 时使用。
  编排层不重写业务，一律复用现有 service；新增业务能力须先按 reference.md 的能力契约封装。
---

# AI 适配流水线 — 编排层 Skill

> **Cursor 项目 Skill**（`.cursor/skills/adapt-pipeline/`）。
> 配套文档：[数据模型与契约](reference.md) · [UI 交互设计](ui-spec.md) · [分期执行清单](implementation.md)

## 何时加载

- 实现或修改 `services/tahp/adapt-pipeline/**`
- 新增 / 删除 / 调整流水线的某个业务节点
- 把一个已有业务能力（编译、刷机、提交…）接入流水线
- 实现流水线实时进度 UI

**硬性规则**：编排层**不实现业务逻辑**。任何节点的实际工作都必须落在已有 service 或独立的新 service 里，编排层只负责「调用 → 观察 → 判定 → 转移」。

---

## 一、要解决的问题

把工程里已经存在的 6 个能力串成一条可自动流转、可视化、可人工介入的工作流：

```
选项目 → 拉前置 → AI适配 → 编译 → 烧录 → AI自检 ──通过──→ 提交Gerrit → 人工入库
                           ▲     ▲      ▲  │
                           │     │      │  失败
                           │     │      │  ↓
                           │     │      │  AI故障分析 → 人工审核 + AI修改
                           └─────┴──────┴───────────────────┘
                              按产物新鲜度自动推荐恢复点
```

任一节点失败后人工介入修复，**恢复点由产物新鲜度自动推导**——没改代码就只重跑烧录，改了代码才回编译。详见 [4.4](#44-失败后的断点恢复)。

### 四条不可妥协的约束

| 约束 | 来源 | 设计后果 |
|---|---|---|
| **节点可动态增删** | 编译（P1）由他人并行开发，后续还会加节点 | 阶段插件化 + 流程定义数据化 |
| **能力未就绪不能阻塞** | P1 未完成时流水线也要能跑 | `manual_gate` 降级机制 |
| **不重写已有业务** | 变更控制规则 | 阶段只持有外部任务引用，进程内订阅事件 |
| **失败可从中间恢复** | 编译 4–8h，整条重来代价不可接受 | 产物依赖声明 + 失效传播 |

---

## 二、架构

```
┌──────────────────────────────────────────────────────┐
│  Orchestrator（编排器）                                │
│  · 读 WorkflowDefinition（数据）                       │
│  · 驱动 StageRegistry 里的 StageDefinition（插件）     │
│  · 只存 run 元数据 + 外部任务引用 + 阶段判定           │
└───────────┬──────────────────────────┬───────────────┘
            │ 调用                      │ 订阅
            ▼                          ▼
   ┌────────────────┐        ┌──────────────────────┐
   │ StageDefinition │        │ PipelineEventSource  │
   │  (每节点一个)    │        │  · TaskStreamSource  │
   └────────┬───────┘        │  · SelfCheckSource   │
            │                 └──────────┬───────────┘
            ▼                            │
   ┌─────────────────────────────────────▼──────────┐
   │  现有业务 service（一行不改对外契约）             │
   │  adapt-agent · device-self-check · device-flash │
   │  bug-analysis · central-client · (P1 build)     │
   └─────────────────────────────────────────────────┘
```

**核心原则：编排器不认识任何具体业务。** 它只认识 `StageDefinition` 接口和 `WorkflowDefinition` 数据。这是「可动态增删节点」的全部基础。

### 目录结构

```
services/tahp/adapt-pipeline/
├── types.ts                  # 全部类型定义（唯一真相源）
├── registry.ts               # 阶段注册表
├── workflow.ts               # 流程定义 + 默认流程 + 校验
├── store.ts                  # run 持久化（JSON 落盘）
├── orchestrator.ts           # 状态机驱动
├── capability.ts             # 外部能力契约 + createCapabilityStage 工厂
├── sources/
│   ├── index.ts              # 事件源注册
│   ├── task-stream.ts        # 适配 getTaskStream()
│   └── self-check.ts         # 适配 device-self-check.onEvent()
└── stages/
    ├── index.ts              # ★ 新增阶段唯一要改的文件（一行 import）
    ├── prereq.ts
    ├── adapt.ts
    ├── build.ts
    ├── flash.ts
    ├── selfcheck.ts
    ├── triage.ts
    ├── human-review.ts
    └── gerrit.ts
```

---

## 三、扩展机制（本 Skill 的核心）

### 3.1 阶段插件接口

每个节点实现同一个接口，编排器只调这几个方法。完整类型见 [reference.md](reference.md#stagedefinition)。

```typescript
export interface StageDefinition {
  key: string
  label: string
  consumes?: ArtifactKind[]                    // 依赖哪些产物（决定能否从此恢复）
  produces?: ArtifactKind[]                    // 产出哪些产物（决定谁会失效）
  isHumanGate?: boolean                        // 人工门，回环边只能从它出发
  probe?(ctx: { run: Readonly<PipelineRun> }): Promise<StageAvailability>   // 能力探测
  start(ctx: StageContext): Promise<void>      // 调外部能力，把 runId 写进 state.refs
  observe?(ctx: StageContext, ev: ObservedEvent): void   // 翻译外部事件为本阶段进度
  evaluate(ctx: StageContext): StageVerdict    // 判定：running/done/failed/waiting_human/skipped
  handleHumanAction?(ctx: StageContext, actionId: string, payload?: Record<string, unknown>): Promise<void>
  cancel?(ctx: StageContext): Promise<void>
}
```

`evaluate` 的返回值就是状态机的输入，`StageVerdict` 只有 5 种，不可扩充。

### 3.2 新增一个节点 = 2 步

```typescript
// 1) 新建 stages/my-stage.ts
import { registerStage } from '../registry'

registerStage({
  key: 'my_stage',
  label: '我的节点',
  async start(ctx) {
    const { runId } = await myService.start(ctx.run.project_code)
    ctx.patchState({ refs: { my_run_id: runId } })
  },
  evaluate(ctx) {
    const s = ctx.state.progress?.state
    if (s === 'success') return { status: 'done' }
    if (s === 'failed') return { status: 'failed', error: ctx.state.progress?.error ?? '未知失败' }
    return { status: 'running' }
  },
})
```

```typescript
// 2) 在 stages/index.ts 加一行
import './my-stage'
```

然后在流程定义的 `nodes` 数组里插入 `{ key: 'my_stage', enabled: true }`。
**UI 无需任何改动**——步进条按后端返回的节点数组渲染，未注册专用渲染器时自动用默认面板。

### 3.3 删除 / 停用一个节点

改流程定义即可，**不删代码**：

```typescript
{ key: 'gerrit', enabled: false }   // 停用
```

或从 `nodes` 数组移除。阶段实现文件保留，随时可再启用。

### 3.4 `manual_gate` 降级 —— P1 未就绪时的关键机制

这是本方案能「先串起来、后填能力」的原因。

节点的 `onUnavailable` 决定探测失败后的行为：

| 值 | 行为 | 适用 |
|---|---|---|
| `manual_gate`（**默认**） | 转 `waiting_human`，UI 出「已手工完成，继续 / 跳过」按钮 | **编译（P1 未接入期间）**、刷机、提交 |
| `skip` | 直接标记 `skipped`，流程继续 | 可选节点，如 triage |
| `fail` | 标记失败并走 `onFail`（缺省 `ABORT`，即整个 run 失败） | 不可缺的前置，如 prereq |

`onUnavailable` 可省略，缺省即 `manual_gate`——**故意选这个默认值**：新节点若忘了声明，最坏结果是停下来等人，而不是静默跳过或炸掉整条流水线。

时间线：

```
今天           build.probe() → { available:false, reason:'编译能力尚未接入' }
              → onUnavailable:'manual_gate' → 等人点「已手工完成，继续」
              → 整条流水线端到端可跑通 ✅

P1 上线后      build.probe() → { available:true }
              → 自动执行 → 零代码改动切换 ✅
```

**实现要求**：`stages/build.ts` 从第一天就写好，只是 `probe()` 返回不可用。P1 接入时只改 `probe()` 与 `start()` 的实现体，**不动编排器、不动流程定义、不动 UI**。

### 3.5 外部能力契约 + 工厂

绝大多数节点都是「启动一个外部长任务 → 轮询/订阅状态 → 判定成败」。这类节点**不要手写 StageDefinition**，用工厂：

```typescript
// stages/build.ts
import { createCapabilityStage } from '../capability'
import { buildCapability } from '../../build-capability'   // ← P1 同事产出

registerStage(createCapabilityStage({
  key: 'build',
  label: '编译',
  capability: buildCapability,
  buildInput: ctx => ({
    mappedRoot: ctx.run.build_context.mapped_root,
    workspace: ctx.run.build_context.workspace,
    mode: ctx.run.iteration === 1 ? 'full' : 'incremental',
    components: ctx.run.build_context.components,
    variant: ctx.run.build_context.variant,
  }),
}))
```

`ExternalCapability` 接口定义见 [reference.md](reference.md#externalcapability)。**这份接口就是交给 P1 同事的契约**——他只要实现这 5 个方法，接入成本约 30 行。

---

## 四、流程定义

流程是**数据**不是代码。默认定义在 `workflow.ts`，可被 `.tahp-config/adapt-pipeline/workflow.json` 覆盖。

### 4.1 默认流程

| # | key | label | onDone | onFail | onUnavailable |
|---|---|---|---|---|---|
| 1 | `prereq` | 前置信息 | ↓ | ABORT | `fail` |
| 2 | `adapt` | AI 适配 | ↓ | ABORT | `fail` |
| 3 | `build` | 编译 | ↓ | `human_review` | `manual_gate` |
| 4 | `flash` | 烧录 | ↓ | `human_review` | `manual_gate` |
| 5 | `selfcheck` | AI 自检 | `gerrit` | `triage` | `manual_gate` |
| 6 | `triage` | AI 故障分析 | `human_review` | `human_review` | `skip` |
| 7 | `human_review` | 人工审核 | `build` ⟲ | ABORT | `fail`（无 probe，恒可用） |
| 8 | `gerrit` | 提交 Gerrit | END | `human_review` | `manual_gate` |

`onDone` 缺省 = 数组下一个节点。`human_review → build` 是**兜底**回环目标；实际目标由用户选的恢复点决定（见 4.4）。
`iteration` 是**条件**自增：只有代码真的变了才算新一轮，纯环境重试不占额度。

### 4.2 为什么是「线性 + 分支」而不是 DAG

业务流本身是线性的，只有一处回环。引入通用 DAG 引擎会带来拓扑排序、并发合流、环检测等一堆复杂度，**属于过度设计**。当前模型完全够用，且状态机只有一个「当前节点」指针，调试和 UI 都简单。

若将来真出现并行分支需求，扩展点是 `WorkflowNode.parallel?: string[]`，届时再加。

### 4.3 收敛保护

`maxIterations` 默认 3。超出后 run 转 `waiting_human`，reason = `max_iterations_exceeded`，由人决定 `[继续加一轮]` 还是 `[终止]`，避免坏项目无人值守地长期占用编译机与设备。

因为 `iteration` 是条件自增，纯环境重试（没改代码）不消耗额度——额度只用来度量「改了几轮代码还没收敛」。

### 4.4 失败后的断点恢复

节点失败 → 人工修复 → 从**哪个节点**继续？编译一次 4–8h，答错这个问题代价很大。

**不让人裸选节点。** 反例：自检失败 → 人改了代码 → 直接从 `selfcheck` 重跑 → 但设备上还是旧镜像 → 测出「通过」→ `gerrit` 自动提交。全程无报错，流水线可信度归零。

正确做法是让系统推导。每个阶段声明消费和产出什么产物：

```
产物链   prereq → source → build → flashed → testresult → triage
产出者   prereq   adapt     build   flash      selfcheck    triage
                    ↑
              human_review 也产出 source   ← 枢纽
```

节点完成时刷新自己的产物，并把**下游全部标记 stale**。恢复到某节点的前提是它 `consumes` 的产物都新鲜。

`human_review` 产出 `source` 是这个模型的枢纽——它让「改了代码就必须回编译」变成**自动推导**的结论，而不是写死的规则。是否真的改了代码用 git 快照指纹判定（进入时打快照 A，确认时打快照 B），**不靠人自己勾选**。

于是同一套算法自然给出：

| 情况 | 推荐恢复点 |
|---|---|
| 编译失败，改了 Makefile | `build` |
| **烧录失败（USB 松了），没改代码** | **`flash`** — 省一次 4–8h 编译 |
| 自检失败，改了驱动代码 | `build` |
| 自检失败，判定是用例本身的问题 | `selfcheck` |
| 改了代码却想只跑 selfcheck | 标 unsafe，提示「设备镜像已过期」 |

unsafe 的选项**不隐藏**，灰显 + 标原因，二次确认后可强制执行。隐藏会让人觉得工具在跟自己作对。

完整算法、`ResumeRequest`、`scope`（增量续跑 / 全量重来）语义见 [reference.md 第 11 节](reference.md#11-断点恢复)。

---

## 五、状态模型

### Run 状态

`draft` → `running` ⇄ `waiting_human` → `passed` / `failed` / `aborted`（`paused` 为人工暂停）

### 阶段状态

`pending` → `running` → `done` / `failed` / `waiting_human` / `skipped`

### 持久化

`{projectRoot}/.tahp-config/adapt-pipeline/runs/{runId}.json` + `index.json`。

与 `test-plan-executions.json`、`self-check-review-meta.json` 同一套风格，**不引数据库**。

**必须持久化的理由**：编译 4–8h、GMS 8h、功耗 24h，服务重启不能丢流程。启动时 `orchestrator.recover()` 读回 `running` / `waiting_human` 的 run，重新挂事件订阅。

---

## 六、与现有能力的对接点

| 阶段 | 复用 | 关键位置 |
|---|---|---|
| prereq | `centralClient.resolveAdaptPrereqs()` | [central-client.ts](../../../tahp-console/packages/server/src/services/tahp/sync/central-client.ts) `:166` |
| adapt | `startAdaptAgentRun()` **逐域串行** | [adapt-agent.ts](../../../tahp-console/packages/server/src/services/tahp/adapt-agent.ts) `:497` |
| build | P1 `ExternalCapability`（未就绪→manual_gate） | 待接入 |
| flash | `runDeviceFlash()` | [device-flash.ts](../../../tahp-console/packages/server/src/services/tahp/device-flash.ts) `:1186` |
| selfcheck | `recommendTestCasesWithMeta()` → `startCustomTest()` | [gerrit-case-recommendation.ts](../../../tahp-console/packages/server/src/services/tahp/gerrit-case-recommendation.ts) `:335` |
| triage | `POST /api/tahp/bug-analysis/local` | [bug-analysis.ts](../../../tahp-console/packages/server/src/services/tahp/bug-analysis.ts) |
| gerrit | 仿 [gerrit-review.ts](../../../tahp-console/packages/server/src/services/tahp/gerrit-review.ts) 走 Agent Bridge 调 `gerrit-submit` Skill | 待新建 |

### 事件订阅（进程内，不改对外协议）

| 源 | 钩子 | 适配文件 |
|---|---|---|
| Agent 类任务 | `getTaskStream().on('event')` | `sources/task-stream.ts` |
| 自检 / 刷机 | `device-self-check.onEvent()` `:425-430` | `sources/self-check.ts` |

---

## 七、已确认的业务约束

以下几条来自需求确认，实现时**不得擅自更改**：

### 7.1 适配必须逐域串行

`per-domain CR` 要求能区分「哪个文件是哪个域改的」。git 只知道文件变了，不知道归属，因此必须**每个域适配完立即打一次 git 快照**，用相邻快照差集归属该域。这决定了 `stages/adapt.ts` 是串行 fan-out，不是并行。

**不要用适配报告的 `file_changes` 做变更判定。** 它是从工具 preview 和 LLM 回复正文里正则推断的（见 [adapt-agent-report.ts](../../../tahp-console/packages/server/src/services/tahp/adapt-agent-report.ts) `:139-178`），会漏也会多。**git 是唯一真相源**，`file_changes` 仅供 UI 展示。

### 7.2 同文件跨域冲突必须拦截

两个域改同一文件时（如 TP 与 LCM 都改 `*_touch.dtsi`），按域拆 CR 会出错。`stages/gerrit.ts` 必须检测快照重叠，命中即转 `waiting_human`，**禁止自动提交**。

### 7.3 跨 run 资源冲突必须在启动前拦截

编译 workspace、自检设备、同域适配任务都是独占资源。两个 run 抢同一个会互相破坏（产物覆盖、设备抢占、任务误杀）。
`POST /runs/:runId/start` 必须先做冲突检测，命中即拒绝启动并告知占用者。
**不实现资源排队**——检测到就拒绝，由用户决定。详见 [reference.md 第 10 节](reference.md#10-并发与资源占用)。

### 7.4 恢复点必须由产物新鲜度推导

**禁止**在 UI 或 API 上开放「任选节点恢复」而不做新鲜度校验。理由见 4.4：从过期产物恢复会产生**静默的错误结论**，比直接报错危险得多。

具体要求：

- 恢复点候选一律走 `computeResumePoints()`，**不得**在前端另写一套判断
- `source` 是否变更用 git 快照指纹判定，**不得**改成让用户勾选「我改过代码」
- 允许 `force` 从 unsafe 节点恢复，但必须二次确认并记进 `iterations[].note`

---

## 八、分期路线

完整任务清单见 [implementation.md](implementation.md)。顺序的核心思想是**先让流程能端到端跑通（节点全手工），再逐个自动化**。

| 期 | 内容 | 产出 |
|---|---|---|
| **F0** | types / registry / workflow / store | 地基 |
| **F1** | 编排器（含产物失效传播与恢复点计算）+ 能力工厂 + 事件源 | 状态机可跑 |
| **F2** | `prereq` + `adapt` 阶段（真实） | 前两节点自动化 |
| **F3** | 其余 6 个阶段（`manual_gate` 占位） | **流程端到端可跑通** |
| **F4** | REST 路由 + `pipeline.*` 事件 + 启动恢复 | 可编程 |
| **F5** | UI：步进条 + 看板骨架 | **可视化** |
| **F6** | UI：节点面板 + 人工介入 + 恢复点选择器 + 迭代条 | 交互完整 |
| **F7** | `git-snapshot.ts`（同时提供 source 指纹） | 变更真相源 |
| **F8** | `flash` + `selfcheck` 实装 | |
| **F9** | `triage` + `human_review` 实装 + 回环闭合 | |
| **F10** | `gerrit` 实装 + 冲突检测 | |
| **F11** | **接入 P1 编译能力**（只写 adapter，约 30 行） | |
| **F12** | 专用渲染器 + 流程编排 Tab | |

每期独立成一个提交，控制在 8 个文件内（工作区变更控制规则）。

---

## 九、边界（禁止事项）

- **禁止**修改 `adapt-agent.ts` / `device-self-check.ts` / `device-flash.ts` / `bug-analysis.ts` 的对外接口。需要新钩子时优先用进程内事件订阅
- **禁止**在编排层写业务逻辑（组件推导、用例筛选、日志解析都归各自 service）
- **禁止**引入工作流引擎依赖、规则引擎、DAG 库、状态机库
- **禁止**为了流水线去改 `paths.ts` / `unified-config.ts` / `jira-workspace.ts` / `hermes-agent-main/`
- **禁止**在没有 `probe()` 的情况下硬调用未就绪能力

---

## 十、验证

```bash
cd tahp-console
npm run setup                       # 首次
npx vitest run tests/server/adapt-pipeline-workflow.test.ts
npx vitest run tests/server/adapt-pipeline-orchestrator.test.ts
npm test                            # 发 MR 前全量
npm run build                       # 改 TS/路由必跑
```

每期的具体验收项见 [implementation.md](implementation.md) 各期「验收」小节。

手动冒烟（F6 之后可做）：

1. `/#/tahp/pipeline` → 新建运行 → 选项目 → 启动
2. 步进条出现 8 个节点，`prereq` / `adapt` 自动跑
3. 走到 `build` 停在橙色 `waiting_human`，提示「编译能力尚未接入」
4. 点「已手工完成，继续」→ 流程推进到 `flash`
5. 模拟 `flash` 失败 → 恢复点选择器在**未改代码**时推荐 `flash`；改一个文件后推荐变 `build`
6. 重启 BFF → 刷新页面 → run 状态与阶段进度**完整恢复**
