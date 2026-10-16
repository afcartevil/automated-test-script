/**
 * 流水线烧录前的 OEM 锁探测 / 自动解锁。
 * 解锁步骤与桌面 oem unlock_product.bat 一致，脚本在 assets/oem-unlock-product.bat。
 */
import { existsSync } from 'node:fs'
import { spawn } from 'node:child_process'
import { resolve } from 'node:path'

export type OemLocked = 'unlocked' | 'locked' | 'unknown'
export type OemBuildKind = 'user' | 'userdebug' | 'userroot' | 'unknown'
export type OemWizardGate = 'unlocked' | 'block_user' | 'offer_auto_unlock' | 'unknown'

export interface OemLockStatus {
  serial: string
  flash_locked: string
  build_type: string
  locked: OemLocked
  build_kind: OemBuildKind
  gate: OemWizardGate
}

const GETPROP_TIMEOUT_MS = 15_000
const UNLOCK_TIMEOUT_MS = 10 * 60_000

export function parseFlashLocked(raw: string): OemLocked {
  const v = String(raw ?? '').trim()
  if (v === '0') return 'unlocked'
  if (v === '1') return 'locked'
  return 'unknown'
}

export function parseBuildKind(raw: string): OemBuildKind {
  const v = String(raw ?? '').trim().toLowerCase().replace(/-/g, '_')
  if (v === 'user') return 'user'
  if (v === 'userdebug') return 'userdebug'
  if (v === 'userroot' || v === 'user_root') return 'userroot'
  if (v === 'eng') return 'userdebug'
  return 'unknown'
}

export function resolveOemWizardGate(locked: OemLocked, buildKind: OemBuildKind): OemWizardGate {
  if (locked === 'unlocked') return 'unlocked'
  if (locked !== 'locked') return 'unknown'
  if (buildKind === 'user') return 'block_user'
  if (buildKind === 'userdebug' || buildKind === 'userroot') return 'offer_auto_unlock'
  return 'unknown'
}

export function resolveOemUnlockScriptPath(): string {
  const candidates = [
    resolve(__dirname, 'assets', 'oem-unlock-product.bat'),
    resolve(__dirname, 'adapt-pipeline', 'assets', 'oem-unlock-product.bat'),
    resolve(process.cwd(), 'packages/server/src/services/tahp/adapt-pipeline/assets/oem-unlock-product.bat'),
    resolve(process.cwd(), 'dist/server/adapt-pipeline/assets/oem-unlock-product.bat'),
  ]
  for (const p of candidates) {
    if (existsSync(p)) return p
  }
  throw new Error(`未找到 oem-unlock-product.bat（tried: ${candidates.join(' | ')})`)
}

function assertSerial(serial: string): string {
  const s = String(serial ?? '').trim()
  if (!s || /[\s&|<>^"]/.test(s)) {
    throw new Error('无效的设备 serial')
  }
  return s
}

function adbGetprop(serial: string, prop: string, timeoutMs = GETPROP_TIMEOUT_MS): Promise<string> {
  return new Promise((resolvePromise, reject) => {
    const proc = spawn('adb', ['-s', serial, 'shell', 'getprop', prop], { windowsHide: true })
    let stdout = ''
    let stderr = ''
    const timer = setTimeout(() => {
      proc.kill()
      reject(new Error(`getprop ${prop} 超时`))
    }, timeoutMs)
    proc.stdout?.on('data', (chunk: Buffer) => { stdout += chunk.toString('utf8') })
    proc.stderr?.on('data', (chunk: Buffer) => { stderr += chunk.toString('utf8') })
    proc.on('error', (err) => {
      clearTimeout(timer)
      reject(err)
    })
    proc.on('close', (code) => {
      clearTimeout(timer)
      if (code !== 0 && !stdout.trim()) {
        reject(new Error(stderr.trim() || `getprop ${prop} exit=${code}`))
        return
      }
      resolvePromise(stdout.trim())
    })
  })
}

export async function probeOemLockStatus(serial: string): Promise<OemLockStatus> {
  const id = assertSerial(serial)
  const [flash_locked, build_type] = await Promise.all([
    adbGetprop(id, 'ro.boot.flash.locked'),
    adbGetprop(id, 'ro.build.type'),
  ])
  const locked = parseFlashLocked(flash_locked)
  const build_kind = parseBuildKind(build_type)
  return {
    serial: id,
    flash_locked,
    build_type,
    locked,
    build_kind,
    gate: resolveOemWizardGate(locked, build_kind),
  }
}

export interface OemUnlockRunResult {
  ok: boolean
  exit_code: number
  output: string
  error?: string
}

export function runOemUnlockProduct(
  serial: string,
  onLine?: (line: string) => void,
  timeoutMs = UNLOCK_TIMEOUT_MS,
): Promise<OemUnlockRunResult> {
  const id = assertSerial(serial)
  const bat = resolveOemUnlockScriptPath()
  return new Promise((resolvePromise) => {
    const proc = spawn('cmd.exe', ['/d', '/c', bat, id], { windowsHide: true })
    let output = ''
    const timer = setTimeout(() => {
      proc.kill()
    }, timeoutMs)
    const append = (chunk: Buffer) => {
      const text = chunk.toString('utf8')
      output += text
      for (const line of text.split(/\r?\n/)) {
        if (line.trim()) onLine?.(line)
      }
    }
    proc.stdout?.on('data', append)
    proc.stderr?.on('data', append)
    proc.on('error', (err) => {
      clearTimeout(timer)
      resolvePromise({
        ok: false,
        exit_code: -1,
        output,
        error: err.message,
      })
    })
    proc.on('close', (code) => {
      clearTimeout(timer)
      const exit_code = code ?? -1
      resolvePromise({
        ok: exit_code === 0,
        exit_code,
        output,
        error: exit_code === 0 ? undefined : `oem-unlock-product.bat exit=${exit_code}`,
      })
    })
  })
}
