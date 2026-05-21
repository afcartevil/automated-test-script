/**
 * Socket.IO /tahp-run 命名空间 — 把 TaskStream 的事件推送到前端.
 */
import type { Server as IOServer } from 'socket.io'
import { getTaskStream, TaskEvent } from '../../services/tahp/task-stream'
import { logger } from '../../services/logger'

export function setupTahpRunSocket(io: IOServer): void {
  const ns = io.of('/tahp-run')
  ns.on('connection', (socket) => {
    logger.info({ sid: socket.id }, '[tahp-run] client connected')
    socket.emit('hello', { server: 'tahp-console', ts: Date.now() })
    socket.on('disconnect', (reason) => {
      logger.info({ sid: socket.id, reason }, '[tahp-run] client disconnected')
    })
  })

  const stream = getTaskStream()
  stream.on('event', (ev: TaskEvent) => {
    ns.emit(ev.type, ev)
  })
  logger.info('[tahp-run] socket namespace ready')
}
