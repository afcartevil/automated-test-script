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
import {
  isOfficialTcardZipName,
  missingTcardZipHint,
  pickPreferredTcardZipPath,
  rankTcardZip,
  sortTcardZipPaths,
} from './device-tcard-zip'

export const RELEASE_VERSION_ROOT = '\\\\10.150.98.24\\sw_ver_release\\RELEASE_VERSIONS'
export const CI_RELEASE_VERSION_ROOT = '\\\\10.205.4.40\\sw_version\\CI\\RELEASE_VERSIONS'

const BRAND_PROPS = ['ro.product.brand', 'ro.build.brand', 'ro.product.manufacturer']
const PROJECT_PROPS = ['ro.product.name', 'ro.build.product', 'ro.product.device', 'ro.product.model']
const ANDROID_LETTER_MAP: Record<string, number> = { T: 13, U: 14, V: 15, W: 16, X: 17, Y: 18 }
const USER_FOLDER_RE = /^([A-Za-z0-9]+)-(\d+\.\d+\.\d+\.\d+(?:SP\d+)?)?(?:\(([A-Z0-9]+)\))?(.*)$/i
/** OP 市场：`OP` 或 `OP001PF001AZ`。不包含 OPPJ 等其它以 OP 开头的市场。 */
const OP_MARKET_RE = /^OP(\d|$)/i
const MR_FOLDER_RE = /-([TUVWXY])-([A-Z]+)-(\d{6}V\d+)/i
const VERSION_TOKEN_RE = /\d+\.\d+\.\d+\.\d+(?:SP\d+)?/gi
const MR_VERSION_TOKEN_RE = /\d{6}V\d+/g
const USER_FULL_ZIP_RE = /^[A-Za-z0-9]+-\d+\.\d+\.\d+\.\d+(?:SP\d+)?\([A-Z0-9]+\)\.zip$/i
const MR_FULL_ZIP_RE = /^[A-Za-z0-9]+-[A-Za-z0-9]+-[TUVWXY]-[A-Z]+-\d{6}V\d+\.zip$/i
const SKIP_ZIP_RE = /(_user|_userdebug|_eng|efuse|target_files|ota_tools|^OTA_TOOLS\.zip$|trpre_apk)/i

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
    isOpMarket: OP_MARKET_RE.test(market),
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
    isOpMarket: OP_MARKET_RE.test(match[2]),
    sortKey: numericSortKey(match[3]),
  }
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function classifyReleaseZipName(name: string): 'full' | 'tcard' | 'skip' {
  const fileName = basename(name)
  if (!/\.zip$/i.test(fileName)) return 'skip'
  if (isOfficialTcardZipName(fileName)) return 'tcard'
  if (SKIP_ZIP_RE.test(fileName)) return 'skip'
  if ((fileName.match(VERSION_TOKEN_RE)?.length ?? 0) >= 2) return 'skip'
  if ((fileName.match(MR_VERSION_TOKEN_RE)?.length ?? 0) >= 2) return 'skip'
  if (USER_FULL_ZIP_RE.test(fileName) || MR_FULL_ZIP_RE.test(fileName)) return 'full'
  return 'skip'
}

export function zipMatchesRelease(fileName: string, release: ParsedReleaseVersion): boolean {
  const name = basename(fileName)
  if (release.channel === 'MR' || MR_FULL_ZIP_RE.test(name)) {
    const stem = release.folderName.replace(/_MR\d+.*$/i, '')
    if (name.toLowerCase() === `${stem}.zip`.toLowerCase()) return true
    return new RegExp(`-${escapeRegExp(release.versionName)}\\.zip$`, 'i').test(name)
  }
  if (release.market) {
    return new RegExp(
      `-${escapeRegExp(release.versionName)}\\(${escapeRegExp(release.market)}\\)\\.zip$`,
      'i',
    ).test(name)
  }
  return new RegExp(`-${escapeRegExp(release.versionName)}(?:\\(|\\.zip$)`, 'i').test(name)
}

export function pickFullFlashZip(paths: string[], release?: ParsedReleaseVersion): string | undefined {
  const full = paths.filter((path) => classifyReleaseZipName(path) === 'full')
  if (!full.length) return undefined
  if (release) {
    const matched = full.filter((path) => zipMatchesRelease(path, release))
    if (matched.length) return matched.slice().sort().reverse()[0]
  }
  return full.slice().sort().reverse()[0]
}

function zipFilesIn(dir: string): string[] {
  return safeDirEntries(dir)
    .filter((entry) => entry.isFile() && /\.zip$/i.test(entry.name))
    .map((entry) => join(dir, entry.name))
}

function samePath(a: string, b: string): boolean {
  return a.replace(/[\\/]+$/, '').replace(/\//g, '\\').toLowerCase()
    === b.replace(/[\\/]+$/, '').replace(/\//g, '\\').toLowerCase()
}

/**
 * USER 外发包通常在 `{版本}/Open`；Android 14 MR 会多一层不固定平台目录
 * （如 `tran_mtk_u0.mp1.rc_v3.8_os13.6-os14.0_mp.rel_231212`），Open 在其下。
 */
export function resolveReleasePackageRoot(versionPath: string): string {
  type Candidate = { root: string; openPath: string; nested: boolean; name: string }
  const candidates: Candidate[] = []
  const directOpen = join(versionPath, 'Open')
  if (existsSync(directOpen)) {
    candidates.push({ root: versionPath, openPath: directOpen, nested: false, name: 'Open' })
  }
  for (const entry of safeDirEntries(versionPath)) {
    if (!entry.isDirectory() || entry.name.toUpperCase() === 'OPEN') continue
    const openPath = join(versionPath, entry.name, 'Open')
    if (existsSync(openPath)) {
      candidates.push({
        root: join(versionPath, entry.name),
        openPath,
        nested: true,
        name: entry.name,
      })
    }
  }
  if (!candidates.length) return versionPath
  const withZips = candidates.filter((item) => zipFilesIn(item.openPath).length > 0)
  const pool = withZips.length ? withZips : candidates
  const direct = pool.find((item) => !item.nested)
  if (direct) return direct.root
  return (pool.find((item) => /^tran_mtk/i.test(item.name)) || pool[0]).root
}

function extraPackageSegment(versionPath: string, packageRoot: string): string {
  return samePath(versionPath, packageRoot) ? '' : basename(packageRoot)
}

function listZipFiles(versionPath: string): string[] {
  const packageRoot = resolveReleasePackageRoot(versionPath)
  const roots = [join(packageRoot, 'Open'), packageRoot]
  for (const root of roots) {
    if (!existsSync(root)) continue
    const zips = zipFilesIn(root)
    if (zips.length) return zips
  }
  return []
}

export function packageSetFromPaths(paths: string[], release?: ParsedReleaseVersion): ReleasePackageSet {
  return {
    fullZip: pickFullFlashZip(paths, release),
    tcardZips: sortTcardZipPaths(paths.filter((path) => classifyReleaseZipName(path) === 'tcard')),
  }
}

export function pickTcardZipForPreviousAndroid(paths: string[], previousAndroid: number): string | undefined {
  return pickPreferredTcardZipPath(paths, previousAndroid)
}

export function listVersionFolders(modelRoot: string): ParsedReleaseVersion[] {
  const versions: ParsedReleaseVersion[] = []
  const userRoot = join(modelRoot, 'USER')
  for (const entry of safeDirEntries(userRoot)) {
    if (!entry.isDirectory()) continue
    const folderPath = join(userRoot, entry.name)
    const packageRoot = resolveReleasePackageRoot(folderPath)
    const extra = extraPackageSegment(folderPath, packageRoot)
    const relativePath = extra ? join('USER', entry.name, extra) : join('USER', entry.name)
    const parsed = parseUserReleaseFolder(entry.name, packageRoot, relativePath)
    if (parsed) versions.push(parsed)
  }
  for (const project of safeDirEntries(modelRoot)) {
    if (!project.isDirectory() || project.name.toUpperCase() === 'USER') continue
    const mrRoot = join(modelRoot, project.name, 'MR')
    for (const entry of safeDirEntries(mrRoot)) {
      if (!entry.isDirectory()) continue
      const folderPath = join(mrRoot, entry.name)
      const packageRoot = resolveReleasePackageRoot(folderPath)
      const extra = extraPackageSegment(folderPath, packageRoot)
      const relativePath = extra
        ? join(project.name, 'MR', entry.name, extra)
        : join(project.name, 'MR', entry.name)
      const parsed = parseMrReleaseFolder(entry.name, packageRoot, relativePath)
      if (parsed) versions.push(parsed)
    }
  }
  return versions
}

function compareReleasePreference(a: ParsedReleaseVersion, b: ParsedReleaseVersion): number {
  if (a.isOpMarket !== b.isOpMarket) return a.isOpMarket ? -1 : 1
  return b.sortKey.localeCompare(a.sortKey) || b.folderName.localeCompare(a.folderName)
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

/** 同一 Android 大版本下，优先 OP、再新版本，找到第一个匹配的 T卡包。 */
export function pickTcardZipFromVersions(
  versions: ParsedReleaseVersion[],
  previousAndroid: number,
): { version: ParsedReleaseVersion; path: string; tcardZips: string[] } | undefined {
  for (const version of versions.slice().sort(compareReleasePreference)) {
    const tcardZips = sortTcardZipPaths(packagesForVersion(version).tcardZips, previousAndroid)
    if (tcardZips[0]) return { version, path: tcardZips[0], tcardZips }
  }
  return undefined
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

function packagesForVersion(version: ParsedReleaseVersion): ReleasePackageSet {
  return packageSetFromPaths(listZipFiles(version.folderPath), version)
}

function findFullZipForAndroid(versions: ParsedReleaseVersion[], androidVersion: number): string | undefined {
  const ranked = versions
    .filter((item) => item.androidVersion === androidVersion)
    .slice()
    .sort((a, b) => b.sortKey.localeCompare(a.sortKey) || b.folderName.localeCompare(a.folderName))
  for (const item of ranked) {
    const fullZip = packagesForVersion(item).fullZip
    if (fullZip) return fullZip
  }
  return undefined
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
    const packages = packagesForVersion(candidate)
    if (!packages.fullZip) {
      packages.fullZip = findFullZipForAndroid(versions, release.androidVersion)
    }
    packages.tcardZips = versions
      .filter((item) => item.androidVersion === release.androidVersion)
      .slice()
      .sort(compareReleasePreference)
      .flatMap((item) => packagesForVersion(item).tcardZips)
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
  return androidVersions.map((androidVersion, index) => {
    const group = releases.filter((item) => item.androidVersion === androidVersion)
    const release = pickLatestForAndroid(releases, androidVersion)!
    const ci = findCi(release)
    const packages = ci?.packages || packagesForVersion(release)
    const previousAndroid = index > 0 ? androidVersions[index - 1] : undefined
    const isBaseline = previousAndroid == null
    const ciTcardZips = previousAndroid != null
      ? (ci?.packages.tcardZips || []).filter((path) => rankTcardZip(path, previousAndroid) >= 0)
      : (ci?.packages.tcardZips || [])
    const shanghaiHit = previousAndroid != null
      ? pickTcardZipFromVersions(group, previousAndroid)
      : undefined
    const usingShanghaiTcard = !isBaseline && !ciTcardZips[0] && Boolean(shanghaiHit?.path)
    const tcardZips = ciTcardZips[0] ? ciTcardZips : (shanghaiHit?.tcardZips || [])
    const tcardZip = tcardZips[0]
    const missingTcard = !isBaseline && !tcardZip
    const packagePath = isBaseline ? (packages.fullZip || '') : (tcardZip || '')
    const targetModel = ci?.model || ''
    const stepRelease = usingShanghaiTcard && shanghaiHit ? shanghaiHit.version : release
    const needsTransfer = !ci || usingShanghaiTcard
    return {
      androidVersion,
      androidLabel: release.androidLabel,
      releaseVersionName: stepRelease.versionName,
      releaseFolder: stepRelease.folderName,
      channel: stepRelease.channel,
      packagePath,
      fullZip: packages.fullZip,
      tcardZips,
      sourcePath: needsTransfer ? packagePath : undefined,
      cqTargetPath: ciRootFor(targetModel, stepRelease),
      needsTransfer,
      available: Boolean(ci) && !missingTcard && !usingShanghaiTcard,
      selected: Boolean(ci) && !missingTcard && !usingShanghaiTcard,
      unavailableReason: missingTcard ? missingTcardZipHint(previousAndroid) : undefined,
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
  const path = daily.tcardPackagePath || ''
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
