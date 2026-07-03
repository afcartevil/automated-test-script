import fs from 'fs'
import path from 'path'
import crypto from 'crypto'
import { spawn, spawnSync } from 'child_process'
import type { ServerResponse } from 'http'
import { config as serverConfig } from '../../config'

export type ModemBaselineStatus = 'running' | 'success' | 'failed' | 'conflict'
export type ModemBaselineMode = 'stop_after_merge'

export type ModemBaselineConfig = {
  NODE_BRANCH: string
  target_BRANCH: string
  AP_lable: string
  DESCRIPTION?: string
  JIRAID: string
  work_dir: string
  mapped_prefix?: string
  remote_prefix?: string
}

export type ModemBaselineRunMeta = {
  runId: string
  status: ModemBaselineStatus
  mode: ModemBaselineMode
  createdAt: string
  startedAt?: string
  finishedAt?: string
  config: ModemBaselineConfig
  remoteWorkDir?: string
  logPath?: string
  reportPath?: string
  conflictFiles?: string[]
  error?: string
}

type HarnessResult = {
  status: string
  exit_code: number
  command: string
  output?: string
  error?: string
}

type RunRuntime = {
  runId: string
  clients: Set<ServerResponse>
}

const runtimes = new Map<string, RunRuntime>()

function nowIso() {
  return new Date().toISOString()
}

function toolRootCandidates() {
  const envOverride = process.env.MODEM_BASELINE_TOOL_ROOT?.trim()
  const candidates = [
    envOverride ? path.resolve(envOverride) : '',
    path.resolve(process.cwd(), '..', 'tools', 'modem-patch-tool'),
    path.resolve(process.cwd(), 'tools', 'modem-patch-tool'),
  ].filter(Boolean)

  return Array.from(new Set(candidates))
}

function modemBaselineToolRoot() {
  for (const candidate of toolRootCandidates()) {
    if (fs.existsSync(candidate)) {
      return candidate
    }
  }

  return toolRootCandidates()[0] ?? path.resolve(process.cwd(), '..', 'tools', 'modem-patch-tool')
}

function ensureToolRoot() {
  const toolRoot = modemBaselineToolRoot()
  if (!fs.existsSync(toolRoot)) {
    throw new Error(`Modem基线工具目录不存在: ${toolRoot}；请检查 EA/tools/modem-patch-tool 或 MODEM_BASELINE_TOOL_ROOT`)
  }
  return toolRoot
}

function defaultConfigPath() {
  return path.resolve(ensureToolRoot(), 'config', 'baseline_upgrade.json')
}

function runsRootDir() {
  return path.resolve(serverConfig.dataDir, 'modem-baseline', 'runs')
}

function ensureDir(dir: string) {
  fs.mkdirSync(dir, { recursive: true })
}

function ensureDataDirs() {
  ensureDir(runsRootDir())
}

function runDir(runId: string) {
  return path.resolve(runsRootDir(), runId)
}

function ensureRunDirs(runId: string) {
  ensureDir(runDir(runId))
  ensureDir(path.resolve(runDir(runId), 'logs'))
  ensureDir(path.resolve(runDir(runId), 'artifacts'))
}

function runMetaPath(runId: string) {
  return path.resolve(runDir(runId), 'meta.json')
}

function runConfigPath(runId: string) {
  return path.resolve(runDir(runId), 'config.json')
}

function runLogPath(runId: string) {
  return path.resolve(runDir(runId), 'logs', 'runtime.log.txt')
}

function createRunId() {
  return `${Date.now()}-${crypto.randomBytes(4).toString('hex')}`
}

function writeRunMeta(meta: ModemBaselineRunMeta) {
  ensureRunDirs(meta.runId)
  fs.writeFileSync(runMetaPath(meta.runId), JSON.stringify(meta, null, 2), 'utf-8')
}

export function readModemBaselineRun(runId: string): ModemBaselineRunMeta | null {
  const metaPath = runMetaPath(runId)
  if (!fs.existsSync(metaPath)) return null
  try {
    return JSON.parse(fs.readFileSync(metaPath, 'utf-8')) as ModemBaselineRunMeta
  } catch {
    return null
  }
}

export function listModemBaselineRuns(): ModemBaselineRunMeta[] {
  ensureDataDirs()
  const items: ModemBaselineRunMeta[] = []
  const entries = fs.readdirSync(runsRootDir(), { withFileTypes: true })
  for (const entry of entries) {
    if (!entry.isDirectory()) continue
    const meta = readModemBaselineRun(entry.name)
    if (meta) items.push(meta)
  }
  return items.sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1))
}

export function readModemBaselineLog(runId: string) {
  const meta = readModemBaselineRun(runId)
  if (!meta?.logPath || !fs.existsSync(meta.logPath)) return ''
  return fs.readFileSync(meta.logPath, 'utf-8')
}

function sendEvent(res: ServerResponse, event: string, data: unknown) {
  res.write(`event: ${event}\n`)
  res.write(`data: ${JSON.stringify(data)}\n\n`)
}

function runtimeFor(runId: string) {
  let runtime = runtimes.get(runId)
  if (!runtime) {
    runtime = { runId, clients: new Set() }
    runtimes.set(runId, runtime)
  }
  return runtime
}

function broadcast(runId: string, event: string, data: unknown) {
  const runtime = runtimes.get(runId)
  if (!runtime) return
  for (const client of runtime.clients) {
    try {
      sendEvent(client, event, data)
    } catch {
      runtime.clients.delete(client)
    }
  }
}

export function registerModemBaselineSseClient(runId: string, res: ServerResponse) {
  const meta = readModemBaselineRun(runId)
  if (!meta) {
    throw new Error('run_not_found')
  }

  const runtime = runtimeFor(runId)
  runtime.clients.add(res)

  sendEvent(res, 'status', { status: meta.status, reportPath: meta.reportPath, error: meta.error })
  if (meta.logPath && fs.existsSync(meta.logPath)) {
    const text = fs.readFileSync(meta.logPath, 'utf-8')
    if (text) sendEvent(res, 'log', { line: text, full: true })
  }
  if (meta.conflictFiles?.length) {
    sendEvent(res, 'conflicts', { files: meta.conflictFiles })
  }
}

export function unregisterModemBaselineSseClient(runId: string, res: ServerResponse) {
  runtimes.get(runId)?.clients.delete(res)
}

function summarizeForLog(text: unknown, limit = 160) {
  const normalized = String(text ?? '').replace(/\s+/g, ' ').trim()
  return normalized.length > limit ? `${normalized.slice(0, limit)}...` : normalized
}

async function sleep(ms: number) {
  await new Promise(resolve => setTimeout(resolve, ms))
}

async function harnessExec(command: string, opts?: { timeoutMs?: number }): Promise<HarnessResult> {
  const timeoutMs = opts?.timeoutMs ?? 5 * 60 * 1000
  const isWindows = process.platform === 'win32'
  const appData = process.env.APPDATA
  const npmBinDir = appData ? path.resolve(appData, 'npm') : null
  const harnessPs1 = npmBinDir ? path.resolve(npmBinDir, 'harness.ps1') : null

  return await new Promise<HarnessResult>((resolve, reject) => {
    const args = [
      '--json',
      'remote-runner',
      'bridge-exec',
      '--i-understand-this-runs-raw-shell',
      '--command',
      command,
    ]

    const env = isWindows && npmBinDir
      ? { ...process.env, PATH: `${process.env.PATH ?? ''};${npmBinDir}` }
      : process.env

    const processRef = isWindows && harnessPs1 && fs.existsSync(harnessPs1)
      ? spawn('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', harnessPs1, ...args], { stdio: ['ignore', 'pipe', 'pipe'], env })
      : spawn('harness', args, { stdio: ['ignore', 'pipe', 'pipe'], env })

    let stdout = ''
    let stderr = ''
    let settled = false

    const timer = setTimeout(() => {
      if (settled) return
      try {
        processRef.kill('SIGKILL')
      } catch {}
      reject(new Error('harness timeout'))
    }, timeoutMs)

    processRef.stdout.on('data', (chunk) => {
      stdout += chunk.toString()
      if (settled) return
      const text = stdout.trim()
      if (!text.startsWith('{')) return
      try {
        const parsed = JSON.parse(text) as HarnessResult
        settled = true
        clearTimeout(timer)
        try {
          processRef.kill('SIGKILL')
        } catch {}
        resolve(parsed)
      } catch {}
    })

    processRef.stderr.on('data', (chunk) => {
      stderr += chunk.toString()
    })

    processRef.on('error', (error) => {
      if (settled) return
      clearTimeout(timer)
      reject(error)
    })

    processRef.on('close', () => {
      if (settled) return
      clearTimeout(timer)
      try {
        resolve(JSON.parse(stdout) as HarnessResult)
      } catch {
        reject(new Error(`invalid harness json: ${stderr || stdout}`))
      }
    })
  })
}

function computeRemoteWorkDir(config: ModemBaselineConfig) {
  const mappedPrefix = config.mapped_prefix ?? 'Z:'
  const remotePrefix = config.remote_prefix ?? '/work/user/code'
  const normalized = path.win32.normalize(config.work_dir)
  if (normalized.startsWith(mappedPrefix)) {
    const relative = normalized.slice(mappedPrefix.length).replace(/\\/g, '/')
    return `${remotePrefix}${relative}`
  }
  return config.work_dir
}

function computeMappedWorkDir(config: ModemBaselineConfig) {
  const mappedPrefix = config.mapped_prefix ?? 'Z:'
  const normalized = path.win32.normalize(config.work_dir)
  if (normalized.startsWith(mappedPrefix)) return normalized
  return null
}

function parseMergeConflictLog(text: string) {
  const files = new Set<string>()
  for (const line of text.split('\n')) {
    const matched = line.match(/Merge conflict in\s+(.+?)\s*$/)
    if (matched?.[1]) files.add(matched[1].trim())
  }
  return Array.from(files).sort()
}

function hasConflictMarker(buf: Buffer) {
  if (buf.indexOf(Buffer.from('<<<<<<<')) >= 0) return true
  if (buf.indexOf(Buffer.from('<<<<<<<', 'utf16le')) >= 0) return true
  return false
}

async function listUnmergedFiles(config: ModemBaselineConfig) {
  const remoteWorkDir = computeRemoteWorkDir(config)

  try {
    const stripAnsi = (value: string) => value.replace(/\x1b\[[0-9;]*[A-Za-z]|\x1b./g, '')
    const extractBetween = (text: string) => {
      const stripped = stripAnsi(text)
      const start = stripped.indexOf('__APM_BEGIN__')
      if (start < 0) return stripped
      const end = stripped.indexOf('__APM_END__', start)
      return end >= 0
        ? stripped.slice(start + '__APM_BEGIN__'.length, end)
        : stripped.slice(start + '__APM_BEGIN__'.length)
    }

    const unmergedByLsFiles = await harnessExec(
      `cd ${remoteWorkDir} && echo __APM_BEGIN__ && (git ls-files -u | cut -f2 | sort -u || true) && echo __APM_END__`,
    )
    if (unmergedByLsFiles.status === 'ok' && unmergedByLsFiles.exit_code === 0) {
      const files = extractBetween(unmergedByLsFiles.output ?? '')
        .split('\n')
        .map(line => line.trim())
        .filter(line => line && !line.startsWith('Updating files:'))
      if (files.length) return files
    }

    const unmergedByDiff = await harnessExec(
      `cd ${remoteWorkDir} && echo __APM_BEGIN__ && (GIT_PAGER=cat git diff --name-only --diff-filter=U || true) && echo __APM_END__`,
    )
    if (unmergedByDiff.status === 'ok' && unmergedByDiff.exit_code === 0) {
      const files = extractBetween(unmergedByDiff.output ?? '')
        .split('\n')
        .map(line => line.trim())
        .filter(line => line && !line.startsWith('Updating files:'))
      if (files.length) return files
    }

    const mergeState = await harnessExec(
      `cd ${remoteWorkDir} && test -f .git/MERGE_HEAD && echo __APM_MERGE_HEAD__ || echo __APM_NO__`,
    )
    if (mergeState.status === 'ok' && mergeState.exit_code === 0) {
      const output = stripAnsi(mergeState.output ?? '')
      if (!output.includes('__APM_MERGE_HEAD__')) return []
    }
  } catch {}

  const mapped = computeMappedWorkDir(config)
  if (!mapped) return []

  const conflictLog = path.resolve(mapped, 'log', 'merge_conflict.log')
  for (let i = 0; i < 6; i += 1) {
    try {
      if (fs.existsSync(conflictLog)) {
        const parsed = parseMergeConflictLog(fs.readFileSync(conflictLog, 'utf-8'))
        if (parsed.length) {
          return parsed.filter(relativePath => {
            const fullPath = path.resolve(mapped, relativePath.replace(/\//g, path.sep))
            try {
              if (!fs.existsSync(fullPath)) return true
              return hasConflictMarker(fs.readFileSync(fullPath))
            } catch {
              return true
            }
          })
        }
      }
    } catch {}
    await sleep(800)
  }

  return []
}

async function checkBridgeHealthy(appendLog: (line: string) => void, retries = 2, timeoutMs = 60_000) {
  let lastError: unknown = null
  for (let index = 0; index <= retries; index += 1) {
    try {
      if (index > 0) await sleep(1200)
      appendLog(`[precheck] bridge check attempt=${index + 1}/${retries + 1} timeout_ms=${timeoutMs}\n`)
      const probe = await harnessExec('echo bridge_check', { timeoutMs })
      const outputSummary = summarizeForLog(probe.output)
      const errorSummary = summarizeForLog(probe.error)
      appendLog(
        `[precheck] bridge check attempt=${index + 1}/${retries + 1} result status=${probe.status} exit_code=${probe.exit_code} output="${outputSummary}" error="${errorSummary}"\n`,
      )
      if (probe.status === 'ok' && probe.exit_code === 0 && probe.output?.includes('bridge_check')) {
        appendLog(`[precheck] bridge check attempt=${index + 1}/${retries + 1} passed\n`)
        return true
      }
      lastError = new Error(
        `unexpected_probe_result status=${probe.status} exit_code=${probe.exit_code} output="${outputSummary}" error="${errorSummary}"`,
      )
    } catch (error) {
      lastError = error
      appendLog(`[precheck] bridge check attempt=${index + 1}/${retries + 1} failed: ${String((error as Error)?.message ?? error)}\n`)
    }
  }

  appendLog(`[precheck] bridge check failed: ${String((lastError as Error)?.message ?? lastError)}\n`)
  return false
}

function decodeText(buffer: Buffer) {
  const utf8 = buffer.toString('utf-8')
  if (utf8.includes('\u0000')) {
    const utf16 = buffer.toString('utf16le')
    return utf16.charCodeAt(0) === 0xfeff ? utf16.slice(1) : utf16
  }
  return utf8
}

async function postProcessRun(runId: string, config: ModemBaselineConfig, code: number | null, appendLog: (line: string) => void) {
  const current = readModemBaselineRun(runId)
  if (!current) return

  const mapped = computeMappedWorkDir(config)
  const remote = computeRemoteWorkDir(config)
  const mergeLogPath = mapped ? path.resolve(mapped, 'log', 'merge_conflict.log') : null
  const localMergeHead = mapped ? path.resolve(mapped, '.git', 'MERGE_HEAD') : null
  appendLog(
    `[conflicts] mapped=${mapped ?? ''} log=${mergeLogPath ?? ''} log_exists=${mergeLogPath ? fs.existsSync(mergeLogPath) : false} merge_head_exists=${localMergeHead ? fs.existsSync(localMergeHead) : false}\n`,
  )

  if (mergeLogPath && fs.existsSync(mergeLogPath)) {
    let text: string | null = null
    let matches = 0
    let readError: unknown = null
    let prevSize = -1
    let stableReads = 0
    let tries = 0

    for (let index = 0; index < 10; index += 1) {
      tries = index + 1
      try {
        const stat = fs.statSync(mergeLogPath)
        const size = stat.size
        text = decodeText(fs.readFileSync(mergeLogPath))
        matches = Array.from(text.matchAll(/Merge conflict in\s+(.+?)\s*$/gm)).length
        const previous = prevSize
        if (matches > 0) break
        stableReads = size > 0 && size === prevSize ? stableReads + 1 : 0
        prevSize = size
        appendLog(`[conflicts] merge_conflict.log retry=${index + 1}/10 size=${size} prev_size=${previous} stable=${stableReads} matches=${matches} text_len=${text.length}\n`)
      } catch (error) {
        readError = error
        appendLog(`[conflicts] merge_conflict.log retry=${index + 1}/10 error=${String((error as Error)?.message ?? error)}\n`)
      }
      await sleep(1000)
    }

    if (text != null) {
      appendLog(`[conflicts] merge_conflict.log done tries=${tries} size=${prevSize} stable=${stableReads}\n`)
      appendLog(`[conflicts] merge_conflict.log matches=${matches}\n`)
    } else if (readError) {
      appendLog(`[conflicts] merge_conflict.log read failed: ${String((readError as Error)?.message ?? readError)}\n`)
    }
  }

  try {
    const mergeHeadProbe = await harnessExec(`cd ${remote} && test -f .git/MERGE_HEAD && echo __APM_MERGE_HEAD__ || echo __APM_NO__`, { timeoutMs: 8000 })
    const raw = (mergeHeadProbe.output ?? '').trim()
    const cleaned = raw.split('\n').map(line => line.trim()).filter(line => line && !line.startsWith('Updating files:')).join('\n').trim()
    const marker = cleaned.match(/__APM_(MERGE_HEAD|NO)__/)
    const remoteHead = marker?.[1] === 'MERGE_HEAD' ? 'MERGE_HEAD' : marker?.[1] === 'NO' ? 'NO' : cleaned || raw
    appendLog(`[conflicts] remote_merge_head=${remoteHead}\n`)
  } catch (error) {
    appendLog(`[conflicts] remote_merge_head probe failed: ${String((error as Error)?.message ?? error)}\n`)
  }

  try {
    const mergeSizeProbe = await harnessExec(`cd ${remote} && test -f log/merge_conflict.log && stat -c%s log/merge_conflict.log || echo MISSING`, { timeoutMs: 8000 })
    const raw = (mergeSizeProbe.output ?? '').trim()
    const cleaned = raw.split('\n').map(line => line.trim()).filter(line => line && !line.startsWith('Updating files:'))
    appendLog(`[conflicts] remote_merge_conflict_size=${cleaned[cleaned.length - 1] ?? ''}\n`)
  } catch (error) {
    appendLog(`[conflicts] remote_merge_conflict_size probe failed: ${String((error as Error)?.message ?? error)}\n`)
  }

  const conflictFiles = await listUnmergedFiles(config)
  appendLog(`[conflicts] detected_files=${conflictFiles.length}\n`)

  let status: ModemBaselineStatus = code === 0 ? 'success' : code === 2 ? 'conflict' : 'failed'
  if (conflictFiles.length > 0) status = 'conflict'

  if (status !== 'conflict' && ((localMergeHead && fs.existsSync(localMergeHead)) || current.remoteWorkDir)) {
    try {
      const probe = await harnessExec(`cd ${remote} && test -f .git/MERGE_HEAD && echo __APM_MERGE_HEAD__ || echo __APM_NO__`, { timeoutMs: 8000 })
      if ((probe.output ?? '').includes('__APM_MERGE_HEAD__')) {
        status = 'conflict'
      }
    } catch {}
  }

  const nextMeta: ModemBaselineRunMeta = {
    ...current,
    status,
    finishedAt: nowIso(),
    conflictFiles: conflictFiles.length ? conflictFiles : undefined,
  }
  writeRunMeta(nextMeta)
  broadcast(runId, 'status', { status: nextMeta.status, reportPath: nextMeta.reportPath, error: nextMeta.error })
  broadcast(runId, 'conflicts', { files: conflictFiles })
}

function updateReportPathFromLog(runId: string, line: string) {
  const matched = line.match(/Report(?: generated locally)?:\s*(.+)\s*$/)
  if (!matched?.[1]) return
  const current = readModemBaselineRun(runId)
  if (!current) return
  const nextMeta: ModemBaselineRunMeta = { ...current, reportPath: matched[1].trim() }
  writeRunMeta(nextMeta)
  broadcast(runId, 'status', { status: nextMeta.status, reportPath: nextMeta.reportPath, error: nextMeta.error })
}

function appendRunLog(runId: string, logPath: string, line: string) {
  fs.appendFileSync(logPath, line, 'utf-8')
  broadcast(runId, 'log', { line })
  updateReportPathFromLog(runId, line)
}

function markRunFailed(runId: string, error: string) {
  const current = readModemBaselineRun(runId)
  if (!current) return
  const nextMeta: ModemBaselineRunMeta = {
    ...current,
    status: 'failed',
    finishedAt: nowIso(),
    error,
  }
  writeRunMeta(nextMeta)
  broadcast(runId, 'status', { status: nextMeta.status, reportPath: nextMeta.reportPath, error: nextMeta.error })
}

function validateConfig(input: unknown): ModemBaselineConfig | null {
  if (!input || typeof input !== 'object') return null
  const value = input as Partial<ModemBaselineConfig>
  if (!value.NODE_BRANCH || !value.target_BRANCH || !value.AP_lable || !value.JIRAID || !value.work_dir) {
    return null
  }
  return {
    NODE_BRANCH: String(value.NODE_BRANCH),
    target_BRANCH: String(value.target_BRANCH),
    AP_lable: String(value.AP_lable),
    DESCRIPTION: value.DESCRIPTION ? String(value.DESCRIPTION) : undefined,
    JIRAID: String(value.JIRAID),
    work_dir: String(value.work_dir),
    mapped_prefix: value.mapped_prefix ? String(value.mapped_prefix) : undefined,
    remote_prefix: value.remote_prefix ? String(value.remote_prefix) : undefined,
  }
}

export function getModemBaselineDefaults() {
  const toolRoot = ensureToolRoot()
  const defaults = defaultConfigPath()
  if (!fs.existsSync(defaults)) {
    throw new Error(`默认配置不存在: ${defaults}`)
  }

  const raw = JSON.parse(fs.readFileSync(defaults, 'utf-8')) as Partial<ModemBaselineConfig>
  return {
    toolRoot,
    config: {
      NODE_BRANCH: String(raw.NODE_BRANCH ?? ''),
      target_BRANCH: String(raw.target_BRANCH ?? ''),
      AP_lable: String(raw.AP_lable ?? ''),
      DESCRIPTION: String(raw.DESCRIPTION ?? ''),
      JIRAID: String(raw.JIRAID ?? ''),
      work_dir: String(raw.work_dir ?? ''),
      mapped_prefix: String(raw.mapped_prefix ?? ''),
      remote_prefix: String(raw.remote_prefix ?? ''),
    } satisfies ModemBaselineConfig,
  }
}

async function startBackgroundRun(runId: string, config: ModemBaselineConfig, scriptName: string) {
  const toolRoot = ensureToolRoot()
  const logPath = runLogPath(runId)
  const scriptPath = path.resolve(toolRoot, scriptName)
  const pythonExe = process.env.PYTHON ?? 'python'
  const configPath = runConfigPath(runId)

  try {
    const bridgeReady = await checkBridgeHealthy(line => appendRunLog(runId, logPath, line))
    if (!bridgeReady) {
      markRunFailed(runId, 'bridge_not_ready')
      return
    }
  } catch {
    markRunFailed(runId, 'bridge_not_ready')
    return
  }

  const processRef = spawn(pythonExe, ['-u', scriptPath, configPath], {
    cwd: toolRoot,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1', SKIP_BRIDGE_CHECK: 'true' },
  })

  processRef.on('error', (error) => {
    appendRunLog(runId, logPath, `[spawn] failed: ${String((error as Error)?.message ?? error)}\n`)
    markRunFailed(runId, 'spawn_failed')
  })
  processRef.stdout.on('data', chunk => appendRunLog(runId, logPath, chunk.toString()))
  processRef.stderr.on('data', chunk => appendRunLog(runId, logPath, chunk.toString()))
  processRef.on('close', async (code) => {
    await postProcessRun(runId, config, code, line => appendRunLog(runId, logPath, line))
  })
}

export function createModemBaselineRun(input: unknown) {
  ensureToolRoot()
  ensureDataDirs()
  const validated = validateConfig(input)
  if (!validated) {
    throw new Error('invalid_config')
  }

  const runId = createRunId()
  ensureRunDirs(runId)
  const logPath = runLogPath(runId)
  const remoteWorkDir = computeRemoteWorkDir(validated)
  const meta: ModemBaselineRunMeta = {
    runId,
    status: 'running',
    mode: 'stop_after_merge',
    createdAt: nowIso(),
    startedAt: nowIso(),
    config: validated,
    remoteWorkDir,
    logPath,
  }

  fs.writeFileSync(runConfigPath(runId), JSON.stringify(validated, null, 2), 'utf-8')
  fs.writeFileSync(logPath, '', 'utf-8')
  writeRunMeta(meta)
  void startBackgroundRun(runId, validated, 'debug_stop_after_merge.py')

  return { runId, status: meta.status }
}

export function continueModemBaselineRun(runId: string) {
  ensureToolRoot()
  const meta = readModemBaselineRun(runId)
  if (!meta) throw new Error('not_found')
  if (meta.status === 'running') throw new Error('running')
  if (meta.status !== 'conflict') throw new Error('not_in_conflict')
  if (!meta.logPath) throw new Error('missing_log_path')

  const nextMeta: ModemBaselineRunMeta = {
    ...meta,
    status: 'running',
    finishedAt: undefined,
    conflictFiles: undefined,
    error: undefined,
  }
  writeRunMeta(nextMeta)
  broadcast(runId, 'status', { status: nextMeta.status, reportPath: nextMeta.reportPath, error: nextMeta.error })
  appendRunLog(runId, meta.logPath, '[continue] requested\n')
  void startBackgroundRun(runId, meta.config, 'debug_continue_after_merge.py')
  return { runId, status: nextMeta.status }
}

export async function refreshModemBaselineConflicts(runId: string, autoStageResolved = true) {
  const meta = readModemBaselineRun(runId)
  if (!meta) throw new Error('not_found')
  const appendLog = (line: string) => {
    if (!meta.logPath) return
    appendRunLog(runId, meta.logPath, line)
  }

  appendLog(`[refresh] requested autoStage=${Number(autoStageResolved)}\n`)
  let staged = 0
  let filesBefore: string[] = []
  let filesAfter: string[] = []

  try {
    filesBefore = await listUnmergedFiles(meta.config)
    appendLog(`[refresh] before=${filesBefore.length}\n`)
  } catch (error) {
    appendLog(`[refresh] list before failed: ${String((error as Error)?.message ?? error)}\n`)
  }

  if (autoStageResolved && filesBefore.length) {
    const remote = computeRemoteWorkDir(meta.config)
    const mapped = computeMappedWorkDir(meta.config)
    let batchHandled = false

    if (mapped) {
      try {
        const gitDir = path.win32.resolve(mapped, '.git')
        const scriptPath = path.win32.resolve(gitDir, 'apm_refresh_conflicts.sh')
        const script = `#!/bin/bash
set +e
staged=0
unmerged="$(GIT_PAGER=cat git diff --name-only --diff-filter=U 2>/dev/null || true)"
if [ -n "$unmerged" ]; then
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    if GIT_PAGER=cat git grep -n -E '^(<<<<<<<|=======|>>>>>>>)' -- "$f" >/dev/null 2>&1; then
      echo "__APM_MARKER__:$f"
    else
      if git add -- "$f" >/dev/null 2>&1; then
        staged=$((staged+1))
        echo "__APM_STAGED__:$f"
      else
        echo "__APM_ADD_FAIL__:$f"
      fi
    fi
  done <<< "$unmerged"
fi
echo "__APM_STAGED_COUNT__:$staged"
echo "__APM_REMAINING_BEGIN__"
GIT_PAGER=cat git diff --name-only --diff-filter=U 2>/dev/null || true
echo "__APM_REMAINING_END__"
`
        fs.writeFileSync(scriptPath, script.replace(/\r\n/g, '\n'), 'utf-8')
        const result = await harnessExec(`cd ${remote} && bash .git/apm_refresh_conflicts.sh`, { timeoutMs: 120000 })
        const raw = (result.output ?? '').trim()
        appendLog(`[refresh] batch status=${result.status} exit_code=${result.exit_code}\n`)
        const matched = raw.match(/__APM_STAGED_COUNT__:(\d+)/)
        staged = matched ? Number(matched[1]) : 0
        for (const line of raw.split('\n').map(item => item.trim()).filter(Boolean)) {
          if (line.startsWith('__APM_MARKER__:')) appendLog(`[refresh] marker remains: ${line.slice('__APM_MARKER__:'.length)}\n`)
          if (line.startsWith('__APM_ADD_FAIL__:')) appendLog(`[refresh] git add failed: ${line.slice('__APM_ADD_FAIL__:'.length)}\n`)
        }
        batchHandled = true
      } catch (error) {
        appendLog(`[refresh] batch failed: ${String((error as Error)?.message ?? error)}\n`)
      }
    }

    if (!batchHandled) {
      const quote = (value: string) => `'${String(value).replace(/'/g, `'\"'\"'`)}'`
      for (const file of filesBefore) {
        try {
          const probe = await harnessExec(
            `cd ${remote} && set +e; GIT_PAGER=cat git grep -n -E '^(<<<<<<<|=======|>>>>>>>)' -- ${quote(file)} >/dev/null 2>&1; rc=$?; echo __APM_RC:\${rc}__`,
            { timeoutMs: 45000 },
          )
          const match = (probe.output ?? '').trim().match(/__APM_RC:(\d+)__/)
          const rc = match ? Number(match[1]) : null
          if (rc === 1) {
            const add = await harnessExec(`cd ${remote} && git add -- ${quote(file)}`, { timeoutMs: 45000 })
            if (add.status === 'ok' && add.exit_code === 0) staged += 1
          }
        } catch (error) {
          appendLog(`[refresh] stage failed: ${file} err=${String((error as Error)?.message ?? error)}\n`)
        }
      }
    }
  }

  try {
    filesAfter = await listUnmergedFiles(meta.config)
    appendLog(`[refresh] staged=${staged} remaining=${filesAfter.length}\n`)
  } catch (error) {
    appendLog(`[refresh] list after failed: ${String((error as Error)?.message ?? error)}\n`)
    filesAfter = filesBefore
  }

  const nextMeta: ModemBaselineRunMeta = {
    ...meta,
    conflictFiles: filesAfter.length ? filesAfter : undefined,
    // Refresh only reconciles the conflict list. It must not auto-advance
    // the run state, otherwise manual "continue" becomes impossible.
    status: meta.status === 'conflict' ? 'conflict' : meta.status,
  }
  writeRunMeta(nextMeta)
  broadcast(runId, 'conflicts', { files: filesAfter })
  broadcast(runId, 'status', { status: nextMeta.status, reportPath: nextMeta.reportPath, error: nextMeta.error })
  return { files: filesAfter, staged }
}

export function openModemBaselineConflictFile(runId: string, relativeFile: string) {
  const meta = readModemBaselineRun(runId)
  if (!meta) throw new Error('not_found')
  const file = String(relativeFile ?? '').trim()
  if (!file) throw new Error('bad_request')

  const mapped = computeMappedWorkDir(meta.config)
  if (!mapped) throw new Error('mapped_not_available')

  const fullPath = path.win32.resolve(mapped, file.replace(/\//g, '\\'))
  const relative = path.win32.relative(mapped, fullPath)
  if (!relative || relative.startsWith('..') || path.win32.isAbsolute(relative)) {
    throw new Error('path_outside_workdir')
  }
  if (!fs.existsSync(fullPath)) {
    throw new Error('file_not_found')
  }

  const powershellPath = process.platform === 'win32' ? 'powershell.exe' : 'powershell'
  const quoted = `'${fullPath.replace(/'/g, "''")}'`
  const result = spawnSync(
    powershellPath,
    ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', `Invoke-Item -LiteralPath ${quoted}`],
    { windowsHide: true, timeout: 5000, encoding: 'utf-8' },
  )

  if (result.error) {
    throw new Error(`spawn_failed:${String(result.error.message ?? result.error)}`)
  }
  if (typeof result.status === 'number' && result.status !== 0) {
    throw new Error(`open_failed:${(result.stderr || '').trim()}`)
  }

  return { success: true }
}
