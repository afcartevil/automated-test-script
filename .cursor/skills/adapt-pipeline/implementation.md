# adapt-pipeline — 分期执行清单

> 配套 [SKILL.md](SKILL.md) · [数据契约](reference.md) · [UI 设计](ui-spec.md)
> 本文件供 AI / 开发按序执行。**每期独立成一个提交，文件数 ≤8**（工作区 `00-change-control` 规则）。

## 执行总纲

1. **顺序不可跳跃**：F1 依赖 F0 的类型，F4 依赖 F3 的 API
2. **每期必须自验收**：完成「验收」全部勾项才进入下一期
3. **类型只在 `types.ts` 定义**，其他文件一律 import
4. **禁止**修改现有业务 service 的对外接口
5. 每期结束跑 `npm run build`；改了逻辑的期跑对应 vitest

根目录：`tahp-console/packages/server/src/services/tahp/adapt-pipeline/`（下称 `AP/`）

---

## 期次总览

| 期 | 目标 | 文件数 | 关键产出 |
|---|---|---|---|
| F0 | 类型 / 注册表 / 流程定义 / 存储 | 5 | 地基 |
| F1 | 编排器（+ 产物失效传播 / 恢复点计算）+ 能力工厂 + 事件源 | 6 | 状态机可跑 |
| F2 | prereq + adapt 阶段（真实） | 4 | 前两节点自动化 |
| F3 | 其余 6 个阶段（manual_gate 占位） | 7 | **流程端到端可跑通** |
| F4 | REST 路由 + 事件 + 启动恢复 | 5 | 可编程 |
| F5 | UI：步进条 + 看板骨架 | 7 | **可视化** |
| F6 | UI：节点面板 + 人工介入 + 恢复点选择器 + 迭代条 | 8 | 交互完整 |
| F7 | git 快照器（+ source 指纹） | 3 | 变更真相源 |
| F8 | flash + selfcheck 实装 | 5 | |
| F9 | triage + human_review 实装 | 4 | 回环闭合 |
| F10 | gerrit 实装 + 冲突检测 | 4 | |
| **F11** | **接入 P1 编译能力** | **2** | 约 30 行 adapter |
| F12 | 专用渲染器 + 流程编排 Tab | 7 | |

---

## F0 · 基础类型与存储

### 文件

| 操作 | 路径 |
|---|---|
| 新增 | `AP/types.ts` |
| 新增 | `AP/registry.ts` |
| 新增 | `AP/workflow.ts` |
| 新增 | `AP/store.ts` |
| 新增 | `tests/server/adapt-pipeline-workflow.test.ts` |

### 要点

**`types.ts`** — 照抄 [reference.md 第 1、2、4 节](reference.md#1-核心类型) 的全部类型，一字不改。这是唯一真相源。

**`registry.ts`**

```typescript
const REGISTRY = new Map<string, StageDefinition>()

export function registerStage(def: StageDefinition): void {
  if (REGISTRY.has(def.key)) throw new Error(`stage already registered: ${def.key}`)
  REGISTRY.set(def.key, def)
}
export function getStage(key: string): StageDefinition | undefined { return REGISTRY.get(key) }
export function listStages(): StageDefinition[] { return [...REGISTRY.values()] }
export function resetRegistryForTest(): void { REGISTRY.clear() }   // 仅测试用
```

**`workflow.ts`** — `DEFAULT_WORKFLOW` 常量 + `validateWorkflow()` + `loadWorkflow()`。

`validateWorkflow` 必须实现 [reference.md 第 4 节](reference.md#校验规则validateworkflow)的 7 条规则，返回 `{ ok: true } | { ok: false; errors: string[] }`。

> 第 7 条（回环源节点必须 `isHumanGate`）是死循环的最后一道防线。
> `increment_iteration` 是**条件**自增（只有代码变了才 +1），所以第 6 条单独已兜不住：
> 若有人把 `selfcheck.onFail` 直接指回 `build` 而代码没变，会无人值守地反复编译。

`loadWorkflow()`：读 `.tahp-config/adapt-pipeline/workflow.json`，校验通过则用之，否则 `logger.warn` 后回落 `DEFAULT_WORKFLOW`。**校验不通过绝不静默使用。**

**`store.ts`**

```typescript
export function createRun(input: CreateRunInput): PipelineRun
export function getRun(runId: string): PipelineRun | null
export function saveRun(run: PipelineRun, opts?: { immediate?: boolean }): void
export function listRuns(filter?: { status?: RunStatus[]; limit?: number; offset?: number }): { items: RunSummary[]; total: number }
export function listActiveRunIds(): string[]      // running | waiting_human，供 recover 用
export function findResourceConflict(candidate: PipelineRun): ResourceConflict | null   // 本期返回 null，F4 补齐
```

- 落盘布局照 [reference.md 第 8 节](reference.md#8-持久化布局)
- `saveRun` 默认 500ms 防抖；`immediate: true` 时同步写
- 目录不存在自动 `mkdirSync({ recursive: true })`
- `index.json` 写入用「临时文件 + rename」保证原子性
- `createRun` 把 `artifacts` 初始化为 `{}`（空 = 全部缺失，只有第一个节点可进入）

### 验收

- [ ] `validateWorkflow(DEFAULT_WORKFLOW)` 通过（注册桩阶段后）
- [ ] 缺失 stage、悬空 onDone 目标、无 `increment_iteration` 的回环 均被拒绝并给出可读 error
- [ ] 回环源节点未标 `isHumanGate` 时被拒绝（第 7 条）
- [ ] `createRun` → `saveRun` → 重新 `getRun` 数据一致
- [ ] `npx vitest run tests/server/adapt-pipeline-workflow.test.ts`

---

## F1 · 编排器与事件源

### 文件

| 操作 | 路径 |
|---|---|
| 新增 | `AP/orchestrator.ts` |
| 新增 | `AP/capability.ts` |
| 新增 | `AP/sources/index.ts` |
| 新增 | `AP/sources/task-stream.ts` |
| 新增 | `AP/sources/self-check.ts` |
| 新增 | `tests/server/adapt-pipeline-orchestrator.test.ts` |

### `orchestrator.ts` 核心

导出：`startRun` / `advance` / `submitHumanAction` / `computeResumePoints` / `resumeFrom` / `pauseRun` / `abortRun` / `recover`

> 没有独立的 `retryNode`——「重跑当前节点」是 `resumeFrom(runId, { node: 当前节点 })` 的特例。

**`enter(runId, nodeKey)`** —— 进入一个节点：

```
1. nodeKey === 'END'   → run.status = 'passed'，emit run_completed，return
2. nodeKey === 'ABORT' → run.status = 'failed'，emit run_failed，return
3. node = workflow.nodes.find(key)；node.enabled === false → enter(下一个 enabled)
4. stage = getStage(node.key)；不存在 → run failed（不应发生，validateWorkflow 已拦）
5. availability = stage.probe ? await stage.probe({ run }) : { available: true }
6. 不可用时按 node.onUnavailable 分支：
     'skip'        → state.status='skipped'，enter(下一个)
     'fail'        → state.status='failed'，transition(node.onFail ?? 'ABORT')
     'manual_gate' → state.status='waiting_human'
                     human = { reason:'capability_unavailable',
                               message: availability.reason ?? '该能力尚未接入',
                               actions:[{id:'confirm_done',label:'已手工完成，继续'},
                                        {id:'skip',label:'跳过'}] }
                     run.status='waiting_human'，emit waiting_human，return
7. state.status='running'，state.started_at=now，attempt++
8. await stage.start(ctx)
9. registerCorrelations(runId, node.key, state.refs)
10. advance(runId)
```

**`advance(runId)`** —— 判定并转移：

```
verdict = stage.evaluate(ctx)
switch (verdict.status):
  'running'       → patch progress，emit node_progress，return
  'waiting_human' → state.status='waiting_human'，run.status='waiting_human'
                    state.human = verdict，emit waiting_human，return
  'skipped'       → state.status='skipped'，transition(下一个)
  'done'          → state.status='done'，finished_at=now，summary=verdict.summary
                    refreshArtifacts(run, node, stage.produces ?? [])      ★ 见下
                    transition(node.onDone ?? 下一个 enabled, node.onDoneEffect)
  'failed'        → state.error=verdict.error
                    refreshArtifacts(run, node, verdict.produced ?? [])    ★ 失败也可能有有效产物
                    若 verdict.retryable && attempt < (node.maxAttempts ?? 0) → 重跑 enter
                    否则 state.status='failed'，transition(node.onFail ?? 'ABORT')
```

**`refreshArtifacts(run, node, kinds)`** —— 产物台账维护，是断点恢复的全部基础（[reference.md 11.2](reference.md#112-失效传播)）：

```
for kind of kinds:
    run.artifacts[kind] = { kind, produced_by: node.key, produced_at: now,
                            fingerprint: 阶段回填的指纹, stale: false }
BFS 从 kinds 出发沿依赖图向下游走，visited 去重，跳过 kinds 本身:
    run.artifacts[downstream].stale = true
    run.artifacts[downstream].stale_reason = `${上游 kind} 已更新`
```

调用时机：

- `verdict.status === 'done'` → `kinds = stage.produces ?? []`
- `verdict.status === 'failed'` → `kinds = verdict.produced ?? []`
  （自检用例失败仍产出有效报告，`triage` 要消费它）

依赖图在模块加载时由各 `StageDefinition` 的 `consumes` / `produces` 一次性推导成 `Map<ArtifactKind, ArtifactKind[]>`。

> ⚠ **图里有环**：`source → build → flashed → testresult → triage → source`（末跳来自 `human_review`）。
> 必须用 `visited` 集合，且起点产物本身不参与标记，否则 `human_review` 刚刷新的 `source` 会被自己绕一圈标成过期。

**编排器不得出现任何具体节点名或产物名的硬编码。**

**`transition(runId, target, effect?)`**：

```
若 effect === 'increment_iteration':
    ★ 条件自增：source 指纹相较本轮开始时未变化 → 跳过自增，直接转移
      （纯环境重试不占迭代额度，否则收敛曲线失真、额度被白白烧掉）
    next = run.iteration + 1
    若 next > workflow.maxIterations:
        run.status = 'waiting_human'
        挂 human = { reason:'max_iterations_exceeded',
                     actions:[{id:'extend',label:'继续加一轮'},{id:'abort',label:'终止',danger:true}] }
        return
    run.iteration = next
    push iterations 记录，emit iteration_started
清理离开节点的 correlation
emit node_changed
enter(runId, target)
```

**`submitHumanAction(runId, node, actionId, payload)`**：

```
'confirm_done' → payload.resume_node 存在 → resumeFrom(runId, {node,scope,force})
                 否则 视为该节点 done，refreshArtifacts + transition(onDone)
'skip'         → state.status='skipped'，transition(下一个)
'retry'        → resumeFrom(runId, { node: 同节点, scope: 'continue' })
'abort'        → abortRun
'extend'       → maxIterations++（仅本 run），继续 transition
其他           → 交给 stage.handleHumanAction()，之后 advance()
```

**`computeResumePoints(run)` / `resumeFrom(runId, req)`** —— 照 [reference.md 11.4 / 11.6](reference.md#114-恢复点计算) 实现。

要点：

- `computeResumePoints` 是**纯函数**，只读 `run.artifacts` 与各 stage 的 `consumes`，可单测
- `recommended` 三条规则照 [reference.md 11.4](reference.md#114-恢复点计算) 实现。
  **不要**简化成「最靠前的 safe 节点」——`prereq` / `adapt` 跑完后恒 safe，那样会推荐重拉前置、重跑适配
- `resumeFrom` 在 `safety === 'unsafe' && !req.force` 时**抛错**，由路由层转 409
- 恢复时把目标节点及其之后所有节点的 `StageState` 重置为 `pending`、`attempt` 归零；
  旧的 `refs` / `summary` 归档进 `iterations[]`，**不直接丢弃**（历史轮次视图要用）
- `req.scope`（缺省 `'continue'`）通过 `node.params` 传给阶段：
  `adapt` 决定是否重置已完成域，`build` 决定 `mode: incremental | full`
- source 指纹比对在 F7 才真正可用；**本期先让它恒返回「未变更」**，
  F7 接入 `git-snapshot` 后自动生效，不用改这里的逻辑

**`recover()`**：照 [reference.md 第 8 节](reference.md#恢复)5 步实现。

> **并发保护**：同一 `runId` 的 `advance` 必须串行。用一个 `Map<runId, Promise>` 做链式排队，避免事件风暴导致状态机重入。

### `capability.ts`

实现 `createCapabilityStage()`（签名见 [reference.md 第 3 节](reference.md#createcapabilitystage-工厂)）：

- `capability === null` → `probe()` 恒返回 `{ available:false, reason:'能力尚未接入' }`
- `start()` → `capability.start(buildInput(ctx))`，把 `runId` 写进 `refs[`${key}_run_id`]`
- 有 `subscribe` 用订阅，否则 `setInterval` 轮询 `getStatus`（默认 5s）
- 状态写进 `state.progress`；`evaluate` 只读 `state.progress` 做映射
- `success` → `done`（先调 `onSuccess`）；`failed` → `failed`；`cancelled` → `failed` 且 `retryable:false`
- `cancel()` 转发并清理定时器 / 取消订阅

### `sources/`

```typescript
// sources/task-stream.ts
export const taskStreamSource: PipelineEventSource = {
  id: 'task-stream',
  subscribe(onEvent) {
    const handler = (ev: TaskEvent) => onEvent({
      source: 'task-stream',
      type: ev.type,
      correlation: { taskId: ev.task_id },
      payload: ev.payload ?? {},
      ts: ev.ts,
    })
    getTaskStream().on('event', handler)
    return () => getTaskStream().off('event', handler)
  },
}
```

`self-check.ts` **写法不同**，不能照抄上面的模式。现有 `device-self-check.onEvent(eventName, cb)`：

1. 只接受**具名**事件，无通配订阅
2. **没有反注册函数**

必须用「模块内一次性安装 + 内部扇出」，并做**幂等保护**（重复安装会导致事件重复投递）。完整代码骨架见 [reference.md 第 5 节](reference.md#-两个源的能力不对称实现方式不同)，直接照抄。

需监听的事件名：`flash_log` `flash_completed` `case_completed` `test_completed` `test_ended` `test_error` `report_ready` `precheck_failed` `manual_confirm`。

`sources/index.ts` 注册两个源并暴露 `startSources()` / `stopSources()`；`startSources()` 也要幂等。

> 只读订阅，**不得**修改被包装 service 的任何行为。特别地：**不要**给 `device-self-check.ts` 加 `offEvent`——底层监听常驻不会泄漏（编排器是进程内单例），加接口反而违反变更控制。

### 验收

- [ ] 用 2 个假阶段（一个立即 done、一个 waiting_human）跑通 `enter → advance → transition`
- [ ] `manual_gate` 分支：probe 不可用时正确停在 `waiting_human` 且 actions 正确
- [ ] `confirm_done` 能推进到下一节点
- [ ] 回环时 source 变更则 `iteration` 自增；超上限转 `waiting_human` 而非死循环
- [ ] `advance` 并发调用 10 次，状态机不重入、结果一致
- [ ] `startSources()` 调用两次，同一自检事件**只投递一次**（幂等保护生效）
- [ ] 节点 done 后 `produces` 转新鲜、下游产物全部转 `stale`
- [ ] `computeResumePoints`：source 未变时 `flash` 为 safe；source 变更后 `flash` / `selfcheck` 转 unsafe 且 `missing` 正确
- [ ] `resumeFrom` 对 unsafe 节点在无 `force` 时抛错，带 `force` 时放行
- [ ] source 未变的恢复**不增加** `iteration`；变更时才 +1
- [ ] `npx vitest run tests/server/adapt-pipeline-orchestrator.test.ts`

---

## F2 · prereq + adapt 阶段

### 文件

| 操作 | 路径 |
|---|---|
| 新增 | `AP/stages/index.ts` |
| 新增 | `AP/stages/prereq.ts` |
| 新增 | `AP/stages/adapt.ts` |
| 新增 | `tests/server/adapt-pipeline-stages.test.ts` |

### `stages/prereq.ts`

- `start()`：调 `centralClient.resolveAdaptPrereqs({ project_code, campaign_id })`，把返回的 `domains[]` 归一为 `PipelineDomain[]` 写进 `run.domains`；同时写 `from_os` / `to_os`
- **路径归属校验**：每个域 `form_data` 里的路径字段必须以 `build_context.mapped_root` 开头，否则收集进 `invalid_paths`
- `evaluate()`：
  - 有 `invalid_paths` → `waiting_human`，message 列出问题字段
  - 有域 `incomplete_required` 非空 → `waiting_human`，actions 含 `confirm_done`（用户在 UI 补填后继续）
  - 否则 `done`
- `probe()`：`isCentralConfigured()` 为 false → 不可用（`onUnavailable: 'fail'`，直接失败并提示去配置）

### `stages/adapt.ts`

**必须串行**（见 [SKILL.md 7.1](SKILL.md#71-适配必须逐域串行)）。

- `start()`：取第一个 `enabled && status==='pending'` 的域，调 `startAdaptAgentRun()`，taskId 写进域与 `refs.adapt_task_ids`
- `observe()`：只认 `correlation.taskId === 当前域的 adapt_task_id`
  - `task.completed` → 域 `done`；**F7 后**在此打 git 快照写 `changed_files`；然后启动下一个域
  - `task.failed` → 域 `failed`
  - `task.user_input_requested` / `task.approval_requested` → 记进 `state.progress.pending_interaction`
- `evaluate()`：
  - 有 `pending_interaction` → `waiting_human`，actions 引导用户去 adapt-debug 处理
  - 全部 enabled 域 `done` → `done`，summary = `{ total, done, skipped }`
  - 任一域 `failed` → `failed`（`onFail: ABORT`）
  - 否则 `running`，progress = `{ percent: done/total*100, text: '3/5 域' }`
- `cancel()`：对进行中的 taskId 调 `cancelAdaptAgentRun()`

`stages/index.ts` 目前内容：

```typescript
import './prereq'
import './adapt'
```

### 验收

- [ ] mock `resolveAdaptPrereqs`，prereq 能正确产出 `domains[]`
- [ ] `incomplete_required` 非空时停在 `waiting_human`
- [ ] 路径不在 `mapped_root` 下时被拦截
- [ ] adapt **串行**：域 1 未完成时不得启动域 2（断言 `startAdaptAgentRun` 调用次数）
- [ ] 域 1 完成后自动启动域 2

---

## F3 · 其余 6 个阶段（占位）

> 本期目标：**让整条流程端到端跑通**。除 prereq/adapt 外全部走 `manual_gate`。

### 文件

| 操作 | 路径 |
|---|---|
| 新增 | `AP/stages/build.ts` |
| 新增 | `AP/stages/flash.ts` |
| 新增 | `AP/stages/selfcheck.ts` |
| 新增 | `AP/stages/triage.ts` |
| 新增 | `AP/stages/human-review.ts` |
| 新增 | `AP/stages/gerrit.ts` |
| 修改 | `AP/stages/index.ts`（+6 行 import） |

### 要点

`build.ts` 用工厂，capability 先传 `null`：

```typescript
import { createCapabilityStage } from '../capability'
import { registerStage } from '../registry'

// P1 编译能力就绪后，把 null 换成 buildCapability，其余不动
registerStage(createCapabilityStage({
  key: 'build',
  label: '编译',
  capability: null,
  consumes: ['source'],
  produces: ['build'],
  buildInput: ctx => ({
    mappedRoot: ctx.run.build_context.mapped_root,
    workspace: ctx.run.build_context.workspace,
    mode: ctx.run.iteration === 1 ? 'full' : 'incremental',
    components: ctx.run.build_context.components,
    variant: ctx.run.build_context.variant,
    parallelProfile: ctx.run.build_context.parallel_profile,
  }),
  onSuccess: (ctx, result) => {
    ctx.patchState({ summary: { artifacts_dir: result.artifactsDir, artifacts: result.artifacts } })
  },
}))
```

`flash.ts` / `selfcheck.ts` / `gerrit.ts` 同样用工厂 + `capability: null`。

**8 个阶段都必须声明 `consumes` / `produces`**，照 [reference.md 第 4 节的产物依赖表](reference.md#产物依赖声明)一字不差。
漏声明会让恢复点计算把该节点误判为「永远 safe」，从而放过过期产物——这正是要防的静默错误。

`triage.ts` 本期让 `probe()` 恒返回 `{ available: false, reason: '故障分析尚未接入' }`，
由流程定义的 `onUnavailable: 'skip'` 自动跳过——**不要**在 `evaluate()` 里硬返回 `skipped`，
那样 F9 实装时要改判定逻辑；用 probe 则只需替换 probe 实现。

`human-review.ts` 是**唯一没有外部能力**的阶段，手写：

```typescript
registerStage({
  key: 'human_review',
  label: '人工审核',
  consumes: ['triage'],
  produces: ['source'],        // 人工改代码 = 产出新 source，下游全部失效
  isHumanGate: true,           // 回环边只能从人工门出发（validateWorkflow 第 7 条）
  async start(ctx) { ctx.log('等待人工审核修改结果') },
  evaluate(ctx) {
    return {
      status: 'waiting_human',
      reason: 'awaiting_review',
      message: '请审核 AI 故障分析结论并完成代码修改，完成后选择从哪个节点继续。',
      actions: [
        { id: 'confirm_done', label: '继续' },
        { id: 'abort', label: '终止流水线', danger: true },
      ],
    }
  },
})
```

> F9 会把 `confirm_done` 的候选改为由 `computeResumePoints()` 动态生成。本期先放单个按钮，走 `onDone` 兜底。

### 验收

- [ ] 8 个节点全部注册成功，`validateWorkflow(DEFAULT_WORKFLOW)` 通过
- [ ] 8 个节点的 `consumes` / `produces` 与 reference 第 4 节的表**逐行一致**
- [ ] **端到端**：创建 run → 启动 → prereq/adapt 自动 → build 停在 `waiting_human`（「编译能力尚未接入」）→ `confirm_done` → flash → … → gerrit → `END`，run 转 `passed`
- [ ] selfcheck 手工点「跳过」时不进 triage，直接到 gerrit

---

## F4 · REST 路由 + 事件 + 启动恢复

### 文件

| 操作 | 路径 |
|---|---|
| 新增 | `routes/tahp/adapt-pipeline.ts` |
| 新增 | `AP/events.ts` |
| 新增 | `AP/timeline.ts` |
| 修改 | `routes/tahp/index.ts`（+2 行） |
| 修改 | `src/index.ts`（bootstrap 末尾 +2 行：`startSources()` / `recover()`） |

### 要点

- 路由按 [reference.md 第 6 节](reference.md#6-rest-api)全量实现，统一信封 `{ success, data?, error? }`
- `events.ts`：封装 `emitPipeline(runId, type, payload)` → `getTaskStream().publish()`，payload 必带 `run_id`。**照抄** `adapt-agent.ts:298-305` 的 `emit()` 写法
- `timeline.ts`：`PipelineRun` → `TimelineView` 的投影函数，纯函数，含 `pending_human_count` 与 `is_loop_target` 计算
- `src/index.ts` 只加两行，位置在 `startPlanExecutor()` 之后
- **`POST /runs/:runId/start` 必须先调 `findResourceConflict()`**（[reference.md 第 10 节](reference.md#10-并发与资源占用)），
  命中冲突返回 409 + 占用者 `run_id`，**不要启动**。这个检查放在 store 层，F0 时可先留空实现，本期补齐
- `GET /resume-points` 直接返回 `computeResumePoints()` 结果；`POST /resume` 转发 `resumeFrom()`，
  unsafe 且未带 `force` 时返回 **409** + `missing` 明细，**不要**在路由层重新实现新鲜度判断

### 验收

- [ ] `POST /runs` → `GET /runs/:id/timeline` 返回结构符合 `TimelineView`
- [ ] Socket 客户端能收到 `pipeline.run_started` / `node_changed` / `waiting_human`
- [ ] `POST /human-action` 能推进流程
- [ ] `GET /resume-points` 返回的 `recommended` 在「未改代码的烧录失败」场景下是 `flash`
- [ ] `POST /resume` 到 unsafe 节点：不带 `force` 返 409，带 `force` 成功并 emit `pipeline.resumed`
- [ ] 两个 run 用同一 workspace / 同一 device 时，第二个启动被拒且错误信息含占用者 run_id
- [ ] **重启 BFF 后**：`waiting_human` 的 run 完整恢复，可继续操作
- [ ] `npm run build` 通过

---

## F5 · UI 步进条与看板骨架

### 文件

| 操作 | 路径 |
|---|---|
| 新增 | `client/src/components/common/EaStageStepper.vue` |
| 新增 | `client/src/api/tahp/adapt-pipeline.ts` |
| 新增 | `client/src/stores/tahp/adapt-pipeline.ts` |
| 新增 | `client/src/views/tahp/AdaptPipelineView.vue` |
| 新增 | `client/src/components/tahp/pipeline/PipelineRunList.vue` |
| 修改 | `client/src/router/index.ts`（+5 行） |
| 修改 | `client/src/components/layout/EaShell.vue`（+1 导航项） |

### 要点

- `EaStageStepper` 严格按 [ui-spec 第 4 节](ui-spec.md#4-eastagestepper核心组件)，**纯展示、无业务判断**
- store 订阅 `pipeline.*`（复用 `api/tahp/socket.ts` 的 `subscribeTahp`），按 `run_id` 分桶
- 断线降级 5s 轮询 `timeline`
- 文案入 locale

### 验收

- [ ] `/#/tahp/pipeline` 可访问，run 列表正常
- [ ] 步进条完全由 `timeline.nodes` 渲染，**代码中搜不到任何节点 key 硬编码**
- [ ] 后端状态变化 2s 内反映到步进条

---

## F6 · 节点面板 + 人工介入 + 迭代条

### 文件

| 操作 | 路径 |
|---|---|
| 新增 | `client/src/components/common/EaLogViewer.vue` |
| 新增 | `.../pipeline/PipelineRunDetail.vue` |
| 新增 | `.../pipeline/PipelineNodeList.vue` |
| 新增 | `.../pipeline/PipelineNodePanel.vue` |
| 新增 | `.../pipeline/stage-panels/DefaultPanel.vue` |
| 新增 | `.../pipeline/PipelineHumanPanel.vue` |
| 新增 | `.../pipeline/PipelineResumePicker.vue` |
| 新增 | `.../pipeline/PipelineIterationBar.vue` |

### 要点

- `EaLogViewer` **必须虚拟滚动**，环形缓冲 2000 行
- `PipelineNodePanel` 用渲染器注册表分发，未注册回落 `DefaultPanel`
- 人工卡片按 `human.actions[]` 动态渲染；`fields` 非空时弹 `NModal`
- `PipelineResumePicker` 照 [ui-spec 6.4](ui-spec.md#64-恢复点选择器)：
  候选**全量展示**（含 unsafe），默认选中 `recommended`，选 unsafe 弹二次确认并带 `force: true`。
  **不得**在前端另写一套新鲜度判断，safety 一律以接口返回为准

### 验收

- [ ] 点击步进条节点 → 中栏切换，URL 带 `?node=`
- [ ] 未写专用渲染器的节点用 `DefaultPanel` 正常显示，不白屏
- [ ] 人工卡片可提交并推进流程
- [ ] 恢复点选择器：默认选中 safe 推荐项；unsafe 项可见、灰显、附原因、二次确认后可提交
- [ ] 5 万行日志滚动不卡顿
- [ ] 迭代 ≥2 时收敛条与回环弧线正确

---

## F7 · git 快照器

### 文件

| 操作 | 路径 |
|---|---|
| 新增 | `services/tahp/git-snapshot.ts` |
| 修改 | `AP/stages/adapt.ts`（域完成后打快照） |
| 新增 | `tests/server/git-snapshot.test.ts` |

### 要点

```typescript
export interface GitSnapshot { repo: string; files: Array<{ path: string; status: string }>; takenAt: string }

export async function takeSnapshot(roots: string[]): Promise<GitSnapshot[]>
export function diffSnapshots(before: GitSnapshot[], after: GitSnapshot[]): string[]
/** 稳定哈希，用作 source 产物指纹；文件顺序必须先排序再哈希 */
export function fingerprint(snapshots: GitSnapshot[]): string
```

`fingerprint()` 是断点恢复判定「人到底改没改代码」的唯一依据（[reference.md 11.3](reference.md#113-source-指纹怎么知道人到底改没改代码)）。本期接入后，F1 里那个恒返回「未变更」的桩自动生效。

`human-review.ts` 需在 `start()` 时打快照存进 `progress.snapshot_before`，供 `resumeFrom` 比对。

- 用 `execFile('git', [...])` **参数数组**，禁止拼 shell 字符串（`tahp-console-dev` 规则）
- 多仓：`build_context` 下可能有多个 git 仓，逐仓 `git status --porcelain`
- Windows 映射盘上 git 不可用时，回落 `harness remote-runner` 在 Linux 侧执行（参考 `gerrit-submit` skill 的 `harness_remote.py` 思路）
- **绝不使用**适配报告的 `file_changes` 做判定

### 验收

- [ ] 临时 git 仓中 新增/修改/删除 文件都能被正确捕获
- [ ] `diffSnapshots` 只返回两次快照之间的增量
- [ ] adapt 阶段每个域完成后 `domains[].changed_files` 被正确填充
- [ ] `fingerprint()` 对同一工作区两次调用结果一致；改动任一文件后必然变化
- [ ] human_review 期间**未改代码**时恢复点仍推荐 `flash`；改了代码后推荐 `build`

---

## F8 · flash + selfcheck 实装

### 文件

| 操作 | 路径 |
|---|---|
| 新增 | `services/tahp/flash-artifact-resolver.ts` |
| 新增 | `services/tahp/selfcheck-case-planner.ts` |
| 修改 | `AP/stages/flash.ts` |
| 修改 | `AP/stages/selfcheck.ts` |
| 新增 | `tests/server/selfcheck-case-planner.test.ts` |

### 要点

**`flash-artifact-resolver.ts`**：build `summary.artifacts_dir`（Linux 路径）→ 映射盘 Windows 路径 → 校验存在 → 返回可喂给 `runDeviceFlash()` 的 `pkgPath`。
解析不到时返回 `null`，flash 阶段转 `waiting_human` 让用户手选包（复用 `flash/pick-path`）。

> ⚠️ **上线前必须手工验证一次**「rdtool package 产物 → device_update 刷入设备」。此路径从未被验证过。

**`selfcheck-case-planner.ts`**：构造 `mustTestItems` 并调 `recommendTestCasesWithMeta()`。

```typescript
export function buildMustTestItems(run: PipelineRun): string[]
// 素材：domains[].domain_label + 适配报告 audit_summary + changed_files 路径关键词
export async function planCases(run: PipelineRun): Promise<TestPlan>
```

**已知限制（写进代码注释）**：推荐引擎候选库仅覆盖 `week_driver` / `week_tdd` / `str4_driver_component`，**推不出 monkey / smoke / gms / power**。这类需求走 `TestPlan.mode='fixed'` 手工指定。

**`selfcheck.ts`**：`startCustomTest()` → observe SSE `case_completed` / `test_completed` / `report_ready`。
`evaluate` 的 `failed` 必须在 summary 里区分 `failure_kind: 'case_failed' | 'infra_error'`，并据此声明产出：

- `case_failed` → `{ status:'failed', error, produced: ['testresult'] }`（报告有效，`triage` 要消费）
- `infra_error` → `{ status:'failed', error }`（无有效报告，`triage` 自然变 unsafe）

### 验收

- [ ] `buildMustTestItems` 对典型域产出非空且含域标签
- [ ] `mustTestItems` 为空时降级为 `fixed` 模式，不静默跑空用例集
- [ ] selfcheck 能正确接收 SSE 并统计通过/失败
- [ ] `infra_error` 与 `case_failed` 判定正确
- [ ] `case_failed` 后 `testresult` 为新鲜、`triage` 为 safe；`infra_error` 后 `triage` 为 unsafe

---

## F9 · triage + human_review 实装

### 文件

| 操作 | 路径 |
|---|---|
| 新增 | `services/tahp/selfcheck-failure-bundle.ts` |
| 修改 | `AP/stages/triage.ts` |
| 修改 | `AP/stages/human-review.ts`（挂分析结论摘要） |
| 新增 | `tests/server/selfcheck-failure-bundle.test.ts` |

### 要点

**`selfcheck-failure-bundle.ts`**：把失败证据收敛成一个目录喂给 bug-analysis。

```typescript
export async function buildFailureBundle(reportId: string): Promise<{ dir: string; description: string }>
```

产出 `reports/self-check/{deviceId}/{ts}/failure-bundle/`，内含：
- `failed-cases.json`（来自 `detail.json` 的 `failedCaseItems[]`）
- 能定位到的用例日志 / logcat 拷贝
- `README.md`：问题描述，作为 `problem_description`

**`triage.ts`**：
- `start()` 先看 selfcheck 的 `summary.failure_kind`
  - `infra_error` → **不调 bug-analysis**，直接 `waiting_human`（AI 分析不了环境问题）
  - `case_failed` → 打包 → `POST /bug-analysis/local`
- observe `task.completed` → 取报告 → `done`

**`human-review.ts`**：`evaluate()` 的 `actions` 改为**动态生成**——调 `computeResumePoints(ctx.run)`，把候选渲染成 `HumanAction`：

```typescript
const { points, recommended } = computeResumePoints(ctx.run)
actions: [
  { id: 'confirm_done', label: '继续', fields: [
      { name: 'resume_node',  label: '从哪里继续', required: true },
      { name: 'resume_scope', label: '范围' },
  ]},
  { id: 'abort', label: '终止流水线', danger: true },
]
```

候选清单与 `recommended` 一并挂进 `state.progress.resume_points` 供前端渲染。
**不要**在这里写死「重新编译」——那会绕过新鲜度推导（[SKILL.md 7.4](SKILL.md#74-恢复点必须由产物新鲜度推导)）。

### 验收

- [ ] bundle 目录结构正确，`failed-cases.json` 内容与报告一致
- [ ] `infra_error` 时不触发 bug-analysis
- [ ] human_review 面板能看到分析结论摘要
- [ ] human_review 的候选恢复点随代码是否变更而变化，且默认项始终 safe

---

## F10 · gerrit 实装 + 冲突检测

### 文件

| 操作 | 路径 |
|---|---|
| 新增 | `services/tahp/gerrit-submit.ts` |
| 修改 | `AP/stages/gerrit.ts` |
| 新增 | `tests/server/gerrit-submit.test.ts` |
| 修改 | locale 文件 |

### 要点

- `gerrit-submit.ts` **仿** [gerrit-review.ts](../../../tahp-console/packages/server/src/services/tahp/gerrit-review.ts)：走 Agent Bridge 加载 `gerrit-submit` Skill，逐域提交
- **冲突检测（强制）**：提交前比对各域 `changed_files`，存在交集时该批次转 `waiting_human`，标记 `blocked_conflict`，**禁止自动提交**
- commit message 用 `gerrit-submit/commit-template.md` 模板
- 从 Agent 输出解析 CR URL 写进 `gerrit_changes[]`

### 验收

- [ ] 两个域改同一文件时被拦截且不提交
- [ ] 正常情况每域生成一个 CR，URL 正确回填
- [ ] Agent Bridge 未运行时 probe 不可用 → `manual_gate`

---

## F11 · 接入 P1 编译能力

> 等同事的编译功能开发完成后执行。**这是全流程中最小的一期。**

### 文件

| 操作 | 路径 |
|---|---|
| 新增 | `services/tahp/build-capability.ts`（适配同事的 API → `ExternalCapability`） |
| 修改 | `AP/stages/build.ts`（`capability: null` → `capability: buildCapability`，1 行） |

### 要点

1. 先核对同事的实现是否满足 [reference.md 第 3 节](reference.md#3-externalcapability)契约；不满足则在 `build-capability.ts` 里做适配，**不要求对方改**
2. `probe()` 必须真实反映可用性（依赖检查、齐治 bridge 是否 READY）
3. 成功时 `result` 需带 `artifactsDir`，供 F8 的产物解析使用

### 验收

- [ ] `GET /capabilities` 中 build 显示可用
- [ ] 新建 run 后 build 节点**自动执行**，不再停人工门
- [ ] 编译失败时正确走 `onFail: human_review`
- [ ] **编排器、流程定义、UI 均未改动**（用 `git diff --stat` 自证）

---

## F12 · 专用渲染器 + 流程编排 Tab

### 文件

| 操作 | 路径 |
|---|---|
| 新增 | `stage-panels/AdaptPanel.vue` |
| 新增 | `stage-panels/BuildPanel.vue` |
| 新增 | `stage-panels/FlashPanel.vue` |
| 新增 | `stage-panels/SelfCheckPanel.vue` |
| 新增 | `stage-panels/TriagePanel.vue` / `GerritPanel.vue` |
| 新增 | `PipelineWorkflowEditor.vue` |
| 修改 | locale 文件 |

`BuildPanel` 必须显式展示「本轮编译组件」清单（防漏编的安全设计）。
流程编排 Tab 初版**只做开关 + 只读展示**，不做拖拽排序。

---

## 全局验证

```bash
cd tahp-console
npm run setup                  # 首次或 Python/venv 变更后
npm test                       # 发 MR 前全量
npm run build                  # 每期必跑
```

### 手动冒烟（F6 之后）

1. `/#/tahp/pipeline` → 新建运行 → 选项目 → 确认前置 → 启动
2. 步进条 8 节点，`prereq` / `adapt` 自动跑，域逐个变绿
3. 走到 `build` 停橙色，右栏提示「编译能力尚未接入」
4. 点「已手工完成，继续」→ 推进到 `flash`
5. 在 `flash` 处手工点「失败」模拟烧录挂掉 → 打开恢复点选择器，
   **不改任何代码**时推荐项应为 `flash`（而非 `build`），`selfcheck` 应为 unsafe
6. 在工作区随便改一个文件再看一次 → 推荐项变为 `build`，`flash` / `selfcheck` 均转 unsafe
7. **重启 BFF** → 刷新页面 → 状态、日志、待办、恢复点完整恢复
8. 走完到 `gerrit` → run 转 `passed`

---

## F13 · 完整体验闭环

### 文件

| 操作 | 路径 |
|---|---|
| 新增 | `client/.../PipelineCreateWizard.vue` |
| 修改 | `AdaptPipelineView.vue` · `PipelineRunDetail.vue` · `BuildPanel.vue` |
| 修改 | `EaLogViewer.vue` · `api/adapt-pipeline.ts` · `stores/adapt-pipeline.ts` |
| 修改 | `timeline.ts`（透传 build_context） |

### 要点

- **新建运行四步向导**：选项目 → 确认前置 → 配置执行 → 确认启动（含不可用能力预告）
- 看板头栏：**暂停 / 终止 / 从…恢复**；状态中文 + 运行时长
- 窄屏 `<1400px`：人工介入收为抽屉，页头徽章唤起
- `BuildPanel` 展示 `build_context.components`（防漏编）
- `EaLogViewer` 搜索 + 级别过滤 + 虚拟滚动
- **唯一允许占位**：F11 编译自动执行（仍 `manual_gate`）

### 验收

- [ ] 向导可创建并启动 run，看板自动选中
- [ ] 中心未配置 / Bridge 未运行有明确提示
- [ ] 暂停、终止、恢复点选择可用
- [ ] 编译面板显示组件清单

---

## 反模式清单（禁止）

| 禁止 | 原因 |
|---|---|
| 在编排器里写 `if (node.key === 'build')` | 破坏插件化，节点不可增删 |
| 前端硬编码节点列表 | 新增节点要改前端 |
| 用适配报告 `file_changes` 做变更判定 | 启发式推断，会漏会多 |
| 开放「任选节点恢复」而不校验产物新鲜度 | 从过期镜像跑自检会得出**静默的错误结论** |
| 让用户勾选「我改过代码」代替 git 指纹 | 人会记错，判据必须客观 |
| 在前端另写一套 safety 判断 | 与后端推导漂移，迟早不一致 |
| 未 probe 就调用外部能力 | P1 未就绪时整条流程崩 |
| 把业务逻辑写进 `evaluate()` | `evaluate` 必须是纯函数 |
| 引入工作流/DAG/状态机三方库 | 过度设计，当前模型足够 |
| 修改现有业务 service 对外接口 | 违反变更控制 |
| 为流水线改 `paths.ts` / `unified-config.ts` | 敏感链，禁止 |
