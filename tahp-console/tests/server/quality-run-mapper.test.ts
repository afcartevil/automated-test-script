import { describe, expect, it } from 'vitest'
import {
  buildSelfCheckRunId,
  mapSelfCheckReportToQualityRun,
  mapSelfCheckStatusToRunStatus,
  matchCentralProject,
  parseProjectFromScheduleKey,
  UNASSIGNED_PROJECT,
} from '../../packages/server/src/services/tahp/quality-run-mapper'

describe('quality-run-mapper', () => {
  it('parses project from scheduleKey', () => {
    expect(parseProjectFromScheduleKey('X6876|STR4A|2026/06/28|monkey')).toBe('X6876')
    expect(parseProjectFromScheduleKey('')).toBeUndefined()
  })

  it('builds safe run_id', () => {
    const id = buildSelfCheckRunId('ABC:123', '2026-07-23T10-00-00.000Z')
    expect(id).toBe('sc-ABC_123-2026-07-23T10-00-00.000Z')
    expect(id.length).toBeLessThanOrEqual(180)
  })

  it('maps status', () => {
    expect(mapSelfCheckStatusToRunStatus('完成(通过)', 0, 10)).toBe('pass')
    expect(mapSelfCheckStatusToRunStatus('完成(失败)', 3, 10)).toBe('partial')
    expect(mapSelfCheckStatusToRunStatus('完成(失败)', 10, 10)).toBe('fail')
  })

  it('matches central project by code/prefix', () => {
    const projects = [
      { code: 'X6850Android16', name: 'X6850 A16', active_campaign_id: 'android-15-to-16' },
      { code: 'X6876', name: 'X6876', active_campaign_id: null },
    ]
    expect(matchCentralProject('X6876', projects)).toEqual({
      project_code: 'X6876',
      campaign_id: undefined,
    })
    expect(matchCentralProject('X6850', projects)?.project_code).toBe('X6850Android16')
    expect(matchCentralProject('UNKNOWN', projects)).toBeNull()
  })

  it('maps self-check report to quality run contract', () => {
    const run = mapSelfCheckReportToQualityRun({
      summary: {
        deviceId: 'dev-1',
        deviceName: 'Phone',
        testType: 'week',
        startTime: '2026-07-23T10:00:00.000Z',
        endTime: '2026-07-23T11:00:00.000Z',
        status: '完成(失败)',
        totalCases: 3,
        passedCases: 2,
        failedCases: 1,
        skippedCases: 0,
        project_code: 'X6876',
        campaign_id: 'android-15-to-16',
      },
      detail: {
        aiSummary: '失败 1 项',
        failedCaseItems: [{
          caseKey: 'week/driver/1',
          caseName: '驱动用例',
          module: 'driver',
          status: '失败',
          message: 'timeout',
        }],
      },
      sessionDir: '2026-07-23T10-00-00',
      reportRelPath: 'self-check/dev-1/2026-07-23T10-00-00',
      owner: 'neng.zhou@PC',
    })

    expect(run.dimension).toBe('self-check')
    expect(run.project_code).toBe('X6876')
    expect(run.campaign_id).toBe('android-15-to-16')
    expect(run.status).toBe('partial')
    expect(run.metrics?.pass_rate).toBeCloseTo(0.667, 2)
    expect(run.issues).toHaveLength(1)
    expect(run.issues?.[0].severity).toBe('critical')
    expect(run.run_id).toContain('sc-dev-1-')
  })

  it('falls back to unassigned project', () => {
    const run = mapSelfCheckReportToQualityRun({
      summary: {
        deviceId: 'd',
        deviceName: 'n',
        testType: 'smoke',
        status: '完成(通过)',
        totalCases: 1,
        passedCases: 1,
        failedCases: 0,
        skippedCases: 0,
      },
      sessionDir: 's',
      reportRelPath: 'self-check/d/s',
    })
    expect(run.project_code).toBe(UNASSIGNED_PROJECT)
    expect(run.status).toBe('pass')
  })
})
