/**
 * 本机 Modem Meta MetaCLI 探测与进程启动。
 * 安装目录权威源：一键配置表单「Modem 工具 → Modem Meta」（unified-config.modem_meta_root）。
 */
import { spawn } from 'child_process'
import { existsSync, readFileSync } from 'fs'
import { join, resolve, dirname } from 'path'
import { readUnifiedConfig } from '../unified-config'

export const MODEM_META_CONFIG_HINT =
  '未配置 Modem Meta 安装目录。请前往「配置 → 一键配置表单 → Modem 工具」填写后保存，再重试备份/恢复。'

/** 从一键配置表单读取已保存的 Modem Meta 安装目录（不含 env 预填） */
export function readConfiguredModemMetaRoot(): string | undefined {
  try {
    const v = (readUnifiedConfig().modem_meta_root || '').trim()
    return v || undefined
  } catch {
    return undefined
  }
}

/** 支持安装根目录，或误填为 .../bin/MetaCLI.exe 的路径 */
export function normalizeModemMetaRoot(raw: string): string {
  let path = resolve(raw.trim())
  const base = path.replace(/\\/g, '/').toLowerCase()
  if (base.endsWith('/bin/metacli.exe') || base.endsWith('/metacli.exe')) {
    path = dirname(dirname(path))
  }
  return path
}

/**
 * 解析 Modem Meta 安装根目录。
 * - explicit：仅测试或内部覆盖
 * - 否则只读一键配置表单已保存值（不静默使用硬编码默认路径）
 */
export function resolveModemMetaRoot(explicit?: string): string {
  const raw = explicit?.trim() || readConfiguredModemMetaRoot()
  if (!raw) return ''
  return normalizeModemMetaRoot(raw)
}

export function resolveMetaCliExe(metaRoot: string): string {
  return join(metaRoot, 'bin', 'MetaCLI.exe')
}

export function buildMetaCliEnv(metaRoot: string): NodeJS.ProcessEnv {
  const extra = [
    metaRoot,
    join(metaRoot, 'bin'),
    join(metaRoot, 'systems', 'Microsoft.VC140.CRT'),
    join(metaRoot, 'systems', 'Microsoft.VC90.CRT'),
    join(metaRoot, 'systems', 'Qt'),
  ]
  const sep = process.platform === 'win32' ? ';' : ':'
  return {
    ...process.env,
    PATH: `${extra.join(sep)}${sep}${process.env.PATH ?? ''}`,
  }
}

export function resolveModemMetaLastOpenIniPath(metaRoot: string): string | undefined {
  const settingsPath = join(metaRoot, 'configs', 'User_Latest_Settings.txt')
  if (!existsSync(settingsPath)) return undefined
  try {
    const text = readFileSync(settingsPath, 'utf-8')
    const m = /^last_open_path\s*=\s*(.+)$/im.exec(text)
    const raw = m?.[1]?.trim()
    if (!raw) return undefined
    const p = resolve(raw)
    return existsSync(p) ? p : undefined
  } catch {
    return undefined
  }
}

export function probeModemMetaCli(metaRootInput?: string): {
  available: boolean
  reason?: string
  needs_config?: boolean
  meta_root?: string
  meta_cli?: string
  platform?: string
  suggested_items_ini?: string
} {
  if (process.platform !== 'win32') {
    return {
      available: false,
      reason: '射频校准 MetaCLI 仅支持 Windows 本机执行',
      platform: process.platform,
    }
  }

  const configured = readConfiguredModemMetaRoot()
  const raw = metaRootInput?.trim() || configured
  if (!raw) {
    return {
      available: false,
      needs_config: true,
      reason: MODEM_META_CONFIG_HINT,
      platform: process.platform,
    }
  }

  const metaRoot = normalizeModemMetaRoot(raw)
  const metaCli = resolveMetaCliExe(metaRoot)
  if (!existsSync(metaCli)) {
    return {
      available: false,
      needs_config: !configured,
      reason: configured
        ? `一键配置中的 Modem Meta 路径无效（未找到 MetaCLI.exe）。请到「配置 → 一键配置表单 → Modem 工具」更正。当前: ${metaCli}`
        : MODEM_META_CONFIG_HINT,
      meta_root: metaRoot,
      meta_cli: metaCli,
      platform: process.platform,
    }
  }
  return {
    available: true,
    meta_root: metaRoot,
    meta_cli: metaCli,
    platform: process.platform,
    suggested_items_ini: resolveModemMetaLastOpenIniPath(metaRoot),
  }
}

export interface SpawnMetaCliOptions {
  metaRoot: string
  initFilePath: string
  cwd?: string
  timeoutMs?: number
  onStdout?: (chunk: string) => void
  onStderr?: (chunk: string) => void
  signal?: { cancelled: boolean }
}

export function spawnMetaCli(opts: SpawnMetaCliOptions): Promise<{
  stdout: string
  stderr: string
  code: number | null
}> {
  const metaCli = resolveMetaCliExe(opts.metaRoot)
  const env = buildMetaCliEnv(opts.metaRoot)
  const cwd = opts.cwd || opts.metaRoot
  const timeoutMs = opts.timeoutMs ?? 15 * 60 * 1000

  return new Promise((resolvePromise, reject) => {
    const proc = spawn(metaCli, ['-i', opts.initFilePath], {
      cwd,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    })

    let stdout = ''
    let stderr = ''
    let settled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let cancelWatch: ReturnType<typeof setInterval> | undefined

    const cleanup = () => {
      if (timer) clearTimeout(timer)
      if (cancelWatch) clearInterval(cancelWatch)
    }

    const finish = (code: number | null) => {
      if (settled) return
      settled = true
      cleanup()
      resolvePromise({ stdout, stderr, code })
    }

    timer = setTimeout(() => {
      if (settled) return
      settled = true
      cleanup()
      try { proc.kill('SIGKILL') } catch { /* ignore */ }
      reject(new Error(`MetaCLI 超时（${Math.round(timeoutMs / 1000)}s），请确认设备已进入 META 模式且 COM 口可用`))
    }, timeoutMs)

    cancelWatch = setInterval(() => {
      if (settled || !opts.signal?.cancelled) return
      settled = true
      cleanup()
      try { proc.kill('SIGKILL') } catch { /* ignore */ }
      finish(null)
    }, 400)

    proc.stdout?.on('data', (chunk: Buffer) => {
      const text = chunk.toString()
      stdout += text
      opts.onStdout?.(text)
    })
    proc.stderr?.on('data', (chunk: Buffer) => {
      const text = chunk.toString()
      stderr += text
      opts.onStderr?.(text)
    })
    proc.on('error', (err) => {
      if (settled) return
      settled = true
      cleanup()
      reject(err)
    })
    proc.on('close', (code) => finish(code))
  })
}
