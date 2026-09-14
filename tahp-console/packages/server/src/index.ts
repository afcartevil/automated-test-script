import Koa from 'koa'
import cors from '@koa/cors'
import bodyParser from '@koa/bodyparser'
import serve from 'koa-static'
import send from 'koa-send'
import os from 'os'
import { resolve } from 'path'
import { mkdir } from 'fs/promises'
import { readFileSync } from 'fs'
import { Server as SocketIOServer } from 'socket.io'
import { config } from './config'
import { getToken, requireAuth } from './services/auth'
import { initLoginLimiter } from './services/login-limiter'
import { bindShutdown } from './services/shutdown'
import { setupTerminalWebSocket } from './routes/hermes/terminal'
import { startVersionCheck, prefetchHermesVersion } from './routes/health'
import { registerRoutes } from './routes'
import { setChatRunServer } from './routes/hermes/chat-run'
import { ChatRunSocket } from './services/hermes/run-chat'
import { applyBundledAgentEnv } from './services/hermes/bundled-agent'
import { formatTahpPathsForLog, hasTahpProject } from './services/tahp/paths'
import { ensureJiraWorkspaceLayout } from './services/tahp/jira-workspace'
import { startAgentBridgeManager } from './services/hermes/agent-bridge'
import { HermesSkillInjector } from './services/hermes/skill-injector'
import { logger } from './services/logger'
import { installBffDiagnostics, recordFatal } from './services/crash-log'
import { setupTahpRunSocket } from './routes/tahp/tahp-run'
import { initDeviceSelfCheck } from './services/tahp/device-self-check'
import { startSyncScheduler, startBaselineNotifyClient, startTaskNotifyClient, bindStoredJiraIfAny } from './services/tahp/sync'
import { bootstrapAdaptPipeline } from './routes/tahp/adapt-pipeline'
import { pullAllWorkspaceLayouts } from './services/tahp/adapt-layout/service'
import { pullOrReadLineLayouts } from './services/tahp/adapt-layout/line-cache'
import { bootstrapGkiPatchServer } from './services/tahp/gki-patch'
import { startGkiAlertSyncTimer } from './services/tahp/gki-alert-sync'

installBffDiagnostics()

// Injected by esbuild at build time; fallback to reading package.json in dev mode
declare const __APP_VERSION__: string
const APP_VERSION = typeof __APP_VERSION__ !== 'undefined'
  ? __APP_VERSION__
  : (() => { try { return JSON.parse(readFileSync(resolve(__dirname, '../../package.json'), 'utf-8')).version } catch { return 'dev' } })()

let server: any = null
let servers: any[] = []
let chatRunServer: any = null
let agentBridgeManager: any = null

interface ListenResult {
  primary: any
  servers: any[]
}

function listen(app: Koa, port: number, host: string): Promise<any> {
  return new Promise((resolve, reject) => {
    const s = app.listen(port, host)
    s.once('listening', () => resolve(s))
    s.once('error', reject)
  })
}

async function listenWithFallback(app: Koa, port: number, host?: string): Promise<ListenResult> {
  const bindHost = host || '0.0.0.0'
  console.log(`[bootstrap] listening on ${bindHost}:${port}`)
  const primary = await listen(app, port, bindHost)
  return { primary, servers: [primary] }
}

/**
 * 安全获取网络接口信息（兼容 Termux/proot 环境）
 * 在 proot 环境中 os.networkInterfaces() 会抛出权限错误（errno 13）
 */
function safeNetworkInterfaces() {
  try {
    return os.networkInterfaces()
  } catch {
    return {}
  }
}

export async function bootstrap() {
  const bundledAgentEnv = applyBundledAgentEnv()
  if (bundledAgentEnv.applied) {
    console.log(`[bootstrap] bundled hermes-agent env from ${bundledAgentEnv.source}`)
  }

  console.log(`hermes-web-ui v${APP_VERSION} starting...`)
  console.log(`[bootstrap] ${formatTahpPathsForLog()}`)
  if (!hasTahpProject()) {
    console.warn(
      '[bootstrap] TAHP 工程根校验失败，skills/配置/报告路径可能不正确。' +
      '请在 tahp-console/.env 设置 TAHP_PROJECT_ROOT=<git clone 根目录> 后重启。',
    )
  }
  await mkdir(config.uploadDir, { recursive: true })
  await mkdir(config.dataDir, { recursive: true })

  const authToken = await getToken()
  await initLoginLimiter()
  try {
    const skillInjector = new HermesSkillInjector()
    const injectionResult = await skillInjector.injectMissingSkills()
    if (injectionResult.injected.length > 0) {
      console.log('[bootstrap] bundled skills injected:', injectionResult.injected.join(', '))
    }
    if (injectionResult.updated.length > 0) {
      console.log('[bootstrap] bundled skills updated:', injectionResult.updated.join(', '))
    }
  } catch (err) {
    logger.warn(err, '[bootstrap] failed to inject bundled skills')
    console.warn('[bootstrap] failed to inject bundled skills:', err instanceof Error ? err.message : err)
  }

  try {
    const workspaceRoot = ensureJiraWorkspaceLayout()
    console.log(`[bootstrap] jira workspace: ${workspaceRoot}`)
  } catch (err) {
    logger.warn(err, '[bootstrap] failed to ensure jira workspace layout')
    console.warn('[bootstrap] failed to ensure jira workspace:', err instanceof Error ? err.message : err)
  }

  let agentBridgeReady = false
  try {
    agentBridgeManager = await startAgentBridgeManager()
    agentBridgeReady = agentBridgeManager.running
    if (agentBridgeReady) {
      console.log('[bootstrap] agent bridge started')
    } else {
      console.warn('[bootstrap] agent bridge started but not ready')
    }
  } catch (err) {
    logger.warn(err, '[bootstrap] agent bridge failed to start')
    console.warn('[bootstrap] agent bridge failed to start:', err instanceof Error ? err.message : err)
  }
  if (process.env.TAHP_REQUIRE_AGENT === '1' && !agentBridgeReady) {
    console.error(
      '[bootstrap] Agent Bridge 未就绪，已中止启动（TAHP_REQUIRE_AGENT=1）。\n' +
      '  请在本机执行: cd tahp-console && npm run setup:agent -- --force\n' +
      '  并确认服务端日志中有 [agent-bridge] ready',
    )
    process.exit(1)
  }
  const { initAllStores } = await import('./db/hermes/init')
  initAllStores()
  console.log('[bootstrap] all stores initialized')

  const app = new Koa()
  app.use(cors({ origin: config.corsOrigins }))
  app.use(bodyParser({ encoding: 'utf-8', jsonLimit: '20mb' }))
  console.log('[bootstrap] cors + bodyParser registered')

  // Register all routes (handles auth internally)
  const proxyMiddleware = registerRoutes(app, requireAuth(authToken))
  app.use(proxyMiddleware)
  console.log('[bootstrap] routes registered')

  if (authToken) {
    console.log(`Auth enabled — token: ${authToken}`)
    logger.info('Auth enabled — token: %s', authToken)
  }

  // SPA fallback
  const distDir = resolve(__dirname, '..', 'client')
  app.use(serve(distDir))
  app.use(async (ctx) => {
    if (!ctx.path.startsWith('/api') &&
      ctx.path !== '/health' &&
      ctx.path !== '/upload' &&
      ctx.path !== '/webhook' &&
      !ctx.path.startsWith('/webhook/')) {
      await send(ctx, 'index.html', { root: distDir })
    }
  })
  console.log('[bootstrap] SPA fallback registered')

  // Start server using the configured bind host. Default is IPv4 for WSL stability.
  const listenResult = await listenWithFallback(app, config.port, config.host)
  server = listenResult.primary
  servers = listenResult.servers
  console.log('[bootstrap] app.listen called')

  setupTerminalWebSocket(servers)
  console.log('[bootstrap] terminal websocket setup')

  // Socket.IO — create a single shared server instance for /chat-run and /tahp-run namespaces
  const io = new SocketIOServer(servers[0], {
    cors: { origin: config.corsOrigins, methods: ['GET', 'POST'] },
    path: '/socket.io/',
  })

  // Chat run Socket.IO — /chat-run namespace
  chatRunServer = new ChatRunSocket(io)
  setChatRunServer(chatRunServer)
  chatRunServer.init()

  // TAHP Socket.IO — /tahp-run 命名空间
  try {
    setupTahpRunSocket(io)
  } catch (err) {
    logger.warn({ err }, '[bootstrap] tahp-run socket setup failed')
  }

  // Session deleter — periodically drain pending session deletes
  const { SessionDeleter } = await import('./services/hermes/session-deleter')
  const sessionDeleter = SessionDeleter.getInstance()
  const activeProfile = process.env.PROFILE || 'default'
  sessionDeleter.start(activeProfile)
  console.log('[bootstrap] session deleter started, profile=%s', activeProfile)

  // Catch-all: destroy upgrade requests not handled by terminal or Socket.IO
  servers.forEach((httpServer) => {
    httpServer.on('upgrade', (req: any, socket: any) => {
      const url = new URL(req.url || '', `http://${req.headers.host}`)
      if (url.pathname !== '/api/hermes/terminal' && !url.pathname.startsWith('/socket.io/')) {
        socket.destroy()
      }
    })
  })

  const interfaces = safeNetworkInterfaces()
  const localIp = Object.values(interfaces).flat().find(i => i?.family === 'IPv4' && !i?.internal)?.address || 'localhost'
  console.log(`Server: http://localhost:${config.port} (LAN: http://${localIp}:${config.port})`)
  console.log(`Log: ${config.appHome}/logs/server.log`)
  logger.info('Server: http://localhost:%d (LAN: http://%s:%d)', config.port, localIp, config.port)

  servers.forEach((httpServer) => {
    httpServer.on('error', (err: any) => {
      console.error('[bootstrap] server error:', err.code || err.message)
      logger.error({ err }, 'Server error')
    })
  })

  bindShutdown(servers, undefined, chatRunServer, agentBridgeManager)
  startVersionCheck()
  if (agentBridgeReady) {
    prefetchHermesVersion()
  }
  initDeviceSelfCheck()

  // TAHP 中心同步：local 角色 + 已配置中心时，启动拉取调度（离线容忍）
  try {
    startSyncScheduler()
  } catch (err) {
    logger.warn({ err }, '[bootstrap] sync scheduler failed to start')
  }

  // 中心基线通知：出站 Socket.IO，收推送写入本机 inbox
  try {
    startBaselineNotifyClient()
  } catch (err) {
    logger.warn({ err }, '[bootstrap] baseline-notify client failed to start')
  }

  // 任务通道：按 Jira / 一键配置域账号连 /task-notify；已有凭据则绑定中心账户
  try {
    startTaskNotifyClient()
  } catch (err) {
    logger.warn({ err }, '[bootstrap] task-notify client failed to start')
  }
  void bindStoredJiraIfAny()
    .catch((err) => {
      logger.warn({ err }, '[bootstrap] jira-bind on startup failed')
    })
    .finally(() => {
      try {
        startTaskNotifyClient()
      } catch (err) {
        logger.warn({ err }, '[bootstrap] task-notify client failed to start after bind')
      }
    })

  try {
    await bootstrapAdaptPipeline()
  } catch (err) {
    logger.warn({ err }, '[bootstrap] adapt-pipeline recover failed')
  }

  try {
    await pullAllWorkspaceLayouts()
  } catch (err) {
    logger.warn({ err }, '[bootstrap] adapt-layout published pull failed')
  }

  try {
    const { isCentralConfigured } = await import('./services/tahp/runtime-mode')
    const { centralClient } = await import('./services/tahp/sync/central-client')
    const result = await pullOrReadLineLayouts(
      isCentralConfigured()
        ? () => centralClient.fetchPublishedLineLayouts()
        : undefined,
    )
    if (result.pulled) {
      logger.info({ lines: result.cache?.lines.length || 0 }, '[bootstrap] adapt-layout line cache pulled')
    } else if (result.error) {
      logger.warn({ error: result.error, cached: !!result.cache }, '[bootstrap] adapt-layout line cache kept previous')
    }
  } catch (err) {
    logger.warn({ err }, '[bootstrap] adapt-layout line cache pull failed')
  }

  // GKI：后台拉起，不阻塞 Console 主服务就绪；进页时 ensure 会复用同一 startingPromise
  void bootstrapGkiPatchServer()
    .then((gkiResult) => {
      if (gkiResult.ok && !gkiResult.skipped && gkiResult.status) {
        console.log(`[bootstrap] gki-patch ready: ${gkiResult.status.appUrl}`)
      } else if (gkiResult.skipped) {
        console.log('[bootstrap] gki-patch auto-start skipped')
      } else if (!gkiResult.ok) {
        console.warn(
          `[bootstrap] gki-patch failed to start: ${gkiResult.error}\n` +
          '  进入 GKI 页面时会自动重试；也可执行 npm run setup:gki-patch 后重启',
        )
      }
    })
    .catch((err) => {
      logger.warn({ err }, '[bootstrap] gki-patch bootstrap failed')
      console.warn('[bootstrap] gki-patch bootstrap failed:', err instanceof Error ? err.message : err)
    })

  // GKI 异常告警：仅在 Console 进程存活时轻量定时；主路径仍是进工作台补拉
  try {
    startGkiAlertSyncTimer()
  } catch (err) {
    logger.warn({ err }, '[bootstrap] gki-alert-sync timer failed to start')
  }
}

bootstrap().catch((error) => {
  console.error('FATAL: Failed to start Hermes Web UI')
  console.error(error)
  try { recordFatal('bootstrap-failed', error) } catch { /* ignore */ }
  logger.fatal(error, 'Fatal error during bootstrap')
  process.exit(1)
})
