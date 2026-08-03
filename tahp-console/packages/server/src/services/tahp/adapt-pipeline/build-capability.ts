/**
 * 编译能力：Agent Bridge + harness-build* Skill，产出固定 build-result.json
 */
import { randomBytes } from 'crypto'
import { join } from 'path'
import { logger } from '../../logger'
import {
  AgentBridgeClient,
  getAgentBridgeManager,
  type AgentBridgeChatStarted,
  type AgentBridgeOutput,
} from '../../hermes/agent-bridge'
import { filterBridgeToolCallMarkupDelta } from '../../hermes/run-chat/bridge-delta'
import { assertHarnessCliReady } from '../harness-version-gate'
import { humanizeAgentError } from '../adapt-agent-health'
import { tahpPaths } from '../paths'
import {
  buildResultFilePath,
  buildResultPromptBlock,
  looksLikeBackgroundWaitWithoutResult,
  parseBuildResultFromText,
  readBuildResultFile,
  writeBuildResult,
  type BuildResultContract,
} from './build-result-contract'
import {
  defaultBuildSkillId,
  resolveHarnessSkillPath,
} from './harness-skill-registry'
import type {
  BuildCapabilityInput,
  CapabilityEvent,
  CapabilityStatus,
  ExternalCapability,
  StageAvailability,
} from './types'

const bridgeClient = new AgentBridgeClient({ timeoutMs: 10 * 60 * 60_000 })

interface BuildRunCtx {
  runId: string
  pipelineRunId: string
  startedAt: number
  status: CapabilityStatus
  cancelled: boolean
  sessionId: string
  resultPath: string
  listeners: Set<(ev: CapabilityEvent) => void>
}

const runs = new Map<string, BuildRunCtx>()

function genRunId(): string {
  return `build-${Date.now()}-${randomBytes(3).toString('hex')}`
}

function emit(ctx: BuildRunCtx, line?: string) {
  const ev: CapabilityEvent = {
    type: line ? 'log' : 'progress',
    status: ctx.status,
    line,
    phase: ctx.status.phase,
    progress: ctx.status.progress,
  }
  for (const fn of ctx.listeners) {
    try { fn(ev) } catch { /* ignore */ }
  }
}

function toCapabilityResult(result: BuildResultContract): Record<string, unknown> {
  return {
    artifactsDir: result.artifacts_dir,
    artifacts_dir: result.artifacts_dir,
    pkgPath: result.pkg_path,
    pkg_path: result.pkg_path,
    artifacts: result.artifacts,
    durationMs: result.duration_ms,
    failedStage: result.failed_stage,
    skillId: result.skill_id,
    status: result.status,
  }
}

function applyResult(ctx: BuildRunCtx, result: BuildResultContract) {
  if (result.status === 'pass' && (result.artifacts_dir || result.pkg_path)) {
    ctx.status = {
      state: 'success',
      progress: 100,
      phase: 'done',
      message: '编译成功',
      result: toCapabilityResult(result),
    }
  } else {
    ctx.status = {
      state: 'failed',
      phase: result.failed_stage ?? 'build',
      error: result.error || '编译失败或未产出产物路径',
      result: toCapabilityResult(result),
    }
  }
  emit(ctx)
}

function buildInstructions(input: BuildCapabilityInput, skillPath: string, resultPath: string): string {
  const skillId = input.buildSkillId || defaultBuildSkillId(input.buildKind)
  const kind = input.buildKind ?? 'whole_device'
  const components = (input.components ?? []).join(',') || '(空)'
  const markets = (input.markets ?? []).join(',') || ''
  const stages = input.pipelineStages ?? 'build,package'
  return `
你是 TAHP 适配流水线的编译助手。必须严格按指定 harness Skill 执行，禁止在 Windows PowerShell 直接跑 Linux 编译脚本。

# Skill
- Skill ID: \`${skillId}\`
- Skill 路径: \`${skillPath}\`
- 先 Read 该 SKILL.md，再按其中命令执行

# 任务类型
${kind === 'native_module' ? '模块/Native 编译（harness-build-native）' : '整机编译（harness-build-whole-device / pipeline）'}

# 输入参数
- mapped_root: ${input.mappedRoot}
- workspace: ${input.workspace}
- variant: ${input.variant}
- mode: ${input.mode}
- components: ${components}
- parallel_profile: ${input.parallelProfile ?? ''}
- markets: ${markets}
- pipeline_stages: ${stages}
- lunch: ${input.lunch ?? ''}
- native_component: ${input.nativeComponent ?? 'sys'}
- native_target: ${input.nativeTarget ?? ''}

# 执行纪律（违反会导致流水线失败）
1. **禁止向用户提问 / AskUser / 等待确认**。缺参、缺条件、任务无法完成时：立即失败，并按契约写出 \`status: "fail"\` 的 TAHP_BUILD_RESULT（含 error / failed_stage），然后结束。
2. 先 \`harness --json remote-runner discover\` / status，确认 bridge READY；若未 READY，按第 1 条失败退出，不要等待用户去开 Bridge。
3. **整机必须优先一条阻塞命令**：
   \`harness --json build pipeline --mapped-root ... --workspace ... --confirm-workspace-path --stages ${stages} --components ${components || '<components>'} --variant ${input.variant}${markets ? ` --markets ${markets}` : ''}${input.parallelProfile ? ` --parallel-profile ${input.parallelProfile}` : ''}\`
   - MTK 含 \`trreg\` 时务必带 \`--markets\`；\`build pipeline\` **内部**会处理 trreg/trprd 分批与 \`--local\`，**不要**自行拆成多个后台 \`batch-build\`。
   - 该命令会等到整机流水线结束（或失败）才返回；你必须等它返回后再继续。
4. **严禁**「提交后台 + 等待完成通知 + 结束回合」。禁止在编译未完成时结束对话。若误用了 \`batch-build\`：必须用 \`harness --json build status\` **轮询到全部组件完成/失败**，再 \`build artifacts\`，再写 TAHP_BUILD_RESULT；不得口头说「等待通知」后停止。
5. 模块：用 \`harness --json build native-module ...\` 或 Skill 规定命令，同样须阻塞到结束。
6. 编译成功后：\`harness --json build artifacts\`（整机）定位产物目录/主包路径。
7. ${buildResultPromptBlock(resultPath)}
`.trim()
}

function buildUserMessage(input: BuildCapabilityInput): string {
  const skillId = input.buildSkillId || defaultBuildSkillId(input.buildKind)
  return [
    '# 流水线编译任务',
    '',
    `请使用 Skill \`${skillId}\` **阻塞执行到编译结束**，并按契约写出 TAHP_BUILD_RESULT。`,
    '优先使用 `harness --json build pipeline`（一条命令含全部分区；含 trreg 时带 --markets）。',
    '禁止：把 batch-build 丢到后台后以「等待完成通知」结束；禁止 AskUser。',
    '缺参或无法完成时直接 fail + TAHP_BUILD_RESULT。',
    `mapped_root=${input.mappedRoot}`,
    `workspace=${input.workspace}`,
    `variant=${input.variant}`,
    `components=${(input.components ?? []).join(',')}`,
    `pipeline_stages=${input.pipelineStages ?? 'build,package'}`,
    input.markets?.length ? `markets=${input.markets.join(',')}` : '',
    input.parallelProfile ? `parallel_profile=${input.parallelProfile}` : '',
    input.nativeTarget ? `native_target=${input.nativeTarget}` : '',
    input.lunch ? `lunch=${input.lunch}` : '',
  ].filter(Boolean).join('\n')
}

async function runAgent(ctx: BuildRunCtx, input: BuildCapabilityInput, skillPath: string): Promise<void> {
  const manager = getAgentBridgeManager()
  if (!manager.running) {
    throw new Error('Agent Bridge 未运行')
  }

  const instructions = buildInstructions(input, skillPath, ctx.resultPath)
  const userMessage = buildUserMessage(input)

  ctx.status = { state: 'running', progress: 5, phase: 'agent', message: '启动编译 Agent' }
  emit(ctx, '启动编译 Agent…')

  const started: AgentBridgeChatStarted = await bridgeClient.chat(
    ctx.sessionId,
    userMessage,
    undefined,
    instructions,
    'default',
  )

  const markupState: { bridgePendingToolCallMarkup?: string } = {}
  let full = ''

  for await (const chunk of bridgeClient.streamOutput(started.run_id, { intervalMs: 500 })) {
    if (ctx.cancelled) {
      try { await bridgeClient.interrupt(ctx.sessionId, '流水线取消编译') } catch { /* ignore */ }
      ctx.status = { state: 'cancelled', error: '已取消' }
      emit(ctx)
      return
    }

    const out = chunk as AgentBridgeOutput
    for (const ev of out.events || []) {
      if (ev.event === 'tool.started' || ev.event === 'tool.completed') {
        const name = String(ev.tool_name || 'tool')
        ctx.status = {
          ...ctx.status,
          state: 'running',
          phase: 'tool',
          message: name,
          progress: Math.min(90, (ctx.status.progress ?? 10) + 2),
        }
        emit(ctx, `[tool] ${name}`)
      }
    }
    if (out.delta) {
      const cleaned = filterBridgeToolCallMarkupDelta(markupState, out.delta)
      if (cleaned) {
        full += cleaned
        const line = cleaned.trim()
        if (line) emit(ctx, line.slice(0, 500))
      }
    }

    // 中途若已落盘结果文件，可提前结束等待
    const fileHit = readBuildResultFile(ctx.resultPath)
    if (fileHit && (fileHit.status === 'pass' || fileHit.status === 'fail')) {
      applyResult(ctx, fileHit)
      try { await bridgeClient.interrupt(ctx.sessionId, '已拿到编译结果') } catch { /* ignore */ }
      return
    }

    if (out.done) {
      if (out.status === 'error') throw new Error(humanizeAgentError(out.error || 'Agent 出错'))
      if (out.status === 'interrupted') {
        const again = readBuildResultFile(ctx.resultPath)
        if (again) {
          applyResult(ctx, again)
          return
        }
        throw new Error('Agent 运行被中断')
      }
      break
    }
  }

  const fromFile = readBuildResultFile(ctx.resultPath)
  const fromText = parseBuildResultFromText(full)
  const result = fromFile ?? fromText
  if (!result) {
    const bgWait = looksLikeBackgroundWaitWithoutResult(full)
    const error = bgWait
      ? `编译 Agent 在后台任务未完成时结束，未写入结果文件。请点「重新编译」；Agent 须使用阻塞的 harness build pipeline（勿 batch-build 丢后台后结束）。期望文件：${ctx.resultPath}`
      : `未解析到编译结果。请确认 Agent 已写入 ${ctx.resultPath}`
    try {
      writeBuildResult(ctx.resultPath, {
        schema_version: 1,
        status: 'fail',
        failed_stage: 'agent',
        error,
        skill_id: input.buildSkillId || defaultBuildSkillId(input.buildKind),
        notes: bgWait ? 'agent_ended_while_waiting_background_build' : 'missing_tahp_build_result',
      })
    } catch { /* ignore */ }
    throw new Error(error)
  }
  applyResult(ctx, result)
}

export const buildCapability: ExternalCapability<BuildCapabilityInput> = {
  id: 'harness-build-agent',

  async probe(): Promise<StageAvailability> {
    try {
      assertHarnessCliReady()
    } catch (err) {
      return { available: false, reason: (err as Error).message }
    }
    const manager = getAgentBridgeManager()
    if (!manager.running) {
      return { available: false, reason: 'Agent Bridge 未就绪' }
    }
    return { available: true }
  },

  async start(input: BuildCapabilityInput): Promise<{ runId: string }> {
    const skillId = input.buildSkillId || defaultBuildSkillId(input.buildKind)
    const skillPath = resolveHarnessSkillPath(skillId)
    if (!skillPath) {
      throw new Error(`未找到编译 Skill：${skillId}（请检查 %USERPROFILE%\\.claude\\skills）`)
    }

    const runId = genRunId()
    const resultPath = buildResultFilePath(
      join(tahpPaths.reportsDir, 'adapt-pipeline', input.pipelineRunId),
    )
    const ctx: BuildRunCtx = {
      runId,
      pipelineRunId: input.pipelineRunId,
      startedAt: Date.now(),
      status: { state: 'pending', progress: 0, phase: 'init' },
      cancelled: false,
      sessionId: `tahp-pipeline-build-${runId}`,
      resultPath,
      listeners: new Set(),
    }
    runs.set(runId, ctx)

    void runAgent(ctx, input, skillPath).catch((err) => {
      logger.warn({ err: (err as Error).message, runId }, '[build-capability] failed')
      ctx.status = {
        state: 'failed',
        error: (err as Error).message,
      }
      emit(ctx, (err as Error).message)
    })

    return { runId }
  },

  async getStatus(runId: string): Promise<CapabilityStatus> {
    const ctx = runs.get(runId)
    if (!ctx) return { state: 'failed', error: '未知编译任务' }
    // 轮询时再读一次结果文件（Agent 可能已写完）
    if (ctx.status.state === 'running' || ctx.status.state === 'pending') {
      const fileHit = readBuildResultFile(ctx.resultPath)
      if (fileHit) applyResult(ctx, fileHit)
    }
    return ctx.status
  },

  async cancel(runId: string): Promise<void> {
    const ctx = runs.get(runId)
    if (!ctx) return
    ctx.cancelled = true
    ctx.status = { state: 'cancelled', error: '已取消' }
    try {
      await bridgeClient.interrupt(ctx.sessionId, '流水线终止/取消编译')
    } catch { /* ignore */ }
    emit(ctx)
  },

  subscribe(runId: string, onEvent: (ev: CapabilityEvent) => void): () => void {
    const ctx = runs.get(runId)
    if (!ctx) return () => {}
    ctx.listeners.add(onEvent)
    onEvent({
      type: 'progress',
      status: ctx.status,
      phase: ctx.status.phase,
      progress: ctx.status.progress,
    })
    return () => { ctx.listeners.delete(onEvent) }
  },
}
