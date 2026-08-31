import { spawn, type ChildProcess } from 'child_process'
import fs from 'fs'
import http from 'http'
import path from 'path'
import { config as serverConfig } from '../../config'
import { logger } from '../logger'
import { getActiveProfileName } from '../hermes/hermes-profile'
import { resolveGatewayUpstream } from '../hermes/run-chat/handle-api-run'
import { readHarnessEnvFile } from './harness-env-sync'
import { readUnifiedConfig } from './unified-config'

const DEFAULT_PORT = Number(process.env.GKI_PATCH_PORT || 8651)
const STARTUP_TIMEOUT_MS = 60_000
const HEALTH_POLL_MS = 500

/** 集成模式：由 EasyAdapter 托管生命周期；独立模式：使用 run_windows.bat / run_linux.sh */
export function isGkiPatchIntegratedMode() {
  return process.env.GKI_PATCH_STANDALONE !== '1'
}

/**
 * Resolve EasyAdapter's active OpenAI-compatible LLM for GKI Patch injection.
 * Anthropic direct / gateway fallback / missing key → null (GKI keeps own config).
 */
export function resolveEaLlmForGki(): {
  apiKey: string
  apiBase: string
  model: string
} | null {
  if (!isGkiPatchIntegratedMode()) return null
  try {
    const profile = getActiveProfileName() || 'default'
    const gw = resolveGatewayUpstream(profile)
    if (gw.providerType !== 'openai-chat') return null
    const apiKey = (gw.apiKey || '').trim()
    let upstream = (gw.upstream || '').trim().replace(/\/+$/, '')
    if (!apiKey || !upstream || upstream.startsWith('anthropic://')) return null
    // Align with Hermes openai-chat URL: …/v1/chat/completions
    if (upstream.endsWith('/chat/completions')) {
      upstream = upstream.slice(0, -'/chat/completions'.length).replace(/\/+$/, '')
    }
    const apiBase = upstream.endsWith('/v1') ? upstream : `${upstream}/v1`
    const model = (gw.defaultModel || '').trim() || 'gpt-4o'
    return { apiKey, apiBase, model }
  } catch (err) {
    logger.debug(
      { err: (err as Error).message },
      '[gki-patch] failed to resolve EA LLM for GKI',
    )
    return null
  }
}

/**
 * Resolve EasyAdapter harness / 一键配置 SSH for GKI Patch injection.
 * Maps domain + Linux server fields → GKI cqris bastion credentials.
 * EA has no separate Linux username → reuse domain_account as target_user.
 */
export function resolveEaSshForGki(): {
  bastionUser: string
  bastionPassword: string
  targetIp: string
  targetUser: string
  targetPassword: string
  otpSecret: string
} | null {
  if (!isGkiPatchIntegratedMode()) return null
  try {
    const uc = readUnifiedConfig()
    const harness = readHarnessEnvFile()

    const bastionUser = (
      uc.domain_account || harness.HARNESS_QIZHI_USER || ''
    ).trim()
    const bastionPassword = (
      uc.domain_password || harness.HARNESS_QIZHI_BASTION_PASSWORD || ''
    ).trim()
    const targetIp = (
      uc.linux_server_ip || harness.HARNESS_QIZHI_TARGET_HOST || ''
    ).trim()
    const targetPassword = (
      uc.linux_server_password || harness.HARNESS_QIZHI_TARGET_PASSWORD || ''
    ).trim()
    const targetUser = bastionUser
    const otpSecret = (
      uc.qizhi_totp_secret || harness.HARNESS_QIZHI_OTP_SECRET || ''
    ).trim().replace(/\s+/g, '')

    if (!bastionUser || !bastionPassword || !targetIp || !targetPassword) {
      return null
    }
    return {
      bastionUser,
      bastionPassword,
      targetIp,
      targetUser,
      targetPassword,
      otpSecret,
    }
  } catch (err) {
    logger.debug(
      { err: (err as Error).message },
      '[gki-patch] failed to resolve EA SSH for GKI',
    )
    return null
  }
}

/** EasyAdapter 启动时是否自动拉起 GKI Patch 服务 */
export function isGkiPatchAutoStartEnabled() {
  if (process.env.GKI_PATCH_AUTO_START === '0') return false
  if (process.env.TAHP_SKIP_GKI_PATCH_DEPS === '1') return false
  return isGkiPatchIntegratedMode()
}

let childProcess: ChildProcess | null = null
let activePort = DEFAULT_PORT
let startingPromise: Promise<void> | null = null
let gkiQualityPollTimer: ReturnType<typeof setInterval> | null = null
const uploadedGkiJobIds = new Set<string>()

const EA_RESOLVE_CACHE_MS = 15_000
let eaLlmCache: { at: number; value: ReturnType<typeof resolveEaLlmForGki> } | null = null
let eaSshCache: { at: number; value: ReturnType<typeof resolveEaSshForGki> } | null = null

function resolveEaLlmForGkiCached() {
  const now = Date.now()
  if (eaLlmCache && now - eaLlmCache.at < EA_RESOLVE_CACHE_MS) return eaLlmCache.value
  const value = resolveEaLlmForGki()
  eaLlmCache = { at: now, value }
  return value
}

function resolveEaSshForGkiCached() {
  const now = Date.now()
  if (eaSshCache && now - eaSshCache.at < EA_RESOLVE_CACHE_MS) return eaSshCache.value
  const value = resolveEaSshForGki()
  eaSshCache = { at: now, value }
  return value
}

async function fetchGkiUpgradeJobs(): Promise<GkiUpgradeJobRow[]> {
  const url = `http://127.0.0.1:${activePort}/api/upgrade/jobs?limit=50`
  return new Promise((resolve, reject) => {
    const req = http.get(url, { timeout: 10000 }, (res) => {
      let body = ''
      res.on('data', chunk => { body += chunk })
      res.on('end', () => {
        try {
          const parsed = JSON.parse(body) as { jobs?: GkiUpgradeJobRow[] }
          resolve(parsed.jobs || [])
        } catch (e) {
          reject(e)
        }
      })
    })
    req.on('error', reject)
    req.on('timeout', () => {
      req.destroy()
      reject(new Error('GKI jobs request timeout'))
    })
  })
}

function startGkiQualityPoll() {
  if (gkiQualityPollTimer) return
  gkiQualityPollTimer = setInterval(async () => {
    if (!await probeHealth(activePort)) return
    try {
      const { isGkiTerminal } = await import('./quality-run-mapper')
      const { uploadGkiPatchJobToCentral } = await import('./quality-run-upload')
      const jobs = await fetchGkiUpgradeJobs()
      for (const job of jobs) {
        const id = String(job.id)
        if (!isGkiTerminal(job.status)) continue
        if (uploadedGkiJobIds.has(id)) continue
        const res = await uploadGkiPatchJobToCentral(job)
        if (res.uploaded) uploadedGkiJobIds.add(id)
      }
    } catch (err) {
      logger.debug({ err: (err as Error).message }, '[gki-patch] quality poll failed')
    }
  }, 30000)
}

function stopGkiQualityPoll() {
  if (gkiQualityPollTimer) {
    clearInterval(gkiQualityPollTimer)
    gkiQualityPollTimer = null
  }
}

interface GkiUpgradeJobRow {
  id: number | string
  status: string
  from_tag?: string
  to_tag?: string
  phase?: string
  build_exit_code?: number
  applied_commits?: number
  total_commits?: number
  conflict_files?: string[]
  error_msg?: string
  created_at?: string
  completed_at?: string
  repo?: string
  options?: string
}

/** List recent GKI upgrade jobs via local GKI Patch Tool HTTP API. */
export async function listGkiUpgradeJobs(limit = 50): Promise<GkiUpgradeJobRow[]> {
  await ensureGkiPatchServer()
  await waitUntilHealthy(activePort, 15_000)
  const capped = Math.min(200, Math.max(1, limit))
  const url = `http://127.0.0.1:${activePort}/api/upgrade/jobs?limit=${capped}`
  return gkiHttpGetJson<{ jobs?: GkiUpgradeJobRow[] }>(url).then((parsed) => parsed.jobs || [])
}

export type GkiAnalysisTaskRow = {
  id: string
  type?: string
  status?: string
  from_tag?: string
  to_tag?: string
  sha?: string
  created_at?: string
  repo?: string
}

/** List recent GKI analysis tasks via local GKI Patch Tool HTTP API. */
export async function listGkiAnalysisTasks(limit = 50): Promise<GkiAnalysisTaskRow[]> {
  await ensureGkiPatchServer()
  await waitUntilHealthy(activePort, 15_000)
  const capped = Math.min(200, Math.max(1, limit))
  const url = `http://127.0.0.1:${activePort}/api/tasks?limit=${capped}`
  return gkiHttpGetJson<{ tasks?: GkiAnalysisTaskRow[] }>(url).then((parsed) => parsed.tasks || [])
}

function gkiHttpGetJson<T>(url: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const req = http.get(url, { timeout: 10000 }, (res) => {
      let body = ''
      res.on('data', chunk => { body += chunk })
      res.on('end', () => {
        if ((res.statusCode || 500) >= 400) {
          reject(new Error(`GKI HTTP ${res.statusCode}`))
          return
        }
        try {
          resolve(JSON.parse(body) as T)
        } catch (e) {
          reject(e)
        }
      })
    })
    req.on('error', reject)
    req.on('timeout', () => {
      req.destroy()
      reject(new Error('GKI request timeout'))
    })
  })
}

/** Soft wait after ensure — covers brief post-spawn readiness gaps. */
async function waitUntilHealthy(port: number, timeoutMs: number) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (await probeHealth(port)) return
    await new Promise(r => setTimeout(r, 400))
  }
  throw new Error('GKI Patch 服务启动较慢，请稍后重试')
}

function toolRootCandidates() {
  const envOverride = process.env.GKI_PATCH_TOOL_ROOT?.trim()
  const candidates = [
    envOverride ? path.resolve(envOverride) : '',
    path.resolve(process.cwd(), '..', 'tools', 'gki-patch-tool'),
    path.resolve(process.cwd(), 'tools', 'gki-patch-tool'),
    path.resolve(process.cwd(), '..', '..', 'tools', 'gki-patch-tool'),
  ].filter(Boolean)

  return Array.from(new Set(candidates))
}

export function gkiPatchToolRoot() {
  for (const candidate of toolRootCandidates()) {
    if (fs.existsSync(candidate)) {
      return candidate
    }
  }
  return toolRootCandidates()[0] ?? path.resolve(process.cwd(), '..', 'tools', 'gki-patch-tool')
}

function ensureToolRoot() {
  const toolRoot = gkiPatchToolRoot()
  if (!fs.existsSync(toolRoot)) {
    throw new Error(
      `GKI patch tool root not found: ${toolRoot}; please check tools/gki-patch-tool or GKI_PATCH_TOOL_ROOT`,
    )
  }
  return toolRoot
}

function gkiPatchDataDir(toolRoot: string) {
  const override = process.env.GKI_PATCH_DATA_DIR?.trim()
  if (override) return path.resolve(override)
  return path.resolve(toolRoot)
}

function legacyIntegratedDataDir() {
  return path.resolve(serverConfig.dataDir, 'gki-patch')
}

function defaultSettingsPath(toolRoot: string) {
  return path.resolve(toolRoot, 'gki-patch-tool.yaml')
}

function frontendDistPath(toolRoot: string) {
  return path.resolve(toolRoot, 'frontend', 'dist', 'index.html')
}

function pythonExecutable(toolRoot: string) {
  const venvPython = process.platform === 'win32'
    ? path.resolve(toolRoot, '.venv', 'Scripts', 'python.exe')
    : path.resolve(toolRoot, '.venv', 'bin', 'python')
  if (fs.existsSync(venvPython)) return venvPython
  return process.env.PYTHON ?? 'python'
}

function gkiPatchDbPath(dataDir: string) {
  return path.resolve(dataDir, 'web_app', 'data', 'gki_patch.db')
}

function toolDefaultDbPath(toolRoot: string) {
  return path.resolve(toolRoot, 'web_app', 'data', 'gki_patch.db')
}

function copyDatabaseFamily(sourceDb: string, targetDb: string) {
  const suffixes = ['', '-wal', '-shm', '-journal']
  for (const suffix of suffixes) {
    const source = `${sourceDb}${suffix}`
    const target = `${targetDb}${suffix}`
    if (!fs.existsSync(source)) continue
    fs.mkdirSync(path.dirname(target), { recursive: true })
    fs.copyFileSync(source, target)
  }
}

/** 集成模式首次启动时，从旧版 dataDir/gki-patch 或工具目录迁入已有数据库 */
function seedIntegratedDatabase(toolRoot: string, dataDir: string) {
  const targetDb = gkiPatchDbPath(dataDir)
  const sources = [
    toolDefaultDbPath(toolRoot),
    gkiPatchDbPath(legacyIntegratedDataDir()),
  ].filter((source, index, list) => list.indexOf(source) === index && source !== targetDb)

  let migrated = false
  for (const sourceDb of sources) {
    if (!fs.existsSync(sourceDb)) continue

    const sourceSize = fs.statSync(sourceDb).size
    const targetSize = fs.existsSync(targetDb) ? fs.statSync(targetDb).size : 0
    const targetLooksEmpty = targetSize < 1024 * 1024
    const sourceHasData = sourceSize > targetSize

    if (!sourceHasData || (!targetLooksEmpty && targetSize >= sourceSize * 0.9)) {
      continue
    }

    copyDatabaseFamily(sourceDb, targetDb)
    logger.info(
      '[gki-patch] seeded database from %s (%d bytes) to %s',
      sourceDb,
      sourceSize,
      targetDb,
    )
    migrated = true
    break
  }
  return migrated
}

function ensureDataDirs(toolRoot: string) {
  const dataDir = gkiPatchDataDir(toolRoot)
  fs.mkdirSync(path.resolve(dataDir, 'web_app', 'data'), { recursive: true })
  fs.mkdirSync(path.resolve(dataDir, 'outputs'), { recursive: true })
  return dataDir
}

function probeHealth(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${port}/app/`, { timeout: 2000 }, (res) => {
      res.resume()
      resolve(res.statusCode !== undefined && res.statusCode < 500)
    })
    req.on('error', () => resolve(false))
    req.on('timeout', () => {
      req.destroy()
      resolve(false)
    })
  })
}

async function waitForHealthy(port: number) {
  const deadline = Date.now() + STARTUP_TIMEOUT_MS
  while (Date.now() < deadline) {
    if (await probeHealth(port)) return
    await new Promise((r) => setTimeout(r, HEALTH_POLL_MS))
  }
  throw new Error(`GKI patch tool failed to start within ${STARTUP_TIMEOUT_MS / 1000}s on port ${port}`)
}

async function findFreePort(startPort: number) {
  for (let port = startPort; port < startPort + 50; port += 1) {
    if (await probeHealth(port)) {
      activePort = port
      return port
    }
    const available = await new Promise<boolean>((resolve) => {
      const server = http.createServer()
      server.once('error', () => resolve(false))
      server.listen(port, '127.0.0.1', () => {
        server.close(() => resolve(true))
      })
    })
    if (available) {
      activePort = port
      return port
    }
  }
  throw new Error(`No free port found near ${startPort}`)
}

function buildSpawnEnv(toolRoot: string, dataDir: string) {
  const settingsPath = process.env.GKI_SETTINGS?.trim() || defaultSettingsPath(toolRoot)
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    PYTHONUNBUFFERED: '1',
    PYTHONIOENCODING: 'utf-8',
    PYTHONPATH: [toolRoot, path.resolve(toolRoot, 'tools')].join(path.delimiter),
    GKI_SETTINGS: settingsPath,
    GKI_HOST: '127.0.0.1',
    GKI_PORT: String(activePort),
    GKI_DATA_DIR: dataDir,
  }

  const eaLlm = resolveEaLlmForGkiCached()
  if (eaLlm) {
    env.GKI_LLM_MANAGED_BY_EA = '1'
    env.GKI_LLM_API_KEY = eaLlm.apiKey
    env.GKI_LLM_API_BASE = eaLlm.apiBase
    env.GKI_LLM_MODEL = eaLlm.model
    logger.info(
      '[gki-patch] injecting EA LLM base=%s model=%s',
      eaLlm.apiBase,
      eaLlm.model,
    )
  } else {
    delete env.GKI_LLM_MANAGED_BY_EA
    if (isGkiPatchIntegratedMode()) {
      logger.info(
        '[gki-patch] EA has no OpenAI-compatible LLM; GKI will use its own settings/DB config',
      )
    }
  }

  const eaSsh = resolveEaSshForGkiCached()
  if (eaSsh) {
    env.GKI_SSH_MANAGED_BY_EA = '1'
    env.GKI_SSH_BASTION_USER = eaSsh.bastionUser
    env.GKI_SSH_BASTION_PASSWORD = eaSsh.bastionPassword
    env.GKI_SSH_TARGET_IP = eaSsh.targetIp
    env.GKI_SSH_TARGET_USER = eaSsh.targetUser
    env.GKI_SSH_TARGET_PASSWORD = eaSsh.targetPassword
    if (eaSsh.otpSecret) {
      env.GKI_SSH_OTP_SECRET = eaSsh.otpSecret
    } else {
      delete env.GKI_SSH_OTP_SECRET
    }
    logger.info(
      '[gki-patch] injecting EA SSH bastion_user=%s target_ip=%s',
      eaSsh.bastionUser,
      eaSsh.targetIp,
    )
  } else {
    delete env.GKI_SSH_MANAGED_BY_EA
    if (isGkiPatchIntegratedMode()) {
      logger.info(
        '[gki-patch] EA SSH incomplete; GKI will use its own settings/DB SSH config',
      )
    }
  }

  return env
}

async function spawnGkiServer() {
  const toolRoot = ensureToolRoot()
  const dataDir = ensureDataDirs(toolRoot)
  seedIntegratedDatabase(toolRoot, dataDir)

  const dist = frontendDistPath(toolRoot)
  if (!fs.existsSync(dist)) {
    throw new Error(
      `GKI frontend not built: ${dist}; run "cd tools/gki-patch-tool/frontend && npm install && npm run build"`,
    )
  }

  activePort = await findFreePort(DEFAULT_PORT)

  const pythonExe = pythonExecutable(toolRoot)
  const args = [
    '-m', 'uvicorn',
    'web_app.app:app',
    '--host', '127.0.0.1',
    '--port', String(activePort),
    '--workers', '1',
    '--log-level', 'info',
  ]

  childProcess = spawn(pythonExe, args, {
    cwd: toolRoot,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: buildSpawnEnv(toolRoot, dataDir),
    windowsHide: true,
  })

  const logDir = path.resolve(dataDir, 'logs')
  fs.mkdirSync(logDir, { recursive: true })
  const logPath = path.resolve(logDir, 'gki-patch-server.log')
  const logStream = fs.createWriteStream(logPath, { flags: 'a' })
  childProcess.stdout?.pipe(logStream)
  childProcess.stderr?.pipe(logStream)

  childProcess.on('exit', (code, signal) => {
    logger.info('[gki-patch] process exited code=%s signal=%s', code, signal)
    childProcess = null
    startingPromise = null
  })

  childProcess.on('error', (err) => {
    logger.error(err, '[gki-patch] process error')
    childProcess = null
    startingPromise = null
  })

  await waitForHealthy(activePort)
  logger.info('[gki-patch] server ready at http://127.0.0.1:%d/app/', activePort)
}

export async function ensureGkiPatchServer() {
  if (await probeHealth(activePort)) {
    const status = getGkiPatchStatus()
    status.running = true
    startGkiQualityPoll()
    return status
  }

  if (childProcess && !childProcess.killed) {
    await waitForHealthy(activePort)
    const status = getGkiPatchStatus()
    status.running = true
    return status
  }

  if (!startingPromise) {
    startingPromise = spawnGkiServer().finally(() => {
      startingPromise = null
    })
  }
  await startingPromise
  const status = getGkiPatchStatus()
  status.running = true
  startGkiQualityPoll()
  return status
}

/** EasyAdapter bootstrap：集成模式下随主服务一并启动 GKI Patch */
export async function bootstrapGkiPatchServer() {
  if (!isGkiPatchAutoStartEnabled()) {
    logger.info('[gki-patch] integrated auto-start disabled, skipping')
    return { ok: true, skipped: true as const }
  }

  try {
    const status = await ensureGkiPatchServer()
    return { ok: true as const, status }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    logger.warn('[gki-patch] bootstrap start failed: %s', message)
    return { ok: false as const, error: message }
  }
}

export function getGkiPatchStatus() {
  const toolRoot = gkiPatchToolRoot()
  const dataDir = gkiPatchDataDir(toolRoot)
  const dist = frontendDistPath(toolRoot)
  const dbPath = gkiPatchDbPath(dataDir)
  const legacyDbPath = gkiPatchDbPath(legacyIntegratedDataDir())
  const eaLlm = resolveEaLlmForGkiCached()
  const eaSsh = resolveEaSshForGkiCached()
  return {
    toolRoot,
    dataDir,
    dbPath,
    seedDbPath: legacyDbPath,
    port: activePort,
    appBaseUrl: `http://127.0.0.1:${activePort}/app`,
    appUrl: `http://127.0.0.1:${activePort}/app/`,
    running: false as boolean,
    starting: Boolean(startingPromise),
    frontendBuilt: fs.existsSync(dist),
    settingsPath: process.env.GKI_SETTINGS?.trim() || defaultSettingsPath(toolRoot),
    integrated: isGkiPatchIntegratedMode(),
    autoStart: isGkiPatchAutoStartEnabled(),
    llmManagedByEa: Boolean(eaLlm),
    llmModel: eaLlm?.model || '',
    llmApiBase: eaLlm?.apiBase || '',
    sshManagedByEa: Boolean(eaSsh),
    sshTargetIp: eaSsh?.targetIp || '',
    sshBastionUser: eaSsh?.bastionUser || '',
  }
}

export async function getGkiPatchStatusAsync() {
  const status = getGkiPatchStatus()
  status.running = await probeHealth(activePort)
  status.starting = Boolean(startingPromise) && !status.running
  return status
}

export function stopGkiPatchServer() {
  stopGkiQualityPoll()
  if (!childProcess || childProcess.killed) return
  childProcess.kill('SIGTERM')
  childProcess = null
  startingPromise = null
}

export function getGkiPatchDefaults() {
  const toolRoot = ensureToolRoot()
  return {
    toolRoot,
    dataDir: gkiPatchDataDir(toolRoot),
    settingsPath: process.env.GKI_SETTINGS?.trim() || defaultSettingsPath(toolRoot),
    frontendBuilt: fs.existsSync(frontendDistPath(toolRoot)),
    defaultPort: DEFAULT_PORT,
  }
}
