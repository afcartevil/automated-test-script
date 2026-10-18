import { spawn, spawnSync } from 'child_process'
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'fs'
import { homedir } from 'os'
import { basename, dirname, join, resolve } from 'path'
import { extractProjectCandidates, matchProjectFolder, resolveFlashPackageDir, toCiIdhPath, waitForAdbDevice } from './device-flash'
import { resolvePythonSpawn, tahpPaths } from './paths'

export const CQ_UD_ROOT = '\\\\10.205.4.40\\sw_version\\CI'
export const SH_UD_ROOT = '\\\\10.150.98.24\\sw_ver_sh'

const BRAND_PROPS = ['ro.product.brand', 'ro.build.brand', 'ro.product.manufacturer']
const PROJECT_PROPS = ['ro.product.name', 'ro.build.product', 'ro.product.device', 'ro.product.model']
const UD_ZIP_RE = /_ud\.zip$/i

export interface OtaPretestSettings {
  username: string
  password: string
  swdScriptPath: string
  swdToolDir: string
  oemToolDir: string
}

export interface UdPackageResult {
  deviceId: string
  brand: string
  project: string
  packagePath: string
  source: '重庆' | '上海'
  searchedRoots: string[]
  message: string
}

type DirEntry = { name: string; isDirectory: () => boolean; isFile: () => boolean }

function safeEntries(path: string): DirEntry[] {
  try {
    return readdirSync(path, { withFileTypes: true }) as DirEntry[]
  } catch {
    return []
  }
}

function normalizeBrand(raw: string): string | null {
  const upper = raw.trim().toUpperCase()
  if (upper.includes('TECNO')) return 'TECNO'
  if (upper.includes('INFINIX')) return 'INFINIX'
  if (upper.includes('ITEL')) return 'ITEL'
  if (upper.includes('PHILIPS')) return 'PHILIPS'
  return null
}

/**
 * adb root 成功，或提示已经是 root，视为非 user，不需要刷 UD。
 * 明确无法 root（production builds）视为 user，需要刷 UD。
 */
export function classifyAdbRoot(output: string): 'non-user' | 'user' | 'unknown' {
  const text = output.toLowerCase()
  if (/already running as root|already rooted|已\s*root|已经是?\s*root|已是\s*root/.test(text)) return 'non-user'
  if (/restarting adbd as root/.test(text)) return 'non-user'
  if (/cannot run as root|production builds/.test(text)) return 'user'
  return 'unknown'
}

export function needsUdFlash(rootOutput: string): boolean {
  const kind = classifyAdbRoot(rootOutput)
  if (kind === 'unknown') {
    throw new Error(`无法根据 adb root 输出判断版本：${rootOutput.trim() || '无输出'}`)
  }
  return kind === 'user'
}

/** `od -An -tu1` 输出为 1 表示 usbdebug 已写入。 */
export function parseUsbdebugFlag(odOutput: string): number | null {
  const match = odOutput.trim().match(/\d+/)
  if (!match) return null
  const value = Number(match[0])
  return Number.isInteger(value) ? value : null
}

/** `ro.boot.flash.locked=0` 或 verified boot 为 orange/yellow 视为已解锁。 */
export function isOemUnlocked(lockedProp: string, bootState = ''): boolean {
  const locked = lockedProp.trim()
  if (locked === '0') return true
  if (locked === '1') return false
  const state = bootState.trim().toLowerCase()
  return state === 'orange' || state === 'yellow'
}

export const OTA_MIN_BATTERY_LEVEL = 30
const READ_BATTERY_SHELL = 'dumpsys battery | grep level'

/** `dumpsys battery | grep level` 的输出形如 `level: 42`。 */
export function parseBatteryLevel(output: string): number | null {
  const match = output.match(/level:\s*(\d+)/i)
  if (!match) return null
  const level = Number(match[1])
  return Number.isInteger(level) ? level : null
}

export function assertOtaBatteryLevel(level: number): void {
  if (level < OTA_MIN_BATTERY_LEVEL) {
    throw new Error(`手机电量 ${level}% 低于 30%，无法进行连续 OTA 升级`)
  }
}

export function readBatteryLevel(deviceId: string): number {
  const serial = deviceId.trim()
  if (!serial) throw new Error('设备 ID 为空')
  const result = spawnSync('adb', ['-s', serial, 'shell', READ_BATTERY_SHELL], {
    encoding: 'utf8',
    windowsHide: true,
    timeout: 30_000,
  })
  if (result.error) throw new Error(`读取电量失败：${result.error.message}`)
  if (result.status !== 0) {
    throw new Error(`读取电量失败：${String(result.stderr || result.stdout || '').trim() || `退出码 ${result.status}`}`)
  }
  const level = parseBatteryLevel(String(result.stdout || ''))
  if (level == null) throw new Error('无法从 dumpsys battery 解析电量')
  return level
}

export function assertOtaUpgradeBattery(deviceId: string): number {
  const level = readBatteryLevel(deviceId)
  assertOtaBatteryLevel(level)
  return level
}

const READ_ANDROID_RELEASE_SHELL = 'getprop ro.build.version.release'

export function readAndroidRelease(deviceId: string): string {
  const serial = deviceId.trim()
  if (!serial) throw new Error('设备 ID 为空')
  const result = spawnSync('adb', ['-s', serial, 'shell', READ_ANDROID_RELEASE_SHELL], {
    encoding: 'utf8',
    windowsHide: true,
    timeout: 30_000,
  })
  if (result.error) throw new Error(`读取 Android 版本失败：${result.error.message}`)
  if (result.status !== 0) {
    throw new Error(`读取 Android 版本失败：${String(result.stderr || result.stdout || '').trim() || `退出码 ${result.status}`}`)
  }
  return String(result.stdout || '').trim()
}

/** T卡基线版本校验：手机当前 Android 大版本须等于最低勾选版本的上一档。返回 undefined 表示匹配。 */
export function tcardBaselineVersionError(androidRelease: string, expectFromAndroid: number): string | undefined {
  const current = androidRelease.trim()
  const actual = Number.parseInt(current, 10)
  if (Number.isInteger(actual) && actual === expectFromAndroid) return undefined
  const currentLabel = current ? `Android ${current}` : '未知 Android 版本'
  return `当前手机为 ${currentLabel}，与最低勾选版本要求的基线 Android ${expectFromAndroid} 不匹配，请改用 device_update 刷机或调整勾选版本`
}

export function assertTcardBaselineVersion(deviceId: string, expectFromAndroid: number): void {
  const error = tcardBaselineVersionError(readAndroidRelease(deviceId), expectFromAndroid)
  if (error) throw new Error(error)
}

const READ_USBDEBUG_SHELL = 'dd if=/dev/block/by-name/proinfo bs=1 skip=951 count=1 2>/dev/null | od -An -tu1'
const WRITE_USBDEBUG_SHELL = "printf '\\001' | dd of=/dev/block/by-name/proinfo bs=1 seek=951 count=1 conv=notrunc"

function killAdbChild(child: ReturnType<typeof spawn>): void {
  const pid = child.pid
  if (!pid) return
  if (process.platform === 'win32') {
    spawn('taskkill', ['/PID', String(pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' })
    return
  }
  try { child.kill('SIGKILL') } catch { /* already exited */ }
}

function runAdb(
  args: string[],
  timeoutMs: number,
  onLine?: (line: string) => void,
): Promise<{ status: number | null; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn('adb', args, { windowsHide: true })
    let stdout = ''
    let stderr = ''
    let stdoutRest = ''
    let stderrRest = ''
    let settled = false
    const timer = setTimeout(() => {
      killAdbChild(child)
      if (settled) return
      settled = true
      reject(new Error(`adb ${args.slice(2).join(' ')} 超时（${Math.round(timeoutMs / 1000)} 秒）`))
    }, timeoutMs)
    const takeLines = (rest: string, chunk: string): string => {
      const parts = `${rest}${chunk}`.split(/\r?\n/)
      const tail = parts.pop() ?? ''
      for (const line of parts) {
        if (line.trim()) onLine?.(line)
      }
      return tail
    }
    const finish = (fn: () => void) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      fn()
    }
    child.stdout?.on('data', (buf: Buffer) => {
      const text = buf.toString('utf8')
      stdout += text
      stdoutRest = takeLines(stdoutRest, text)
    })
    child.stderr?.on('data', (buf: Buffer) => {
      const text = buf.toString('utf8')
      stderr += text
      stderrRest = takeLines(stderrRest, text)
    })
    child.on('error', (error) => finish(() => reject(error)))
    child.on('close', (code) => {
      if (stdoutRest.trim()) onLine?.(stdoutRest.trim())
      if (stderrRest.trim()) onLine?.(stderrRest.trim())
      finish(() => resolve({ status: code, stdout, stderr }))
    })
  })
}

export async function probeAdbRoot(deviceId: string, onLine?: (line: string) => void): Promise<string> {
  const result = await runAdb(['-s', deviceId, 'root'], 45_000, onLine)
  return `${result.stdout}\n${result.stderr}`.trim()
}

async function adbProp(deviceId: string, prop: string): Promise<string> {
  const result = await runAdb(['-s', deviceId, 'shell', 'getprop', prop], 15_000)
  return result.stdout.trim()
}

async function adbShell(deviceId: string, command: string): Promise<{ status: number | null; stdout: string; stderr: string }> {
  return runAdb(['-s', deviceId, 'shell', command], 20_000)
}

async function readUsbdebugFlag(deviceId: string): Promise<number | null> {
  const result = await adbShell(deviceId, READ_USBDEBUG_SHELL)
  if (result.status !== 0) {
    throw new Error(`读取 usbdebug 失败：${(result.stderr || result.stdout).trim() || `退出码 ${result.status}`}`)
  }
  return parseUsbdebugFlag(result.stdout)
}

async function writeUsbdebugFlag(deviceId: string): Promise<void> {
  const write = await adbShell(deviceId, WRITE_USBDEBUG_SHELL)
  if (write.status !== 0) {
    throw new Error(`写入 usbdebug 失败：${(write.stderr || write.stdout).trim() || `退出码 ${write.status}`}`)
  }
  const sync = await adbShell(deviceId, 'sync')
  if (sync.status !== 0) {
    throw new Error(`sync 失败：${(sync.stderr || sync.stdout).trim() || `退出码 ${sync.status}`}`)
  }
}

async function waitForSystemBoot(deviceId: string, onLog: (line: string) => void): Promise<void> {
  const deadline = Date.now() + 10 * 60_000
  let lastLog = 0
  onLog('[前置操作] 等待系统启动完成 (sys.boot_completed)...')
  while (Date.now() < deadline) {
    const result = await runAdb(['-s', deviceId, 'shell', 'getprop', 'sys.boot_completed'], 8_000)
    if (result.stdout.trim() === '1') {
      onLog('[前置操作] 系统已启动完成')
      return
    }
    if (Date.now() - lastLog > 15_000) {
      onLog('[前置操作] 系统尚未启动完成，继续等待...')
      lastLog = Date.now()
    }
    await new Promise(resolve => setTimeout(resolve, 3_000))
  }
  throw new Error('等待系统启动完成超时')
}

async function shellIsRoot(deviceId: string): Promise<boolean> {
  const result = await runAdb(['-s', deviceId, 'shell', 'id'], 15_000)
  return /uid=0\(root\)/.test(`${result.stdout}\n${result.stderr}`)
}

/** 先等开机完成再 adb root。重启 adbd 时客户端经常没有文字输出，再用 id 确认是否已经是 root。 */
async function readAdbRootState(deviceId: string, onLog: (line: string) => void): Promise<string> {
  await waitForSystemBoot(deviceId, onLog)
  let output = ''
  for (let attempt = 1; attempt <= 5; attempt++) {
    onLog('[前置操作] 正在执行 adb root...')
    output = await probeAdbRoot(deviceId, (line) => onLog(`[前置操作] ${line}`))
    onLog(`[前置操作] adb root：${output || '无输出'}`)
    if (classifyAdbRoot(output) !== 'unknown') break
    const online = await waitForAdbDevice(deviceId, 60_000)
    if (!online) {
      onLog('[前置操作] adb root 后设备未上线，继续等待')
    } else if (await shellIsRoot(deviceId)) {
      onLog('[前置操作] adb root 无文字输出，但 shell 已是 root')
      output = output.trim() || 'already running as root'
      break
    }
    if (attempt < 5) {
      onLog('[前置操作] adb root 还没有有效结果，5 秒后重试')
      await new Promise(resolve => setTimeout(resolve, 5_000))
      await waitForSystemBoot(deviceId, onLog)
    }
  }
  return output
}

async function ensureAdbRoot(deviceId: string, onLog: (line: string) => void): Promise<void> {
  const output = await readAdbRootState(deviceId, onLog)
  if (needsUdFlash(output)) throw new Error('当前仍无法 adb root，不能检查 OEM 解锁或写入 usbdebug')
  const online = await waitForAdbDevice(deviceId, 60_000)
  if (!online) throw new Error('adb root 后设备未重新上线')
}

function newestFirst(a: DirEntry, b: DirEntry): number {
  if (a.name.toUpperCase() === 'TEST') return -1
  if (b.name.toUpperCase() === 'TEST') return 1
  return b.name.localeCompare(a.name, undefined, { numeric: true })
}

function isUdContainer(name: string): boolean {
  const lower = name.toLowerCase()
  return lower === 'derivativeversions' || lower === 'sts_versions'
}

/**
 * 在项目目录下查找最新的 *_ud.zip。
 * 位置：DerivativeVersions，或 TEST 具体版本目录下的 STS_VERSIONS。
 * 搜索限制深度，避免误扫整个版本盘。
 */
export async function findLatestUdZip(
  projectRoot: string,
  onVisit?: (dir: string) => void,
): Promise<string | null> {
  let bestPath: string | null = null
  let bestMtime = -1

  const visit = async (dir: string, depth: number, underUd: boolean): Promise<void> => {
    if (depth > 8) return
    onVisit?.(dir)
    await new Promise(resolve => setImmediate(resolve))
    const entries = safeEntries(dir).sort(newestFirst)
    for (const entry of entries) {
      const full = join(dir, entry.name)
      if (entry.isFile()) {
        if (!underUd || !UD_ZIP_RE.test(entry.name)) continue
        let mtime = 0
        try { mtime = statSync(full).mtimeMs } catch { /* network stat may fail */ }
        if (mtime > bestMtime || (mtime === bestMtime && (!bestPath || full.localeCompare(bestPath) > 0))) {
          bestPath = full
          bestMtime = mtime
        }
        continue
      }
      if (!entry.isDirectory()) continue
      const nextUnderUd = underUd || isUdContainer(entry.name)
      if (!nextUnderUd && depth >= 4) continue
      await visit(full, depth + 1, nextUnderUd)
    }
  }

  await visit(projectRoot, 0, false)
  return bestPath
}

async function resolveIdentity(deviceId: string, root: string): Promise<{ brand: string; project: string }> {
  if (!existsSync(root)) throw new Error(`无法访问版本目录: ${root}`)
  const brandValues = await Promise.all(BRAND_PROPS.map(prop => adbProp(deviceId, prop)))
  const brandName = brandValues.map(normalizeBrand).find(Boolean)
  const brand = safeEntries(root)
    .filter(entry => entry.isDirectory())
    .map(entry => entry.name)
    .find(name => name.toUpperCase() === brandName?.toUpperCase())
  if (!brand) throw new Error(`无法识别设备品牌（${brandValues.filter(Boolean).join(', ') || 'ADB 无返回'}）`)

  const projectValues = await Promise.all(PROJECT_PROPS.map(prop => adbProp(deviceId, prop)))
  const projects = safeEntries(join(root, brand)).filter(entry => entry.isDirectory()).map(entry => entry.name)
  const project = matchProjectFolder(projects, extractProjectCandidates(...projectValues))
  if (!project) {
    throw new Error(`未找到设备项目（候选: ${projectValues.filter(Boolean).join(', ') || 'ADB 无返回'}）`)
  }
  return { brand, project }
}

export function udProjectSearchOrder(brand: string, project: string): Array<{
  projectRoot: string
  source: '重庆' | '上海'
  viaIdh: boolean
  label: string
}> {
  const cqProject = join(CQ_UD_ROOT, brand, project)
  return [
    {
      projectRoot: cqProject,
      source: '重庆',
      viaIdh: false,
      label: '重庆',
    },
    {
      projectRoot: toCiIdhPath(cqProject),
      source: '重庆',
      viaIdh: true,
      label: '重庆 IDH',
    },
    {
      projectRoot: join(SH_UD_ROOT, brand, project),
      source: '上海',
      viaIdh: false,
      label: '上海',
    },
  ]
}

export async function resolveUdPackage(
  deviceId: string,
  onLog?: (line: string) => void,
): Promise<UdPackageResult> {
  const serial = deviceId.trim()
  if (!serial) throw new Error('设备 ID 为空')

  let identity: { brand: string; project: string }
  try {
    identity = await resolveIdentity(serial, CQ_UD_ROOT)
  } catch (cqError) {
    try {
      identity = await resolveIdentity(serial, SH_UD_ROOT)
    } catch {
      throw cqError
    }
  }

  const searchedRoots: string[] = []
  for (const candidate of udProjectSearchOrder(identity.brand, identity.project)) {
    searchedRoots.push(candidate.projectRoot)
    let lastProgress = Date.now()
    const packagePath = await findLatestUdZip(candidate.projectRoot, (dir) => {
      const now = Date.now()
      if (now - lastProgress < 8_000) return
      lastProgress = now
      onLog?.(`[前置操作] 仍在${candidate.label}版本盘查找 UD 包（${basename(dir)}）`)
    })
    if (packagePath) {
      return {
        deviceId: serial,
        ...identity,
        packagePath,
        source: candidate.source,
        searchedRoots,
        message: candidate.viaIdh
          ? '重庆 CI 未找到 UD 包，已从 CI\\IDH 找到'
          : candidate.source === '重庆'
            ? '已从重庆版本盘找到 UD 包'
            : '重庆 CI 与 CI\\IDH 均未找到 UD 包，已回退到上海版本盘',
      }
    }
  }
  throw new Error(`重庆 CI、CI\\IDH 与上海均未找到 DerivativeVersions 或 STS_VERSIONS 下的 *_ud.zip：${searchedRoots.join('；')}`)
}

function runtimeDir(): string {
  const home = process.env.TAHP_CONSOLE_HOME?.trim() || join(homedir(), '.tahp-console')
  const dir = join(home, 'self-check-runtime', 'ota-pretest')
  mkdirSync(dir, { recursive: true })
  return dir
}

function accountStorePath(): string {
  return join(runtimeDir(), 'account.json')
}

export interface OtaAccountStore {
  username: string
  password: string
  swdToolDir: string
}

export function readOtaAccountStore(): OtaAccountStore | null {
  const path = accountStorePath()
  if (!existsSync(path)) return null
  try {
    const raw = JSON.parse(readFileSync(path, 'utf8')) as Partial<OtaAccountStore>
    return {
      username: String(raw.username || '').trim(),
      password: String(raw.password || ''),
      swdToolDir: String(raw.swdToolDir || '').trim(),
    }
  } catch {
    return null
  }
}

function otaPretestToolRoot(): string {
  const fromProject = join(
    tahpPaths.projectRoot,
    'tahp-console',
    'packages',
    'server',
    'src',
    'services',
    'tahp',
    'self-check',
    'tools',
    'ota-pretest',
  )
  if (existsSync(join(fromProject, 'swd_flash.py'))) return fromProject
  return join(tahpPaths.selfCheckDir, 'tools', 'ota-pretest')
}

export function swdProjectConfigPath(): string {
  return join(otaPretestToolRoot(), 'swd_flash_config.ini')
}

function parseSwdConfig(text: string): OtaAccountStore {
  return {
    username: text.match(/^User=(.*)$/m)?.[1]?.trim() || '',
    password: text.match(/^Password=(.*)$/m)?.[1] ?? '',
    swdToolDir: text.match(/^Dir=(.*)$/m)?.[1]?.trim() || '',
  }
}

export function readProjectSwdConfig(): OtaAccountStore | null {
  const path = swdProjectConfigPath()
  if (!existsSync(path)) return null
  try {
    return parseSwdConfig(readFileSync(path, 'utf8'))
  } catch {
    return null
  }
}

export function writeProjectSwdConfig(settings: Pick<OtaPretestSettings, 'username' | 'password' | 'swdToolDir'>): string {
  const path = swdProjectConfigPath()
  mkdirSync(dirname(path), { recursive: true })
  writeFileSync(path, [
    '[ACCOUNT]',
    `User=${settings.username.trim()}`,
    `Password=${settings.password}`,
    '',
    '[TOOL]',
    `Dir=${settings.swdToolDir.trim()}`,
    '',
  ].join('\r\n'), 'utf8')
  return path
}

export function writeOtaAccountStore(settings: Pick<OtaPretestSettings, 'username' | 'password' | 'swdToolDir'>): void {
  const stored = {
    username: settings.username.trim(),
    password: settings.password,
    swdToolDir: settings.swdToolDir.trim(),
  }
  writeFileSync(accountStorePath(), JSON.stringify(stored, null, 2), 'utf8')
  writeProjectSwdConfig(stored)
  writeOemProjectConfig(stored.username, stored.password)
}

/** 账号、密码、SWD 目录以工程内 swd_flash_config.ini 为准。 */
export function applyStoredOtaAccount(current: OtaPretestSettings): OtaPretestSettings {
  const stored = readProjectSwdConfig() || readOtaAccountStore()
  if (!stored) {
    if (current.username.trim() || current.password || current.swdToolDir.trim()) {
      writeOtaAccountStore(current)
    }
    return current
  }
  if (!readProjectSwdConfig()) writeProjectSwdConfig(stored)
  writeOemProjectConfig(stored.username, stored.password)
  return {
    ...current,
    username: stored.username,
    password: stored.password,
    swdToolDir: stored.swdToolDir,
  }
}

const ANDROID_SCATTER_TXT_RE = /_Android_scatter\.txt$/i

/** UD 包固件描述：优先 flash.xml，否则 *_Android_scatter.txt（如 MT6833_Android_scatter.txt）。 */
export function findUdFirmwareFile(dir: string): string | null {
  const xmlHits: string[] = []
  const scatterHits: string[] = []
  const visit = (current: string, depth: number) => {
    if (depth > 8) return
    for (const entry of safeEntries(current)) {
      const full = join(current, entry.name)
      if (entry.isFile()) {
        if (entry.name.toLowerCase() === 'flash.xml') xmlHits.push(full)
        else if (ANDROID_SCATTER_TXT_RE.test(entry.name)) scatterHits.push(full)
      } else if (entry.isDirectory()) visit(full, depth + 1)
    }
  }
  visit(dir, 0)
  const xml = xmlHits.sort((a, b) => {
    const aPreferred = /[\\/]download_agent[\\/]flash\.xml$/i.test(a) ? 1 : 0
    const bPreferred = /[\\/]download_agent[\\/]flash\.xml$/i.test(b) ? 1 : 0
    return bPreferred - aPreferred || a.length - b.length
  })[0]
  if (xml) return xml
  return scatterHits.sort((a, b) => a.length - b.length || a.localeCompare(b))[0] || null
}

function udPackageDir(): string {
  const dir = join(resolveFlashPackageDir(), '_downloads')
  mkdirSync(dir, { recursive: true })
  return dir
}

async function prepareUdFlashXml(packagePath: string, onLog: (line: string) => void): Promise<string> {
  const normalized = packagePath.trim()
  if (!UD_ZIP_RE.test(normalized)) throw new Error('UD 刷机包必须是 *_ud.zip')
  if (!existsSync(normalized)) throw new Error(`UD 刷机包不存在: ${normalized}`)

  const st = statSync(normalized)
  const key = `${basename(normalized, '.zip')}-${Math.round(st.mtimeMs)}-${st.size}`
    .replace(/[^a-zA-Z0-9._-]/g, '_')
  const dest = join(udPackageDir(), key)
  const existing = existsSync(dest) ? findUdFirmwareFile(dest) : null
  if (existing) {
    onLog(`[UD刷机] 使用已解压固件: ${existing}`)
    return existing
  }

  mkdirSync(dest, { recursive: true })
  const python = resolvePythonSpawn()
  const extractScript = join(__dirname, 'self-check', 'python', 'extract_flash_zip.py')
  onLog(`[UD刷机] 正在解压 ${basename(normalized)}...`)
  await new Promise(resolve => setImmediate(resolve))
  try {
    await streamProcess(
      python.command,
      [...python.prefixArgs, '-u', extractScript, normalized, dest],
      {
        env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
        timeoutMs: 30 * 60_000,
        timeoutMessage: 'UD 包解压超时',
      },
      line => onLog(`[UD刷机] ${line}`),
    )
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    throw new Error(message || 'UD 包解压失败')
  }
  const firmware = findUdFirmwareFile(dest)
  if (!firmware) throw new Error(`UD 包中未找到 flash.xml 或 *_Android_scatter.txt: ${normalized}`)
  onLog(`[UD刷机] 已定位固件: ${firmware}`)
  return firmware
}

function resolveSwdToolDir(configured: string): string {
  const candidates = [
    configured,
    process.env.TAHP_SWD_TOOL_DIR || '',
    'E:\\Softwaredownload',
    'D:\\rd_tool\\swd\\Softwaredownload_V9.2026.09.01_for_Development_Center',
  ]
  for (const dir of candidates) {
    const trimmed = dir.trim()
    if (trimmed && existsSync(join(trimmed, 'SWD_Development_Center.exe'))) return trimmed
  }
  return configured.trim()
}

function readDesktopSwdAccount(): { username: string; password: string; toolDir: string } | null {
  const ini = join(homedir(), 'Desktop', 'swd_flash_使用说明', 'swd_flash_config.ini')
  if (!existsSync(ini)) return null
  const text = readFileSync(ini, 'utf8')
  return {
    username: text.match(/^User=(.*)$/m)?.[1]?.trim() || '',
    password: text.match(/^Password=(.*)$/m)?.[1] ?? '',
    toolDir: text.match(/^Dir=(.*)$/m)?.[1]?.trim() || '',
  }
}

function effectiveOtaSettings(settings: OtaPretestSettings): OtaPretestSettings {
  const project = readProjectSwdConfig()
  const desktop = readDesktopSwdAccount()
  const username = settings.username.trim() || project?.username || desktop?.username || ''
  const password = settings.password || project?.password || desktop?.password || ''
  const toolDir = settings.swdToolDir.trim() || project?.swdToolDir || desktop?.toolDir || ''
  return {
    ...settings,
    username,
    password,
    swdToolDir: resolveSwdToolDir(toolDir),
  }
}

function writeSwdConfig(settings: OtaPretestSettings): string {
  const resolved = effectiveOtaSettings(settings)
  if (!resolved.username.trim() || !resolved.password) throw new Error('请先配置账号和密码')
  if (!resolved.swdToolDir.trim()) throw new Error('未找到 SWD 刷机工具，请安装 SWD_Development_Center')
  settings.username = resolved.username
  settings.password = resolved.password
  settings.swdToolDir = resolved.swdToolDir
  return writeProjectSwdConfig(resolved)
}

function streamProcess(
  command: string,
  args: string[],
  options: { cwd?: string; env?: NodeJS.ProcessEnv; timeoutMs: number; timeoutMessage?: string },
  onLog: (line: string) => void,
): Promise<string> {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: options.env,
      windowsHide: true,
    })
    let stderr = ''
    let output = ''
    const timer = setTimeout(() => {
      child.kill('SIGKILL')
      reject(new Error(options.timeoutMessage || '前置操作执行超时'))
    }, options.timeoutMs)
    const consume = (prefix: string, chunk: Buffer) => {
      const text = decodeConsoleText(chunk)
      output += text
      if (prefix) stderr += text
      for (const line of text.split(/\r?\n/)) {
        if (line.trim()) onLog(line)
      }
    }
    child.stdout?.on('data', chunk => consume('', chunk))
    child.stderr?.on('data', chunk => consume('stderr', chunk))
    child.on('error', (error) => {
      clearTimeout(timer)
      reject(error)
    })
    child.on('close', (code) => {
      clearTimeout(timer)
      if (code === 0) resolvePromise(output)
      else reject(new Error(stderr.trim() || `前置操作失败，退出码 ${code ?? -1}`))
    })
  })
}

function decodeConsoleText(chunk: Buffer): string {
  const utf8 = chunk.toString('utf8')
  if (!utf8.includes('\uFFFD')) return utf8
  try {
    return new TextDecoder('gbk').decode(chunk)
  } catch {
    return utf8
  }
}

function readLogSince(logPath: string, offset: number): { text: string; end: number } {
  if (!existsSync(logPath)) return { text: '', end: offset }
  const buffer = readFileSync(logPath)
  const end = buffer.length
  const text = end <= offset ? '' : buffer.subarray(offset).toString('utf8')
  return { text, end }
}

function swdFlashFinished(text: string): 'pass' | 'fail' | null {
  if (/刷机完成:\s*FAIL|!!!\s*异常/i.test(text)) return 'fail'
  if (/刷机完成:\s*PASS/i.test(text)) return 'pass'
  return null
}

function swdExceptionSummary(text: string): string {
  const line = text.split(/\r?\n/).map(item => item.trim()).find(item => /!!!\s*异常/.test(item))
  if (!line) return '请查看刷机日志'
  return line.replace(/^.*!!!\s*异常:\s*/, '').trim() || '请查看刷机日志'
}

async function pythonImports(python: string, statement: string): Promise<boolean> {
  return new Promise((resolve) => {
    const child = spawn(python, ['-c', statement], { windowsHide: true })
    const timer = setTimeout(() => {
      killAdbChild(child)
      resolve(false)
    }, 20_000)
    child.on('error', () => {
      clearTimeout(timer)
      resolve(false)
    })
    child.on('close', (code) => {
      clearTimeout(timer)
      resolve(code === 0)
    })
  })
}

/** 与 swd_flash.bat 一样使用带 pywinauto/psutil 的 venv。UAC 提权会原样重启 sys.executable，系统 Python 没有这些包。 */
async function ensureSwdPython(onLog: (line: string) => void): Promise<string> {
  const venvDir = join(runtimeDir(), 'venv_swd')
  const venvPython = join(venvDir, 'Scripts', 'python.exe')
  if (existsSync(venvPython) && await pythonImports(venvPython, 'import pywinauto, psutil')) {
    return venvPython
  }
  if (existsSync(venvDir)) rmSync(venvDir, { recursive: true, force: true })
  onLog('[UD刷机] 正在准备刷机 Python 环境（pywinauto、psutil），首次会稍久...')
  const base = resolvePythonSpawn()
  await streamProcess(
    base.command,
    [...base.prefixArgs, '-m', 'venv', venvDir],
    { timeoutMs: 3 * 60_000 },
    line => onLog(`[UD刷机] ${line}`),
  )
  if (!existsSync(venvPython)) throw new Error('创建刷机 Python 环境失败')
  await streamProcess(
    venvPython,
    ['-m', 'pip', 'install', '--disable-pip-version-check', 'pywinauto', 'psutil'],
    { timeoutMs: 5 * 60_000 },
    line => onLog(`[UD刷机] ${line}`),
  )
  if (!await pythonImports(venvPython, 'import pywinauto, psutil')) {
    throw new Error('刷机 Python 环境仍无法导入 pywinauto、psutil')
  }
  return venvPython
}

async function waitForElevatedSwd(
  logPath: string,
  initialSize: number,
  onLog: (line: string) => void,
): Promise<void> {
  const deadline = Date.now() + 40 * 60_000
  let offset = initialSize
  while (Date.now() < deadline) {
    if (existsSync(logPath)) {
      const buffer = readFileSync(logPath)
      if (buffer.length > offset) {
        const text = buffer.subarray(offset).toString('utf8')
        offset = buffer.length
        for (const line of text.split(/\r?\n/)) {
          if (line.trim()) onLog(`[UD刷机] ${line}`)
        }
        const outcome = swdFlashFinished(text)
        if (outcome === 'pass') return
        if (outcome === 'fail') throw new Error(`SWD 刷机失败：${swdExceptionSummary(text)}`)
      }
    }
    await new Promise(resolvePromise => setTimeout(resolvePromise, 2_000))
  }
  throw new Error('等待管理员权限下的 SWD 刷机完成超时')
}

export async function runUdFlash(
  deviceId: string,
  packagePath: string,
  settings: OtaPretestSettings,
  onLog: (line: string) => void,
): Promise<void> {
  const script = resolve(settings.swdScriptPath.trim())
  if (!existsSync(script)) throw new Error(`未找到 swd_flash.py: ${script}`)
  const flashXml = await prepareUdFlashXml(packagePath, onLog)
  const config = writeSwdConfig(settings)
  const pythonExe = await ensureSwdPython(onLog)
  const swdLogPath = join(dirname(script), 'swd_flash_log.txt')
  const initialLogSize = existsSync(swdLogPath) ? statSync(swdLogPath).size : 0
  onLog(`[UD刷机] 开始刷写设备 ${deviceId}`)
  const output = await streamProcess(
    pythonExe,
    [script, flashXml, '--config', config, '--flash-timeout', '1800'],
    {
      cwd: dirname(script),
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
      timeoutMs: 40 * 60_000,
    },
    line => onLog(`[UD刷机] ${line}`),
  )
  const logDelta = readLogSince(swdLogPath, initialLogSize)
  const combined = `${output}\n${logDelta.text}`
  const finished = swdFlashFinished(combined)
  if (finished === 'fail') throw new Error(`SWD 刷机失败：${swdExceptionSummary(combined)}`)
  if (finished === 'pass') {
    onLog('[UD刷机] 刷机完成')
    return
  }
  if (/UAC|提权/i.test(combined)) {
    onLog('[UD刷机] 已请求管理员权限。请在 UAC 窗口点“是”，等待提权后的刷机进程完成...')
    await waitForElevatedSwd(swdLogPath, logDelta.end, onLog)
    onLog('[UD刷机] 刷机完成')
    return
  }
  throw new Error('SWD 刷机进程已退出，但没有刷完。若弹出了 UAC 窗口，请点“是”后重试')
}

export interface OtaStartPreview {
  level: number
  allowed: boolean
  message: string
  steps: string[]
  /** 手机当前 Android 大版本（ro.build.version.release），读取失败为空串 */
  androidRelease?: string
}

export async function previewOtaStart(deviceId: string): Promise<OtaStartPreview> {
  const serial = deviceId.trim()
  if (!serial) throw new Error('设备 ID 为空')
  let androidRelease = ''
  try {
    androidRelease = readAndroidRelease(serial)
  } catch { /* 版本号仅作 T卡基线预校验，读取失败不阻塞预览 */ }
  const level = readBatteryLevel(serial)
  if (level < OTA_MIN_BATTERY_LEVEL) {
    return {
      level,
      allowed: false,
      message: `手机电量 ${level}% 低于 30%，无法进行连续 OTA 升级`,
      steps: [],
      androidRelease,
    }
  }
  return {
    level,
    allowed: true,
    message: `当前电量 ${level}%`,
    steps: [
      '检查 adb root：user 版本刷 UD，已 root 则跳过',
      '检查 OEM 解锁，未完成则解锁',
      '检查 usbdebug，不是 1 则写入',
    ],
    androidRelease,
  }
}

function bundledOemRoot(): string {
  const fromProject = join(
    tahpPaths.projectRoot,
    'tahp-console',
    'packages',
    'server',
    'src',
    'services',
    'tahp',
    'self-check',
    'tools',
    'ota-pretest',
    'oem-unlock-windows',
  )
  if (existsSync(join(fromProject, 'config.json'))) return fromProject
  return join(tahpPaths.selfCheckDir, 'tools', 'ota-pretest', 'oem-unlock-windows')
}

function writeOemProjectConfig(username: string, password: string): void {
  if (!username.trim() || !password) return
  const root = bundledOemRoot()
  const configPath = join(root, 'config.json')
  let config: Record<string, unknown> = {}
  if (existsSync(configPath)) {
    try { config = JSON.parse(readFileSync(configPath, 'utf8')) } catch { /* keep defaults */ }
  }
  const body = JSON.stringify({
    url1: 'https://pfgateway.transsion.com:9199/',
    url2: 'https://office-anticrack.transsion-os.com',
    ...config,
    username: username.trim(),
    password,
  }, null, 2)
  mkdirSync(root, { recursive: true })
  writeFileSync(configPath, body, 'utf8')
  const scriptConfig = join(root, 'scripts', 'config.json')
  mkdirSync(dirname(scriptConfig), { recursive: true })
  writeFileSync(scriptConfig, body, 'utf8')
}

function prepareOemConfig(settings: OtaPretestSettings): { script: string; root: string } {
  const stored = readProjectSwdConfig() || readOtaAccountStore()
  const resolved = effectiveOtaSettings({
    ...settings,
    username: settings.username.trim() || stored?.username || '',
    password: settings.password || stored?.password || '',
    swdToolDir: settings.swdToolDir.trim() || stored?.swdToolDir || '',
  })
  settings.username = resolved.username
  settings.password = resolved.password
  const root = bundledOemRoot()
  const script = join(root, 'scripts', 'oem_unlock.pyz')
  if (!existsSync(script)) throw new Error(`未找到 OEM 解锁脚本: ${script}`)
  if (!settings.username.trim() || !settings.password) throw new Error('请先配置账号和密码')
  writeOemProjectConfig(settings.username, settings.password)
  return { script, root }
}

export async function runCombinedPretest(
  deviceId: string,
  packagePath: string | undefined,
  settings: OtaPretestSettings,
  onLog: (line: string) => void,
  options?: { pretestOnly?: boolean },
): Promise<{
  rootOutput: string
  flashedUd: boolean
  udPackagePath?: string
  oemUnlockRan: boolean
  usbdebugWritten: boolean
}> {
  if (options?.pretestOnly) {
    onLog('[前置操作] 仅执行前置操作，不进行连续 OTA 升级')
  }
  const rootOutput = await readAdbRootState(deviceId, onLog)
  const flashUd = needsUdFlash(rootOutput)
  let flashedUd = false
  let usedPath = packagePath?.trim() || ''
  if (flashUd) {
    onLog('[前置操作] adb root 未成功，按 user 版本先刷 UD')
    if (!usedPath) {
      onLog('[前置操作] 正在寻找UD版本刷机包')
      const resolved = await resolveUdPackage(deviceId, onLog)
      usedPath = resolved.packagePath
      onLog(`[前置操作] ${resolved.message}：${usedPath}`)
    }
    await runUdFlash(deviceId, usedPath, settings, onLog)
    flashedUd = true
    onLog('[前置操作] 等待 UD 刷机后的设备重新上线')
    const online = await waitForAdbDevice(deviceId)
    if (!online) throw new Error('UD 刷机后设备未重新上线')
    await ensureAdbRoot(deviceId, onLog)
  } else {
    onLog('[前置操作] adb root 成功，按 UD 或 user root 跳过刷机')
    const online = await waitForAdbDevice(deviceId, 60_000)
    if (!online) throw new Error('adb root 后设备未重新上线')
  }

  const oemUnlocked = isOemUnlocked(
    await adbProp(deviceId, 'ro.boot.flash.locked'),
    await adbProp(deviceId, 'ro.boot.verified_bootstate'),
  )
  const usbdebug = await readUsbdebugFlag(deviceId)
  onLog(`[前置操作] OEM 解锁${oemUnlocked ? '已完成' : '未完成'}，usbdebug=${usbdebug ?? '无法解析'}`)

  let oemUnlockRan = false
  if (!oemUnlocked) {
    await runOemUnlockWithRetry({
      runUnlock: () => runOemUnlock(deviceId, settings, onLog),
      isUnlocked: async () => isOemUnlocked(
        await adbProp(deviceId, 'ro.boot.flash.locked'),
        await adbProp(deviceId, 'ro.boot.verified_bootstate'),
      ),
      onLog,
    })
    oemUnlockRan = true
    onLog('[前置操作] 等待 OEM 解锁后的设备重新上线')
    const online = await waitForAdbDevice(deviceId)
    if (!online) throw new Error('OEM 解锁后设备未重新上线，无法写入 usbdebug')
    await ensureAdbRoot(deviceId, onLog)
  } else {
    onLog('[前置操作] OEM 已解锁，跳过解锁')
  }

  let usbdebugWritten = false
  const usbdebugNow = oemUnlockRan ? await readUsbdebugFlag(deviceId) : usbdebug
  if (usbdebugNow === 1) {
    onLog('[前置操作] usbdebug 已是 1，跳过写入')
  } else {
    onLog('[前置操作] 写入 usbdebug=1')
    await writeUsbdebugFlag(deviceId)
    usbdebugWritten = true
  }
  return { rootOutput, flashedUd, udPackagePath: usedPath || undefined, oemUnlockRan, usbdebugWritten }
}

export async function runOemUnlock(
  deviceId: string,
  settings: OtaPretestSettings,
  onLog: (line: string) => void,
): Promise<void> {
  const { script, root } = prepareOemConfig(settings)
  const python = resolvePythonSpawn()
  onLog(`[OEM解锁] 开始处理设备 ${deviceId}`)
  await streamProcess(
    python.command,
    [...python.prefixArgs, script],
    {
      cwd: root,
      env: { ...process.env, ANDROID_SERIAL: deviceId },
      timeoutMs: 5 * 60_000,
    },
    line => onLog(`[OEM解锁] ${line}`),
  )
  onLog('[OEM解锁] 操作完成')
}

// ─── OEM 解锁自动重试 ────────────────────────────────────────────────────
// 云端授权（office-anticrack unlock-auth）偶发返回 code:-1 空原因失败，有限次重试吸收抖动。

export const OEM_UNLOCK_MAX_ATTEMPTS = Math.max(1, Number(process.env.TAHP_OEM_UNLOCK_ATTEMPTS) || 3)
export const OEM_UNLOCK_RETRY_DELAY_MS = Math.max(0, Number(process.env.TAHP_OEM_UNLOCK_RETRY_DELAY_MS) || 30_000)

export interface OemUnlockRetryDeps {
  runUnlock: () => Promise<void>
  /** 复查设备当前是否已解锁（服务器可能实际已解锁但响应解析失败，避免重复解锁） */
  isUnlocked: () => Promise<boolean>
  onLog: (line: string) => void
  maxAttempts?: number
  retryDelayMs?: number
  sleep?: (ms: number) => Promise<void>
}

export async function runOemUnlockWithRetry(deps: OemUnlockRetryDeps): Promise<void> {
  const maxAttempts = Math.max(1, deps.maxAttempts ?? OEM_UNLOCK_MAX_ATTEMPTS)
  const retryDelayMs = Math.max(0, deps.retryDelayMs ?? OEM_UNLOCK_RETRY_DELAY_MS)
  const sleep = deps.sleep ?? ((ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms)))
  let lastError: unknown
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    if (attempt > 1) {
      deps.onLog(`[OEM解锁] ${Math.round(retryDelayMs / 1000)} 秒后进行第 ${attempt}/${maxAttempts} 次尝试（云端授权偶发失败自动重试）`)
      await sleep(retryDelayMs)
      if (await deps.isUnlocked()) {
        deps.onLog('[OEM解锁] 复查设备已解锁，跳过重试')
        return
      }
    }
    try {
      await deps.runUnlock()
      return
    } catch (err) {
      lastError = err
      deps.onLog(`[OEM解锁] 第 ${attempt}/${maxAttempts} 次尝试失败：${(err as Error)?.message || err}`)
    }
  }
  throw lastError instanceof Error ? lastError : new Error(String(lastError))
}
