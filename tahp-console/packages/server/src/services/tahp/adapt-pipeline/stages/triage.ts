import { registerStageForTest } from '../registry'
import type { StageContext, StageDefinition, StageVerdict } from '../types'
import { buildFailureBundle, resolveReportDir } from '../../selfcheck-failure-bundle'
import { startLocalLogBugAnalysis } from '../../bug-analysis'
import { getAdaptAgentTask } from '../../adapt-agent'

export const triageStageDefinition: StageDefinition = {
  key: 'triage',
  label: '故障分析',
  consumes: ['testresult'],
  produces: ['triage'],

  async probe() {
    // Bug-analysis runs via agent bridge; check if available
    try {
      const task = getAdaptAgentTask?.('__probe_triage__')
      // getAdaptAgentTask may throw or return null if bridge unavailable
      return { available: true }
    } catch {
      return { available: false, reason: 'Agent Bridge 未就绪' }
    }
  },

  async start(ctx: StageContext) {
    const selfcheckStage = ctx.run.stages.selfcheck
    const failureKind = (selfcheckStage?.summary as Record<string, unknown> | undefined)?.failure_kind as string | undefined
    const selfcheckProgress = (selfcheckStage?.progress ?? {}) as Record<string, unknown>

    // infra_error: AI can't analyze infra problems
    if (failureKind === 'infra_error' || selfcheckProgress.state === 'infra_error') {
      ctx.patchState({
        progress: {
          state: 'infra_skip',
          conclusion: '自检为基础设施错误，无法进行 AI 故障分析。',
        },
      })
      ctx.log('自检为 infra_error，跳过 AI 故障分析，转人工处理')
      return
    }

    // case_failed: build bundle and submit to bug-analysis
    const deviceId = ctx.run.device_id ?? (ctx.run.stages.selfcheck?.refs?.selfcheck_device_id as string | undefined)
    const startTime = (selfcheckStage?.started_at ?? ctx.run.created_at) as string

    if (!deviceId) {
      ctx.patchState({ progress: { state: 'error', error: '无法确定设备 ID' } })
      return
    }

    const reportDir = resolveReportDir(deviceId, startTime)
    ctx.log(`构建失败证据包: ${reportDir}`)

    const bundle = await buildFailureBundle(reportDir)
    if (!bundle) {
      ctx.patchState({
        progress: {
          state: 'no_evidence',
          conclusion: '未找到失败证据，无法自动分析。',
        },
      })
      ctx.log('未找到失败证据包，跳过自动分析')
      return
    }

    ctx.log(`提交 bug-analysis: ${bundle.dir}`)
    ctx.patchState({ progress: { state: 'analyzing', bundle_dir: bundle.dir } })

    const result = startLocalLogBugAnalysis({
      logPath: bundle.dir,
      problemDescription: bundle.description,
    })

    if (!result.ok) {
      ctx.patchState({
        progress: { state: 'analysis_failed', error: result.error },
      })
      ctx.log(`bug-analysis 启动失败: ${result.error}`)
      return
    }

    ctx.patchState({
      refs: { ...ctx.state.refs, triage_task_id: result.taskId },
      progress: { state: 'analyzing', task_id: result.taskId },
    })
    ctx.log(`bug-analysis 已启动: taskId=${result.taskId}`)
  },

  observe(ctx: StageContext, ev) {
    if (ev.source !== 'task-stream') return
    const taskId = ctx.state.refs?.triage_task_id
    if (!taskId || ev.correlation.taskId !== taskId) return

    if (ev.type === 'task.completed') {
      const conclusion = String(ev.payload.conclusion ?? ev.payload.summary ?? '分析完成')
      const evidence = (ev.payload.evidence ?? []) as string[]
      ctx.patchState({
        progress: { state: 'success', conclusion, evidence },
        summary: { conclusion, evidence },
      })
      ctx.log('故障分析完成')
    }

    if (ev.type === 'task.failed') {
      ctx.patchState({
        progress: {
          state: 'analysis_failed',
          error: String(ev.payload.error ?? '分析失败'),
        },
      })
    }
  },

  evaluate(ctx: StageContext): StageVerdict {
    const p = ctx.state.progress as Record<string, unknown> | undefined
    const state = p?.state as string | undefined

    if (state === 'success') {
      return {
        status: 'done',
        summary: {
          conclusion: p?.conclusion,
          evidence: p?.evidence,
        },
      }
    }

    if (state === 'infra_skip' || state === 'no_evidence') {
      return {
        status: 'waiting_human',
        reason: state,
        message: String(p?.conclusion ?? '无法自动分析'),
        actions: [
          { id: 'confirm_done', label: '已手工处理，继续' },
          { id: 'skip', label: '跳过', danger: true },
        ],
      }
    }

    if (state === 'analysis_failed' || state === 'error') {
      return {
        status: 'failed',
        error: String(p?.error ?? '故障分析失败'),
        retryable: true,
      }
    }

    return {
      status: 'running',
      progress: { text: '分析中…' },
    }
  },
}

export function installTriageStage(): void {
  registerStageForTest(triageStageDefinition)
}

installTriageStage()
