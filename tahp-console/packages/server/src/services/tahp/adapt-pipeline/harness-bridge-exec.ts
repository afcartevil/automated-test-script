/**
 * 调用 harness remote-runner bridge-exec / discover / bridge-cancel / bridge-serve
 */
import { spawn, execFileSync } from 'child_process'
import { existsSync, readFileSync, unlinkSync } from 'fs'
import { resolve } from 'path'
import { assertHarnessCliReady } from '../harness-version-gate'

export interface BridgeExecResult {
  status: string
  exit_code: number
  command?: string
  output?: string
  error?: string
  [k: string]: unknown
}

export interface BridgeStatus {
  ready: boolean
  raw?: unknown
  error?: string
  sessionPhase?: string
  serviceReachable?: boolean
  readyFileExists?: boolean
  agentNextAction?: string
}

function npmHarnessPs1(): string | null {
  const appData = process.env.APPDATA
  if (!appData) return null
  const ps1 = resolve(appData, 'npm', 'harness.ps1')
  return existsSync(ps1) ? ps1 : null
}

function harnessEnv(): NodeJS.ProcessEnv {
  const isWindows = process.platform === 'win32'
  const appData = process.env.APPDATA
  const npmBinDir = appData ? resolve(appData, 'npm') : null
  if (isWindows && npmBinDir) {
    return { ...process.env, PATH: `${process.env.PATH ?? ''};${npmBinDir}` }
  }
  return process.env
}

function sleep(ms: number): Promise<void> {
  return new Promise(r => setTimeout(r, ms))
}

export function spawnHarness(
  args: string[],
  opts?: {
    timeoutMs?: number
    onStdout?: (chunk: string) => void
    onStderr?: (chunk: string) => void
    signal?: { cancelled: boolean }
    detached?: boolean
  },
): Promise<{ stdout: string; stderr: string; code: number | null }> {
  const timeoutMs = opts?.timeoutMs ?? 5 * 60 * 1000
  const isWindows = process.platform === 'win32'
  const ps1 = npmHarnessPs1()
  const env = harnessEnv()

  return new Promise((resolvePromise, reject) => {
    const processRef = isWindows && ps1
      ? spawn('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ps1, ...args], {
          stdio: opts?.detached ? 'ignore' : ['ignore', 'pipe', 'pipe'],
          env,
          windowsHide: !opts?.detached,
          detached: Boolean(opts?.detached),
        })
      : spawn('harness', args, {
          stdio: opts?.detached ? 'ignore' : ['ignore', 'pipe', 'pipe'],
          env,
          windowsHide: !opts?.detached,
          detached: Boolean(opts?.detached),
        })

    if (opts?.detached) {
      try { processRef.unref() } catch { /* ignore */ }
      resolvePromise({ stdout: '', stderr: '', code: 0 })
      return
    }

    let stdout = ''
    let stderr = ''
    let settled = false

    const timer = setTimeout(() => {
      if (settled) return
      settled = true
      try { processRef.kill('SIGKILL') } catch { /* ignore */ }
      reject(new Error(`harness timeout after ${Math.round(timeoutMs / 1000)}s`))
    }, timeoutMs)

    const finish = (code: number | null) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolvePromise({ stdout, stderr, code })
    }

    processRef.stdout?.on('data', (chunk: Buffer) => {
      const text = chunk.toString()
      stdout += text
      opts?.onStdout?.(text)
      if (opts?.signal?.cancelled) {
        try { processRef.kill('SIGKILL') } catch { /* ignore */ }
      }
    })
    processRef.stderr?.on('data', (chunk: Buffer) => {
      const text = chunk.toString()
      stderr += text
      opts?.onStderr?.(text)
    })
    processRef.on('error', (err) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      reject(err)
    })
    processRef.on('close', (code) => finish(code))
  })
}

function parseJsonLoose(text: string): Record<string, unknown> | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  try {
    return JSON.parse(trimmed) as Record<string, unknown>
  } catch {
    const start = trimmed.indexOf('{')
    const end = trimmed.lastIndexOf('}')
    if (start >= 0 && end > start) {
      try {
        return JSON.parse(trimmed.slice(start, end + 1)) as Record<string, unknown>
      } catch { /* ignore */ }
    }
  }
  return null
}

function bridgeFromPayload(parsed: Record<string, unknown>): BridgeStatus {
  const bridge = (parsed.bridge ?? (parsed as { data?: { bridge?: unknown } }).data?.bridge) as
    | Record<string, unknown>
    | undefined
  const ready = Boolean(
    bridge?.ready
    ?? (parsed as { bridge_ready?: boolean }).bridge_ready
    ?? (parsed as { ready?: boolean }).ready,
  )
  return {
    ready,
    raw: parsed,
    sessionPhase: bridge?.session_phase != null ? String(bridge.session_phase) : undefined,
    serviceReachable: bridge?.service_reachable != null ? Boolean(bridge.service_reachable) : undefined,
    readyFileExists: bridge?.ready_file_exists != null ? Boolean(bridge.ready_file_exists) : undefined,
    agentNextAction: parsed.agent_next_action != null ? String(parsed.agent_next_action) : undefined,
    error: parsed.error_code || parsed.message
      ? String(parsed.message || parsed.error_code)
      : undefined,
  }
}

export async function bridgeExec(
  command: string,
  opts?: {
    timeoutSec?: number
    onStdout?: (chunk: string) => void
    onStderr?: (chunk: string) => void
    signal?: { cancelled: boolean }
  },
): Promise<BridgeExecResult> {
  assertHarnessCliReady()
  const timeoutSec = Math.max(1, opts?.timeoutSec ?? 300)
  const localTimeoutMs = timeoutSec * 1000 + 60_000
  const { stdout, stderr } = await spawnHarness(
    [
      '--json',
      'remote-runner',
      'bridge-exec',
      '--i-understand-this-runs-raw-shell',
      '--timeout',
      String(timeoutSec),
      '--command',
      command,
    ],
    {
      timeoutMs: localTimeoutMs,
      onStdout: opts?.onStdout,
      onStderr: opts?.onStderr,
      signal: opts?.signal,
    },
  )

  const text = stdout.trim()
  try {
    return JSON.parse(text) as BridgeExecResult
  } catch {
    throw new Error(`invalid harness json: ${stderr || stdout || '(empty)'}`)
  }
}

export function discoverBridgeReady(): BridgeStatus {
  try {
    assertHarnessCliReady()
  } catch (err) {
    return { ready: false, error: (err as Error).message }
  }

  try {
    const isWindows = process.platform === 'win32'
    const ps1 = npmHarnessPs1()
    const env = harnessEnv()
    let out: string
    if (isWindows && ps1) {
      out = execFileSync(
        'powershell.exe',
        ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ps1, '--json', 'remote-runner', 'discover'],
        { encoding: 'utf-8', timeout: 60_000, env, windowsHide: true },
      )
    } else {
      out = execFileSync('harness', ['--json', 'remote-runner', 'discover'], {
        encoding: 'utf-8',
        timeout: 60_000,
        env,
        windowsHide: true,
      })
    }
    const parsed = parseJsonLoose(out)
    if (!parsed) return { ready: false, error: 'discover 返回非 JSON' }
    return bridgeFromPayload(parsed)
  } catch (err) {
    return { ready: false, error: (err as Error).message }
  }
}

export async function diagnoseBridge(): Promise<BridgeStatus> {
  try {
    const { stdout, stderr } = await spawnHarness(
      ['--json', 'remote-runner', 'bridge-diagnose'],
      { timeoutMs: 60_000 },
    )
    const parsed = parseJsonLoose(stdout) || parseJsonLoose(stderr)
    if (!parsed) return { ready: false, error: stderr || stdout || 'diagnose 无输出' }
    return bridgeFromPayload(parsed)
  } catch (err) {
    return { ready: false, error: (err as Error).message }
  }
}

export async function bridgeCancel(): Promise<void> {
  try {
    await spawnHarness(['--json', 'remote-runner', 'bridge-cancel'], { timeoutMs: 30_000 })
  } catch { /* ignore */ }
}

function killHarnessBridgeProcesses(): void {
  if (process.platform !== 'win32') return
  try {
    execFileSync('taskkill', ['/F', '/IM', 'harness-bridge.exe'], {
      encoding: 'utf-8',
      timeout: 15_000,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    })
  } catch { /* ignore if not running */ }
}

/** 清掉过期 ready flag，避免服务已挂但 flag 仍存在 */
function clearStaleBridgeReadyFlag(): void {
  const home = process.env.USERPROFILE || process.env.HOME
  if (!home) return
  const flag = resolve(home, '.ssh', 'harness-qizhi-bridge-ready.flag')
  try {
    if (existsSync(flag)) unlinkSync(flag)
  } catch { /* ignore */ }
}

/** harness 自带 venv Python（含 core.totp / bridge_client） */
export function resolveHarnessPython(): string | null {
  const home = process.env.USERPROFILE || process.env.HOME
  if (home) {
    const tip = resolve(home, '.tran_harness', 'bin', 'sidecar-python.txt')
    if (existsSync(tip)) {
      const line = readFileSync(tip, 'utf-8').trim().split(/\r?\n/)[0]?.trim()
      if (line && existsSync(line)) return line
    }
  }
  const local = process.env.LOCALAPPDATA
  if (local) {
    const venvRoot = resolve(local, 'harness', 'npm-venv')
    if (existsSync(venvRoot)) {
      try {
        const versions = execFileSync('cmd', ['/c', 'dir', '/b', '/ad', venvRoot], {
          encoding: 'utf-8',
          windowsHide: true,
          timeout: 5_000,
        })
          .split(/\r?\n/)
          .map(s => s.trim())
          .filter(Boolean)
          .sort()
          .reverse()
        for (const ver of versions) {
          const py = resolve(venvRoot, ver, 'Scripts', 'python.exe')
          if (existsSync(py)) return py
        }
      } catch { /* ignore */ }
    }
  }
  return null
}

/**
 * 用已配置的 HARNESS_QIZHI_OTP_SECRET 生成当前 TOTP，经 bridge_client.start_session(manual_otp=…) 自动登录。
 * （CLI `bridge-serve` 不会自动读 secret；配置中心才会。）不打印口令本身。
 */
export function startBridgeSessionWithTotp(): { ok: boolean; error?: string } {
  const py = resolveHarnessPython()
  if (!py) {
    return { ok: false, error: '未找到 harness Python（sidecar-python / npm-venv）' }
  }
  // 注意：不要 print OTP / secret
  const script = [
    'import json, sys',
    'from core.totp import generate_totp, totp_configured',
    'from cli import bridge_client',
    'if not totp_configured():',
    '    print(json.dumps({"ok": False, "error": "totp_secret_missing"})); sys.exit(2)',
    'bridge_client.ensure_daemon_running()',
    'otp = generate_totp()',
    'bridge_client.start_session(mode="auto", manual_otp=otp, stop_on_prompt_retry=False)',
    'print(json.dumps({"ok": True, "otp_injected": True}))',
  ].join('\n')

  try {
    const out = execFileSync(py, ['-c', script], {
      encoding: 'utf-8',
      timeout: 60_000,
      windowsHide: true,
      env: process.env,
    }).trim()
    const last = out.split(/\r?\n/).filter(Boolean).pop() || '{}'
    const parsed = JSON.parse(last) as { ok?: boolean; error?: string }
    if (!parsed.ok) {
      return { ok: false, error: parsed.error || 'start_session failed' }
    }
    return { ok: true }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    // stderr often contains Chinese error from daemon; strip any 6-digit codes just in case
    const safe = msg.replace(/\b\d{6}\b/g, '******').slice(0, 500)
    return { ok: false, error: safe }
  }
}

/**
 * 后台拉起 bridge：优先 TOTP 自动注入；失败再回退 CLI bridge-serve。
 */
export async function startBridgeServe(opts?: { gui?: boolean }): Promise<{ method: string; detail?: string }> {
  if (opts?.gui === true) {
    process.env.HARNESS_CONFIG_UI_CLI = '1'
    await spawnHarness(['remote-runner', 'bridge-serve', '--gui'], { detached: true, timeoutMs: 5_000 })
    return { method: 'bridge-serve --gui' }
  }

  const totp = startBridgeSessionWithTotp()
  if (totp.ok) {
    return { method: 'totp-auto' }
  }

  await spawnHarness(['remote-runner', 'bridge-serve'], { detached: true, timeoutMs: 5_000 })
  return { method: 'bridge-serve', detail: totp.error }
}

/**
 * 编译前确保 Bridge READY：
 * 1) discover 已 ready → 直接返回
 * 2) phase=exec / busy → bridge-cancel 重试（cancel 无效则强制杀进程）
 * 3) 重启 + 用已存 TOTP secret 自动注入 OTP 并轮询
 */
export async function ensureBridgeReady(opts?: {
  timeoutMs?: number
  onLog?: (line: string) => void
  signal?: { cancelled: boolean }
}): Promise<BridgeStatus> {
  const timeoutMs = opts?.timeoutMs ?? 3 * 60_000
  const log = (line: string) => opts?.onLog?.(line)
  const started = Date.now()

  const checkCancelled = () => {
    if (opts?.signal?.cancelled) throw new Error('已取消')
  }

  let status = discoverBridgeReady()
  if (status.ready) {
    log('Bridge 已 READY')
    return status
  }
  log(`Bridge 未 READY：phase=${status.sessionPhase || '?'} ${status.error || ''}`.trim())

  // 残留 exec：cancel 往往无效（超时），最多试 2 次后强制重启
  for (let i = 0; i < 2; i++) {
    checkCancelled()
    const diag = await diagnoseBridge()
    log(`diagnose: phase=${diag.sessionPhase ?? '?'} ready=${diag.ready} reachable=${diag.serviceReachable}`)
    if (diag.ready) return diag
    if (diag.sessionPhase === 'exec' || /busy|cancel/i.test(String(diag.agentNextAction || diag.error || ''))) {
      log(`尝试 bridge-cancel (${i + 1}/2)…`)
      await bridgeCancel()
      await sleep(2000)
      status = discoverBridgeReady()
      if (status.ready) {
        log('cancel 后 Bridge 已 READY')
        return status
      }
      // cancel 后仍 exec → 不再空转，进入强制重启
      if (status.sessionPhase === 'exec') break
    } else {
      break
    }
  }

  checkCancelled()
  log('清理残留并用已配置 TOTP secret 自动生成口令连接 Bridge…')
  killHarnessBridgeProcesses()
  clearStaleBridgeReadyFlag()
  await sleep(1500)
  const startedHow = await startBridgeServe({ gui: false })
  log(
    startedHow.method === 'totp-auto'
      ? '已注入 TOTP 动态口令，等待会话 READY…'
      : `TOTP 自动注入未成功（${startedHow.detail || 'unknown'}），已回退 bridge-serve`,
  )

  while (Date.now() - started < timeoutMs) {
    checkCancelled()
    await sleep(3000)
    status = discoverBridgeReady()
    if (status.ready) {
      log('Bridge 已 READY')
      return status
    }
    // session failed mid-login：再试一次 TOTP（时钟窗口换码）
    if (status.sessionPhase === 'failed' && startedHow.method === 'totp-auto') {
      log('登录失败，用新一轮 TOTP 重试…')
      const retry = startBridgeSessionWithTotp()
      if (!retry.ok) log(`TOTP 重试失败：${retry.error}`)
      await sleep(2000)
      continue
    }
    const elapsed = Math.round((Date.now() - started) / 1000)
    log(`等待 Bridge READY… ${elapsed}s（phase=${status.sessionPhase ?? '?'}）`)
  }

  const finalDiag = await diagnoseBridge()
  throw new Error(
    finalDiag.error
      || `齐治 Bridge 在 ${Math.round(timeoutMs / 1000)}s 内未 READY。请确认 env.yaml 中 HARNESS_QIZHI_OTP_SECRET 与堡垒机密码有效。`,
  )
}

export function resolveEzBuildScriptPath(): string {
  const candidates = [
    resolve(__dirname, 'adapt-pipeline', 'assets', 'ez-build.sh'),
    resolve(__dirname, 'assets', 'ez-build.sh'),
    resolve(process.cwd(), 'packages/server/src/services/tahp/adapt-pipeline/assets/ez-build.sh'),
  ]
  for (const p of candidates) {
    if (existsSync(p)) return p
  }
  throw new Error(`未找到 ez-build.sh（tried: ${candidates.join(' | ')})`)
}

export function loadEzBuildScript(): string {
  return readFileSync(resolveEzBuildScriptPath(), 'utf-8').replace(/\r\n/g, '\n').replace(/\r/g, '\n')
}
