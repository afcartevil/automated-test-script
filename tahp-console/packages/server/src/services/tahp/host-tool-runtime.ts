/**
 * 本机 ASF / Harness CLI 探测：可执行入口、远程执行形态、提示词用前缀。
 * 不写死 skill 目录名；远程执行按命令是否存在选择 legacy bridge-exec 或 asf bridge cmd。
 */
import { execFileSync, spawn } from 'child_process'
import { existsSync } from 'fs'
import { resolve } from 'path'

export type RemoteExecFlavor = 'legacy-bridge-exec' | 'asf-bridge' | 'unavailable'

export const BRIDGE_EXIT_MARKER = 'TAHP_BRIDGE_EXIT:'

const FLAVOR_TTL_MS = 60_000

let flavorCache: { value: RemoteExecFlavor; at: number } | null = null

function npmBinDir(): string | null {
  const appData = process.env.APPDATA
  if (!appData) return null
  const dir = resolve(appData, 'npm')
  return existsSync(dir) ? dir : null
}

/** npm 全局包里的 harness.js（asf / harness 共用） */
export function resolveHarnessJs(): string | null {
  const dir = npmBinDir()
  if (!dir) return null
  const js = resolve(dir, 'node_modules', '@transsion', 'harness-cli', 'bin', 'harness.js')
  return existsSync(js) ? js : null
}

function npmCliPs1(name: 'asf' | 'harness'): string | null {
  const dir = npmBinDir()
  if (!dir) return null
  const ps1 = resolve(dir, `${name}.ps1`)
  return existsSync(ps1) ? ps1 : null
}

export function hostCliPrefix(): 'asf' | 'harness' {
  const dir = npmBinDir()
  if (dir && existsSync(resolve(dir, 'asf.cmd'))) return 'asf'
  if (dir && existsSync(resolve(dir, 'asf.ps1'))) return 'asf'
  return 'harness'
}

export function hostCliEnv(): NodeJS.ProcessEnv {
  const isWindows = process.platform === 'win32'
  const dir = npmBinDir()
  if (isWindows && dir) {
    return { ...process.env, PATH: `${process.env.PATH ?? ''};${dir}` }
  }
  return process.env
}

/**
 * Windows 优先: node harness.js + argv 数组（保留 --command 整串）。
 * 回退: asf.ps1 / harness.ps1 / PATH 中的 asf|harness。
 */
export function resolveHostCliSpawn(args: string[]): { command: string; argv: string[] } {
  const isWindows = process.platform === 'win32'
  const harnessJs = resolveHarnessJs()
  if (isWindows && harnessJs) {
    return { command: process.execPath, argv: [harnessJs, ...args] }
  }
  const prefix = hostCliPrefix()
  const ps1 = npmCliPs1(prefix) ?? npmCliPs1(prefix === 'asf' ? 'harness' : 'asf')
  if (isWindows && ps1) {
    return {
      command: 'powershell.exe',
      argv: ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ps1, ...args],
    }
  }
  return { command: prefix, argv: args }
}

export function spawnHostCli(
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
  const env = hostCliEnv()
  const { command, argv } = resolveHostCliSpawn(args)

  return new Promise((resolvePromise, reject) => {
    const processRef = spawn(command, argv, {
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
    let timer: ReturnType<typeof setTimeout> | undefined
    let cancelWatch: ReturnType<typeof setInterval> | undefined
    const stopWatch = () => {
      if (timer) clearTimeout(timer)
      if (cancelWatch) clearInterval(cancelWatch)
    }

    timer = setTimeout(() => {
      if (settled) return
      settled = true
      stopWatch()
      try { processRef.kill('SIGKILL') } catch { /* ignore */ }
      reject(new Error(`host CLI timeout after ${Math.round(timeoutMs / 1000)}s`))
    }, timeoutMs)

    cancelWatch = setInterval(() => {
      if (settled || !opts?.signal?.cancelled) return
      settled = true
      stopWatch()
      try { processRef.kill('SIGKILL') } catch { /* ignore */ }
      resolvePromise({ stdout, stderr, code: null })
    }, 400)

    const finish = (code: number | null) => {
      if (settled) return
      settled = true
      stopWatch()
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
      stopWatch()
      reject(err)
    })
    processRef.on('close', (code) => finish(code))
  })
}

function runHostCliSync(args: string[], timeoutMs = 8_000): string {
  const env = hostCliEnv()
  const { command, argv } = resolveHostCliSpawn(args)
  try {
    return execFileSync(command, argv, {
      encoding: 'utf-8',
      timeout: timeoutMs,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
      env,
    })
  } catch (err) {
    const e = err as { stdout?: string; stderr?: string; message?: string }
    return `${e.stdout || ''}\n${e.stderr || ''}\n${e.message || ''}`
  }
}

/** 纯函数：根据 help 文本判定远程执行形态（供测试） */
export function flavorFromHelpText(remoteRunnerHelp: string, bridgeHelp: string): RemoteExecFlavor {
  if (/bridge-exec/.test(remoteRunnerHelp)) return 'legacy-bridge-exec'
  if (/\bcmd\b/.test(bridgeHelp) && /bridge/.test(bridgeHelp)) return 'asf-bridge'
  return 'unavailable'
}

export function detectRemoteExecFlavor(opts?: { refresh?: boolean }): RemoteExecFlavor {
  if (!opts?.refresh && flavorCache && Date.now() - flavorCache.at < FLAVOR_TTL_MS) {
    return flavorCache.value
  }
  const rr = runHostCliSync(['remote-runner', '--help'])
  const br = /bridge-exec/.test(rr) ? '' : runHostCliSync(['bridge', '--help'])
  const value = flavorFromHelpText(rr, br)
  flavorCache = { value, at: Date.now() }
  return value
}

export function resetRemoteExecFlavorCache(): void {
  flavorCache = null
}

/**
 * asf `bridge cmd --wait` 是「sleep 后再 dump pane」，不是远端命令超时。
 * 长 wait 会把 Zellij IPC 晾到 list-panes 超时（Windows 常见 BRIDGE_CMD_FAILED）。
 */
export function asfBridgeWaitSec(timeoutSec: number): number {
  return Math.min(8, Math.max(1, Math.floor(Number(timeoutSec) || 1)))
}

/**
 * 覆盖 asf 内部两次 list-panes（各 30s）+ --wait + 余量。
 * 过短会在 CLI 返回 JSON 前被杀掉，重试逻辑进不去。
 */
export function asfBridgeCliTimeoutMs(waitSec: number): number {
  const wait = Math.max(1, Math.floor(Number(waitSec) || 1))
  return (wait + 90) * 1000
}

export function isTransientAsfBridgeFailure(text: string): boolean {
  return /BRIDGE_CMD_FAILED|zellij timed out|list-panes|host CLI timeout/i.test(String(text || ''))
}

const ASF_BRIDGE_SSH_GONE_RE = /BRIDGE_SSH_DISCONNECTED|OpenSSH is gone|pane_command is local shell|There is no active session|no active session|Session ['`]agent_session\d+['`] not found|session ['`]agent_session\d+['`] not found/i

/** 窗格当前停在 SSH/齐治登录 UI（不要用全文匹配，以免历史输出误伤已重连的 shell） */
const ASF_BRIDGE_LOGIN_UI_RE = /'s password:|Permission denied, please try again|Invalid password for|Password authentication|请选择登录账号|无效的输入[。.]?请选择账号|登录账号列表|set TERM=xterm&& ssh/i

/**
 * asf `bridge cmd/status`：mux 还在但 OpenSSH 已掉，槽已释放。
 * 须 `asf --json bridge up --session N`（或省略 --session）重连，不能只 interrupt 同 session。
 * 另：zellij 名还在但 write-chars 报 no active session（幽灵 mux），
 * `Session 'agent_sessionN' not found`（ls READY 但 mux 已消失），
 * 以及窗格末尾已退回 SSH 密码 / 齐治选账号（cmd 把 shell 打进提示符）也需 down+up。
 * 不匹配编译日志里的泛化 "Permission denied"。
 */
export function isAsfBridgeSshDisconnected(text: string): boolean {
  const s = String(text || '')
  if (ASF_BRIDGE_SSH_GONE_RE.test(s)) return true
  const tail = s.split(/\r?\n/).map(l => l.trim()).filter(Boolean).slice(-16)
  if (!ASF_BRIDGE_LOGIN_UI_RE.test(tail.join('\n'))) return false
  for (let i = tail.length - 1; i >= 0; i--) {
    const line = tail[i]
    if (/^tmux=(?:alive|dead)$/.test(line)) return false
    if (/^TAHP_BRIDGE_EXIT(?:_[A-Za-z0-9]+)?:[0-9]+$/.test(line)) return false
    if (/^---POLL---$/.test(line) || /^---LOG_TAIL---$/.test(line) || /^done_code=/.test(line)) continue
    if (ASF_BRIDGE_LOGIN_UI_RE.test(line)) return true
  }
  return true
}

/** doctor.tools 里 zellij.ok !== true → 需要 `asf --json bridge setup` */
export function asfZellijMissingFromDoctor(parsed: Record<string, unknown> | null): boolean {
  const tools = Array.isArray(parsed?.tools) ? parsed.tools : []
  const zellij = tools.find((item) => {
    if (!item || typeof item !== 'object') return false
    return String((item as Record<string, unknown>).name || '').toLowerCase() === 'zellij'
  }) as Record<string, unknown> | undefined
  if (!zellij) return true
  return zellij.ok !== true
}

/** `zellij list-sessions -s` 一行一个 session 名 */
export function parseZellijLsShort(text: string): string[] {
  return String(text || '')
    .split(/\r?\n/)
    .map((line) => line.trim().split(/\s+/)[0] || '')
    .filter(Boolean)
}

export function asfMuxName(session: number): string {
  return `agent_session${session}`
}

export function parseAsfMuxSession(name: string): number | null {
  const m = /^agent_session(\d+)$/i.exec(String(name || '').trim())
  if (!m) return null
  const n = Number(m[1])
  return Number.isFinite(n) && n >= 1 && n <= 4 ? n : null
}

export interface AsfBridgeSlotClass {
  /** ls READY 且 zellij 确有对应 mux */
  readyWithMux: number[]
  /** ls READY 但 zellij 没有 agent_sessionN（幽灵元数据，须 down+up） */
  staleReady: number[]
  /** zellij 当前列出的槽号 */
  muxSessions: number[]
  /** 可 `bridge up` 的空闲槽（跳过已有 mux / list-panes 超时） */
  upSession: number | null
}

/**
 * 对照 asf `bridge ls` 与 `zellij ls`：名义 READY 必须有 mux 才能用。
 */
export function classifyAsfBridgeSlots(input: {
  slots: Array<{ session: number; phase: string; message?: string }>
  muxNames: string[]
}): AsfBridgeSlotClass {
  const muxSessions = [...new Set(
    input.muxNames.map(parseAsfMuxSession).filter((n): n is number => n != null),
  )].sort((a, b) => a - b)
  const muxSet = new Set(muxSessions)
  const readyWithMux: number[] = []
  const staleReady: number[] = []
  for (const s of input.slots) {
    if (s.phase !== 'ready') continue
    if (muxSet.has(s.session)) readyWithMux.push(s.session)
    else staleReady.push(s.session)
  }
  const blocked = new Set<number>(muxSet)
  for (const s of input.slots) {
    if (/zellij timed out|list-panes/i.test(String(s.message || ''))) blocked.add(s.session)
  }
  let upSession: number | null = null
  for (let n = 1; n <= 4; n++) {
    if (!blocked.has(n)) {
      upSession = n
      break
    }
  }
  return { readyWithMux, staleReady, muxSessions, upSession }
}

/**
 * 认领 up 槽：跳过 zellij ls 里已存在的 agent_sessionN（含幽灵会话），
 * 以及 ls JSON 里 list-panes 超时的槽。`bridge up` 默认占最小 idle 槽，
 * 会撞上删不掉的 agent_session1。
 * 不把「ls READY 但无 mux」当成可直接使用的槽。
 */
export function pickAsfUpSession(input: {
  slots: Array<{ session: number; phase: string; message?: string }>
  muxNames: string[]
}): number | null {
  return classifyAsfBridgeSlots(input).upSession
}

export function asfNeedsZellijSetup(text: string): boolean {
  return /zellij not (found|installed)|install zellij/i.test(String(text || ''))
}

const BRIDGE_EXIT_LINE_RE = /^TAHP_BRIDGE_EXIT(?:_[A-Za-z0-9]+)*:(\d+)$/

/** 每次远程命令唯一标记，避免 Zellij 窗格里旧 TAHP_BRIDGE_EXIT 被误认为本命令已结束。 */
export function newBridgeExitToken(): string {
  const nonce = `${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
  return `TAHP_BRIDGE_EXIT_${nonce}:`
}

/** 给 asf bridge cmd 包一层，从 stdout 取远端退出码（新 CLI 不再返回 exit_code） */
export function wrapRemoteShellForExitCode(command: string, token: string = BRIDGE_EXIT_MARKER): string {
  const trimmed = command.replace(/;\s*$/, '').trim()
  const marker = token.endsWith(':') ? token : `${token}:`
  return `{ ${trimmed}; }; echo ${marker}$?`
}

export function parseWrappedRemoteResult(
  output: string,
  token?: string,
): { output: string; exit_code: number | null } {
  const want = token
    ? (token.endsWith(':') ? token : `${token}:`)
    : null
  const lines = String(output || '').split(/\r?\n/)
  let exit_code: number | null = null
  const kept: string[] = []
  for (const line of lines) {
    const trimmed = line.trim()
    if (want) {
      if (trimmed.startsWith(want)) {
        const code = Number(trimmed.slice(want.length))
        if (Number.isFinite(code)) exit_code = code
        continue
      }
      // 丢掉窗格里残留的其它 exit 行，避免污染上层日志
      if (BRIDGE_EXIT_LINE_RE.test(trimmed) || /^TAHP_BRIDGE_EXIT:\d+$/.test(trimmed)) {
        continue
      }
    } else {
      const m = trimmed.match(/^TAHP_BRIDGE_EXIT(?:_[A-Za-z0-9]+)*:(\d+)$/)
        || trimmed.match(/^TAHP_BRIDGE_EXIT:(\d+)$/)
      if (m) {
        exit_code = Number(m[1])
        continue
      }
    }
    kept.push(line)
  }
  return { output: kept.join('\n').replace(/\n+$/, ''), exit_code }
}

export function hasBridgeExitToken(output: string, token: string): boolean {
  const want = token.endsWith(':') ? token : `${token}:`
  return String(output || '').split(/\r?\n/).some((line) => {
    const trimmed = line.trim()
    if (!trimmed.startsWith(want)) return false
    return Number.isFinite(Number(trimmed.slice(want.length)))
  })
}

export function parseJsonLoose(text: string): Record<string, unknown> | null {
  const trimmed = String(text || '').trim()
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
