/**
 * TaskStream — 把 MCP bridge 的 progress/log 通知规范化为前端可消费的事件流.
 *
 * 事件名 (与 Socket.IO 暴露的相同):
 *   - task.started      { task_id, document_path, module, domain }
 *   - task.phase        { task_id, phase, progress }
 *   - task.step         { task_id, step_id, status, message }
 *   - task.message      { task_id, level, text }
 *   - task.completed    { task_id, result }
 *   - task.failed       { task_id, error }
 *   - task.correction   { task_id, feedback }
 *
 * 来源解析:
 *   MCP notifications/message  params: { level: "info"|"warning"|..., data: <string|object> }
 *   MCP notifications/progress params: { progressToken, progress, total? }
 *   TAHP ProgressEmitter 把结构化 payload 放在 data 字段 — 我们尽量解析 JSON 字符串.
 */
import { EventEmitter } from 'events'
import { getMcpBridge } from './mcp-bridge'
import { logger } from '../logger'

export interface TaskEvent {
  type: string
  task_id?: string
  payload: Record<string, unknown>
  ts: number
}

class TaskStream extends EventEmitter {
  private bound = false

  bind() {
    if (this.bound) return
    const bridge = getMcpBridge()
    bridge.on('log', (params: any) => this.handleLog(params))
    bridge.on('progress', (params: any) => this.handleProgress(params))
    this.bound = true
  }

  private handleLog(params: any) {
    if (!params) return
    const { level, data } = params
    let parsed: any = data
    if (typeof data === 'string') {
      try { parsed = JSON.parse(data) } catch { parsed = { text: data } }
    }
    if (parsed && typeof parsed === 'object') {
      // 进度类 payload
      if (parsed.event && parsed.task_id) {
        this.emit('event', {
          type: parsed.event,
          task_id: parsed.task_id,
          payload: parsed,
          ts: Date.now(),
        } as TaskEvent)
        return
      }
    }
    // 普通日志
    this.emit('event', {
      type: 'task.message',
      task_id: parsed?.task_id,
      payload: { level: level || 'info', text: parsed?.text ?? String(data) },
      ts: Date.now(),
    } as TaskEvent)
  }

  private handleProgress(params: any) {
    if (!params) return
    this.emit('event', {
      type: 'task.progress',
      task_id: String(params.progressToken || ''),
      payload: {
        progress: params.progress,
        total: params.total,
        message: params.message,
      },
      ts: Date.now(),
    } as TaskEvent)
  }

  /** 手动发布事件 (用于 REST 路由本地状态变化) */
  publish(ev: TaskEvent) {
    this.emit('event', ev)
  }
}

let _stream: TaskStream | null = null
export function getTaskStream(): TaskStream {
  if (!_stream) {
    _stream = new TaskStream()
    try { _stream.bind() } catch (err) { logger.warn({ err }, 'task-stream bind failed') }
  }
  return _stream
}
