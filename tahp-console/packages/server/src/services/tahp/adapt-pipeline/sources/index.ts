import type { PipelineEventSource } from '../types'
import { selfCheckSource } from './self-check'
import { taskStreamSource } from './task-stream'

const SOURCES: PipelineEventSource[] = [taskStreamSource, selfCheckSource]

let started = false
let unsubscribeAll: Array<() => void> = []
let onPipelineEvent: ((ev: import('../types').ObservedEvent) => void) | null = null

export function setPipelineEventHandler(
  handler: ((ev: import('../types').ObservedEvent) => void) | null,
): void {
  onPipelineEvent = handler
}

export function startSources(): void {
  if (started) return
  started = true
  for (const src of SOURCES) {
    const off = src.subscribe(ev => {
      onPipelineEvent?.(ev)
    })
    unsubscribeAll.push(off)
  }
}

export function stopSources(): void {
  for (const off of unsubscribeAll) off()
  unsubscribeAll = []
  started = false
}

/** 仅测试 */
export function resetSourcesForTest(): void {
  stopSources()
  onPipelineEvent = null
}
