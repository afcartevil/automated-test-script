import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import {
  buildSelfCheckDetailPayload,
  encodeReportId,
  getSelfCheckReportDetail,
  listSelfCheckReports,
  openSelfCheckReportXlsx,
  submitSelfCheckReportReview,
  isPendingManualReportFillIn,
  PENDING_MANUAL_REPORT_MSG,
  shouldOmitFromSelfCheckReport,
  updateReportCaseResult,
} from '../../packages/server/src/services/tahp/self-check-reports'

describe('self-check-reports', () => {
  it('shouldOmitFromSelfCheckReport only for platform-mismatch NA', () => {
    expect(shouldOmitFromSelfCheckReport({
      status: 'NA',
      message: '非本机平台用例（设备=高通，用例适用=MTK）',
    })).toBe(true)
    expect(shouldOmitFromSelfCheckReport({
      status: 'NA',
      message: '设备不支持（NA）',
    })).toBe(false)
    expect(shouldOmitFromSelfCheckReport({
      status: '通过',
      message: '非本机平台用例',
    })).toBe(false)
  })

  let tempDir: string
  let prevProjectRoot: string | undefined

  beforeEach(() => {
    tempDir = join(tmpdir(), `tahp-self-check-reports-${Date.now()}`)
    // 满足 isValidTahpProjectRoot，否则会回退到真实工程根，读写对不上
    mkdirSync(join(tempDir, 'skills', '.claude', 'skills'), { recursive: true })
    mkdirSync(join(tempDir, 'tahp-console', 'packages', 'server'), { recursive: true })
    mkdirSync(join(tempDir, 'reports', 'self-check', 'dev-1', '2026-06-25T10-00-00'), { recursive: true })
    prevProjectRoot = process.env.TAHP_PROJECT_ROOT
    process.env.TAHP_PROJECT_ROOT = tempDir

    const summary = {
      deviceId: 'dev-1',
      deviceName: 'Test Phone',
      testType: 'week',
      version: 'X6885-15.1.2.001',
      testConfig: {
        autoRetestEnabled: true,
        autoRetestCount: 2,
      },
      startTime: '2026-06-25T10:00:00.000Z',
      endTime: '2026-06-25T11:00:00.000Z',
      duration: 3600,
      status: '完成(失败)',
      totalCases: 3,
      passedCases: 2,
      failedCases: 1,
      skippedCases: 0,
      aiPlanned: true,
      scheduleKey: 'X6876|STR4A|2026/06/28|monkey',
    }
    const failed = [{
      caseKey: 'week/driver/1',
      caseName: 'Case 1',
      module: 'driver',
      status: '失败',
      message: 'timeout',
    }]
    const reportDir = join(tempDir, 'reports', 'self-check', 'dev-1', '2026-06-25T10-00-00')
    writeFileSync(join(reportDir, 'summary.json'), JSON.stringify(summary))
    writeFileSync(join(reportDir, 'detail.json'), JSON.stringify(buildSelfCheckDetailPayload(summary, failed)))
  })

  afterEach(() => {
    if (prevProjectRoot === undefined) delete process.env.TAHP_PROJECT_ROOT
    else process.env.TAHP_PROJECT_ROOT = prevProjectRoot
    if (existsSync(tempDir)) rmSync(tempDir, { recursive: true, force: true })
  })

  it('lists self-check reports from summary.json', async () => {
    const items = await listSelfCheckReports()
    expect(items).toHaveLength(1)
    expect(items[0]?.deviceName).toBe('Test Phone')
    expect(items[0]?.failedCases).toBe(1)
    expect(items[0]?.reviewStatus).toBe('pending')
    expect(items[0]?.aiPlanned).toBe(true)
    expect(items[0]?.scheduleKey).toContain('monkey')
  })

  it('loads report detail with ai summary and failed cases', async () => {
    const rel = 'self-check/dev-1/2026-06-25T10-00-00'
    const reportId = encodeReportId(rel)
    const detail = await getSelfCheckReportDetail(reportId)
    expect(detail?.aiSummary).toContain('失败 1')
    expect(detail?.failedCaseItems).toHaveLength(1)
    expect(detail?.allCaseItems?.length).toBeGreaterThanOrEqual(1)
    expect(detail?.version).toBe('X6885-15.1.2.001')
    expect(detail?.testConfig?.autoRetestEnabled).toBe(true)
    expect(detail?.testConfig?.autoRetestCount).toBe(2)
  })

  it('buildSelfCheckDetailPayload copies version from summary', () => {
    const summary = {
      deviceId: 'd1',
      deviceName: 'Phone',
      testType: 'str4',
      version: 'OTA-1.0',
      status: '完成(通过)',
      totalCases: 1,
      passedCases: 1,
      failedCases: 0,
      skippedCases: 0,
    }
    const detail = buildSelfCheckDetailPayload(summary, [])
    expect(detail.version).toBe('OTA-1.0')
  })

  it('persists manual review conclusion', async () => {
    const rel = 'self-check/dev-1/2026-06-25T10-00-00'
    const reportId = encodeReportId(rel)
    const saved = await submitSelfCheckReportReview(reportId, {
      status: 'reviewed',
      note: '可合入',
    })
    expect(saved?.reviewStatus).toBe('reviewed')
    expect(saved?.reviewNote).toBe('可合入')

    const pending = await listSelfCheckReports({ pendingOnly: true })
    expect(pending).toHaveLength(0)
  })

  it('resolves xlsx path for local open', () => {
    const rel = 'self-check/dev-1/2026-06-25T10-00-00'
    const reportId = encodeReportId(rel)
    const reportDir = join(tempDir, 'reports', rel)
    const xlsxPath = join(reportDir, 'test_report.xlsx')
    writeFileSync(xlsxPath, 'xlsx')

    const opened = openSelfCheckReportXlsx(reportId)
    expect(opened).toBe(xlsxPath)
    expect(existsSync(opened)).toBe(true)
  })

  it('rejects open when xlsx is missing', () => {
    const rel = 'self-check/dev-1/2026-06-25T10-00-00'
    const reportId = encodeReportId(rel)
    expect(() => openSelfCheckReportXlsx(reportId)).toThrow('报告文件不存在')
  })

  it('excludes deferred manual fill-in from failed counts until reviewed', async () => {
    const rel = 'self-check/dev-1/2026-06-25T10-00-00'
    const reportId = encodeReportId(rel)
    const reportDir = join(tempDir, 'reports', rel)
    const summary = {
      deviceId: 'dev-1',
      deviceName: 'Test Phone',
      testType: 'kernel_feature',
      status: '完成(通过)',
      totalCases: 2,
      passedCases: 1,
      failedCases: 0,
      skippedCases: 0,
      pendingManualCases: 1,
    }
    const allCaseItems = [
      {
        caseKey: 'kernel_feature/stability/1',
        caseName: 'log配置',
        module: 'stability',
        testType: 'kernel_feature',
        caseIndex: 1,
        status: '通过',
        message: 'ok',
        automationMode: 'full' as const,
      },
      {
        caseKey: 'kernel_feature/stability/2',
        caseName: '三键uart',
        module: 'stability',
        testType: 'kernel_feature',
        caseIndex: 2,
        status: '待确认',
        message: PENDING_MANUAL_REPORT_MSG,
        automationMode: 'manual' as const,
      },
    ]
    expect(isPendingManualReportFillIn(allCaseItems[1]!)).toBe(true)
    writeFileSync(join(reportDir, 'summary.json'), JSON.stringify(summary))
    writeFileSync(
      join(reportDir, 'detail.json'),
      JSON.stringify(buildSelfCheckDetailPayload(summary, [], allCaseItems)),
    )

    let detail = await getSelfCheckReportDetail(reportId)
    expect(detail?.failedCaseItems).toHaveLength(0)

    detail = await updateReportCaseResult(reportId, 'kernel_feature/stability/2', '通过', '人工补录通过')
    expect(detail?.failedCases).toBe(0)
    expect(detail?.allCaseItems?.find(c => c.caseKey === 'kernel_feature/stability/2')?.status).toBe('通过')
  })

  it('omits platform-mismatch NA cases from report detail and counts', async () => {
    const rel = 'self-check/dev-1/2026-06-25T10-00-00'
    const reportId = encodeReportId(rel)
    const reportDir = join(tempDir, 'reports', rel)
    const summary = {
      deviceId: 'dev-1',
      deviceName: 'Test Phone',
      testType: 'kernel_feature',
      status: '完成(通过)',
      totalCases: 3,
      passedCases: 3,
      failedCases: 0,
      skippedCases: 0,
    }
    const allCaseItems = [
      {
        caseKey: 'kernel_feature/stability/11',
        caseName: 'tranpdb',
        module: 'stability',
        testType: 'kernel_feature',
        caseIndex: 11,
        status: '通过',
        message: 'ok',
        automationMode: 'full' as const,
      },
      {
        caseKey: 'kernel_feature/stability/3',
        caseName: 'mtk-only',
        module: 'stability',
        testType: 'kernel_feature',
        caseIndex: 3,
        status: 'NA',
        message: '非本机平台用例（设备=高通，用例适用=MTK）',
        automationMode: 'full' as const,
      },
      {
        caseKey: 'kernel_feature/stability/5',
        caseName: 'device-na',
        module: 'stability',
        testType: 'kernel_feature',
        caseIndex: 5,
        status: 'NA',
        message: '设备不支持（NA）',
        automationMode: 'full' as const,
      },
    ]
    writeFileSync(join(reportDir, 'summary.json'), JSON.stringify(summary))
    writeFileSync(
      join(reportDir, 'detail.json'),
      JSON.stringify(buildSelfCheckDetailPayload(summary, [], allCaseItems)),
    )

    const detail = await getSelfCheckReportDetail(reportId)
    expect(detail?.allCaseItems?.map(c => c.caseIndex)).toEqual([11, 5])
    expect(detail?.totalCases).toBe(2)
    expect(detail?.passedCases).toBe(2)

    const listed = await listSelfCheckReports()
    expect(listed[0]?.totalCases).toBe(2)
    expect(listed[0]?.passedCases).toBe(2)
  })
})
