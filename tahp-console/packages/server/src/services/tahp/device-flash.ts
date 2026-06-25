/**
 * DeviceUpdate 刷机服务 — 移植自 autotest/interface/device_update_interface.py
 */
import { spawn, spawnSync, type ChildProcessWithoutNullStreams } from 'child_process'
import {
  createReadStream,
  createWriteStream,
  existsSync,
  mkdirSync,
  readdirSync,
  rmSync,
  statSync,
} from 'fs'
import { basename, join, resolve } from 'path'
import { pipeline } from 'stream/promises'
import { Transform } from 'stream'
import { tahpPaths } from './paths'

export interface PickFlashPathResult {
  canceled: boolean
  path?: string
  error?: string
}

const PICKER_SCRIPT = join(__dirname, 'self-check', 'python', 'pick_flash_path.py')
const EXTRACT_ZIP_SCRIPT = join(__dirname, 'self-check', 'python', 'extract_flash_zip.py')

function resolveExtractZipScript(): string {
  if (existsSync(EXTRACT_ZIP_SCRIPT)) return resolve(EXTRACT_ZIP_SCRIPT)
  return join(tahpPaths.selfCheckDir, 'python', 'extract_flash_zip.py')
}

function resolvePickerScript(): string {
  if (existsSync(PICKER_SCRIPT)) return resolve(PICKER_SCRIPT)
  return join(tahpPaths.selfCheckDir, 'python', 'pick_flash_path.py')
}

function pathPickerError(): string | null {
  const script = resolvePickerScript()
  if (!existsSync(script)) return `未找到路径选择脚本: ${script}`
  if (process.platform === 'linux' && !process.env.DISPLAY && !process.env.WAYLAND_DISPLAY) {
    return '无图形界面，请手动输入路径'
  }
  try {
    const probe = spawnSync(tahpPaths.python, [script, '--probe'], {
      encoding: 'utf8',
      windowsHide: true,
      env: pythonPickerEnv(),
      timeout: 10_000,
    })
    if (probe.status !== 0) return 'Python tkinter 不可用，请手动输入路径'
  } catch {
    return '路径选择器不可用'
  }
  return null
}

/** 本机 tkinter 文件选择框（Windows / Linux 桌面 / macOS）。 */
export async function pickLocalFlashPath(): Promise<PickFlashPathResult> {
  const unavailable = pathPickerError()
  if (unavailable) return { canceled: true, error: unavailable }

  const script = resolvePickerScript()
  return new Promise((resolve) => {
    const proc = spawn(tahpPaths.python, [script, '--pick'], {
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: false,
      env: pythonPickerEnv(),
    })
    const stdoutChunks: Buffer[] = []
    proc.stdout?.on('data', (chunk: Buffer) => {
      stdoutChunks.push(chunk)
    })
    proc.on('error', (err) => resolve({ canceled: true, error: err.message }))
    proc.on('close', () => {
      try {
        const stdout = decodeSubprocessBytes(Buffer.concat(stdoutChunks))
        const data = JSON.parse(stdout.trim() || '{}') as PickFlashPathResult
        resolve({
          canceled: Boolean(data.canceled),
          path: typeof data.path === 'string' ? data.path : undefined,
          error: typeof data.error === 'string' ? data.error : undefined,
        })
      } catch {
        resolve({ canceled: true, error: '路径选择结果解析失败' })
      }
    })
  })
}

export const MARKET_VERSIONS = [
  { label: 'Base', value: '' },
  { label: 'Open', value: 'Open' },
  { label: 'Open-Payjoy', value: 'Open-Payjoy' },
  { label: 'RU', value: 'RU' },
  { label: 'Turkey', value: 'Turkey' },
  { label: 'India', value: 'India' },
] as const

export interface DeviceFlashOptions {
  pkgPath: string
  stageVersion?: string
  customMarket?: boolean
  rootPkgPath?: string
  unzipPath?: string
  useCustomUnzipPath?: boolean
}

export interface DeviceFlashResult {
  success: boolean
  returnCode: number
  command: string[]
  workDir: string
  logs: string[]
  error?: string
}

export interface FlashToolInfo {
  deviceUpdateDir: string
  deviceUpdateExe: string
  fastbootExe: string
  flashPackageDir: string
  deviceUpdateExeExists: boolean
}

let activeFlashProcess: ChildProcessWithoutNullStreams | null = null

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

function pythonPickerEnv(): NodeJS.ProcessEnv {
  return {
    ...process.env,
    PYTHONIOENCODING: 'utf-8',
    PYTHONUTF8: '1',
  }
}

function decodeSubprocessBytes(data: Buffer): string {
  if (!data.length) return ''
  if (data[0] === 0xef && data[1] === 0xbb && data[2] === 0xbf) {
    return data.subarray(3).toString('utf8')
  }
  const utf8 = data.toString('utf8')
  if (!utf8.includes('\uFFFD')) return utf8
  try {
    return new TextDecoder('gbk').decode(data)
  } catch {
    return utf8
  }
}

function resolveExecutable(candidates: string[], fallbackName: string): string {
  for (const path of candidates) {
    if (path && existsSync(path)) return resolve(path)
  }
  const pathEnv = process.env.PATH || ''
  for (const dir of pathEnv.split(process.platform === 'win32' ? ';' : ':')) {
    const full = join(dir.trim(), fallbackName + (process.platform === 'win32' ? '.exe' : ''))
    if (existsSync(full)) return full
    const plain = join(dir.trim(), fallbackName)
    if (existsSync(plain)) return plain
  }
  return candidates[0] ? resolve(candidates[0]) : fallbackName
}

export function resolveDeviceUpdateDir(): string {
  const defaultDir = join(tahpPaths.flashToolDir, 'device_update')
  const candidates: string[] = []
  if (process.env.TAHP_FLASH_TOOL_DIR) {
    candidates.push(resolve(process.env.TAHP_FLASH_TOOL_DIR))
  }
  candidates.push(defaultDir)
  if (process.env.TAHP_AUTOTEST_ROOT) {
    candidates.push(join(resolve(process.env.TAHP_AUTOTEST_ROOT), 'flash_tool', 'device_update'))
  }

  for (const dir of candidates) {
    if (existsSync(dir)) return resolve(dir)
  }
  return resolve(defaultDir)
}

export function resolveFlashPackageDir(): string {
  if (process.env.TAHP_FLASH_PACKAGE_DIR) {
    return resolve(process.env.TAHP_FLASH_PACKAGE_DIR)
  }
  return join(tahpPaths.flashToolDir, 'flash_packages')
}

export function resolveDeviceUpdateExe(): string {
  const dir = resolveDeviceUpdateDir()
  return resolveExecutable([join(dir, 'device_update.exe')], 'device_update')
}

export function resolveFastbootExe(): string {
  const dir = resolveDeviceUpdateDir()
  return resolveExecutable([join(dir, 'tools', 'fastboot', 'fastboot.exe')], 'fastboot')
}

export function getFlashToolInfo(): FlashToolInfo {
  const deviceUpdateDir = resolveDeviceUpdateDir()
  const deviceUpdateExe = resolveDeviceUpdateExe()
  return {
    deviceUpdateDir,
    deviceUpdateExe,
    fastbootExe: resolveFastbootExe(),
    flashPackageDir: resolveFlashPackageDir(),
    deviceUpdateExeExists: existsSync(deviceUpdateExe),
  }
}

export function normalizePath(path: string): string {
  const trimmed = path.trim()
  if (trimmed.startsWith('//')) {
    return '\\\\' + trimmed.slice(2).replace(/\//g, '\\')
  }
  return trimmed
}

export function isZipFile(path: string): boolean {
  return path.toLowerCase().endsWith('.zip')
}

export function isNetworkPath(path: string): boolean {
  const normalized = normalizePath(path).replace(/\//g, '\\')
  return normalized.startsWith('\\\\')
}

function findScatterPkgPath(searchRoot: string): string {
  const stack = [searchRoot]
  const scatterMatches: string[] = []
  while (stack.length) {
    const current = stack.pop()!
    let entries: { name: string; isDirectory: () => boolean }[]
    try {
      entries = readdirSync(current, { withFileTypes: true }) as any
    } catch {
      continue
    }
    for (const entry of entries) {
      const full = join(current, entry.name)
      if (entry.isDirectory()) {
        stack.push(full)
      } else if (/scatter\.xml$/i.test(entry.name)) {
        scatterMatches.push(full)
      }
    }
  }
  scatterMatches.sort()
  return scatterMatches[0] ? resolve(scatterMatches[0]) : resolve(searchRoot)
}

function formatByteSize(bytes: number): string {
  const gib = bytes / 1024 / 1024 / 1024
  if (gib >= 1) return `${gib.toFixed(2)} GiB`
  const mib = bytes / 1024 / 1024
  if (mib >= 1) return `${mib.toFixed(1)} MiB`
  return `${Math.max(1, Math.round(bytes / 1024))} KiB`
}

async function copyFileWithProgress(
  src: string,
  dest: string,
  onLog?: (line: string) => void,
  label = 'ZIP'
): Promise<void> {
  const total = statSync(src).size
  const totalLabel = formatByteSize(total)
  onLog?.(`[刷机] 开始复制 ${label} 到本地（共 ${totalLabel}）: ${dest}`)

  let copied = 0
  let lastReportPct = -1
  let lastReportAt = 0
  const report = (force = false) => {
    const pct = total > 0 ? Math.min(100, Math.floor((copied * 100) / total)) : 100
    const now = Date.now()
    if (
      !force &&
      pct < 100 &&
      pct - lastReportPct < 2 &&
      now - lastReportAt < 1500
    ) {
      return
    }
    lastReportPct = pct
    lastReportAt = now
    onLog?.(
      `[刷机] 复制 ${label} 进度: ${pct}% (${formatByteSize(copied)}/${totalLabel})`
    )
  }

  const counter = new Transform({
    transform(chunk, _encoding, callback) {
      copied += chunk.length
      report()
      callback(null, chunk)
    },
  })

  try {
    await pipeline(createReadStream(src), counter, createWriteStream(dest))
  } catch (err) {
    if (existsSync(dest)) rmSync(dest, { force: true })
    throw err
  }

  report(true)
  onLog?.(`[刷机] 复制 ${label} 完成: ${dest}`)
}

async function ensureLocalZip(
  zipPath: string,
  cacheDir: string,
  onLog?: (line: string) => void
): Promise<string> {
  const zipFile = resolve(normalizePath(zipPath))
  if (!existsSync(zipFile)) {
    throw new Error(`ZIP 文件不存在: ${zipFile}`)
  }
  if (!isNetworkPath(zipPath)) return zipFile

  const downloadDir = join(cacheDir, '_downloads')
  mkdirSync(downloadDir, { recursive: true })
  const localZip = join(downloadDir, basename(zipFile))
  if (existsSync(localZip) && statSync(localZip).size === statSync(zipFile).size) {
    onLog?.(`[刷机] 使用已缓存的本地 ZIP: ${localZip}`)
    return localZip
  }
  onLog?.(`[刷机] 从网络路径复制 ZIP 到本地: ${localZip}`)
  await copyFileWithProgress(zipFile, localZip, onLog, 'ZIP')
  return localZip
}

const ZIP_2GIB = 2 * 1024 * 1024 * 1024

function extractZipWithPython(
  zipFile: string,
  extractDir: string,
  onLog?: (line: string) => void
): void {
  const script = resolveExtractZipScript()
  if (!existsSync(script)) {
    throw new Error(`未找到 ZIP 解压脚本: ${script}`)
  }
  const size = statSync(zipFile).size
  if (size > ZIP_2GIB) {
    onLog?.(
      `[刷机] ZIP 约 ${(size / 1024 / 1024 / 1024).toFixed(2)} GiB，使用 Python zipfile 解压`
    )
  }
  const result = spawnSync(tahpPaths.python, [script, zipFile, extractDir], {
    encoding: 'utf8',
    windowsHide: true,
    env: pythonPickerEnv(),
    maxBuffer: 50 * 1024 * 1024,
  })
  if (result.status !== 0) {
    const detail = (result.stderr || result.stdout || '').trim()
    throw new Error(detail || `Python 解压失败，退出码 ${result.status}`)
  }
  onLog?.(`[刷机] ZIP 解压完成: ${extractDir}`)
}

async function extractZipPackage(
  zipPath: string,
  unzipParent: string,
  onLog?: (line: string) => void,
  preferScatter = true
): Promise<string> {
  const cacheDir = resolve(unzipParent)
  mkdirSync(cacheDir, { recursive: true })
  const localZip = await ensureLocalZip(zipPath, cacheDir, onLog)
  const extractDir = join(cacheDir, basename(localZip, '.zip'))

  if (existsSync(extractDir) && readdirSync(extractDir).length > 0) {
    onLog?.(`[刷机] 解压目录已存在，跳过解压: ${extractDir}`)
  } else {
    if (existsSync(extractDir)) rmSync(extractDir, { recursive: true, force: true })
    mkdirSync(extractDir, { recursive: true })
    onLog?.(`[刷机] 开始解压 ZIP 到: ${extractDir}`)
    extractZipWithPython(localZip, extractDir, onLog)
  }

  if (!existsSync(extractDir) || readdirSync(extractDir).length === 0) {
    throw new Error(`ZIP 解压后目录为空或不存在: ${extractDir}`)
  }
  return preferScatter ? findScatterPkgPath(extractDir) : resolve(extractDir)
}

async function prepareRootPkgPath(
  rootPkgPath: string,
  onLog?: (line: string) => void
): Promise<string> {
  if (!rootPkgPath) return ''
  const path = resolve(normalizePath(rootPkgPath))
  if (existsSync(path) && statSync(path).isDirectory()) {
    const prepared = resolve(path)
    onLog?.(`[刷机] Root 包使用目录: ${prepared}`)
    return prepared
  }
  if (isZipFile(rootPkgPath)) {
    const rootCache = join(resolveFlashPackageDir(), 'root', '_downloads')
    mkdirSync(rootCache, { recursive: true })
    const src = path
    if (!existsSync(src)) throw new Error(`Root ZIP 不存在: ${src}`)
    const dst = join(rootCache, basename(src))
    if (existsSync(dst) && statSync(dst).size === statSync(src).size) {
      onLog?.(`[刷机] 使用已缓存的 Root ZIP: ${dst}`)
    } else {
      onLog?.(`[刷机] 缓存 Root ZIP 到本地: ${dst}`)
      await copyFileWithProgress(src, dst, onLog, 'Root 包')
    }
    return resolve(dst)
  }
  if (!existsSync(path)) throw new Error(`Root 包路径不存在: ${rootPkgPath}`)
  const prepared = resolve(path)
  onLog?.(`[刷机] Root 包使用路径: ${prepared}`)
  return prepared
}

export function buildFlashCommand(
  serials: string[],
  pkgPath: string,
  options: {
    rootPkgPath?: string
    stageVersion?: string
    customMarket?: boolean
    skipUnzip?: boolean
  } = {}
): string[] {
  const exe = resolveDeviceUpdateExe()
  if (!existsSync(exe)) {
    throw new Error(`未找到 device_update 可执行文件: ${exe}`)
  }
  const cmd = [exe]
  if (serials.length) cmd.push('-s', ...serials)
  cmd.push('-p', pkgPath)
  if (options.rootPkgPath) cmd.push('-rp', options.rootPkgPath)
  if (options.stageVersion) cmd.push('-stage', options.stageVersion)
  if (options.customMarket) cmd.push('-c')
  if (options.skipUnzip) cmd.push('-su')
  return cmd
}

export async function prepareFlashPkgPath(
  pkgPath: string,
  options: DeviceFlashOptions,
  onLog?: (line: string) => void
): Promise<{ pkgPath: string; skipUnzip: boolean }> {
  let prepared = normalizePath(pkgPath)
  if (!existsSync(prepared) && !isNetworkPath(prepared)) {
    throw new Error(`版本路径不存在: ${prepared}`)
  }

  let skipUnzip = false
  if (isZipFile(prepared)) {
    if (isNetworkPath(prepared)) {
      const cacheDir = resolveFlashPackageDir()
      onLog?.(`[刷机] 版本 ZIP 位于网络路径，将缓存到本地后由 device_update 解压: ${cacheDir}`)
      prepared = await ensureLocalZip(prepared, cacheDir, onLog)
      return { pkgPath: prepared, skipUnzip: false }
    }
    if (options.useCustomUnzipPath && options.unzipPath) {
      prepared = await extractZipPackage(prepared, options.unzipPath, onLog)
      skipUnzip = true
    }
  }
  return { pkgPath: prepared, skipUnzip }
}

export async function runDeviceFlash(
  serials: string[],
  options: DeviceFlashOptions,
  onLog?: (line: string) => void
): Promise<DeviceFlashResult> {
  const logs: string[] = []
  const log = (line: string) => {
    logs.push(line)
    onLog?.(line)
  }

  try {
    const { pkgPath, skipUnzip } = await prepareFlashPkgPath(options.pkgPath, options, log)
    const rootPkgPath = await prepareRootPkgPath(options.rootPkgPath || '', log)
    const cmd = buildFlashCommand(serials, pkgPath, {
      rootPkgPath,
      stageVersion: options.stageVersion,
      customMarket: options.customMarket,
      skipUnzip,
    })
    const workDir = resolveDeviceUpdateDir()
    log(`启动命令: ${cmd.map((p) => (p.includes(' ') ? `"${p}"` : p)).join(' ')}`)
    log(`工作目录: ${workDir}`)
    log('='.repeat(60))

    const returnCode = await new Promise<number>((resolvePromise, reject) => {
      const proc = spawn(cmd[0], cmd.slice(1), {
        cwd: workDir,
        windowsHide: true,
      })
      activeFlashProcess = proc as ChildProcessWithoutNullStreams

      proc.stdout?.on('data', (chunk: Buffer) => {
        const text = decodeSubprocessBytes(chunk)
        for (const line of text.split(/\r?\n/)) {
          if (line) log(line)
        }
      })
      proc.stderr?.on('data', (chunk: Buffer) => {
        const text = decodeSubprocessBytes(chunk)
        for (const line of text.split(/\r?\n/)) {
          if (line) log(line)
        }
      })
      proc.on('error', (err) => {
        activeFlashProcess = null
        reject(err)
      })
      proc.on('close', (code) => {
        activeFlashProcess = null
        resolvePromise(code ?? -1)
      })
    })

    const success = returnCode === 0
    if (success) {
      log('[刷机] 刷机进程正常结束')
    } else {
      log(`[刷机] 刷机进程结束，返回码: ${returnCode}`)
    }
    return { success, returnCode, command: cmd, workDir, logs }
  } catch (err: any) {
    const message = err?.message || String(err)
    log(`[刷机] 异常: ${message}`)
    return {
      success: false,
      returnCode: -1,
      command: [],
      workDir: resolveDeviceUpdateDir(),
      logs,
      error: message,
    }
  }
}

export function stopActiveFlash(): boolean {
  if (!activeFlashProcess) return false
  try {
    activeFlashProcess.kill()
    return true
  } catch {
    return false
  }
}

export async function waitForAdbDevice(
  serial: string,
  timeoutMs = 300_000,
  pollIntervalMs = 5_000
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const online = await listAdbDeviceIds()
    if (online.includes(serial)) return true
    await sleep(pollIntervalMs)
  }
  return false
}

export function listAdbDeviceIds(): Promise<string[]> {
  return new Promise((resolvePromise) => {
    const ids: string[] = []
    const proc = spawn('adb', ['devices'], { windowsHide: true })
    let stdout = ''
    proc.stdout?.on('data', (chunk) => {
      stdout += chunk.toString('utf8')
    })
    proc.on('close', () => {
      for (const line of stdout.split(/\r?\n/)) {
        const parts = line.trim().split(/\s+/)
        if (parts.length >= 2 && parts[1] === 'device') ids.push(parts[0])
      }
      resolvePromise(ids)
    })
    proc.on('error', () => resolvePromise([]))
  })
}
