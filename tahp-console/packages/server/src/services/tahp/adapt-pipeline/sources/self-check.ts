import { onEvent } from '../../device-self-check'
import type { ObservedEvent, PipelineEventSource } from '../types'

const SELF_CHECK_EVENTS = [
  'flash_log',
  'flash_completed',
  'case_completed',
  'test_completed',
  'test_ended',
  'test_error',
  'report_ready',
  'precheck_failed',
  'manual_confirm',
] as const

const fanout = new Set<(ev: ObservedEvent) => void>()
let installed = false

function install(): void {
  if (installed) return
  installed = true
  for (const name of SELF_CHECK_EVENTS) {
    onEvent(name, (data: Record<string, unknown>) => {
      const ev: ObservedEvent = {
        source: 'self-check',
        type: name,
        correlation: { deviceId: data?.deviceId as string | undefined },
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
    return () => {
      fanout.delete(onEv)
    }
  },
}

/** 仅测试：重置扇出安装状态 */
export function resetSelfCheckSourceForTest(): void {
  fanout.clear()
  installed = false
}
