import { registerStageForTest } from '../registry'
import type { StageContext, StageDefinition, StageVerdict } from '../types'
import { planCases } from '../../selfcheck-case-planner'
import {
  startCustomTest,
  onEvent,
  type CaseResult,
  type TestSession,
} from '../../device-self-check'

export const selfcheckStageDefinition: StageDefinition = {
  key: 'selfcheck',
  label: 'AI 自检',
  consumes: ['flashed'],
  produces: ['testresult'],

  async probe() {
    // Self-check is always locally available (Python runner)
    return { available: true }
  },

  async start(ctx: StageContext) {
    const deviceId = ctx.run.device_id
    if (!deviceId) {
      ctx.patchState({ progress: { state: 'error', error: '未配置设备 ID' } })
      return
    }

    ctx.log('规划测试用例…')
    const planResult = await planCases(ctx.run)
    ctx.patchState({
      progress: {
        state: 'planning',
        plan_source: planResult.source,
        total: planResult.cases.length,
        passed: 0,
        failed: 0,
        running: 0,
      },
    })

    if (!planResult.cases.length) {
      ctx.log(`用例规划结果为空 (source=${planResult.source})，转人工选择`)
      ctx.patchState({
        progress: {
          state: 'waiting_cases',
          message: '推荐引擎未产出用例，请手工指定测试用例',
          plan_source: planResult.source,
          total: 0, passed: 0, failed: 0, running: 0,
        },
      })
      return
    }

    const selectedCases = planResult.plan.selected_cases ?? planResult.cases.map(c => c.caseKey)
    ctx.log(`共 ${selectedCases.length} 条用例，启动自检…`)

    // Subscribe to self-check events for this device
    const handleCaseCompleted = (data: Record<string, unknown>) => {
      if (data.deviceId !== deviceId) return
      const result = data.result as CaseResult | undefined
      if (!result) return

      const prev = (ctx.state.progress ?? {}) as Record<string, unknown>
      const passed = (Number(prev.passed) || 0) + (result.status === '通过' ? 1 : 0)
      const failed = (Number(prev.failed) || 0) + (result.status === '失败' ? 1 : 0)
      const failedCases = [...((prev.failed_cases ?? []) as Array<{ name: string; message?: string }>)]
      if (result.status === '失败') {
        failedCases.push({ name: result.caseName ?? String(data.caseKey), message: result.message })
      }

      ctx.patchState({
        progress: {
          ...prev,
          state: 'running',
          passed,
          failed,
          running: Math.max(0, (Number(prev.total) || 0) - passed - failed),
          failed_cases: failedCases,
        },
      })
      ctx.log(`[${result.status}] ${result.caseName ?? data.caseKey}`)
    }

    const handleTestCompleted = (data: Record<string, unknown>) => {
      if (data.deviceId !== deviceId) return
      const session = data.session as TestSession | undefined
      const prev = (ctx.state.progress ?? {}) as Record<string, unknown>

      const failedCount = Number(prev.failed) || 0
      const isInfraError = session && !session.isRunning && failedCount === 0
        && (Number(prev.passed) || 0) === 0

      ctx.patchState({
        progress: {
          ...prev,
          state: failedCount > 0 ? 'case_failed' : (isInfraError ? 'infra_error' : 'success'),
          running: 0,
        },
      })
    }

    onEvent('case_completed', handleCaseCompleted)
    onEvent('test_completed', handleTestCompleted)

    ctx.patchState({
      progress: {
        ...(ctx.state.progress as Record<string, unknown>),
        state: 'running',
        total: selectedCases.length,
        running: selectedCases.length,
      },
      refs: {
        ...ctx.state.refs,
        selfcheck_device_id: deviceId,
        selfcheck_selected_cases: selectedCases,
      },
    })

    try {
      await startCustomTest(deviceId, selectedCases, [])
    } catch (err) {
      ctx.patchState({
        progress: {
          ...(ctx.state.progress as Record<string, unknown>),
          state: 'infra_error',
          error: String(err),
          running: 0,
        },
      })
      ctx.log(`自检启动失败: ${err}`)
    }
  },

  evaluate(ctx: StageContext): StageVerdict {
    const p = ctx.state.progress as Record<string, unknown> | undefined
    const state = p?.state as string | undefined

    if (state === 'waiting_cases') {
      return {
        status: 'waiting_human',
        reason: 'selfcheck_no_cases',
        message: String(p?.message ?? '请手工指定测试用例'),
        actions: [
          { id: 'skip', label: '跳过自检', danger: true },
        ],
      }
    }

    if (state === 'success') {
      return {
        status: 'done',
        summary: {
          total: p?.total,
          passed: p?.passed,
          failed: p?.failed,
        },
      }
    }

    if (state === 'case_failed') {
      return {
        status: 'failed',
        error: `${p?.failed ?? 0} 条用例失败`,
        retryable: true,
        produced: ['testresult'],
      }
    }

    if (state === 'infra_error' || state === 'error') {
      return {
        status: 'failed',
        error: String(p?.error ?? '自检基础设施错误'),
        retryable: true,
        // No testresult produced — triage will be unsafe
      }
    }

    return {
      status: 'running',
      progress: {
        percent: (p?.total && Number(p.total) > 0)
          ? Math.round(((Number(p.passed) || 0) + (Number(p.failed) || 0)) / Number(p.total) * 100)
          : undefined,
        text: `${p?.passed ?? 0} 通过 / ${p?.failed ?? 0} 失败`,
      },
    }
  },

  async cancel(ctx: StageContext) {
    const deviceId = ctx.run.device_id
    if (deviceId) {
      try {
        const { endTest } = await import('../../device-self-check')
        await endTest(deviceId)
      } catch { /* best effort */ }
    }
  },
}

export function installSelfcheckStage(): void {
  registerStageForTest(selfcheckStageDefinition)
}

installSelfcheckStage()
