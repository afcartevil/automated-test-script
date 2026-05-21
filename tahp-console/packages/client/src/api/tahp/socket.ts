/**
 * TAHP /tahp-run Socket.IO 客户端 — 订阅任务进度事件流.
 */
import { io, type Socket } from 'socket.io-client'
import { getApiKey } from '../client'

export interface TahpEvent {
  type: string
  task_id?: string
  payload: Record<string, unknown>
  ts: number
}

let _socket: Socket | null = null

export function getTahpSocket(): Socket {
  if (_socket && _socket.connected) return _socket
  if (_socket) {
    _socket.connect()
    return _socket
  }
  const token = getApiKey()
  const s = io('/tahp-run', {
    transports: ['websocket', 'polling'],
    auth: token ? { token } : undefined,
    query: token ? { token } : undefined,
  })
  s.on('connect', () => {
    // eslint-disable-next-line no-console
    console.info('[tahp-run] connected', s.id)
  })
  s.on('disconnect', (reason) => {
    // eslint-disable-next-line no-console
    console.info('[tahp-run] disconnected', reason)
  })
  _socket = s
  return s
}

export type TahpEventHandler = (ev: TahpEvent) => void

export function subscribeTahp(eventName: string, handler: TahpEventHandler): () => void {
  const s = getTahpSocket()
  s.on(eventName, handler)
  return () => { s.off(eventName, handler) }
}

export function disconnectTahpSocket() {
  if (_socket) {
    _socket.disconnect()
    _socket = null
  }
}
