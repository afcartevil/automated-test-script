/**
 * TaskStream — Agent 任务事件总线，供 Socket.IO /tahp-run 推送给前端。
 *
 * 事件名:
 *   - task.started / task.phase / task.step / task.message
 *   - task.completed / task.failed / task.correction
 *   - task.skill_use / task.file_change / task.plan / task.tool_completed
 */
import { EventEmitter } from 'events'

export interface TaskEvent {
  type: string
  task_id?: string
  payload: Record<string, unknown>
  ts: number
}

class TaskStream extends EventEmitter {
  /** 手动发布事件 (bug-analysis / adapt-agent 等服务直接调用) */
  publish(ev: TaskEvent) {
    this.emit('event', ev)
  }
}

let _stream: TaskStream | null = null
export function getTaskStream(): TaskStream {
  if (!_stream) _stream = new TaskStream()
  return _stream
}
