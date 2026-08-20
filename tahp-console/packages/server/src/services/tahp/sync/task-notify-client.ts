/**
 * 本机出站连接中心 `/task-notify`：auth.owner = Jira 用户名（禁止 user@host）。
 */
import { io, type Socket } from 'socket.io-client'
import { config } from '../../../config'
import { logger } from '../../logger'
import { isCentralConfigured, isLocal } from '../runtime-mode'
import { readJiraUsername } from '../jira-user-config'
import { readCentralUserSession } from '../central-user-session'

let socket: Socket | null = null
let started = false
let currentOwner = ''
const unreadIds = new Set<string>()
const unreadItems = new Map<string, {
  package_id: string
  notice_type?: string
  title?: string
  next?: string
}>()

function resolveOwner(explicit?: string): string {
  const fromArg = String(explicit || '').trim()
  if (fromArg && !fromArg.includes('@')) return fromArg
  const fromSession = String(readCentralUserSession()?.username || '').trim()
  if (fromSession && !fromSession.includes('@')) return fromSession
  const fromJira = String(readJiraUsername() || '').trim()
  if (fromJira && !fromJira.includes('@')) return fromJira
  return ''
}

function connect(owner: string): void {
  const baseUrl = config.tahp.centralUrl.replace(/\/+$/, '')
  currentOwner = owner
  socket = io(`${baseUrl}/task-notify`, {
    path: '/socket.io/',
    auth: {
      token: config.tahp.centralToken,
      owner,
    },
    transports: ['websocket', 'polling'],
    reconnection: true,
    reconnectionDelay: 2000,
    reconnectionDelayMax: 15000,
  })

  socket.on('connect', () => {
    socket?.emit('task.hello', { owner })
    logger.info({ url: baseUrl, owner }, '[task-notify] connected')
  })

  socket.on('connect_error', (err) => {
    logger.warn({ err: err.message }, '[task-notify] connect_error')
  })

  socket.on('disconnect', (reason) => {
    logger.info({ reason }, '[task-notify] disconnected')
  })

  socket.on('task.package', (payload: {
    package_id?: string
    notice_type?: string
    title?: string
    next?: string
  } = {}) => {
    const id = String(payload.package_id || '').trim()
    if (!id) return
    unreadIds.add(id)
    unreadItems.set(id, {
      package_id: id,
      notice_type: payload.notice_type,
      title: payload.title,
      next: payload.next,
    })
    socket?.emit('task.package.ack', { package_id: id })
    logger.info({ package_id: id, notice_type: payload.notice_type, unread: unreadIds.size }, '[task-notify] package received')
  })
}

export function startTaskNotifyClient(): void {
  if (!isLocal()) {
    logger.info('[task-notify] role=central, client disabled')
    return
  }
  if (!isCentralConfigured()) {
    logger.info('[task-notify] central not configured, client disabled')
    return
  }
  const owner = resolveOwner()
  if (!owner) {
    logger.info('[task-notify] no Jira owner yet, client deferred')
    return
  }
  if (started && currentOwner.toLowerCase() === owner.toLowerCase() && socket) return
  stopTaskNotifyClient()
  started = true
  connect(owner)
}

export function reconnectTaskNotifyClient(owner?: string): void {
  const next = resolveOwner(owner)
  if (!next) return
  if (!isLocal() || !isCentralConfigured()) return
  if (started && currentOwner.toLowerCase() === next.toLowerCase() && socket?.connected) {
    socket.emit('task.hello', { owner: next })
    return
  }
  stopTaskNotifyClient()
  started = true
  connect(next)
}

export function stopTaskNotifyClient(): void {
  if (socket) {
    try {
      socket.removeAllListeners()
      socket.close()
    } catch {
      /* ignore */
    }
    socket = null
  }
  started = false
  currentOwner = ''
}

export function getTaskNotifyOwner(): string {
  return currentOwner
}

export function getTaskUnreadIds(): string[] {
  return [...unreadIds]
}

export function getTaskInboxPatches(): Array<{
  package_id: string
  notice_type?: string
  title?: string
  next?: string
}> {
  return [...unreadItems.values()].filter(item => item.notice_type)
}

export function clearTaskUnread(packageId?: string): void {
  if (packageId) {
    unreadIds.delete(packageId)
    unreadItems.delete(packageId)
  } else {
    unreadIds.clear()
    unreadItems.clear()
  }
}
