/**
 * 已外发 Android 版本解析：上海盘提供版本清单，重庆盘提供实际升级包。
 */
import { spawn } from 'child_process'
import { existsSync, readdirSync } from 'fs'
import { basename, join } from 'path'
import {
  extractProjectCandidates,
  resolveHighestDailyAndroidTcardPackage,
} from './device-flash'

export const RELEASE_VERSION_ROOT = '\\\\10.150.98.24\\sw_ver_release\\RELEASE_VERSIONS'
export const CI_RELEASE_VERSION_ROOT = '\\\\10.205.4.40\\sw_version\\CI\\RELEASE_VERSIONS'

const BRAND_PROPS = ['ro.product.brand', 'ro.build.brand', 'ro.product.manufacturer']
const PROJECT_PROPS = ['ro.product.name', 'ro.build.product', 'ro.product.device', 'ro.product.model']
const ANDROID_LETTER_MAP: Record<string, number> = { T: 13, U: 14, V: 15, W: 16, X: 17, Y: 18 }
const USER_FOLDER_RE = /^([A-Za-z0-9]+)-(\d+\.\d+\.\d+\.\d+(?:SP\d+)?)?(?:\(([A-Z0-9]+)\))?(.*)$/i
const MR_FOLDER_RE = /-([TUVWXY])-([A-Z]+)-(\d{6}V\d+)/i
const VERSION_TOKEN_RE = /\d+\.\d+\.\d+\.\d+(?:SP\d+)?/gi
const EXCLUDED_ZIP_RE = /(_user|_userdebug|_eng|efuse)/i

export type ReleaseChannel = 'USER' | 'MR' | 'DAILY'
export type UpgradeMethod = 'device_update' | 'tcard'

export interface ParsedReleaseVersion {
  folderName: string
  folderPath: string
  relativePath: string
  channel: ReleaseChannel
  androidVersion: number
  androidLabel: string
  versionName: string
  market: string
  isOpMarket: boolean
  sortKey: string
}

export interface ReleasePackageSet {
  fullZip?: string
  tcardZips: string[]
}

export interface AndroidUpgradeStep {
  androidVersion: number
  androidLabel: string
  releaseVersionName: string
  releaseFolder: string
  channel: ReleaseChannel
  packagePath: string
  fullZip?: string
  tcardZips: string[]
  sourcePath?: string
  cqTargetPath: string
  needsTransfer: boolean
  available: boolean
  selected: boolean
  unavailableReason?: string
}

export interface ReleaseUpgradePlan {
  deviceId: string
  brand: string
  model: string
  ciModels: string[]
  releaseRoot: string
  ciRoot: string
  steps: AndroidUpgradeStep[]
  dailyHighestAndroidVersion?: number
  dailyTcardOverrideApplied?: boolean
  dailyTcardPackagePath?: string
  dailyTcardSource?: 'DEV' | 'TEST'
  dailyResolveWarning?: string
}

type DirEntry = { name: string; isDirectory: () => boolean; isFile: () => boolean }

function safeDirEntries(dir: string): DirEntry[] {
  try {
    return readdirSync(dir, { withFileTypes: true }) as DirEntry[]
  } catch {
    return []
  }
}

function getAdbProp(deviceId: string, prop: string): Promise<string> {
  return new Promise((resolvePromise) => {
    const proc = spawn('adb', ['-s', deviceId, 'shell', 'getprop', prop], { windowsHide: true })
    let stdout = ''
    proc.stdout?.on('data', (chunk: Buffer) => { stdout += chunk.toString('utf8') })
    proc.on('close', () => resolvePromise(stdout.trim()))
    proc.on('error', () => resolvePromise(''))
  })
}

function normalizeBrandName(raw: string): string | null {
  const upper = raw.trim().toUpperCase()
  if (upper.includes('TECNO')) return 'TECNO'
  if (upper.includes('INFINIX')) return 'INFINIX'
  if (upper.includes('ITEL')) return 'ITEL'
  if (upper.includes('PHILIPS')) return 'PHILIPS'
  return null
}

function androidLabel(androidVersion: number, letter?: string): string {
  return `Android ${androidVersion}${letter ? ` (${letter})` : ''}`
}

function numericSortKey(value: string): string {
  const parts = value.match(/\d+/g) || []
  return parts.map((part) => part.padStart(10, '0')).join('.')
}

export function parseUserReleaseFolder(
  folderName: string,
  folderPath = folderName,
  relativePath = join('USER', folderName),
): ParsedReleaseVersion | null {
  const match = folderName.trim().match(USER_FOLDER_RE)
  if (!match?.[2]) return null
  const androidVersion = Number(match[2].split('.')[0])
  if (!Number.isFinite(androidVersion) || androidVersion < 10) return null
  const market = match[3] || ''
  return {
    folderName,
    folderPath,
    relativePath,
    channel: 'USER',
    androidVersion,
    androidLabel: androidLabel(androidVersion),
    versionName: match[2],
    market,
    isOpMarket: /^OP/i.test(market),
    sortKey: numericSortKey(match[2]),
  }
}

export function parseMrReleaseFolder(
  folderName: string,
  folderPath = folderName,
  relativePath = folderName,
): ParsedReleaseVersion | null {
  const match = folderName.trim().match(MR_FOLDER_RE)
  if (!match) return null
  const letter = match[1].toUpperCase()
  const androidVersion = ANDROID_LETTER_MAP[letter]
  if (!androidVersion) return null
  return {
    folderName,
    folderPath,
    relativePath,
    channel: 'MR',
    androidVersion,
    androidLabel: androidLabel(androidVersion, letter),
    versionName: match[3],
    market: match[2],
    isOpMarket: /^OP/i.test(match[2]),
    sortKey: numericSortKey(match[3]),
  }
}

export function classifyReleaseZipName(name: string): 'full' | 'tcard' | 'skip' {
  const fileName = basename(name)
  if (!/\.zip$/i.test(fileName)) return 'skip'
  if (EXCLUDED_ZIP_RE.test(fileName) && !/^Tcard_/i.test(fileName)) return 'skip'
  if (/^Tcard_/i.test(fileName) || (fileName.match(VERSION_TOKEN_RE)?.length ?? 0) >= 2) return 'tcard'
  return 'full'
}

function listZipFiles(versionPath: string): string[] {
  const roots = [join(versionPath, 'Open'), versionPath]
  for (const root of roots) {
    if (!existsSync(root)) continue
    const zips = safeDirEntries(root)
      .filter((entry) => entry.isFile() && /\.zip$/i.test(entry.name))
      .map((entry) => join(root, entry.name))
    if (zips.length) return zips
  }
  return []
}

export function packageSetFromPaths(paths: string[]): ReleasePackageSet {
  const full = paths.filter((path) => classifyReleaseZipName(path) === 'full').sort().reverse()
  const tcard = paths.filter((path) => classifyReleaseZipName(path) === 'tcard').sort().reverse()
  return { fullZip: full[0], tcardZips: tcard }
}

export function pickTcardZipForPreviousAndroid(paths: string[], previousAndroid: number): string | undefined {
  const hinted = paths.filter((path) => new RegExp(`_a${previousAndroid}(?:\\D|$)`, 'i').test(basename(path)))
  return (hinted.length ? hinted : paths).slice().sort().reverse()[0]
}

function listVersionFolders(modelRoot: string): ParsedReleaseVersion[] {
  const versions: ParsedReleaseVersion[] = []
  const userRoot = join(modelRoot, 'USER')
  for (const entry of safeDirEntries(userRoot)) {
    if (!entry.isDirectory()) continue
    const parsed = parseUserReleaseFolder(entry.name, join(userRoot, entry.name))
    if (parsed) versions.push(parsed)
  }
  for (const project of safeDirEntries(modelRoot)) {
    if (!project.isDirectory() || project.name.toUpperCase() === 'USER') continue
    const mrRoot = join(modelRoot, project.name, 'MR')
    for (const entry of safeDirEntries(mrRoot)) {
      if (!entry.isDirectory()) continue
      const relativePath = join(project.name, 'MR', entry.name)
      const parsed = parseMrReleaseFolder(entry.name, join(mrRoot, entry.name), relativePath)
      if (parsed) versions.push(parsed)
    }
  }
  return versions
}

export function pickLatestForAndroid(
  versions: ParsedReleaseVersion[],
  androidVersion: number,
): ParsedReleaseVersion | undefined {
  const group = versions.filter((item) => item.androidVersion === androidVersion)
  const opGroup = group.filter((item) => item.isOpMarket)
  return (opGroup.length ? opGroup : group).slice().sort((a, b) =>
    b.sortKey.localeCompare(a.sortKey) || b.folderName.localeCompare(a.folderName)
  )[0]
}

export function assertContinuousUpgradeEligible(releases: { androidVersion: number }[]): void {
  const androidVersions = [...new Set(releases.map((item) => item.androidVersion))]
  if (androidVersions.length < 2) {
    const label = androidVersions.length ? `Android ${androidVersions[0]}` : '无有效 Android 版本'
    throw new Error(`仅识别到一个 Android 大版本（${label}），不能使用连续版本升级`)
  }
}

export function modelFamilyVariants(model: string): string[] {
  const out = [model]
  const withB = model.match(/^([A-Za-z]+\d+)B(-.+)$/i)
  if (withB) out.push(`${withB[1]}${withB[2]}`)
  else {
    const withoutB = model.match(/^([A-Za-z]+\d+)(-.+)$/i)
    if (withoutB) out.push(`${withoutB[1]}B${withoutB[2]}`)
  }
  return out
}

export function collectModelCandidates(...values: string[]): string[] {
  const candidates = new Set<string>()
  for (const value of values) {
    const trimmed = value.trim()
    if (!trimmed) continue
    candidates.add(trimmed)
    const dashed = trimmed.match(/^([A-Za-z]+\d+[A-Za-z]?-[A-Za-z0-9]+)/)
    if (dashed) candidates.add(dashed[1])
  }
  extractProjectCandidates(...values).forEach((item) => candidates.add(item))
  return [...candidates].sort((a, b) => b.length - a.length)
}

export function matchModelFolder(folders: string[], candidates: string[]): string | null {
  const explicitCandidates = candidates.filter((candidate) => candidate.includes('-'))
  for (const candidate of explicitCandidates) {
    const exact = folders.find((folder) => folder.toUpperCase() === candidate.toUpperCase())
    if (exact) return exact
  }
  const baseCandidates = candidates.filter((candidate) => !candidate.includes('-'))
  for (const candidate of baseCandidates) {
    const standard = folders.find((folder) =>
      new RegExp(`^${candidate.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}-H[A-Z0-9]+$`, 'i').test(folder)
    )
    if (standard) return standard
  }
  for (const candidate of candidates) {
    const exact = folders.find((folder) => folder.toUpperCase() === candidate.toUpperCase())
    if (exact) return exact
  }
  for (const candidate of candidates) {
    const hit = folders.find((folder) => folder.toUpperCase().startsWith(`${candidate.toUpperCase()}-`))
    if (hit) return hit
  }
  return null
}

function findCiVersion(
  ciBrandRoot: string,
  models: string[],
  release: ParsedReleaseVersion,
): { model: string; version: ParsedReleaseVersion; packages: ReleasePackageSet } | null {
  for (const model of models) {
    const versions = listVersionFolders(join(ciBrandRoot, model))
    const exact = versions.find((item) => item.folderName === release.folderName)
    const candidate = exact || pickLatestForAndroid(versions, release.androidVersion)
    if (!candidate) continue
    const packages = packageSetFromPaths(listZipFiles(candidate.folderPath))
    if (packages.fullZip || packages.tcardZips.length) return { model, version: candidate, packages }
  }
  return null
}

export function buildUpgradeSteps(
  releases: ParsedReleaseVersion[],
  findCi: (release: ParsedReleaseVersion) => { model: string; version: ParsedReleaseVersion; packages: ReleasePackageSet } | null,
  ciRootFor: (model: string, release: ParsedReleaseVersion) => string,
): AndroidUpgradeStep[] {
  const androidVersions = [...new Set(releases.map((item) => item.androidVersion))].sort((a, b) => a - b)
  return androidVersions.map((androidVersion) => {
    const release = pickLatestForAndroid(releases, androidVersion)!
    const sourcePackages = packageSetFromPaths(listZipFiles(release.folderPath))
    const ci = findCi(release)
    const packages = ci?.packages || sourcePackages
    const packagePath = packages.fullZip || packages.tcardZips[0] || release.folderPath
    const targetModel = ci?.model || ''
    return {
      androidVersion,
      androidLabel: release.androidLabel,
      releaseVersionName: release.versionName,
      releaseFolder: release.folderName,
      channel: release.channel,
      packagePath,
      fullZip: packages.fullZip,
      tcardZips: packages.tcardZips,
      sourcePath: ci ? undefined : packagePath,
      cqTargetPath: ciRootFor(targetModel, release),
      needsTransfer: !ci,
      available: Boolean(ci),
      selected: Boolean(ci),
    }
  })
}

export function applyHighestDailyTcardOverride(
  steps: AndroidUpgradeStep[],
  daily: { androidVersion: number; tcardPackagePath: string },
): boolean {
  if (!steps.length) return false
  const releaseHighest = Math.max(...steps.map((step) => step.androidVersion))
  if (daily.androidVersion !== releaseHighest) return false
  const step = steps.find((item) => item.androidVersion === releaseHighest)
  if (!step) return false
  step.tcardZips = [
    daily.tcardPackagePath,
    ...step.tcardZips.filter((path) => path !== daily.tcardPackagePath),
  ]
  step.packagePath = daily.tcardPackagePath
  step.sourcePath = undefined
  step.needsTransfer = false
  step.available = true
  step.selected = true
  return true
}

export function mergeHighestDailyVersion(
  steps: AndroidUpgradeStep[],
  daily: {
    androidVersion: number
    systemVersion: string
    versionName: string
    devProjectPath: string
    openPath: string
    tcardPackagePath?: string
    tcardResolveWarning?: string
  },
): { added: boolean; overrideApplied: boolean } {
  const existing = steps.find((step) => step.androidVersion === daily.androidVersion)
  if (existing) {
    return {
      added: false,
      overrideApplied: daily.tcardPackagePath
        ? applyHighestDailyTcardOverride(steps, {
            androidVersion: daily.androidVersion,
            tcardPackagePath: daily.tcardPackagePath,
          })
        : false,
    }
  }
  const path = daily.tcardPackagePath || daily.openPath
  steps.push({
    androidVersion: daily.androidVersion,
    androidLabel: `Android ${daily.androidVersion}`,
    releaseVersionName: `${daily.systemVersion} / ${daily.versionName}`,
    releaseFolder: basename(daily.devProjectPath),
    channel: 'DAILY',
    packagePath: path,
    tcardZips: daily.tcardPackagePath ? [daily.tcardPackagePath] : [],
    cqTargetPath: daily.openPath,
    needsTransfer: false,
    available: Boolean(daily.tcardPackagePath),
    selected: Boolean(daily.tcardPackagePath),
    unavailableReason: daily.tcardPackagePath
      ? undefined
      : (daily.tcardResolveWarning || `Android ${daily.androidVersion} 未找到 T卡升级包`),
  })
  steps.sort((a, b) => a.androidVersion - b.androidVersion)
  return { added: true, overrideApplied: false }
}

async function resolveDeviceIdentity(deviceId: string): Promise<{ brand: string; model: string }> {
  if (!existsSync(RELEASE_VERSION_ROOT)) throw new Error(`无法访问上海外发版本目录: ${RELEASE_VERSION_ROOT}`)
  const [brandProps, projectProps] = await Promise.all([
    Promise.all(BRAND_PROPS.map((prop) => getAdbProp(deviceId, prop))),
    Promise.all(PROJECT_PROPS.map((prop) => getAdbProp(deviceId, prop))),
  ])
  const brands = safeDirEntries(RELEASE_VERSION_ROOT).filter((entry) => entry.isDirectory()).map((entry) => entry.name)
  const normalized = brandProps.map(normalizeBrandName).find(Boolean)
  const brand = brands.find((item) => item.toUpperCase() === normalized?.toUpperCase())
  if (!brand) throw new Error(`无法识别设备品牌（${brandProps.filter(Boolean).join(', ') || 'ADB 无返回'}）`)
  const models = safeDirEntries(join(RELEASE_VERSION_ROOT, brand))
    .filter((entry) => entry.isDirectory()).map((entry) => entry.name)
  const model = matchModelFolder(models, collectModelCandidates(...projectProps))
  if (!model) throw new Error(`未在上海外发目录找到设备型号（候选: ${projectProps.filter(Boolean).join(', ') || '无'}）`)
  return { brand, model }
}

export async function resolveReleaseUpgradePlan(deviceId: string): Promise<ReleaseUpgradePlan> {
  const serial = deviceId.trim()
  if (!serial) throw new Error('设备 ID 为空')
  const { brand, model } = await resolveDeviceIdentity(serial)
  const releaseRoot = join(RELEASE_VERSION_ROOT, brand, model)
  const releases = listVersionFolders(releaseRoot)
  if (!releases.length) throw new Error(`未找到已外发 USER/MR 版本: ${releaseRoot}`)

  const ciBrandRoot = join(CI_RELEASE_VERSION_ROOT, brand)
  const ciModels = modelFamilyVariants(model)
  const steps = buildUpgradeSteps(
    releases,
    (release) => findCiVersion(ciBrandRoot, ciModels, release),
    (matchedModel, release) => join(ciBrandRoot, matchedModel || model, release.relativePath, 'Open'),
  )
  let dailyHighestAndroidVersion: number | undefined
  let dailyTcardOverrideApplied = false
  let dailyTcardPackagePath: string | undefined
  let dailyTcardSource: 'DEV' | 'TEST' | undefined
  let dailyResolveWarning: string | undefined
  try {
    const daily = await resolveHighestDailyAndroidTcardPackage(serial)
    dailyHighestAndroidVersion = daily.androidVersion
    dailyTcardPackagePath = daily.tcardPackagePath
    dailyTcardSource = daily.tcardSource
    const merged = mergeHighestDailyVersion(steps, daily)
    dailyTcardOverrideApplied = merged.overrideApplied
  } catch (err: any) {
    dailyResolveWarning = err?.message || '获取 sw_ver_sh 最高 Android daily T卡包失败'
  }
  assertContinuousUpgradeEligible(steps)
  return {
    deviceId: serial,
    brand,
    model,
    ciModels,
    releaseRoot,
    ciRoot: join(ciBrandRoot, model),
    steps,
    dailyHighestAndroidVersion,
    dailyTcardOverrideApplied,
    dailyTcardPackagePath,
    dailyTcardSource,
    dailyResolveWarning,
  }
}
