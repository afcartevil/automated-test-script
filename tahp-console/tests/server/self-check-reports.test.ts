import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import {
  buildSelfCheckDetailPayload,
  encodeReportId,
  getSelfCheckReportDetail,
  listSelfCheckReports,
  submitSelfCheckReportReview,
} from '../../packages/server/src/services/tahp/self-check-reports'

describe('self-check-reports', () => {
  let tempDir: string
  let prevProjectRoot: string | undefined

  beforeEach(() => {
    tempDir = join(tmpdir(), `tahp-self-check-reports-${Date.now()}`)
    mkdirSync(join(tempDir, 'reports', 'self-check', 'dev-1', '2026-06-25T10-00-00'), { recursive: true })
    prevProjectRoot = process.env.TAHP_PROJECT_ROOT
    process.env.TAHP_PROJECT_ROOT = tempDir

    const summary = {
      deviceId: 'dev-1',
      deviceName: 'Test Phone',
      testType: 'week',
      startTime: '2026-06-25T10:00:00.000Z',
      endTime: '2026-06-25T11:00:00.000Z',
      duration: 3600,
      status: '完成(失败)',
      totalCases: 3,
      passedCases: 2,
      failedCases: 1,
      skippedCases: 0,
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
  })

  it('loads report detail with ai summary and failed cases', async () => {
    const rel = 'self-check/dev-1/2026-06-25T10-00-00'
    const reportId = encodeReportId(rel)
    const detail = await getSelfCheckReportDetail(reportId)
    expect(detail?.aiSummary).toContain('失败 1')
    expect(detail?.failedCaseItems).toHaveLength(1)
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
})
