import type {
  ExternalCapability,
  StageContext,
  StageDefinition,
  StageVerdict,
} from './types'

const pollTimers = new Map<string, ReturnType<typeof setInterval>>()
const pollUnsubs = new Map<string, () => void>()

function timerKey(runId: string, nodeKey: string): string {
  return `${runId}:${nodeKey}`
}

function clearPoll(runId: string, nodeKey: string): void {
  const key = timerKey(runId, nodeKey)
  const timer = pollTimers.get(key)
  if (timer) {
    clearInterval(timer)
    pollTimers.delete(key)
  }
  const unsub = pollUnsubs.get(key)
  if (unsub) {
    unsub()
    pollUnsubs.delete(key)
  }
}

export function createCapabilityStage<TInput>(opts: {
  key: string
  label: string
  capability: ExternalCapability<TInput> | null
  consumes?: StageDefinition['consumes']
  produces?: StageDefinition['produces']
  buildInput: (ctx: StageContext) => TInput
  onSuccess?: (ctx: StageContext, result: Record<string, unknown>) => void
  pollIntervalMs?: number
}): StageDefinition {
  const pollMs = opts.pollIntervalMs ?? 5000

  const def: StageDefinition = {
    key: opts.key,
    label: opts.label,
    consumes: opts.consumes,
    produces: opts.produces,
    async probe() {
      if (!opts.capability) {
        return { available: false, reason: '能力尚未接入' }
      }
      return opts.capability.probe()
    },
    async start(ctx) {
      if (!opts.capability) return
      const input = opts.buildInput(ctx)
      const { runId } = await opts.capability.start(input)
      const refKey = `${opts.key}_run_id`
      ctx.patchState({
        refs: { ...ctx.state.refs, [refKey]: runId },
        progress: { state: 'pending' },
      })

      const applyStatus = (status: import('./types').CapabilityStatus) => {
        if (status.state === 'success' && status.result) {
          opts.onSuccess?.(ctx, status.result)
        }
        ctx.patchState({
          progress: {
            state: status.state,
            progress: status.progress,
            phase: status.phase,
            message: status.message,
            error: status.error,
            result: status.result,
          },
        })
      }

      if (opts.capability.subscribe) {
        const off = opts.capability.subscribe(runId, ev => {
          if (ev.status) applyStatus(ev.status)
          if (ev.line) ctx.log(ev.line)
        })
        pollUnsubs.set(timerKey(ctx.run.run_id, opts.key), off)
      } else {
        const timer = setInterval(async () => {
          try {
            const status = await opts.capability!.getStatus(runId)
            applyStatus(status)
          } catch (err) {
            ctx.log(String(err))
          }
        }, pollMs)
        pollTimers.set(timerKey(ctx.run.run_id, opts.key), timer)
      }
    },
    evaluate(ctx): StageVerdict {
      const p = ctx.state.progress as Record<string, unknown> | undefined
      const state = p?.state as string | undefined
      if (state === 'success') {
        return { status: 'done', summary: p?.result as Record<string, unknown> | undefined }
      }
      if (state === 'failed') {
        return {
          status: 'failed',
          error: String(p?.error ?? '能力执行失败'),
          retryable: true,
        }
      }
      if (state === 'cancelled') {
        return { status: 'failed', error: '已取消', retryable: false }
      }
      return {
        status: 'running',
        progress: {
          percent: p?.progress as number | undefined,
          text: p?.phase as string | undefined,
        },
      }
    },
    async cancel(ctx) {
      clearPoll(ctx.run.run_id, opts.key)
      const refKey = `${opts.key}_run_id`
      const extId = ctx.state.refs[refKey] as string | undefined
      if (extId && opts.capability) {
        await opts.capability.cancel(extId)
      }
    },
  }

  return def
}

export function clearCapabilityPollForTest(): void {
  for (const t of pollTimers.values()) clearInterval(t)
  pollTimers.clear()
  for (const u of pollUnsubs.values()) u()
  pollUnsubs.clear()
}
