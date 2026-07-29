import { getTaskStream, type TaskEvent } from '../../task-stream'
import type { ObservedEvent, PipelineEventSource } from '../types'

export const taskStreamSource: PipelineEventSource = {
  id: 'task-stream',
  subscribe(onEvent) {
    const handler = (ev: TaskEvent) => {
      onEvent({
        source: 'task-stream',
        type: ev.type,
        correlation: { taskId: ev.task_id },
        payload: ev.payload ?? {},
        ts: ev.ts,
      } satisfies ObservedEvent)
    }
    getTaskStream().on('event', handler)
    return () => {
      getTaskStream().off('event', handler)
    }
  },
}
