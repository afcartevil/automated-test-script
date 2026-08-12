/**
 * 本机出站连接中心 `/baseline-notify`：收推送 → 写入本地 inbox → ack。
 * 不轮询业务接口；补推由中心在 hello 时主动下发。
 */
import crypto from 'crypto'
import fs from 'fs'
import path from 'path'
import { io, type Socket } from 'socket.io-client'
import { config } from '../../../config'
import { logger } from '../../logger'
import { ingestModemBaselineNotice } from '../modem-baseline-notices'
import { getLocalActor, isCentralConfigured, isLocal } from '../runtime-mode'

type CentralBaselineNotice = {
  noticeId: string
  source: string
  sourceId?: string
  title?: string
  text: string
  platform?: string
  version?: string
  tosVersion?: string
  module?: string
  payload?: Record<string, unknown>
  receivedAt: string
  updatedAt?: string
}

type LocalDeliveryCursor = {
  lastAckNoticeId?: string
  lastAckReceivedAt?: string
  updatedAt: string
}

let socket: Socket | null = null
let started = false

function modemPatchDir(): string {
  return path.resolve(config.dataDir, 'modem-patch')
}

function installIdPath(): string {
  return path.join(modemPatchDir(), 'install-id.txt')
}

function cursorPath(): string {
  return path.join(modemPatchDir(), 'central-delivery-cursor.json')
}

function ensureDir(filePath: string) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true })
}

export function getOrCreateInstallId(): string {
  const file = installIdPath()
  try {
    if (fs.existsSync(file)) {
      const existing = fs.readFileSync(file, 'utf-8').trim()
      if (existing) return existing
    }
  } catch {
    /* recreate below */
  }
  const id = crypto.randomBytes(8).toString('hex')
  try {
    ensureDir(file)
    fs.writeFileSync(file, id, 'utf-8')
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[baseline-notify] failed to persist install-id')
  }
  return id
}

export function getBaselineNotifyActor(): string {
  return `${getLocalActor()}:${getOrCreateInstallId()}`
}

function loadLocalCursor(): LocalDeliveryCursor | undefined {
  const file = cursorPath()
  if (!fs.existsSync(file)) return undefined
  try {
    const raw = JSON.parse(fs.readFileSync(file, 'utf-8')) as LocalDeliveryCursor
    if (raw && typeof raw === 'object') return raw
  } catch {
    /* ignore */
  }
  return undefined
}

function saveLocalCursor(notice: Pick<CentralBaselineNotice, 'noticeId' | 'receivedAt'>): void {
  const file = cursorPath()
  const prev = loadLocalCursor()
  const at = String(notice.receivedAt || '').trim()
  if (!at) return
  const prevAt = String(prev?.lastAckReceivedAt || '').trim()
  if (prevAt && at < prevAt) return
  const next: LocalDeliveryCursor = {
    lastAckNoticeId: notice.noticeId,
    lastAckReceivedAt: at,
    updatedAt: new Date().toISOString(),
  }
  try {
    ensureDir(file)
    fs.writeFileSync(file, JSON.stringify(next, null, 2), 'utf-8')
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[baseline-notify] failed to save local cursor')
  }
}

function handleNotice(notice: CentralBaselineNotice, sock: Socket): void {
  if (!notice?.noticeId || !notice?.text) {
    logger.warn('[baseline-notify] ignore invalid notice payload')
    return
  }
  try {
    const { created } = ingestModemBaselineNotice(
      {
        source: notice.source,
        sourceId: notice.sourceId,
        title: notice.title,
        text: notice.text,
        platform: notice.platform,
        version: notice.version,
        tosVersion: notice.tosVersion,
      },
      {
        preferNoticeId: notice.noticeId,
        preferReceivedAt: notice.receivedAt,
      },
    )
    saveLocalCursor(notice)
    sock.emit('baseline.ack', {
      noticeId: notice.noticeId,
      receivedAt: notice.receivedAt,
    })
    logger.info(
      {
        noticeId: notice.noticeId,
        source: notice.source,
        sourceId: notice.sourceId || '-',
        created,
      },
      '[baseline-notify] ingested',
    )
  } catch (err) {
    logger.warn(
      { err: (err as Error).message, noticeId: notice.noticeId },
      '[baseline-notify] ingest failed',
    )
  }
}

export function startBaselineNotifyClient(): void {
  if (started) return
  if (!isLocal()) {
    logger.info('[baseline-notify] role=central, client disabled')
    return
  }
  if (!isCentralConfigured()) {
    logger.info('[baseline-notify] central not configured, client disabled')
    return
  }

  started = true
  const baseUrl = config.tahp.centralUrl.replace(/\/+$/, '')
  const actor = getBaselineNotifyActor()

  socket = io(`${baseUrl}/baseline-notify`, {
    path: '/socket.io/',
    auth: {
      token: config.tahp.centralToken,
      actor,
    },
    transports: ['websocket', 'polling'],
    reconnection: true,
    reconnectionDelay: 2000,
    reconnectionDelayMax: 15000,
  })

  socket.on('connect', () => {
    const cursor = loadLocalCursor()
    socket?.emit('baseline.hello', {
      actor,
      clientVersion: 'tahp-console',
      cursor: cursor
        ? {
            lastAckReceivedAt: cursor.lastAckReceivedAt,
            lastAckNoticeId: cursor.lastAckNoticeId,
          }
        : undefined,
    })
    logger.info({ url: baseUrl, actor }, '[baseline-notify] connected')
  })

  socket.on('baseline.notice', (notice: CentralBaselineNotice) => {
    if (!socket) return
    handleNotice(notice, socket)
  })

  socket.on('baseline.catchup_done', (payload: { count?: number }) => {
    logger.info({ count: payload?.count ?? 0 }, '[baseline-notify] catchup done')
  })

  socket.on('connect_error', (err) => {
    logger.warn({ err: err.message }, '[baseline-notify] connect_error')
  })

  socket.on('disconnect', (reason) => {
    logger.info({ reason }, '[baseline-notify] disconnected')
  })
}

export function stopBaselineNotifyClient(): void {
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
}
