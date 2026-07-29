# adapt-pipeline — 数据模型与契约参考

> 配套 [SKILL.md](SKILL.md)。本文件是实现时的**精确依据**，类型以本文件为准。
> 全部类型集中定义在 `services/tahp/adapt-pipeline/types.ts`，不允许在别处重复声明。

## 目录

- [1. 核心类型](#1-核心类型)
- [2. StageDefinition](#2-stagedefinition)
- [3. ExternalCapability](#3-externalcapability)（★ 交给 P1 的契约）
- [4. WorkflowDefinition](#4-workflowdefinition)
- [5. 事件源与观察事件](#5-事件源与观察事件)
- [6. REST API](#6-rest-api)
- [7. pipeline.* 事件协议](#7-pipeline-事件协议)
- [8. 持久化布局](#8-持久化布局)
- [9. 各阶段输入输出速查](#9-各阶段输入输出速查)
- [10. 并发与资源占用](#10-并发与资源占用)
- [11. 断点恢复](#11-断点恢复)（★ 失败后从任意安全节点继续）

---

## 1. 核心类型

```typescript
export type RunStatus =
  | 'draft' | 'running' | 'waiting_human' | 'paused'
  | 'passed' | 'failed' | 'aborted'

export type StageStatus =
  | 'pending' | 'running' | 'waiting_human' | 'done' | 'failed' | 'skipped'

export interface PipelineRun {
  run_id: string                       // run-{timestamp}-{hex6}
  workflow_id: string
  workflow_version: number

  /* 项目上下文 */
  project_code: string
  campaign_id?: string
  from_os?: string
  to_os?: string

  /* 运行态 */
  status: RunStatus
  current_node: string | null          // WorkflowNode.key；END 时为 null
  iteration: number                    // 从 1 开始
  max_iterations: number
  created_at: string
  updated_at: string
  finished_at?: string
  abort_reason?: string

  /* 适配域（prereq 阶段填充，adapt 阶段串行消费） */
  domains: PipelineDomain[]

  /* 编译上下文（新建运行时确定） */
  build_context: BuildContext

  /* 自检目标 */
  device_id?: string
  test_plan?: TestPlan

  /* 各节点运行态，key = WorkflowNode.key */
  stages: Record<string, StageState>

  /* 迭代历史，用于收敛曲线 */
  iterations: IterationRecord[]

  /* 产物新鲜度台账 —— 断点恢复的判定依据（见第 11 节） */
  artifacts: Partial<Record<ArtifactKind, ArtifactState>>

  /* 产出 */
  gerrit_changes?: GerritChangeRef[]
}

export interface PipelineDomain {
  workspace_id: string                 // adapt-debug | feature-adapt | carrier-config
  domain_id: string                    // tp | lcm | charging | ...
  domain_label: string
  module: string                       // telephony | kernel-driver | ...
  related_skills: string[]
  form_data: Record<string, unknown>
  incomplete_required: string[]
  enabled: boolean                     // 用户可在新建向导里取消勾选
  status: 'pending' | 'running' | 'done' | 'failed' | 'skipped'
  adapt_task_id?: string
  /** git 快照差集 —— 该域的真实变更文件（唯一真相源） */
  changed_files?: string[]
  error?: string
}

export interface BuildContext {
  mapped_root: string                  // 如 Z:\
  workspace: string                    // Linux 相对路径，如 project/KM9_NEW
  components: string[]                 // 全量组件集合
  variant: string                      // userdebug | user
  parallel_profile?: 'mtk' | 'qcom'
  markets?: string[]
}

export interface TestPlan {
  mode: 'recommend' | 'fixed'
  test_type?: string                   // fixed 模式使用
  selected_cases?: string[]            // recommend 模式产出的 caseKey 列表
  must_test_items?: string[]           // 推荐引擎的输入，便于复现
}

export interface StageState {
  key: string
  status: StageStatus
  started_at?: string
  finished_at?: string
  attempt: number                      // 本节点在当前 run 内第几次执行
  /** 外部任务引用 —— 编排层只存引用，不复制业务数据 */
  refs: StageRefs
  /** 阶段自报进度，结构由各阶段自定 */
  progress?: Record<string, unknown>
  /** 完成摘要，用于 UI 与迭代记录 */
  summary?: Record<string, unknown>
  /** waiting_human 时的说明与可选动作 */
  human?: { reason: string; message: string; actions: HumanAction[] }
  error?: string
  /** 能力探测结果 */
  availability?: StageAvailability
}

export interface StageRefs {
  adapt_task_ids?: string[]
  build_run_id?: string
  flash_log_path?: string
  selfcheck_report_id?: string
  selfcheck_device_id?: string
  bug_task_ids?: string[]
  gerrit_task_id?: string
  [k: string]: unknown                 // 允许新阶段自定义引用键
}

export interface HumanAction {
  id: string                           // confirm_done | skip | retry | abort | ...
  label: string
  /** 需要用户填写的字段，为空则是纯按钮 */
  fields?: Array<{ name: string; label: string; required?: boolean; placeholder?: string }>
  danger?: boolean
}

export interface IterationRecord {
  index: number
  started_at: string
  finished_at?: string
  verdict: 'passed' | 'failed' | 'running' | 'aborted'
  failed_case_count?: number
  triage_task_id?: string
  /** 本轮由哪个节点恢复启动（非首轮时有值） */
  resumed_from?: string
  note?: string
}

/** 流水线产物类型 —— 断点恢复靠它推导「哪些节点现在还能安全进入」 */
export type ArtifactKind =
  | 'prereq'      // 域清单与前置表单
  | 'source'      // 工作区代码状态
  | 'build'       // 编译产物
  | 'flashed'     // 设备上已刷入的镜像
  | 'testresult'  // 自检报告
  | 'triage'      // 故障分析结论

export interface ArtifactState {
  kind: ArtifactKind
  produced_by: string                  // 产出它的节点 key
  produced_at: string
  /** 内容指纹。source 用 git 快照哈希，其余可用产物路径 + mtime */
  fingerprint?: string
  /** 被上游重新产出而失效 */
  stale: boolean
  /** 失效原因，直接展示给用户，如「代码已变更」 */
  stale_reason?: string
}

export interface GerritChangeRef {
  domain_id: string
  repo: string
  change_url?: string
  change_number?: string
  status: 'pending' | 'submitted' | 'failed' | 'blocked_conflict'
  files: string[]
  error?: string
}
```

---

## 2. StageDefinition

```typescript
export interface StageAvailability {
  available: boolean
  reason?: string                      // 不可用原因，直接展示给用户
  version?: string
  detail?: Record<string, unknown>
}

export type StageVerdict =
  | { status: 'running'; progress?: Record<string, unknown> }
  | { status: 'done'; summary?: Record<string, unknown> }
  /** produced：失败但仍产出了有效产物时声明（如自检用例失败仍有报告），见第 11 节 */
  | { status: 'failed'; error: string; retryable?: boolean; produced?: ArtifactKind[] }
  | { status: 'waiting_human'; reason: string; message: string; actions: HumanAction[] }
  | { status: 'skipped'; reason: string }

export interface StageContext {
  run: Readonly<PipelineRun>
  node: Readonly<WorkflowNode>
  state: Readonly<StageState>
  /** 合并式更新本阶段状态，会触发持久化与 pipeline.stage_progress */
  patchState(patch: Partial<StageState>): void
  /** 更新 run 级字段（如 domains[].changed_files），仅限阶段职责范围内 */
  patchRun(patch: Partial<PipelineRun>): void
  /** 追加一行日志，进入 stage 日志环形缓冲并推送前端 */
  log(line: string): void
}

export interface StageDefinition {
  key: string
  label: string
  /** 本阶段消费的产物；恢复到本节点时这些必须全部新鲜（见第 11 节） */
  consumes?: ArtifactKind[]
  /** 本阶段成功后产出/刷新的产物；下游依赖它的产物自动转 stale */
  produces?: ArtifactKind[]
  /** 人工门节点（恒等人操作）。回环边的源节点必须是它，防止机器自转 */
  isHumanGate?: boolean
  /** 缺省视为始终可用 */
  probe?(ctx: { run: Readonly<PipelineRun> }): Promise<StageAvailability>
  start(ctx: StageContext): Promise<void>
  observe?(ctx: StageContext, ev: ObservedEvent): void
  evaluate(ctx: StageContext): StageVerdict
  handleHumanAction?(ctx: StageContext, actionId: string, payload?: Record<string, unknown>): Promise<void>
  cancel?(ctx: StageContext): Promise<void>
}
```

### 调用时序

```
orchestrator.enter(node)
  ├─ probe()               —— 有则调；不可用 → 按 node.onUnavailable 处理
  ├─ start()               —— 置 running
  ├─ evaluate()            —— 立即判定一次（同步完成的阶段可直接 done）
  └─ 每次 observe() 后再 evaluate()
```

`evaluate` 必须是**纯函数**（只读 ctx，不产生副作用）。副作用一律放 `start` / `observe` / `handleHumanAction`。

---

## 3. ExternalCapability

> ★ **这是交给 P1 编译开发同事的接口契约。** 实现这 5 个方法即可被流水线接入，无需了解编排层。

```typescript
export interface CapabilityStatus {
  state: 'pending' | 'running' | 'success' | 'failed' | 'cancelled'
  progress?: number                    // 0..100
  phase?: string                       // 如 'repo' | 'build' | 'package'
  message?: string
  result?: Record<string, unknown>     // 成功时的结构化产出
  error?: string
}

export interface CapabilityEvent {
  type: 'log' | 'phase' | 'progress' | 'done'
  line?: string
  phase?: string
  progress?: number
  status?: CapabilityStatus
}

export interface ExternalCapability<TInput = unknown> {
  readonly id: string
  /** 能力是否可用（依赖是否就绪、外部服务是否可达） */
  probe(): Promise<StageAvailability>
  /** 启动一次执行，返回可用于查询的 runId */
  start(input: TInput): Promise<{ runId: string }>
  /** 查询状态，编排器兜底轮询用 */
  getStatus(runId: string): Promise<CapabilityStatus>
  /** 取消 */
  cancel(runId: string): Promise<void>
  /** 可选：流式订阅；提供则编排器优先用它，不再轮询 */
  subscribe?(runId: string, onEvent: (ev: CapabilityEvent) => void): () => void
}
```

### 编译能力的输入约定

```typescript
export interface BuildCapabilityInput {
  mappedRoot: string
  workspace: string
  mode: 'full' | 'incremental'
  components: string[]
  variant: string
  parallelProfile?: 'mtk' | 'qcom'
  markets?: string[]
}

// 成功时 CapabilityStatus.result 期望包含：
export interface BuildCapabilityResult {
  artifactsDir?: string                // Linux 侧产物目录
  artifacts?: Array<{ name: string; path: string; sizeBytes?: number }>
  durationMs?: number
  failedStage?: string                 // 失败时
}
```

### createCapabilityStage 工厂

```typescript
export function createCapabilityStage<TInput>(opts: {
  key: string
  label: string
  capability: ExternalCapability<TInput> | null   // null → 恒定不可用，走 manual_gate
  consumes?: ArtifactKind[]                       // 原样透传给 StageDefinition
  produces?: ArtifactKind[]
  buildInput: (ctx: StageContext) => TInput
  /** 可选：把 result 写回 run（如产物路径给 flash 用） */
  onSuccess?: (ctx: StageContext, result: Record<string, unknown>) => void
  pollIntervalMs?: number                         // 默认 5000
}): StageDefinition
```

工厂已内置：`probe` 转发、`refs` 写入、轮询 / 订阅二选一、`cancel` 转发、失败信息透传。
**新增外部长任务类节点一律用它，不要手写。**

---

## 4. WorkflowDefinition

```typescript
export type NodeTarget = string | 'END' | 'ABORT'

export interface WorkflowNode {
  key: string                          // → StageDefinition.key
  enabled: boolean
  /** 缺省 'manual_gate'：忘了声明时停下等人，而非静默跳过或炸掉流程 */
  onUnavailable?: 'manual_gate' | 'skip' | 'fail'
  onDone?: NodeTarget                  // 缺省 = 数组下一个 enabled 节点
  onFail?: NodeTarget                  // 缺省 = 'ABORT'
  /**
   * 转移时的副作用。`increment_iteration` 是**条件**自增：
   * 仅当 source 指纹相较本轮开始时已变更才 +1。
   * 纯环境重试（没改代码）不占用迭代额度，收敛曲线才有意义。
   */
  onDoneEffect?: 'increment_iteration'
  params?: Record<string, unknown>
  /** 该节点最大重试次数，超出转 waiting_human。默认 0 */
  maxAttempts?: number
}

export interface WorkflowDefinition {
  id: string
  version: number
  label: string
  maxIterations: number
  nodes: WorkflowNode[]
}
```

### 默认流程 `DEFAULT_WORKFLOW`

```typescript
export const DEFAULT_WORKFLOW: WorkflowDefinition = {
  id: 'adapt-default',
  version: 1,
  label: '标准适配流水线',
  maxIterations: 3,
  nodes: [
    { key: 'prereq',       enabled: true, onUnavailable: 'fail' },
    { key: 'adapt',        enabled: true, onUnavailable: 'fail' },
    { key: 'build',        enabled: true, onUnavailable: 'manual_gate', onFail: 'human_review' },
    { key: 'flash',        enabled: true, onUnavailable: 'manual_gate', onFail: 'human_review' },
    { key: 'selfcheck',    enabled: true, onUnavailable: 'manual_gate', onDone: 'gerrit', onFail: 'triage' },
    { key: 'triage',       enabled: true, onUnavailable: 'skip',        onDone: 'human_review', onFail: 'human_review' },
    // onDone: 'build' 只是「用户没显式选恢复点」时的兜底；
    // 正常路径由 confirm_done 携带的 resume_node 决定目标（见第 11 节）
    { key: 'human_review', enabled: true, onUnavailable: 'fail',        onDone: 'build', onDoneEffect: 'increment_iteration' },
    { key: 'gerrit',       enabled: true, onUnavailable: 'manual_gate', onDone: 'END', onFail: 'human_review' },
  ],
}
```

### 校验规则（`validateWorkflow`）

启动 run 前必须通过，任一不满足即拒绝：

1. `nodes` 非空，`key` 唯一
2. 每个 `key` 都能在 `StageRegistry` 找到
3. 所有 `onDone` / `onFail` 目标存在于 `nodes`，或为 `END` / `ABORT`
4. 至少有一条路径可达 `END`
5. `maxIterations >= 1`
6. 回环边（目标节点在数组中更靠前）必须带 `onDoneEffect: 'increment_iteration'`，否则判为死循环
7. 回环边的**源节点** `StageDefinition.isHumanGate` 必须为 `true`

> 第 7 条是第 6 条的补丁。`increment_iteration` 改成条件自增后，第 6 条不再能兜住死循环：
> 若有人把 `selfcheck.onFail` 直接指回 `build`，而代码没变，就会无人值守地反复编译（每轮 4–8h）。
> 要求回环必经人工门，保证机器永远不会自己转圈。

### 产物依赖声明

各阶段的 `consumes` / `produces`，恢复点计算完全依据这张表：

| 节点 | consumes | produces |
|---|---|---|
| `prereq` | — | `prereq` |
| `adapt` | `prereq` | `source` |
| `build` | `source` | `build` |
| `flash` | `build` | `flashed` |
| `selfcheck` | `flashed` | `testresult` |
| `triage` | `testresult` | `triage` |
| `human_review` | `triage` | `source`（人工改代码即产出新 source） |
| `gerrit` | `source` + `testresult` | — |

`human_review` 产出 `source` 这一条是整个模型的枢纽：它让「人改了代码 ⇒ build/flashed/testresult 全部失效 ⇒ 只能从 build 重来」成为**自动推导**的结论，而不是写死在流程定义里的规则。

### 覆盖机制

`.tahp-config/adapt-pipeline/workflow.json` 存在且 `validateWorkflow` 通过时使用它，否则回落 `DEFAULT_WORKFLOW` 并记 warn 日志。**校验不通过绝不静默使用坏定义。**

---

## 5. 事件源与观察事件

```typescript
export interface ObservedEvent {
  source: 'task-stream' | 'self-check' | 'capability'
  type: string                         // 原始事件名，如 task.completed / case_completed
  /** 用于路由到具体 run/stage 的关联键 */
  correlation: { taskId?: string; deviceId?: string; runId?: string }
  payload: Record<string, unknown>
  ts: number
}

export interface PipelineEventSource {
  id: string
  subscribe(onEvent: (ev: ObservedEvent) => void): () => void
}
```

### 现有两个源

| 文件 | 包装对象 | 关联键 |
|---|---|---|
| `sources/task-stream.ts` | `getTaskStream().on('event')` | `taskId` ← `ev.task_id` |
| `sources/self-check.ts` | `device-self-check.onEvent()` `:425-430` | `deviceId` ← `payload.deviceId` |

#### ⚠ 两个源的能力不对称，实现方式不同

**`task-stream`** — `TaskStream extends EventEmitter`（[task-stream.ts](../../../tahp-console/packages/server/src/services/tahp/task-stream.ts) `:19`），
`.on('event', h)` / `.off('event', h)` 均可用，可直接按标准模式实现 `subscribe` 返回反注册函数。

**`self-check`** — 现有 `onEvent(eventName, callback)` 有两个硬限制：

1. **只接受具名事件**，没有通配订阅
2. **没有 `offEvent`，无法反注册**（`eventListeners[name]` 只增不减）

因此 `sources/self-check.ts` **不能**直接把 `onEvent` 包成 `subscribe`。正确写法是**模块初始化时一次性注册，内部再做扇出**：

```typescript
const SELF_CHECK_EVENTS = [
  'flash_log', 'flash_completed',
  'case_completed', 'test_completed', 'test_ended', 'test_error',
  'report_ready', 'precheck_failed', 'manual_confirm',
] as const

const fanout = new Set<(ev: ObservedEvent) => void>()
let installed = false

function install() {
  if (installed) return          // ★ 幂等保护：onEvent 无法反注册，重复安装会导致事件重复投递
  installed = true
  for (const name of SELF_CHECK_EVENTS) {
    onEvent(name, (data: any) => {
      const ev: ObservedEvent = {
        source: 'self-check',
        type: name,
        correlation: { deviceId: data?.deviceId },
        payload: data ?? {},
        ts: Date.now(),
      }
      for (const cb of fanout) cb(ev)
    })
  }
}

export const selfCheckSource: PipelineEventSource = {
  id: 'self-check',
  subscribe(onEv) {
    install()
    fanout.add(onEv)
    return () => { fanout.delete(onEv) }   // 反注册只摘扇出，底层监听常驻
  },
}
```

**不要**为此给 `device-self-check.ts` 加 `offEvent`——底层监听常驻不会造成泄漏（编排器是进程内单例），加接口反而违反变更控制。

新增自检事件名时，往 `SELF_CHECK_EVENTS` 追加即可。

### 路由规则

编排器维护 `correlationIndex: Map<string, { runId, nodeKey }>`。阶段 `start()` 写 `refs` 时，编排器自动把 `refs` 里的 id 注册进索引；事件到达时按 `correlation` 反查，只投递给对应 run 的对应 stage 的 `observe()`。

**不匹配的事件直接丢弃**，不做广播——这是避免流水线被无关事件淹没的关键。

---

## 6. REST API

前缀 `/api/tahp/adapt-pipeline`，统一信封 `{ success, data?, error? }`（沿用 `routes/tahp/*` 约定）。

| Method | Path | Body / Query | 返回 |
|---|---|---|---|
| POST | `/runs` | `CreateRunRequest` | `{ run_id, domains, workflow }` |
| GET | `/runs` | `?status=&limit=&offset=` | `{ items: RunSummary[], total }` |
| GET | `/runs/:runId` | — | `PipelineRun` |
| GET | `/runs/:runId/timeline` | — | `TimelineView`（★ UI 主数据源） |
| POST | `/runs/:runId/start` | — | `{ ok: true }` |
| POST | `/runs/:runId/human-action` | `{ node, action_id, payload? }` | `{ ok: true }` |
| GET | `/runs/:runId/resume-points` | — | `{ points: ResumePoint[], recommended: string \| null }` |
| POST | `/runs/:runId/resume` | `ResumeRequest` | `{ ok: true, iteration }` |
| POST | `/runs/:runId/pause` | — | `{ ok: true }` |
| POST | `/runs/:runId/abort` | `{ reason? }` | `{ ok: true }` |
| GET | `/runs/:runId/logs/:node` | `?tail=500` | `{ lines: string[] }` |
| GET | `/prereqs/:projectCode` | `?campaign_id=` | 转发 `resolveAdaptPrereqs` 并归一为 `PipelineDomain[]` |
| GET | `/workflow` | — | 当前生效的 `WorkflowDefinition` + 各节点 `probe()` 结果 |
| PUT | `/workflow` | `WorkflowDefinition` | 校验后落盘 |
| GET | `/capabilities` | — | `Array<{ key, label, availability }>` |

### CreateRunRequest

```typescript
interface CreateRunRequest {
  project_code: string
  campaign_id?: string
  domain_ids?: string[]                // 不传 = 全部 enabled
  build_context: BuildContext
  device_id?: string
  test_plan?: TestPlan
  max_iterations?: number
  workflow_id?: string
}
```

### TimelineView（UI 主数据源）

```typescript
interface TimelineView {
  run_id: string
  project_code: string
  status: RunStatus
  iteration: number
  max_iterations: number
  current_node: string | null
  started_at: string
  duration_ms: number
  nodes: Array<{
    key: string
    label: string
    status: StageStatus
    enabled: boolean
    duration_ms?: number
    progress?: { percent?: number; text?: string }
    summary_line?: string              // 一行摘要，如 "5/5 域完成"
    unavailable_reason?: string
    human?: { reason: string; message: string; actions: HumanAction[] }
    is_loop_target?: boolean           // 回环目标，UI 画弧线
  }>
  iterations: IterationRecord[]
  pending_human_count: number
}
```

**前端不得硬编码节点列表**，一律按 `nodes` 渲染。

---

## 7. pipeline.* 事件协议

复用 `TaskStream` + Socket.IO `/tahp-run`（[task-stream.ts](../../../tahp-console/packages/server/src/services/tahp/task-stream.ts)）。所有 payload **必带 `run_id`**。

| 事件 | payload 关键字段 |
|---|---|
| `pipeline.run_started` | `run_id, project_code, workflow_id, nodes[]` |
| `pipeline.node_changed` | `run_id, from, to, iteration, reason` |
| `pipeline.node_progress` | `run_id, node, status, percent?, text?, summary_line?` |
| `pipeline.node_log` | `run_id, node, line` |
| `pipeline.waiting_human` | `run_id, node, reason, message, actions[]` |
| `pipeline.human_resolved` | `run_id, node, action_id` |
| `pipeline.resumed` | `run_id, from_node, resume_node, scope, forced, source_changed, iteration` |
| `pipeline.iteration_started` | `run_id, iteration, trigger` |
| `pipeline.run_completed` | `run_id, verdict, duration_ms, summary` |
| `pipeline.run_failed` | `run_id, error, node` |

### 前端订阅策略

- 看板页只订阅 `pipeline.*`，按 `run_id` 过滤
- **不订阅**底层 `task.*` / 自检 SSE。点开某节点详情时才按 `refs` 里的 id 复用现有 `useTahpTasksStore` 或自检 SSE 拉详细日志
- `pipeline.node_log` 做客户端节流（≥200ms 合批），避免编译日志刷爆

---

## 8. 持久化布局

```
{projectRoot}/.tahp-config/adapt-pipeline/
├── workflow.json                 # 可选，覆盖默认流程
├── policy.json                   # 默认 build_context / 用例策略 / 迭代上限
├── index.json                    # run 摘要索引（列表页用，避免全量读）
└── runs/
    └── {runId}.json              # PipelineRun 全量
```

日志单独存，不进 run JSON（避免文件膨胀）：

```
{projectRoot}/reports/adapt-pipeline/{runId}/
├── {node}.log                    # 每节点一份，追加写
└── summary.json                  # 结束时归档
```

### 写入策略

- `patchState` 触发**防抖写盘**（500ms），避免高频事件打爆磁盘
- 节点转移、`waiting_human`、run 终态 → **立即同步写盘**
- `index.json` 只在 run 创建 / 状态变更时更新

### 恢复

`orchestrator.recover()` 在 [index.ts](../../../tahp-console/packages/server/src/index.ts) bootstrap 末尾调用：

1. 读 `index.json`，筛出 `running` / `waiting_human`
2. 逐个读回 run，重建 `correlationIndex`
3. 重新挂事件订阅
4. 对 `running` 节点调 `evaluate()` 复判（外部任务可能已在停机期间结束）
5. 外部任务已不存在 → 转 `waiting_human`，reason = `lost_after_restart`

---

## 9. 各阶段输入输出速查

| 阶段 | 读 run | 写 run | 外部调用 | done 判据 |
|---|---|---|---|---|
| `prereq` | `project_code`, `campaign_id` | `domains[]`, `from_os`, `to_os` | `resolveAdaptPrereqs()` | 所有 enabled 域 `incomplete_required` 为空 |
| `adapt` | `domains[]` | `domains[].adapt_task_id`, `.changed_files`, `.status` | `startAdaptAgentRun()` × N **串行** + git 快照 | 全部 enabled 域 done |
| `build` | `build_context`, `iteration` | `stages.build.summary.artifacts` | `buildCapability`（未就绪→manual_gate） | `CapabilityStatus.state === 'success'` |
| `flash` | `device_id`, build 产物 | `refs.flash_log_path` | `runDeviceFlash()` | SSE `flash_completed.success === true` |
| `selfcheck` | `device_id`, `domains[]`, `test_plan` | `refs.selfcheck_report_id`, `summary.failed_cases` | `recommendTestCasesWithMeta()` → `startCustomTest()` | 报告就绪且 `failed === 0` |
| `triage` | selfcheck 失败摘要 | `refs.bug_task_ids` | 证据打包 → `POST /bug-analysis/local` | 分析报告就绪 |
| `human_review` | 全部 | `iterations[]` | 无 | 用户点 `confirm_done` |
| `gerrit` | `domains[].changed_files` | `gerrit_changes[]` | Agent Bridge → `gerrit-submit` Skill | 全部域 CR 提交成功 |

### selfcheck 失败语义区分

`evaluate` 返回 `failed` 时，`summary.failure_kind` 必须区分：

- `case_failed` — 用例失败，正常走 `triage`
- `infra_error` — 设备掉线 / 刷机异常 / Python 崩溃

`triage.start()` 读到 `infra_error` 时**不调 bug-analysis**，直接返回 `waiting_human`（分析用例失败的 AI 解决不了环境问题）。这是阶段内部逻辑，不污染流程定义。

---

## 10. 并发与资源占用

多个 run 同时存在时会争抢三类独占资源。**F4 实现 `POST /runs/:runId/start` 时必须一并处理**，否则两个 run 会互相破坏。

| 资源 | 冲突后果 | 处理 |
|---|---|---|
| **编译 workspace** | 两个 run 编同一 `mapped_root + workspace`，产物互相覆盖，自检结果失真 | 启动前校验：已有 `running` / `waiting_human` 的 run 占用同一 workspace 时**拒绝启动**，返回占用者 `run_id` |
| **自检设备** | `startTest` 要求设备 `空闲`，第二个 run 会直接失败 | 同上，`device_id` 已被占用则拒绝启动 |
| **同域适配任务** | `AdaptDebugView` 会自动 cancel 同域旧任务，跨 run 会误杀 | adapt 阶段启动前检查该域是否有其他 run 的活跃任务，有则 `waiting_human` |

### 实现

```typescript
// store.ts
export function findResourceConflict(candidate: PipelineRun): ResourceConflict | null
// 返回 { kind: 'workspace' | 'device' | 'domain', holderRunId, detail }
```

- 只与 `running` / `waiting_human` 的 run 比对；终态 run 不占资源
- 冲突信息要能直接展示给用户：「workspace `project/KM9_NEW` 正被 run-xxx 占用」
- **不实现资源队列**——检测到冲突就拒绝并提示，让用户自己决定等待或终止对方。排队调度属于过度设计，当前场景（少量并行项目）用不上

### 与 `test-plan-executor` 的关系

[test-plan-executor.ts](../../../tahp-console/packages/server/src/services/tahp/test-plan-executor.ts) 会自动给空闲设备派测试任务，可能抢走流水线正要用的设备。

当前处理：**不做互斥**。流水线的 `flash` / `selfcheck` 阶段若因设备忙失败，走正常 `onFail` 路径转人工。若实际使用中冲突频繁，再考虑给设备加占用标记——**先不预防性实现**。

---

## 11. 断点恢复

节点失败（编译挂了、烧录设备掉了、自检不过）→ 人工介入修复 → 从**某个节点**继续往下跑，而不是整条重来。

### 11.1 为什么不能让人裸选节点

反例：自检失败 → 人改了驱动代码 → 想省时间直接从 `selfcheck` 重跑。
但设备上刷的还是改代码**之前**的镜像，测出来「通过」，`gerrit` 阶段就把这份代码提交了。
**没有任何报错**，流水线的可信度直接归零。

所以恢复点必须由系统按产物新鲜度推导，人只在推导结果里做选择。

### 11.2 失效传播

节点产出产物时（`done`，或 `failed` 但声明了 `produced`，见 11.4），编排器做两件事：

1. 把每个产物写进 `run.artifacts`，`stale: false`，更新 `produced_at` / `fingerprint`
2. 沿依赖链把**所有下游**产物标记 `stale: true`，并写 `stale_reason`

依赖链由各阶段的 `consumes` / `produces` 声明推出（表见第 4 节），编排器不认识任何具体节点名。

```typescript
// orchestrator.ts
function refreshArtifacts(run: PipelineRun, node: WorkflowNode, kinds: ArtifactKind[]): void
// 刷新 kinds + 沿依赖链传播 stale
```

> ⚠ **依赖图有环**：`source → build → flashed → testresult → triage → source`（最后一跳来自 `human_review`）。
> 传播必须用 `visited` 集合做广度优先，且**起点产物本身不得被标 stale**——
> 否则 `human_review` 刷新 `source` 后会绕一圈把自己刚产出的 `source` 标成过期。

### 11.3 source 指纹：怎么知道人到底改没改代码

**不能靠人自己勾选。** 用 git 快照指纹自动判定，复用 F7 的 `git-snapshot.ts`：

- 进入 `human_review` 时打快照 A，存进 `stages.human_review.progress.snapshot_before`
- 人提交 `confirm_done` 时打快照 B
- `hash(A) !== hash(B)` → source 刷新，`build` / `flashed` / `testresult` 全部 stale
- 相等 → 人只是确认了一下，各产物**保持有效**

这条是「烧录失败不用重编译」和「改了代码必须重编译」两个相反行为的**同一个判据**。

### 11.4 恢复点计算

```typescript
export interface ResumePoint {
  node: string
  label: string
  safety: 'safe' | 'unsafe'
  /** unsafe 时列出缺失或过期的产物 */
  missing?: Array<{ kind: ArtifactKind; reason: string }>
  /** 一句话说明，直接展示，如「编译产物已过期（代码已变更）」 */
  hint?: string
}

export function computeResumePoints(run: PipelineRun): {
  points: ResumePoint[]
  recommended: string | null
}
```

**safety 判定**——遍历 workflow 里所有 `enabled` 节点：

```
missing = (stage.consumes ?? []).filter(k => !run.artifacts[k] || run.artifacts[k].stale)
missing 为空 → 'safe'，否则 'unsafe'
```

**recommended 判定**——按序取第一个命中的：

1. 最靠前的、**`produces` 中含 stale 或缺失产物**、且 `safe` 的节点
2. 若无，取 run 内**最后一个 `failed` 的节点**（若它 `safe`）
3. 再无 → `null`

> 规则 1 不能简化成「最靠前的 safe 节点」。`prereq` / `adapt` 在跑完之后永远是 safe 的，
> 那样会推荐用户重新拉前置信息、重跑一遍 AI 适配——完全不是他想要的。
> 判据是「**它的产出过期了**」，不是「它能进」。
>
> 规则 2 兜的是「什么都没过期但就是要重跑」的场景：自检挂了，人判定是用例本身的问题，
> 没改任何代码。此时全部产物新鲜，规则 1 空手而归，应当推荐重跑失败的那个节点。

#### 失败节点也可能产出有效产物

`selfcheck` 因用例失败而 `failed` 时，它**确实产出了一份有效的测试报告**——`triage` 正是要消费它。
若只在 `done` 时刷新产物，`triage` 会因为 `testresult` 缺失而永远 unsafe。

因此 `failed` 判定可声明产出：

```typescript
| { status: 'failed'; error: string; retryable?: boolean; produced?: ArtifactKind[] }
```

- `done` → 刷新 `stage.produces` 全部
- `failed` → 只刷新 `verdict.produced ?? []`

`selfcheck` 据此区分：`case_failed` 带 `produced: ['testresult']`，`infra_error` 不带。
这也让「`infra_error` 不该进 bug-analysis」从阶段内部的 if 变成产物模型的自然结论。

### 11.5 场景对照

这张表不是规则清单，是上面算法在各场景下的**推导结果**——实现时不要照着写 if：

| 情况 | source 指纹 | 推导 | recommended |
|---|---|---|---|
| 编译失败，人改了 Makefile | 变了 | build/flashed/testresult 全 stale，最靠前的过期产出者是 build | `build` |
| **烧录失败（USB 松了），没改代码** | 未变 | build 新鲜、flashed 缺失 | **`flash`**（省一次 4–8h 编译） |
| 自检失败，人改了驱动代码 | 变了 | 同第一行 | `build` |
| 自检失败，判定是用例本身的问题 | 未变 | 全部产物新鲜 → 规则 1 落空 → 取最后失败节点 | `selfcheck` |
| 自检失败，改了代码却想只跑 selfcheck | 变了 | flashed 已 stale | 推荐 `build`；`selfcheck` 标 unsafe「设备镜像已过期」 |

### 11.6 恢复请求

```typescript
export interface ResumeRequest {
  node: string
  /** 节点内部断点续跑范围，缺省 'continue' */
  scope?: 'continue' | 'restart'
  /** 从 unsafe 节点恢复时必须显式传 true */
  force?: boolean
}
```

`scope` 语义（**缺省增量续跑**，省时间优先）：

| 值 | `adapt` | `build` |
|---|---|---|
| `continue`（默认） | 只跑 `status !== 'done'` 的域 | `mode: 'incremental'` |
| `restart` | 全部域重置为 `pending` 重跑 | `mode: 'full'` |

对没有内部子任务的节点（`flash` / `selfcheck` / `gerrit`），两个值等价。

```typescript
export async function resumeFrom(runId: string, req: ResumeRequest): Promise<void>
```

行为：

```
1. 校验 node 在 workflow 内且 enabled
2. point = computeResumePoints(run).points.find(node)
   point.safety === 'unsafe' && !req.force  → 抛错，返回 409 + missing 明细
3. 若当前停在 human_review：打快照 B，比对 progress.snapshot_before
      不同 → refreshArtifacts(run, human_review, ['source'])，source_changed = true
      相同 → 不动产物，source_changed = false
4. source_changed 时 iteration += 1（超 maxIterations 走既有的 waiting_human 分支）
   未变更则 iteration 不动
5. 把 node 及其**之后**所有节点的 StageState 重置为 pending，attempt 归零
   （之前的 refs / summary 归档进 iterations，不直接丢弃）
6. 按 scope 预置节点入参（adapt 域状态 / build mode）
7. emit pipeline.resumed，enter(runId, node)
```

### 11.7 强制恢复

用户可从 `unsafe` 节点恢复，**二次确认即可**，不额外限制后续提交。

- UI 不隐藏 unsafe 选项，灰显 + 标注具体原因，勾选后弹确认框
- `force: true` 记进 `iterations[].note`，便于事后复盘
- 隐藏选项会让人觉得工具在跟自己作对；标原因才能让人做知情决定

### 11.8 与既有动作的关系

`POST /runs/:runId/retry-node` **不再单独存在**，它是 `resume` 的特例（`{ node: 当前失败节点, scope: 'continue' }`）。

`submitHumanAction` 的 `confirm_done` 支持携带恢复参数：

```typescript
{ node: 'human_review', action_id: 'confirm_done',
  payload: { resume_node: 'flash', resume_scope: 'continue', force: false } }
```

`payload.resume_node` 存在 → 走 `resumeFrom()`；不存在 → 退回 `node.onDone` 的兜底目标。
`human_review` 的 `actions` 由 `evaluate()` **动态生成**：把 `computeResumePoints()` 的结果渲染成候选，而不是写死「已修改，重新编译」一个按钮。
