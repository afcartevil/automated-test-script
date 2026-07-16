import { spawn, type ChildProcess } from 'child_process'
import fs from 'fs'
import http from 'http'
import path from 'path'
import { config as serverConfig } from '../../config'
import { logger } from '../logger'

const DEFAULT_PORT = Number(process.env.GKI_PATCH_PORT || 8651)
const STARTUP_TIMEOUT_MS = 60_000
const HEALTH_POLL_MS = 500

/** 集成模式：由 EasyAdapter 托管生命周期；独立模式：使用 run_windows.bat / run_linux.sh */
export function isGkiPatchIntegratedMode() {
  return process.env.GKI_PATCH_STANDALONE !== '1'
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
  return {
    ...process.env,
    PYTHONUNBUFFERED: '1',
    PYTHONIOENCODING: 'utf-8',
    PYTHONPATH: [toolRoot, path.resolve(toolRoot, 'tools')].join(path.delimiter),
    GKI_SETTINGS: settingsPath,
    GKI_HOST: '127.0.0.1',
    GKI_PORT: String(activePort),
    GKI_DATA_DIR: dataDir,
  }
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
  return {
    toolRoot,
    dataDir,
    dbPath,
    seedDbPath: legacyDbPath,
    port: activePort,
    appBaseUrl: `http://127.0.0.1:${activePort}/app`,
    appUrl: `http://127.0.0.1:${activePort}/app/`,
    running: false as boolean,
    frontendBuilt: fs.existsSync(dist),
    settingsPath: process.env.GKI_SETTINGS?.trim() || defaultSettingsPath(toolRoot),
    integrated: isGkiPatchIntegratedMode(),
    autoStart: isGkiPatchAutoStartEnabled(),
  }
}

export async function getGkiPatchStatusAsync() {
  const status = getGkiPatchStatus()
  status.running = await probeHealth(activePort)
  return status
}

export function stopGkiPatchServer() {
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
