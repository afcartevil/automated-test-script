/**
 * 远程 shell：新 CLI 静默 asf bridge cmd / bridge up；旧 CLI 走 remote-runner bridge-exec。
 * 不探测、不调用 Transhell 桌面桥。
 */
import { execFileSync } from 'child_process'
import { existsSync, readFileSync, unlinkSync } from 'fs'
import { resolve } from 'path'
import { assertHarnessCliReady } from '../harness-version-gate'
import {
  detectRemoteExecFlavor,
  hostCliEnv,
  parseJsonLoose,
  parseWrappedRemoteResult,
  resolveHarnessJs,
  resolveHostCliSpawn,
  spawnHostCli,
  wrapRemoteShellForExitCode,
  asfBridgeWaitSec,
  isTransientAsfBridgeFailure,
  asfBridgeCliTimeoutMs,
  asfZellijMissingFromDoctor,
  asfNeedsZellijSetup,
  pickAsfUpSession,
  parseZellijLsShort,
  type RemoteExecFlavor,
} from '../host-tool-runtime'

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

export { resolveHarnessJs }

function sleep(ms: number): Promise<void> {
  return new Promise(r => setTimeout(r, ms))
}

export function resolveHarnessSpawn(args: string[]): { command: string; argv: string[] } {
  return resolveHostCliSpawn(args)
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
  return spawnHostCli(args, opts)
}

let asfSession: number | null = null

function remoteFlavor(): RemoteExecFlavor {
  return detectRemoteExecFlavor()
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

function asfSessionsFromPayload(parsed: Record<string, unknown> | null): Array<{
  session: number
  phase: string
  slot?: string
  message?: string
}> {
  const raw = parsed?.sessions
  if (!Array.isArray(raw)) return []
  return raw.map((item) => {
    const row = item as Record<string, unknown>
    return {
      session: Number(row.session),
      phase: String(row.phase || ''),
      slot: row.slot != null ? String(row.slot) : undefined,
      message: row.message != null ? String(row.message) : undefined,
    }
  }).filter(s => Number.isFinite(s.session) && s.session > 0)
}

async function listAsfBridgeSessions(): Promise<Array<{ session: number; phase: string; message?: string }>> {
  const { stdout, stderr } = await spawnHarness(['--json', 'bridge', 'ls'], { timeoutMs: 30_000 })
  const parsed = parseJsonLoose(stdout) || parseJsonLoose(stderr)
  return asfSessionsFromPayload(parsed)
}

async function ensureAsfZellijInstalled(opts?: {
  signal?: { cancelled: boolean }
  onLog?: (line: string) => void
}): Promise<void> {
  const log = (line: string) => opts?.onLog?.(line)
  const { stdout, stderr } = await spawnHarness(['--json', 'bridge', 'doctor'], {
    timeoutMs: 45_000,
    signal: opts?.signal,
  })
  const parsed = parseJsonLoose(stdout) || parseJsonLoose(stderr)
  if (!parsed || !asfZellijMissingFromDoctor(parsed)) return
  log('Zellij 未安装，自动执行 asf --json bridge setup…')
  await spawnHarness(['--json', 'bridge', 'setup'], {
    timeoutMs: 180_000,
    signal: opts?.signal,
    onStdout: (chunk) => {
      const line = chunk.trim()
      if (line) log(line.slice(0, 400))
    },
  })
}

async function listZellijMuxNames(): Promise<string[]> {
  const localApp = process.env.LOCALAPPDATA || ''
  const candidates = [
    localApp ? resolve(localApp, 'Zellij', 'zellij.EXE') : '',
    localApp ? resolve(localApp, 'Zellij', 'zellij.exe') : '',
    process.env.HOME ? resolve(process.env.HOME, '.local', 'bin', 'zellij') : '',
  ].filter(Boolean)
  const bin = candidates.find(p => existsSync(p))
  if (!bin) return []
  try {
    const out = execFileSync(bin, ['list-sessions', '-s'], {
      encoding: 'utf-8',
      timeout: 8_000,
      windowsHide: true,
    })
    return parseZellijLsShort(out)
  } catch {
    return []
  }
}

async function tryAsfBridgeUp(session: number, opts?: {
  signal?: { cancelled: boolean }
}): Promise<{ parsed: Record<string, unknown> | null; stdout: string; stderr: string }> {
  try {
    const { stdout, stderr } = await spawnHarness(
      ['--json', 'bridge', 'up', '--session', String(session)],
      { timeoutMs: 180_000, signal: opts?.signal },
    )
    return {
      parsed: parseJsonLoose(stdout) || parseJsonLoose(stderr),
      stdout,
      stderr,
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    return { parsed: null, stdout: '', stderr: msg }
  }
}

function asfUpReadySession(parsed: Record<string, unknown> | null): number | null {
  const fromUp = parsed?.session != null ? Number(parsed.session) : NaN
  if (!Number.isFinite(fromUp) || fromUp <= 0) return null
  const phase = String(parsed?.phase || '')
  if (phase === 'ready' || !phase) return fromUp
  return null
}

async function ensureAsfBridgeSession(opts?: {
  signal?: { cancelled: boolean }
  onLog?: (line: string) => void
}): Promise<number> {
  const log = (line: string) => opts?.onLog?.(line)
  await ensureAsfZellijInstalled(opts)

  const slots = await listAsfBridgeSessions()
  const existing = slots.find(s => s.phase === 'ready')
  if (existing) {
    asfSession = existing.session
    log(`ASF Bridge session ${existing.session} 已 READY`)
    return existing.session
  }

  const muxNames = await listZellijMuxNames()
  const session = pickAsfUpSession({ slots, muxNames })
  if (session == null) {
    throw new Error(
      `ASF Bridge 四个槽的 Zellij 名都被占用（${muxNames.join(', ') || 'unknown'}）。agent_session1 若是幽灵会话，请结束残留 zellij.EXE 后重试。`,
    )
  }
  if (muxNames.includes('agent_session1') || session !== 1) {
    log(`跳过幽灵/占用 mux，静默 bridge up --session ${session}（zellij ls: ${muxNames.join(', ') || '(empty)'}）`)
  } else {
    log(`ASF Bridge 无现成 session，静默 bridge up --session ${session}…`)
  }

  const signal = { cancelled: false }
  const pumpCancel = setInterval(() => {
    if (opts?.signal?.cancelled) signal.cancelled = true
  }, 400)
  const upPromise = tryAsfBridgeUp(session, { signal })
  const upDeadline = Date.now() + 180_000
  try {
    while (Date.now() < upDeadline) {
      if (opts?.signal?.cancelled) throw new Error('已取消')
      await sleep(2000)
      const hit = (await listAsfBridgeSessions()).find(s => s.phase === 'ready')
      if (hit) {
        signal.cancelled = true
        asfSession = hit.session
        log(`ASF Bridge session ${hit.session} 已 READY（up CLI 可能仍阻塞，已继续）`)
        return hit.session
      }
    }
  } finally {
    clearInterval(pumpCancel)
  }

  const up = await upPromise
  const ready = asfUpReadySession(up.parsed)
  if (ready != null) {
    asfSession = ready
    log(`ASF Bridge up session=${ready}`)
    return ready
  }

  for (let i = 0; i < 15; i++) {
    if (opts?.signal?.cancelled) throw new Error('已取消')
    await sleep(2000)
    const again = await listAsfBridgeSessions()
    const hit = again.find(s => s.phase === 'ready')
    if (hit) {
      asfSession = hit.session
      log(`ASF Bridge session ${hit.session} 已 READY`)
      return hit.session
    }
  }
  const detail = asfFailureMessage(up.parsed, up.stderr)
  throw new Error(
    `ASF Bridge 未能自动登录（${detail.slice(0, 400)}）。请确认一键配置表单已保存齐治凭据与 TOTP。`,
  )
}

function asfFailureMessage(parsed: Record<string, unknown> | null, stderr: string): string {
  if (!parsed) return stderr.trim() || 'asf bridge cmd 无输出'
  const parts = [parsed.error_code, parsed.message, parsed.error]
    .filter(v => v != null && String(v).trim())
    .map(v => String(v))
  return [...new Set(parts)].join(': ') || stderr.trim() || 'asf bridge cmd 失败'
}

async function asfBridgeCmdOnce(
  session: number,
  wrapped: string,
  opts: {
    waitSec: number
    timeoutSec: number
    onStdout?: (chunk: string) => void
    onStderr?: (chunk: string) => void
    signal?: { cancelled: boolean }
  },
): Promise<BridgeExecResult> {
  const localTimeoutMs = asfBridgeCliTimeoutMs(opts.waitSec)
  try {
    const { stdout, stderr } = await spawnHarness(
      [
        '--json',
        'bridge',
        'cmd',
        '--session',
        String(session),
        '--wait',
        String(opts.waitSec),
        '--lines',
        '200',
        wrapped,
      ],
      {
        timeoutMs: localTimeoutMs,
        onStdout: opts.onStdout,
        onStderr: opts.onStderr,
        signal: opts.signal,
      },
    )
    const parsed = parseJsonLoose(stdout) || parseJsonLoose(stderr)
    if (!parsed) {
      return {
        status: 'error',
        exit_code: -1,
        command: wrapped,
        output: stdout,
        error: `invalid asf bridge json: ${stderr || stdout || '(empty)'}`,
      }
    }
    const fail = asfFailureMessage(parsed, stderr)
    if (String(parsed.status).toLowerCase() === 'error' || parsed.error_code) {
      return {
        status: 'error',
        exit_code: -1,
        command: wrapped,
        output: parsed.output != null ? String(parsed.output) : stdout,
        error: fail,
        error_code: parsed.error_code != null ? String(parsed.error_code) : undefined,
      }
    }

    let output = String(parsed.output || '')
    let complete = parsed.complete !== false
    if (!complete && output.indexOf('TAHP_BRIDGE_EXIT:') < 0) {
      const deadline = Date.now() + opts.timeoutSec * 1000
      while (Date.now() < deadline && !opts.signal?.cancelled) {
        await sleep(2000)
        const read = await spawnHarness(
          ['--json', 'bridge', 'read', '--session', String(session), '--lines', '400'],
          { timeoutMs: 30_000, signal: opts.signal },
        )
        const rp = parseJsonLoose(read.stdout) || parseJsonLoose(read.stderr)
        if (rp && (String(rp.status).toLowerCase() === 'error' || rp.error_code)) {
          return {
            status: 'error',
            exit_code: -1,
            command: wrapped,
            output: rp.output != null ? String(rp.output) : output,
            error: asfFailureMessage(rp, read.stderr),
            error_code: rp.error_code != null ? String(rp.error_code) : undefined,
          }
        }
        if (rp?.output != null) output = String(rp.output)
        if (output.indexOf('TAHP_BRIDGE_EXIT:') >= 0) {
          complete = true
          break
        }
      }
    }
    const parsedOut = parseWrappedRemoteResult(output)
    const exit_code = parsedOut.exit_code
    return {
      status: String(parsed.status || (complete ? 'ok' : 'error')),
      exit_code: exit_code == null ? -1 : exit_code,
      command: wrapped,
      output: parsedOut.output,
      error: exit_code == null && !complete ? 'asf bridge cmd 未完成' : undefined,
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    return {
      status: 'error',
      exit_code: -1,
      command: wrapped,
      error: msg,
    }
  }
}

async function asfBridgeCmd(
  command: string,
  opts?: {
    timeoutSec?: number
    onStdout?: (chunk: string) => void
    onStderr?: (chunk: string) => void
    signal?: { cancelled: boolean }
  },
): Promise<BridgeExecResult> {
  const timeoutSec = Math.max(1, opts?.timeoutSec ?? 300)
  const waitSec = asfBridgeWaitSec(timeoutSec)
  const note = (line: string) => opts?.onStdout?.(`${line}\n`)
  const session = await ensureAsfBridgeSession({ signal: opts?.signal, onLog: note })
  const wrapped = wrapRemoteShellForExitCode(command)

  let last: BridgeExecResult | null = null
  for (let attempt = 1; attempt <= 3; attempt++) {
    const result = await asfBridgeCmdOnce(session, wrapped, {
      waitSec,
      timeoutSec,
      onStdout: opts?.onStdout,
      onStderr: opts?.onStderr,
      signal: opts?.signal,
    })
    const blob = `${result.error || ''}\n${result.output || ''}`
    if (!isTransientAsfBridgeFailure(blob)) {
      return { ...result, command }
    }
    last = { ...result, command }
    note(`ASF Bridge 瞬时失败 (${attempt}/3): ${result.error || 'zellij timeout'}，同 session 重试`)
    try {
      await spawnHarness(
        ['--json', 'bridge', 'interrupt', '--session', String(session)],
        { timeoutMs: 15_000, signal: opts?.signal },
      )
    } catch { /* ignore */ }
    await sleep(1500)
  }
  return last!
}

async function legacyBridgeExec(
  command: string,
  opts?: {
    timeoutSec?: number
    onStdout?: (chunk: string) => void
    onStderr?: (chunk: string) => void
    signal?: { cancelled: boolean }
  },
): Promise<BridgeExecResult> {
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
  const flavor = remoteFlavor()
  if (flavor === 'legacy-bridge-exec') return legacyBridgeExec(command, opts)
  if (flavor === 'asf-bridge') return asfBridgeCmd(command, opts)
  throw new Error('本机 CLI 无 remote-runner bridge-exec，也无 asf bridge cmd，无法执行远程命令')
}

function discoverLegacyBridgeReady(): BridgeStatus {
  try {
    const { command, argv } = resolveHarnessSpawn(['--json', 'remote-runner', 'discover'])
    const out = execFileSync(command, argv, {
      encoding: 'utf-8',
      timeout: 60_000,
      windowsHide: true,
      env: hostCliEnv(),
    })
    const parsed = parseJsonLoose(out)
    if (!parsed) return { ready: false, error: 'discover 返回非 JSON' }
    return bridgeFromPayload(parsed)
  } catch (err) {
    return { ready: false, error: (err as Error).message }
  }
}

/** ASF session 是否 READY。不含 mapped_root，代码拉取须用 {@link discoverRemoteRunner}。 */
function discoverAsfBridgeReady(): BridgeStatus {
  try {
    const { command, argv } = resolveHarnessSpawn(['--json', 'bridge', 'ls'])
    const out = execFileSync(command, argv, {
      encoding: 'utf-8',
      timeout: 30_000,
      windowsHide: true,
      env: hostCliEnv(),
    })
    const parsed = parseJsonLoose(out)
    const ready = asfSessionsFromPayload(parsed).some(s => s.phase === 'ready')
    const first = asfSessionsFromPayload(parsed).find(s => s.phase === 'ready')
    if (first) asfSession = first.session
    return {
      ready,
      raw: parsed || undefined,
      sessionPhase: first?.phase,
      error: ready ? undefined : String(parsed?.message || 'ASF Bridge 无 ready session'),
    }
  } catch (err) {
    return { ready: false, error: (err as Error).message }
  }
}

export function discoverBridgeReady(): BridgeStatus {
  try {
    assertHarnessCliReady()
  } catch (err) {
    return { ready: false, error: (err as Error).message }
  }
  const flavor = remoteFlavor()
  if (flavor === 'asf-bridge') return discoverAsfBridgeReady()
  return discoverLegacyBridgeReady()
}

/**
 * 映射盘 / runner 发现。与 {@link discoverBridgeReady} 不是同一件事：
 * ASF 的 `bridge ls` 只有 session，没有 mapped_root。
 * `asf` 与旧 `harness` 都保留 `remote-runner discover`。
 */
export function discoverRemoteRunner(): Record<string, unknown> | null {
  try {
    assertHarnessCliReady()
    const { command, argv } = resolveHarnessSpawn(['--json', 'remote-runner', 'discover'])
    const out = execFileSync(command, argv, {
      encoding: 'utf-8',
      timeout: 60_000,
      windowsHide: true,
      env: hostCliEnv(),
    })
    return parseJsonLoose(out)
  } catch {
    return null
  }
}

export async function diagnoseBridge(): Promise<BridgeStatus> {
  const flavor = remoteFlavor()
  if (flavor === 'asf-bridge') {
    try {
      const { stdout, stderr } = await spawnHarness(['--json', 'bridge', 'doctor'], { timeoutMs: 60_000 })
      const parsed = parseJsonLoose(stdout) || parseJsonLoose(stderr)
      if (!parsed) return { ready: false, error: stderr || stdout || 'doctor 无输出' }
      const sessions = asfSessionsFromPayload(parsed)
      const ready = sessions.some(s => s.phase === 'ready')
      return {
        ready,
        raw: parsed,
        sessionPhase: sessions.find(s => s.phase === 'ready')?.phase,
        error: ready ? undefined : String(parsed.message || ''),
      }
    } catch (err) {
      return { ready: false, error: (err as Error).message }
    }
  }
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
  const flavor = remoteFlavor()
  if (flavor === 'asf-bridge') {
    const session = asfSession
    if (session == null) return
    try {
      await spawnHarness(
        ['--json', 'bridge', 'interrupt', '--session', String(session)],
        { timeoutMs: 30_000 },
      )
    } catch { /* ignore */ }
    return
  }
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
    for (const rel of ['.tran_asf/bin/sidecar-python.txt', '.tran_harness/bin/sidecar-python.txt']) {
      const tip = resolve(home, rel)
      if (existsSync(tip)) {
        const line = readFileSync(tip, 'utf-8').trim().split(/\r?\n/)[0]?.trim()
        if (line && existsSync(line)) return line
      }
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
 * 编译前确保远程执行通路 READY。
 * 新 CLI：静默 asf bridge up（凭据在 env.yaml）；旧 CLI：TOTP / bridge-serve。
 * 不探测、不等待 Transhell 桌面桥。
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

  if (remoteFlavor() === 'asf-bridge') {
    const session = await ensureAsfBridgeSession({ signal: opts?.signal, onLog: log })
    return { ready: true, sessionPhase: 'ready', agentNextAction: `asf-bridge session ${session}` }
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
