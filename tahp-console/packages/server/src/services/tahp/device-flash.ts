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
import { basename, dirname, join, resolve } from 'path'
import { pipeline } from 'stream/promises'
import { Transform } from 'stream'
import * as XLSX from 'xlsx'
import { tahpPaths } from './paths'

export interface PickFlashPathResult {
  canceled: boolean
  path?: string
  error?: string
}

export interface DailySystemVersionOption {
  label: string
  value: string
  branchFolder: string
}

export interface DailyFlashOptions {
  deviceId: string
  brand: string
  project: string
  devRoot: string
  devProjectPath: string
  systemVersions: DailySystemVersionOption[]
}

export interface LatestDailyFlashRequest {
  deviceId: string
  /** 省略时自动选择项目 DEV 下最新的 tOS 分支（如 tOS17.0 > tOS16.3 > tOS16.2） */
  systemVersion?: string
}

export interface LatestDailyFlashResult {
  deviceId: string
  brand: string
  project: string
  systemVersion: string
  branchFolder: string
  devRoot: string
  devProjectPath: string
  branchPath: string
  versionPath: string
  versionName: string
  releaseNotePath: string
  archivePathCq: string
  resolvedArchivePath: string
  openPath: string
  packagePath: string
  usedIdhFallback: boolean
}

const EXTRACT_ZIP_SCRIPT = join(__dirname, 'self-check', 'python', 'extract_flash_zip.py')
const DAILY_VERSION_ROOT = '\\\\10.150.98.24\\sw_ver_sh'
const RELEASE_NOTE_FILE = 'ReleaseNote.xlsx'
const DEFAULT_DEV_PROJECT_KEYWORD = 'Android_16'
const RELEASE_BRANCH_SUFFIX = '_mtk_sys_release'
const BRAND_PROPS = ['ro.product.brand', 'ro.build.brand', 'ro.product.manufacturer']
const PROJECT_PROPS = [
  'ro.product.name',
  'ro.build.product',
  'ro.product.device',
  'ro.product.model',
]

function resolveExtractZipScript(): string {
  if (existsSync(EXTRACT_ZIP_SCRIPT)) return resolve(EXTRACT_ZIP_SCRIPT)
  return join(tahpPaths.selfCheckDir, 'python', 'extract_flash_zip.py')
}

function commandAvailable(cmd: string): boolean {
  const probe = spawnSync(process.platform === 'win32' ? 'where' : 'which', [cmd], {
    encoding: 'utf8',
    windowsHide: true,
  })
  return probe.status === 0
}

function pathPickerError(): string | null {
  if (process.platform === 'linux') {
    if (!process.env.DISPLAY && !process.env.WAYLAND_DISPLAY) {
      return '无图形界面，请手动输入路径'
    }
    if (!commandAvailable('zenity') && !commandAvailable('kdialog')) {
      return '请安装 zenity 或 kdialog（sudo apt install zenity），或手动输入路径'
    }
  }
  if (process.platform === 'win32' && !commandAvailable('powershell.exe')) {
    return '未找到 PowerShell，请手动输入路径'
  }
  return null
}

const WINDOWS_PICKER_SCRIPT = `
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class TahpFg {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
  public static void ForceForeground(IntPtr hWnd) {
    // 模拟一次 ALT 抬起，解除 Windows 前台锁定，再抢前台
    keybd_event(0x12, 0, 0, UIntPtr.Zero);
    keybd_event(0x12, 0, 0x0002, UIntPtr.Zero);
    ShowWindow(hWnd, 5);
    BringWindowToTop(hWnd);
    SetForegroundWindow(hWnd);
  }
}
"@
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.FormBorderStyle = 'None'
$owner.Size = New-Object System.Drawing.Size(1, 1)
$owner.StartPosition = 'Manual'
$owner.Location = New-Object System.Drawing.Point(-2000, -2000)
$owner.Add_Shown({ [TahpFg]::ForceForeground($owner.Handle) })
$owner.Show()
$owner.Activate()
[TahpFg]::ForceForeground($owner.Handle)
$dlg = New-Object System.Windows.Forms.OpenFileDialog
$dlg.Title = '选择版本包（zip / scatter xml）'
$dlg.Filter = '刷机包 (*.zip;*.xml)|*.zip;*.xml|ZIP (*.zip)|*.zip|Scatter XML (*.xml)|*.xml|所有文件 (*.*)|*.*'
$dlg.FilterIndex = 1
$result = $dlg.ShowDialog($owner)
if ($result -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $dlg.FileName }
$owner.Dispose()
`

function pickFlashPathWindows(): PickFlashPathResult {
  // 用 -EncodedCommand（base64/UTF-16LE）避免内嵌 C#/中文/引号被命令行转义破坏
  const encoded = Buffer.from(WINDOWS_PICKER_SCRIPT, 'utf16le').toString('base64')
  const proc = spawnSync(
    'powershell.exe',
    ['-NoProfile', '-STA', '-EncodedCommand', encoded],
    { encoding: 'utf8', windowsHide: false }
  )
  const path = (proc.stdout || '').trim()
  if (path) return { canceled: false, path }
  return { canceled: true }
}

function pickFlashPathDarwin(): PickFlashPathResult {
  const proc = spawnSync(
    'osascript',
    [
      '-e',
      'tell application "System Events" to activate',
      '-e',
      'POSIX path of (choose file with prompt "选择版本包（zip / scatter xml）")',
    ],
    { encoding: 'utf8', windowsHide: false }
  )
  const path = (proc.stdout || '').trim()
  if (proc.status === 0 && path) return { canceled: false, path }
  return { canceled: true }
}

function pickFlashPathLinux(): PickFlashPathResult {
  if (commandAvailable('zenity')) {
    const proc = spawnSync(
      'zenity',
      [
        '--file-selection',
        '--modal',
        '--title=选择版本包（zip / scatter xml）',
        '--file-filter=刷机包 | *.zip *.xml',
        '--file-filter=所有文件 | *',
      ],
      { encoding: 'utf8', windowsHide: false }
    )
    const path = (proc.stdout || '').trim()
    if (proc.status === 0 && path) return { canceled: false, path }
    return { canceled: true }
  }
  const proc = spawnSync(
    'kdialog',
    ['--getopenfilename', '', '刷机包 (*.zip *.xml)|*.zip *.xml', '选择版本包（zip / scatter xml）'],
    { encoding: 'utf8', windowsHide: false }
  )
  const path = (proc.stdout || '').trim()
  if (proc.status === 0 && path) return { canceled: false, path }
  return { canceled: true }
}

/** 本机系统文件选择框（Windows PowerShell / macOS osascript / Linux zenity）。 */
export async function pickLocalFlashPath(): Promise<PickFlashPathResult> {
  const unavailable = pathPickerError()
  if (unavailable) return { canceled: true, error: unavailable }

  try {
    if (process.platform === 'win32') return pickFlashPathWindows()
    if (process.platform === 'darwin') return pickFlashPathDarwin()
    if (process.platform === 'linux') return pickFlashPathLinux()
    return { canceled: true, error: '当前平台不支持文件选择，请手动输入路径' }
  } catch (err: any) {
    return { canceled: true, error: err?.message || '路径选择失败' }
  }
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
  /** 勾选后从 pkgPath 同目录自动查找 user_root 小包 */
  enableRootPkg?: boolean
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

function safeDirEntries(dir: string): { name: string; isDirectory: () => boolean; isFile: () => boolean }[] {
  try {
    return readdirSync(dir, { withFileTypes: true }) as any
  } catch {
    return []
  }
}

function newestByNameTimestamp(baseDir: string, entries: string[]): string | null {
  const candidates = entries.map((name) => {
    const full = join(baseDir, name)
    const timestamp = name.match(/^(\d{4})\.(\d{2})\.(\d{2})\.(\d{2})\.(\d{2})\.(\d{2})_(\d+)/)
    const timeKey = timestamp ? timestamp.slice(1).join('') : ''
    let mtime = 0
    try {
      mtime = statSync(full).mtimeMs
    } catch {
      // keep lexical timestamp ordering even if stat fails on a network share
    }
    return { name, timeKey, mtime }
  })
  candidates.sort((a, b) => {
    if (a.timeKey || b.timeKey) return b.timeKey.localeCompare(a.timeKey)
    if (a.mtime !== b.mtime) return b.mtime - a.mtime
    return b.name.localeCompare(a.name)
  })
  return candidates[0]?.name || null
}

function getAdbProp(deviceId: string, prop: string): Promise<string> {
  return new Promise((resolvePromise) => {
    const proc = spawn('adb', ['-s', deviceId, 'shell', 'getprop', prop], { windowsHide: true })
    let stdout = ''
    proc.stdout?.on('data', (chunk: Buffer) => {
      stdout += chunk.toString('utf8')
    })
    proc.on('close', () => resolvePromise(stdout.trim()))
    proc.on('error', () => resolvePromise(''))
  })
}

export function buildReleaseBranchFolder(systemVersion: string): string {
  const trimmed = systemVersion.trim()
  const match =
    trimmed.match(/^tOS(\d+)\.(\d+)$/i) ||
    trimmed.match(/^(\d+)\.(\d+)$/)
  if (!match) {
    throw new Error(`无效系统版本: ${systemVersion}`)
  }
  return `tOS${match[1]}.${match[2]}.0${RELEASE_BRANCH_SUFFIX}`
}

export function normalizeSystemVersionLabel(branchFolder: string): string | null {
  const match = branchFolder.match(/^tOS(\d+)\.(\d+)\.0_mtk_sys_release$/i)
  if (!match) return null
  return `tOS${match[1]}.${match[2]}`
}

function compareSystemVersionLabels(a: string, b: string): number {
  const parse = (label: string) => {
    const match = label.match(/^tOS(\d+)\.(\d+)$/i)
    return match ? [Number(match[1]), Number(match[2])] : [0, 0]
  }
  const [aMajor, aMinor] = parse(a)
  const [bMajor, bMinor] = parse(b)
  if (aMajor !== bMajor) return bMajor - aMajor
  return bMinor - aMinor
}

function normalizeBrandName(raw: string): string | null {
  const upper = raw.trim().toUpperCase()
  if (!upper) return null
  if (upper.includes('TECNO')) return 'TECNO'
  if (upper.includes('INFINIX')) return 'INFINIX'
  if (upper.includes('ITEL')) return 'itel'
  return null
}

function extractProjectCandidates(...values: string[]): string[] {
  const candidates = new Set<string>()
  for (const raw of values) {
    const value = raw.trim()
    if (!value) continue
    const head = value.split(/[-_[\s(]/)[0]?.trim()
    if (head && /^[A-Za-z]+\d+/.test(head)) {
      candidates.add(head.toUpperCase())
    }
    const inline = value.match(/([A-Za-z]+\d+)/g)
    inline?.forEach((part) => candidates.add(part.toUpperCase()))
  }
  return [...candidates]
}

function resolveBrandFromProps(props: string[]): string {
  const shareBrands = safeDirEntries(DAILY_VERSION_ROOT)
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)

  for (const raw of props) {
    const brand = normalizeBrandName(raw)
    if (brand && shareBrands.includes(brand)) return brand
  }

  if (shareBrands.includes('TECNO')) return 'TECNO'
  throw new Error(`无法识别品牌，请确认设备已连接且可访问 ${DAILY_VERSION_ROOT}`)
}

function resolveProjectOnShare(brand: string, candidates: string[]): string {
  const brandRoot = join(DAILY_VERSION_ROOT, brand)
  if (!existsSync(brandRoot)) {
    throw new Error(`品牌路径不存在: ${brandRoot}`)
  }

  const projects = safeDirEntries(brandRoot)
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)

  for (const candidate of candidates) {
    const exact = projects.find((name) => name.toUpperCase() === candidate.toUpperCase())
    if (exact) return exact
  }

  for (const candidate of candidates) {
    const prefix = projects.find((name) => name.toUpperCase().startsWith(candidate.toUpperCase()))
    if (prefix) return prefix
  }

  throw new Error(`无法识别项目代号（候选: ${candidates.join(', ') || '无'}）`)
}

export async function resolveFlashDeviceIdentity(deviceId: string): Promise<{
  deviceId: string
  brand: string
  project: string
  devRoot: string
  devProjectPath: string
}> {
  const serial = deviceId.trim()
  if (!serial) throw new Error('设备 ID 为空')

  const [brandProps, projectProps] = await Promise.all([
    Promise.all(BRAND_PROPS.map((prop) => getAdbProp(serial, prop))),
    Promise.all(PROJECT_PROPS.map((prop) => getAdbProp(serial, prop))),
  ])

  const brand = resolveBrandFromProps(brandProps)
  const project = resolveProjectOnShare(brand, extractProjectCandidates(...projectProps))
  const devRoot = join(DAILY_VERSION_ROOT, brand, project, 'DEV')
  if (!existsSync(devRoot)) throw new Error(`DEV 路径不存在: ${devRoot}`)

  const devProjectPath = findDevProjectPath(devRoot, DEFAULT_DEV_PROJECT_KEYWORD)
  return { deviceId: serial, brand, project, devRoot, devProjectPath }
}

export function listSystemVersions(devProjectPath: string): DailySystemVersionOption[] {
  const options = safeDirEntries(devProjectPath)
    .filter(
      (entry) =>
        entry.isDirectory() &&
        /^tOS\d+\.\d+\.0_mtk_sys_release$/i.test(entry.name),
    )
    .map((entry) => entry.name)
    .map((branchFolder) => {
      const label = normalizeSystemVersionLabel(branchFolder) || branchFolder
      return { label, value: label, branchFolder }
    })
    .sort((a, b) => compareSystemVersionLabels(a.label, b.label))

  return options
}

export async function getDailyFlashOptions(deviceId: string): Promise<DailyFlashOptions> {
  const identity = await resolveFlashDeviceIdentity(deviceId)
  const systemVersions = listSystemVersions(identity.devProjectPath)
  if (!systemVersions.length) {
    throw new Error(`项目 DEV 目录下未找到 tOS 系统版本分支: ${identity.devProjectPath}`)
  }
  return {
    deviceId: identity.deviceId,
    brand: identity.brand,
    project: identity.project,
    devRoot: identity.devRoot,
    devProjectPath: identity.devProjectPath,
    systemVersions,
  }
}

function findDevProjectPath(devRoot: string, devProjectKeyword: string): string {
  const keyword = devProjectKeyword.trim() || DEFAULT_DEV_PROJECT_KEYWORD
  const devProjects = safeDirEntries(devRoot)
    .filter((entry) => entry.isDirectory() && entry.name.includes(keyword))
    .map((entry) => entry.name)
  if (!devProjects.length) {
    throw new Error(`未在 DEV 下找到包含「${keyword}」的项目 DEV 目录: ${devRoot}`)
  }
  const latest = newestByNameTimestamp(devRoot, devProjects) || devProjects.sort().at(-1)!
  return join(devRoot, latest)
}

function findReleaseBranchBySystemVersion(devProjectPath: string, systemVersion: string): string {
  const branchFolder = buildReleaseBranchFolder(systemVersion)
  const branchPath = join(devProjectPath, branchFolder)
  if (!existsSync(branchPath)) {
    throw new Error(`未找到系统版本分支: ${branchFolder}`)
  }
  return branchPath
}

function findLatestStableVersion(stableRoot: string): { versionName: string; versionPath: string } {
  const versions = safeDirEntries(stableRoot)
    .filter((entry) => entry.isDirectory() && /^\d{4}\.\d{2}\.\d{2}\.\d{2}\.\d{2}\.\d{2}_\d+/.test(entry.name))
    .map((entry) => entry.name)
  if (!versions.length) {
    throw new Error(`stable 下未找到 daily 版本目录: ${stableRoot}`)
  }
  const versionName = newestByNameTimestamp(stableRoot, versions) || versions[0]
  return { versionName, versionPath: join(stableRoot, versionName) }
}

function cellText(value: unknown): string {
  return String(value ?? '').trim()
}

function extractArchivePathCqFromReleaseNote(releaseNotePath: string): string {
  const workbook = XLSX.readFile(releaseNotePath, { cellDates: true })
  for (const sheetName of workbook.SheetNames) {
    const sheet = workbook.Sheets[sheetName]
    const rows = XLSX.utils.sheet_to_json(sheet, {
      header: 1,
      defval: '',
      raw: false,
    }) as unknown[][]

    for (let rowIdx = 0; rowIdx < rows.length; rowIdx += 1) {
      const row = rows[rowIdx]
      for (let colIdx = 0; colIdx < row.length; colIdx += 1) {
        const text = cellText(row[colIdx])
        if (!text) continue

        const inlineMatch = text.match(/archive_path_cq\s*[:=：]\s*(.+)$/i)
        if (inlineMatch?.[1]?.trim()) return normalizePath(inlineMatch[1])

        if (text.toLowerCase() !== 'archive_path_cq') continue

        const right = cellText(row[colIdx + 1])
        if (right) return normalizePath(right)

        for (let nextRow = rowIdx + 1; nextRow < rows.length; nextRow += 1) {
          const below = cellText(rows[nextRow]?.[colIdx])
          if (below) return normalizePath(below)
        }
      }
    }
  }
  throw new Error(`ReleaseNote.xlsx 中未找到 archive_path_cq: ${releaseNotePath}`)
}

function buildIdhArchivePath(path: string, brand: string): string {
  const normalized = normalizePath(path).replace(/\//g, '\\')
  const escapedBrand = brand.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const brandPattern = new RegExp(`(\\\\CI\\\\)${escapedBrand}(\\\\)`, 'i')
  if (brandPattern.test(normalized)) {
    return normalized.replace(brandPattern, `$1IDH\\${brand}$2`)
  }
  if (/\\CI\\/i.test(normalized)) {
    return normalized.replace(/\\CI\\/i, '\\CI\\IDH\\')
  }
  return normalized
}

function resolveExistingArchivePath(archivePath: string, brand: string): { path: string; usedIdhFallback: boolean } {
  const normalized = normalizePath(archivePath)
  if (existsSync(normalized)) return { path: normalized, usedIdhFallback: false }

  const idhPath = buildIdhArchivePath(normalized, brand)
  if (idhPath !== normalized && existsSync(idhPath)) {
    return { path: idhPath, usedIdhFallback: true }
  }

  throw new Error(`archive_path_cq 路径不存在，IDH 兜底也不存在: ${normalized}`)
}

// 构建产物 / 单分区包后缀，不能作为整包刷机包（如 *_user_EFUSE.zip）。
const EXCLUDED_PACKAGE_PATTERN = /(_user|_userdebug|_eng|efuse)/i
const USER_ROOT_PACKAGE_PATTERN = /user_root/i

function findUserRootPkgInDirectory(searchDir: string): string | null {
  if (!existsSync(searchDir)) return null
  const zipFiles = safeDirEntries(searchDir)
    .filter((entry) => entry.isFile() && /\.zip$/i.test(entry.name))
    .map((entry) => entry.name)
    .filter((name) => USER_ROOT_PACKAGE_PATTERN.test(name))
  const latestZip = newestByNameTimestamp(searchDir, zipFiles)
  return latestZip ? join(searchDir, latestZip) : null
}

function collectUserRootSearchDirs(pkgPath: string): string[] {
  const normalized = normalizePath(pkgPath.trim())
  if (!normalized) return []

  const dirs: string[] = []
  const pushDir = (dir: string) => {
    const resolved = resolve(dir)
    if (!dirs.includes(resolved)) dirs.push(resolved)
  }

  if (existsSync(normalized)) {
    const stat = statSync(normalized)
    if (stat.isFile()) {
      pushDir(dirname(normalized))
    } else {
      pushDir(normalized)
      pushDir(join(normalized, '..'))
    }
    return dirs
  }

  if (isZipFile(normalized) || /\.xml$/i.test(normalized)) {
    pushDir(dirname(normalized))
  } else {
    pushDir(normalized)
    pushDir(join(normalized, '..'))
  }
  return dirs
}

export function resolveUserRootPkgPath(pkgPath: string): string {
  for (const searchDir of collectUserRootSearchDirs(pkgPath)) {
    const found = findUserRootPkgInDirectory(searchDir)
    if (found) return found
  }
  throw new Error(`未在刷机包路径下找到 user_root 小包: ${pkgPath}`)
}

function findFlashPackageInOpenPath(openPath: string): string {
  if (!existsSync(openPath)) {
    throw new Error(`Open 刷机包目录不存在: ${openPath}`)
  }

  const entries = safeDirEntries(openPath)
  const zipFiles = entries
    .filter((entry) => entry.isFile() && /\.zip$/i.test(entry.name))
    .map((entry) => entry.name)

  // 优先选不含 _user/EFUSE 等后缀的整包刷机包；没有时再退回全部 zip。
  const preferredZips = zipFiles.filter((name) => !EXCLUDED_PACKAGE_PATTERN.test(name))
  const zipPool = preferredZips.length ? preferredZips : zipFiles
  const latestZip = newestByNameTimestamp(openPath, zipPool)
  if (latestZip) return join(openPath, latestZip)

  // 没有 zip 时再考虑 scatter xml。
  const xmlFiles = entries
    .filter((entry) => entry.isFile() && /\.xml$/i.test(entry.name))
    .map((entry) => entry.name)
  const latestXml = newestByNameTimestamp(openPath, xmlFiles)
  if (latestXml) return join(openPath, latestXml)

  const dirs = entries.filter((entry) => entry.isDirectory()).map((entry) => entry.name)
  const scatterDir = dirs.find((name) => findScatterPkgPath(join(openPath, name)) !== resolve(join(openPath, name)))
  if (scatterDir) return join(openPath, scatterDir)

  // device_update can accept a package directory; use Open itself when no single file is present.
  return openPath
}

export function pickLatestSystemVersion(versions: DailySystemVersionOption[]): string {
  if (!versions.length) {
    throw new Error('未找到可用的 tOS 系统版本')
  }
  const sorted = [...versions].sort((a, b) => compareSystemVersionLabels(a.label, b.label))
  return sorted[0]!.value
}

export async function resolveLatestDailyFlashPackage(
  request: LatestDailyFlashRequest
): Promise<LatestDailyFlashResult> {
  const identity = await resolveFlashDeviceIdentity(request.deviceId)
  const availableVersions = listSystemVersions(identity.devProjectPath)
  const systemVersion = request.systemVersion?.trim() || pickLatestSystemVersion(availableVersions)
  const branchFolder = buildReleaseBranchFolder(systemVersion)
  const branchPath = findReleaseBranchBySystemVersion(identity.devProjectPath, systemVersion)
  const stableRoot = join(branchPath, 'stable')
  if (!existsSync(stableRoot)) throw new Error(`release 分支下 stable 路径不存在: ${stableRoot}`)

  const { versionName, versionPath } = findLatestStableVersion(stableRoot)
  const releaseNotePath = join(versionPath, RELEASE_NOTE_FILE)
  if (!existsSync(releaseNotePath)) throw new Error(`最新 daily 版本缺少 ${RELEASE_NOTE_FILE}: ${releaseNotePath}`)

  const archivePathCq = extractArchivePathCqFromReleaseNote(releaseNotePath)
  const resolved = resolveExistingArchivePath(archivePathCq, identity.brand)
  const openPath = join(resolved.path, 'Open')
  const packagePath = findFlashPackageInOpenPath(openPath)

  return {
    deviceId: identity.deviceId,
    brand: identity.brand,
    project: identity.project,
    systemVersion,
    branchFolder,
    devRoot: identity.devRoot,
    devProjectPath: identity.devProjectPath,
    branchPath,
    versionPath,
    versionName,
    releaseNotePath,
    archivePathCq,
    resolvedArchivePath: resolved.path,
    openPath,
    packagePath,
    usedIdhFallback: resolved.usedIdhFallback,
  }
}

export type PlannedTestType = 'str4' | 'week' | 'monkey' | 'smoke'

/** 与 device-self-check StartTestFlashPayload 结构兼容 */
export interface PlannedTestFlashPayload {
  enabled: boolean
  pkgPath?: string
  rootPkgPath?: string
  enableRootPkg?: boolean
  stageVersion?: string
}

export function findRootPackageInArchive(resolvedArchivePath: string): string | undefined {
  const rootPath = join(resolvedArchivePath, 'Root')
  if (!existsSync(rootPath)) return undefined
  try {
    return findFlashPackageInOpenPath(rootPath)
  } catch {
    return undefined
  }
}

/** monkey / smoke 规划自动执行需与手动 UI 一致：刷机 + 勾选「刷 Root 包」 */
const PLANNED_TEST_TYPES_WITH_ROOT_PKG: PlannedTestType[] = ['monkey', 'smoke']

/** AI 测试规划自动执行：解析 latest daily + Open 市场 */
export async function buildPlannedTestFlashPayload(
  deviceId: string,
  testType: PlannedTestType,
): Promise<PlannedTestFlashPayload> {
  const daily = await resolveLatestDailyFlashPackage({ deviceId })
  const payload: PlannedTestFlashPayload = {
    enabled: true,
    pkgPath: daily.packagePath,
    stageVersion: 'Open',
  }
  if (PLANNED_TEST_TYPES_WITH_ROOT_PKG.includes(testType)) {
    payload.enableRootPkg = true
  }
  return payload
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
    let resolvedRootPkgPath = options.rootPkgPath?.trim() || ''
    if (!resolvedRootPkgPath && options.enableRootPkg) {
      resolvedRootPkgPath = resolveUserRootPkgPath(options.pkgPath)
      log(`[刷机] 自动解析 user_root 小包: ${resolvedRootPkgPath}`)
    }
    const rootPkgPath = await prepareRootPkgPath(resolvedRootPkgPath, log)
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
