/**
 * 设备自检报告列表、详情与人工 Review 元数据
 */
import { existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'fs'
import { spawn } from 'child_process'
import { platform } from 'os'
import { join, resolve, sep } from 'path'
import { getTahpProjectRoot } from './paths'
import { safeFileStore } from '../safe-file-store'

function projectRoot(): string {
  return getTahpProjectRoot()
}

function reportsDir(): string {
  return join(projectRoot(), 'reports')
}

export type SelfCheckReviewStatus = 'pending' | 'reviewed' | 'retest'

export interface SelfCheckFailedCaseItem {
  caseKey: string
  caseName: string
  module: string
  status: string
  message: string
}

export interface SelfCheckCaseItem {
  caseKey: string
  caseName: string
  module: string
  testType: string
  caseIndex: number
  status: string
  message: string
  fullAutomation?: boolean
  automationMode?: 'full' | 'semi' | 'manual'
  steps?: { stepDesc: string; status: string; timestamp: string }[]
  /** 失败用例导出的设备日志目录 */
  failureLogDir?: string
}

export interface SelfCheckFlashBeforeTestConfig {
  enabled: boolean
  pkgPath?: string
  enableRootPkg?: boolean
  rootPkgPath?: string
  stageVersion?: string
}

/** 质量验测开始前的前置配置快照（写入 summary/detail.json） */
export interface SelfCheckTestConfig {
  monkeyDuration?: string
  smokeUsdSkipSpdInfo?: boolean
  gmsTradefedPath?: Record<string, string>
  autoRetestEnabled?: boolean
  autoRetestCount?: number
  flashBeforeTest?: SelfCheckFlashBeforeTestConfig
  prioritizeTddManual?: boolean
  selectedCases?: string[]
}

export interface SelfCheckReportSummary {
  reportId: string
  deviceId: string
  deviceName: string
  testType: string
  /** persist.sys.ota_version（报告生成时 adb getprop） */
  version?: string
  startTime: string
  endTime?: string
  status: string
  totalCases: number
  passedCases: number
  failedCases: number
  skippedCases: number
  reviewStatus: SelfCheckReviewStatus
  completedAt: string
  reportPath: string
  aiPlanned?: boolean
  scheduleKey?: string
  testConfig?: SelfCheckTestConfig
}

export interface SelfCheckReportDetail extends SelfCheckReportSummary {
  aiSummary: string
  failedCaseItems: SelfCheckFailedCaseItem[]
  allCaseItems: SelfCheckCaseItem[]
  reviewNote?: string
  reviewedAt?: string
}

interface SummaryJson {
  deviceId: string
  deviceName: string
  testType: string
  /** adb shell getprop persist.sys.ota_version */
  version?: string
  startTime?: string
  endTime?: string
  duration?: number
  status: string
  totalCases: number
  passedCases: number
  failedCases: number
  skippedCases: number
  aiPlanned?: boolean
  scheduleKey?: string
  testConfig?: SelfCheckTestConfig
}

interface DetailJson extends SummaryJson {
  aiSummary?: string
  failedCaseItems?: SelfCheckFailedCaseItem[]
  allCaseItems?: SelfCheckCaseItem[]
}

interface ReviewMetaStore {
  reports: Record<string, {
    status: SelfCheckReviewStatus
    note?: string
    updatedAt: string
  }>
}

function selfCheckReportsRoot(): string {
  return join(reportsDir(), 'self-check')
}

function reviewMetaPath(): string {
  return join(projectRoot(), '.tahp-config', 'self-check-review-meta.json')
}

function ensureReviewMetaDir(): void {
  const dir = join(projectRoot(), '.tahp-config')
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
}

export function encodeReportId(relativePath: string): string {
  return Buffer.from(relativePath, 'utf-8').toString('base64url')
}

export function decodeReportId(reportId: string): string {
  const rel = Buffer.from(reportId, 'base64url').toString('utf-8')
  if (!rel.startsWith('self-check/') || rel.includes('..')) {
    throw new Error('无效的报告 ID')
  }
  return rel
}

async function loadReviewMetaStore(): Promise<ReviewMetaStore> {
  const path = reviewMetaPath()
  if (!existsSync(path)) return { reports: {} }
  try {
    const raw = await safeFileStore.readText(path)
    const data = JSON.parse(raw) as Partial<ReviewMetaStore>
    return { reports: data.reports && typeof data.reports === 'object' ? data.reports : {} }
  } catch {
    return { reports: {} }
  }
}

async function saveReviewMetaStore(store: ReviewMetaStore): Promise<void> {
  ensureReviewMetaDir()
  await safeFileStore.writeText(reviewMetaPath(), `${JSON.stringify(store, null, 2)}\n`)
}

/** Excel 摘要页 / 报告展示：将 testConfig 转为键值行 */
export function formatSelfCheckTestConfigMetaRows(cfg?: SelfCheckTestConfig): string[][] {
  if (!cfg) return []
  const rows: string[][] = []
  if (cfg.monkeyDuration) {
    rows.push(['monkey测试时长', cfg.monkeyDuration])
  }
  if (cfg.smokeUsdSkipSpdInfo !== undefined) {
    rows.push(['跳过 SPD 拉取 (--skip-spd-info)', cfg.smokeUsdSkipSpdInfo ? '是' : '否'])
  }
  if (cfg.gmsTradefedPath) {
    for (const suite of ['cts', 'gts', 'vts'] as const) {
      const path = cfg.gmsTradefedPath[suite]
      if (path) rows.push([`GMS ${suite.toUpperCase()} Tradefed`, path])
    }
  }
  if (cfg.autoRetestEnabled !== undefined) {
    rows.push([
      '自动复测',
      cfg.autoRetestEnabled ? `开启（${cfg.autoRetestCount ?? 0} 次）` : '关闭',
    ])
  }
  if (cfg.prioritizeTddManual) {
    rows.push(['通信人工用例优先', '是'])
  }
  if (cfg.flashBeforeTest?.enabled) {
    rows.push(['测试前刷机', '是'])
    if (cfg.flashBeforeTest.pkgPath) {
      rows.push(['刷机包路径', cfg.flashBeforeTest.pkgPath])
    }
    if (cfg.flashBeforeTest.stageVersion) {
      rows.push(['市场版本', cfg.flashBeforeTest.stageVersion])
    }
    if (cfg.flashBeforeTest.enableRootPkg && cfg.flashBeforeTest.rootPkgPath) {
      rows.push(['Root 刷机包', cfg.flashBeforeTest.rootPkgPath])
    }
  }
  if (cfg.selectedCases?.length) {
    rows.push(['自定义勾选用例数', String(cfg.selectedCases.length)])
  }
  return rows
}

function buildAiSummary(summary: SummaryJson, failed: SelfCheckFailedCaseItem[]): string {
  if (summary.totalCases === 0) {
    return '本次测试未产生用例数据。'
  }
  const passRate = Math.round((summary.passedCases / summary.totalCases) * 100)
  if (failed.length === 0) {
    return `共 ${summary.totalCases} 项用例，全部通过（通过率 ${passRate}%）。设备 ${summary.deviceName}，测试类型 ${summary.testType}。`
  }
  const modules = [...new Set(failed.map(item => item.module))].slice(0, 3).join('、')
  const names = failed.slice(0, 3).map(item => item.caseName).join('；')
  return `共 ${summary.totalCases} 项，通过 ${summary.passedCases}，失败 ${summary.failedCases}（通过率 ${passRate}%）。失败集中在 ${modules || '未知模块'}。建议优先关注：${names}${failed.length > 3 ? ' 等' : ''}。`
}

function readJsonFile<T>(path: string): T | null {
  if (!existsSync(path)) return null
  try {
    return JSON.parse(readFileSync(path, 'utf-8')) as T
  } catch {
    return null
  }
}

function buildSummaryFromDir(relativePath: string, sessionDir: string, deviceId: string): SelfCheckReportSummary | null {
  const absDir = join(reportsDir(), relativePath)
  const summaryPath = join(absDir, 'summary.json')
  const summary = readJsonFile<SummaryJson>(summaryPath)
  if (!summary) return null

  const mtime = existsSync(summaryPath) ? statSync(summaryPath).mtimeMs : 0
  const reportId = encodeReportId(relativePath)

  return {
    reportId,
    deviceId: summary.deviceId || deviceId,
    deviceName: summary.deviceName,
    testType: summary.testType,
    version: summary.version,
    startTime: summary.startTime || sessionDir,
    endTime: summary.endTime,
    status: summary.status,
    totalCases: summary.totalCases ?? 0,
    passedCases: summary.passedCases ?? 0,
    failedCases: summary.failedCases ?? 0,
    skippedCases: summary.skippedCases ?? 0,
    reviewStatus: 'pending',
    completedAt: summary.endTime || new Date(mtime).toISOString(),
    reportPath: relativePath.replace(/\\/g, '/'),
    aiPlanned: summary.aiPlanned === true,
    scheduleKey: summary.scheduleKey,
    testConfig: summary.testConfig,
  }
}

export async function listSelfCheckReports(options?: {
  sinceHours?: number
  pendingOnly?: boolean
}): Promise<SelfCheckReportSummary[]> {
  const root = selfCheckReportsRoot()
  if (!existsSync(root)) return []

  const meta = await loadReviewMetaStore()
  const sinceMs = options?.sinceHours
    ? Date.now() - options.sinceHours * 3600 * 1000
    : 0

  const items: SelfCheckReportSummary[] = []

  for (const deviceId of readdirSync(root, { withFileTypes: true }).filter(d => d.isDirectory()).map(d => d.name)) {
    const deviceDir = join(root, deviceId)
    for (const sessionDir of readdirSync(deviceDir, { withFileTypes: true }).filter(d => d.isDirectory()).map(d => d.name)) {
      const relativePath = join('self-check', deviceId, sessionDir).replace(/\\/g, '/')
      const summary = buildSummaryFromDir(relativePath, sessionDir, deviceId)
      if (!summary) continue

      const completedMs = Date.parse(summary.completedAt) || 0
      if (sinceMs && completedMs < sinceMs) continue

      const review = meta.reports[summary.reportId]
      summary.reviewStatus = review?.status ?? 'pending'
      if (options?.pendingOnly && summary.reviewStatus !== 'pending') continue

      items.push(summary)
    }
  }

  items.sort((a, b) => Date.parse(b.completedAt) - Date.parse(a.completedAt))
  return items
}

export async function countPendingSelfCheckReports(): Promise<number> {
  const items = await listSelfCheckReports({ pendingOnly: true })
  return items.length
}

export async function getSelfCheckReportDetail(reportId: string): Promise<SelfCheckReportDetail | null> {
  const relativePath = decodeReportId(reportId)
  const absDir = join(reportsDir(), relativePath)
  if (!existsSync(absDir)) return null

  const parts = relativePath.split('/')
  const deviceId = parts[1] || ''
  const sessionDir = parts[2] || ''
  const summary = buildSummaryFromDir(relativePath, sessionDir, deviceId)
  if (!summary) return null

  const meta = await loadReviewMetaStore()
  const review = meta.reports[reportId]

  const detailJson = readJsonFile<DetailJson>(join(absDir, 'detail.json'))
  const summaryJson = readJsonFile<SummaryJson>(join(absDir, 'summary.json'))
  const base = summaryJson || detailJson

  const failedCaseItems = detailJson?.failedCaseItems ?? []
  const allCaseItems = detailJson?.allCaseItems?.length
    ? detailJson.allCaseItems
    : failedCaseItems.map(item => ({
        caseKey: item.caseKey,
        caseName: item.caseName,
        module: item.module,
        testType: item.caseKey.split('/')[0] || summary.testType,
        caseIndex: Number.parseInt(item.caseKey.split('/').pop() || '1', 10),
        status: item.status,
        message: item.message,
      }))
  const aiSummary = detailJson?.aiSummary
    ?? (base ? buildAiSummary(base, failedCaseItems) : '暂无 AI 摘要')

  return {
    ...summary,
    reviewStatus: review?.status ?? summary.reviewStatus,
    aiSummary,
    failedCaseItems,
    allCaseItems,
    reviewNote: review?.note,
    reviewedAt: review?.updatedAt,
  }
}

export async function submitSelfCheckReportReview(
  reportId: string,
  payload: { status: SelfCheckReviewStatus; note?: string },
): Promise<SelfCheckReportDetail | null> {
  const detail = await getSelfCheckReportDetail(reportId)
  if (!detail) return null

  const store = await loadReviewMetaStore()
  store.reports[reportId] = {
    status: payload.status,
    note: payload.note?.trim() || undefined,
    updatedAt: new Date().toISOString(),
  }
  await saveReviewMetaStore(store)
  return getSelfCheckReportDetail(reportId)
}

export function buildSelfCheckDetailPayload(
  summary: SummaryJson,
  failedCaseItems: SelfCheckFailedCaseItem[],
  allCaseItems?: SelfCheckCaseItem[],
): DetailJson {
  return {
    ...summary,
    failedCaseItems,
    allCaseItems: allCaseItems ?? failedCaseItems.map(item => ({
      caseKey: item.caseKey,
      caseName: item.caseName,
      module: item.module,
      testType: item.caseKey.split('/')[0] || summary.testType,
      caseIndex: Number.parseInt(item.caseKey.split('/').pop() || '1', 10),
      status: item.status,
      message: item.message,
    })),
    aiSummary: buildAiSummary(summary, failedCaseItems),
  }
}

function collectFailedFromAll(allCaseItems: SelfCheckCaseItem[]): SelfCheckFailedCaseItem[] {
  return allCaseItems
    .filter(c => c.status === '失败' || c.status === '部分通过' || c.status === '待确认')
    .map(c => ({
      caseKey: c.caseKey,
      caseName: c.caseName,
      module: c.module,
      status: c.status,
      message: c.message,
    }))
}

function recomputeSummaryCounts(allCaseItems: SelfCheckCaseItem[]): Pick<
  SummaryJson,
  'totalCases' | 'passedCases' | 'failedCases' | 'skippedCases' | 'status'
> {
  const totalCases = allCaseItems.length
  const passedCases = allCaseItems.filter(c => c.status === '通过').length
  const failedCases = allCaseItems.filter(
    c => c.status === '失败' || c.status === '部分通过' || c.status === '待确认',
  ).length
  const skippedCases = allCaseItems.filter(c => c.status === '跳过' || c.status === 'NA').length
  const status = failedCases === 0 ? '完成(通过)' : '完成(失败)'
  return { totalCases, passedCases, failedCases, skippedCases, status }
}

export async function updateReportCaseResult(
  reportId: string,
  caseKey: string,
  status: string,
  message: string,
): Promise<SelfCheckReportDetail | null> {
  const relativePath = decodeReportId(reportId)
  const absDir = join(reportsDir(), relativePath)
  const detailPath = join(absDir, 'detail.json')
  const summaryPath = join(absDir, 'summary.json')
  const detailJson = readJsonFile<DetailJson>(detailPath)
  const summaryJson = readJsonFile<SummaryJson>(summaryPath)
  if (!detailJson || !summaryJson) return null

  const allCaseItems = [...(detailJson.allCaseItems ?? detailJson.failedCaseItems?.map(item => ({
    caseKey: item.caseKey,
    caseName: item.caseName,
    module: item.module,
    testType: item.caseKey.split('/')[0] || summaryJson.testType,
    caseIndex: Number.parseInt(item.caseKey.split('/').pop() || '1', 10),
    status: item.status,
    message: item.message,
  })) ?? [])]

  const idx = allCaseItems.findIndex(c => c.caseKey === caseKey)
  if (idx < 0) return null

  allCaseItems[idx] = { ...allCaseItems[idx], status, message }
  const failedCaseItems = collectFailedFromAll(allCaseItems)
  const counts = recomputeSummaryCounts(allCaseItems)
  const nextSummary: SummaryJson = { ...summaryJson, ...counts }
  const nextDetail = buildSelfCheckDetailPayload(nextSummary, failedCaseItems, allCaseItems)

  writeFileSync(summaryPath, JSON.stringify(nextSummary, null, 2), 'utf-8')
  writeFileSync(detailPath, JSON.stringify(nextDetail, null, 2), 'utf-8')
  return getSelfCheckReportDetail(reportId)
}

export function reportAbsoluteDir(reportId: string): string {
  return join(reportsDir(), decodeReportId(reportId))
}

export function getSelfCheckReportXlsxPath(reportId: string): string | null {
  const filePath = join(reportAbsoluteDir(reportId), 'test_report.xlsx')
  if (!existsSync(filePath)) return null
  return filePath
}

/** 用系统默认应用打开本地 xlsx（在运行 Console 的机器上打开，非浏览器下载） */
export function openSelfCheckReportXlsx(reportId: string): string {
  const filePath = getSelfCheckReportXlsxPath(reportId)
  if (!filePath) {
    throw new Error('报告文件不存在')
  }
  openLocalPath(filePath)
  return filePath
}

function sanitizeCaseKeyForPath(caseKey: string): string {
  return caseKey.replace(/[\\/:"*?<>|]+/g, '_')
}

function assertPathUnderSelfCheckReports(targetPath: string): string {
  const root = resolve(selfCheckReportsRoot())
  const abs = resolve(targetPath)
  const rootPrefix = root.endsWith(sep) ? root : root + sep
  const absNorm = abs.toLowerCase()
  const rootNorm = root.toLowerCase()
  const prefixNorm = rootPrefix.toLowerCase()
  if (absNorm !== rootNorm && !absNorm.startsWith(prefixNorm)) {
    throw new Error('非法日志路径')
  }
  return abs
}

/** 打开报告中某用例的失败日志目录 */
export async function openSelfCheckCaseFailureLogs(reportId: string, caseKey: string): Promise<string> {
  const detail = await getSelfCheckReportDetail(reportId)
  if (!detail) {
    throw new Error('报告不存在')
  }
  const item = detail.allCaseItems.find(c => c.caseKey === caseKey)
  const reportDir = reportAbsoluteDir(reportId)
  const candidate = item?.failureLogDir
    || join(reportDir, 'failure-logs', sanitizeCaseKeyForPath(caseKey))
  const abs = assertPathUnderSelfCheckReports(candidate)
  if (!existsSync(abs)) {
    throw new Error('失败日志目录不存在')
  }
  openLocalPath(abs)
  return abs
}

/** 打开本机路径（文件用默认应用，目录用资源管理器） */
export function openLocalPath(targetPath: string): void {
  if (!existsSync(targetPath)) {
    throw new Error('路径不存在')
  }
  const plat = platform()
  let child
  if (plat === 'win32') {
    const isDir = statSync(targetPath).isDirectory()
    child = isDir
      ? spawn('explorer', [targetPath], { detached: true, stdio: 'ignore', windowsHide: true })
      : spawn('cmd', ['/c', 'start', '""', targetPath], {
          detached: true,
          stdio: 'ignore',
          windowsHide: true,
        })
  } else if (plat === 'darwin') {
    child = spawn('open', [targetPath], { detached: true, stdio: 'ignore' })
  } else {
    child = spawn('xdg-open', [targetPath], { detached: true, stdio: 'ignore' })
  }
  child.on('error', (err) => {
    throw new Error(`无法打开路径: ${err.message}`)
  })
  child.unref()
}
