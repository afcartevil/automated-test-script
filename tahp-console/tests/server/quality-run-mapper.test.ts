import { describe, expect, it, vi } from 'vitest'
import {
  buildAdaptDebugRunId,
  buildGkiPatchRunId,
  buildModemPatchRunId,
  buildSelfCheckRunId,
  isGkiTerminal,
  isModemTerminal,
  mapAdaptDebugReportToQualityRun,
  mapGkiUpgradeJobToQualityRun,
  mapModemBaselineMetaToQualityRun,
  mapSelfCheckReportToQualityRun,
  mapSelfCheckStatusToRunStatus,
  matchCentralProject,
  parseProjectFromScheduleKey,
  UNASSIGNED_PROJECT,
} from '../../packages/server/src/services/tahp/quality-run-mapper'
import {
  buildAdaptPipelineDomainRunId,
  buildAdaptPipelineMachineRunId,
  isPipelineTerminal,
  mapPipelineRunToQualityRuns,
} from '../../packages/server/src/services/tahp/adapt-pipeline/quality-mapper'
import type { PipelineRun } from '../../packages/server/src/services/tahp/adapt-pipeline/types'

vi.mock('../../packages/server/src/services/tahp/sync/central-client', () => ({
  centralClient: {
    listAdaptPrereqProjects: vi.fn(async () => [
      { code: 'X6850Android16', name: 'X6850', active_campaign_id: 'camp-1' },
    ]),
  },
}))

function minimalPipelineRun(overrides?: Partial<PipelineRun>): PipelineRun {
  return {
    run_id: 'run-test-001',
    workflow_id: 'adapt-default',
    workflow_version: 1,
    project_code: 'X6850Android16',
    campaign_id: 'camp-1',
    status: 'passed',
    current_node: 'gerrit',
    iteration: 1,
    max_iterations: 3,
    adapt_max_retries: 3,
    created_at: '2026-08-18T10:00:00.000Z',
    updated_at: '2026-08-18T12:00:00.000Z',
    finished_at: '2026-08-18T12:00:00.000Z',
    domains: [
      {
        workspace_id: 'adapt-debug',
        domain_id: 'tp',
        domain_label: 'TP',
        module: 'tp',
        related_skills: [],
        form_data: {},
        incomplete_required: [],
        enabled: true,
        status: 'done',
        adapt_task_id: 'ad-tp-1',
        changed_files: ['vendor/tp/a.cpp'],
      },
      {
        workspace_id: 'adapt-debug',
        domain_id: 'display',
        domain_label: 'Display',
        module: 'display',
        related_skills: [],
        form_data: {},
        incomplete_required: [],
        enabled: true,
        status: 'failed',
        error: 'adapt failed',
      },
      {
        workspace_id: 'adapt-debug',
        domain_id: 'nfc',
        domain_label: 'NFC',
        module: 'nfc',
        related_skills: [],
        form_data: {},
        incomplete_required: [],
        enabled: true,
        status: 'pending',
      },
    ],
    build_context: { mapped_root: '/z', workspace: 'ws', variant: 'userdebug' },
    stages: {
      prereq: { key: 'prereq', status: 'done', attempt: 1, refs: {}, finished_at: '2026-08-18T10:05:00.000Z' },
      adapt: { key: 'adapt', status: 'done', attempt: 1, refs: {} },
      build: { key: 'build', status: 'done', attempt: 1, refs: { build_run_id: 'bld-1' } },
      flash: { key: 'flash', status: 'done', attempt: 1, refs: {} },
      selfcheck: { key: 'selfcheck', status: 'done', attempt: 1, refs: { selfcheck_report_id: 'sc-1' } },
      gerrit: { key: 'gerrit', status: 'done', attempt: 1, refs: {} },
    },
    iterations: [],
    artifacts: {},
    gerrit_changes: [{
      domain_id: 'tp',
      repo: 'vendor/transsion/tp',
      change_url: 'https://gerrit.transsion.com/c/vendor/transsion/tp/+/884120',
      change_number: '884120',
      status: 'submitted',
      files: [],
    }],
    ...overrides,
  }
}

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
      owner: 'neng.zhou',
    })

    expect(run.dimension).toBe('self-check')
    expect(run.project_code).toBe('X6876')
    expect(run.status).toBe('partial')
    expect(run.metrics?.pass_rate).toBeCloseTo(0.667, 2)
    expect(run.issues).toHaveLength(1)
  })

  it('maps adapt-debug without pass_rate pollution', () => {
    const run = mapAdaptDebugReportToQualityRun({
      taskId: 'task-1',
      status: 'completed',
      workspaceId: 'adapt-debug',
      domainId: 'tp',
      filesModified: ['a.cpp'],
      auditReport: '',
      owner: 'ming.li',
    })
    expect(run.dimension).toBe('adapt-debug')
    expect(run.run_id).toBe(buildAdaptDebugRunId('task-1'))
    expect(run.metrics?.pass_rate).toBeUndefined()
    expect(run.metrics?.files_total).toBe(1)
  })

  it('maps modem conflict to blocked', () => {
    const run = mapModemBaselineMetaToQualityRun({
      runId: 'r1',
      status: 'conflict',
      mode: 'stop_after_merge',
      phase: 'conflict',
      createdAt: '2026-08-18T10:00:00.000Z',
      config: {
        NODE_BRANCH: 'n',
        target_BRANCH: 't',
        AP_lable: 'X6850',
        JIRAID: 'J-1',
        work_dir: '/w',
      },
      conflictFiles: ['a.c', 'b.c'],
    }, 'wei.chen', 'X6850')
    expect(run.status).toBe('blocked')
    expect(run.metrics?.conflict_count).toBe(2)
    expect(run.metrics?.pass_rate).toBeUndefined()
    expect(run.run_id).toBe(buildModemPatchRunId('r1'))
  })

  it('maps gki with applied_commits keys', () => {
    const run = mapGkiUpgradeJobToQualityRun({
      id: 42,
      status: 'applied',
      applied_commits: 18,
      total_commits: 24,
      conflict_files: ['x.c'],
    }, 'hao.wang', 'GKI')
    expect(run.status).toBe('pass')
    expect(run.metrics?.applied_commits).toBe(18)
    expect(run.metrics?.total_commits).toBe(24)
    expect(run.metrics?.pass_rate).toBeUndefined()
    expect(isGkiTerminal('applied')).toBe(true)
    expect(isGkiTerminal('running')).toBe(false)
  })

  it('modem terminal helper', () => {
    expect(isModemTerminal('success')).toBe(true)
    expect(isModemTerminal('running')).toBe(false)
  })
})

describe('adapt-pipeline quality mapper', () => {
  it('returns empty for non-terminal pipeline', async () => {
    const runs = await mapPipelineRunToQualityRuns(minimalPipelineRun({ status: 'running' }))
    expect(runs).toEqual([])
    expect(isPipelineTerminal('running')).toBe(false)
  })

  it('maps terminal pipeline to machine + domain runs', async () => {
    const runs = await mapPipelineRunToQualityRuns(minimalPipelineRun(), 'neng.zhou')
    expect(runs.length).toBe(3)
    const machine = runs[0]
    expect(machine.parent_run_id).toBeUndefined()
    expect(machine.dimension).toBe('adapt-pipeline')
    expect(machine.metrics?.pass_rate).toBeUndefined()
    expect(machine.metrics?.domains_done).toBe(1)
    expect(machine.run_id).toBe(buildAdaptPipelineMachineRunId('run-test-001'))

    const tp = runs.find(r => r.domain_id === 'tp')
    expect(tp?.status).toBe('pass')
    expect(tp?.parent_run_id).toBe(machine.run_id)
    expect(tp?.artifacts?.some(a => a.ref?.includes('884120'))).toBe(true)
    const extra = tp?.extra?.pipeline as { stages?: unknown[] }
    expect(extra?.stages?.length).toBe(6)

    const display = runs.find(r => r.domain_id === 'display')
    expect(display?.status).toBe('fail')
    expect(display?.artifacts?.some(a => a.type === 'gerrit' && a.ref?.startsWith('http'))).toBe(false)
  })

  it('flash fail keeps adapt reports on domain', async () => {
    const run = minimalPipelineRun({
      status: 'failed',
      stages: {
        ...minimalPipelineRun().stages,
        flash: { key: 'flash', status: 'failed', attempt: 1, refs: {}, error: 'flash fail' },
        selfcheck: { key: 'selfcheck', status: 'pending', attempt: 0, refs: {} },
        gerrit: { key: 'gerrit', status: 'pending', attempt: 0, refs: {} },
      },
    })
    const runs = await mapPipelineRunToQualityRuns(run)
    const tp = runs.find(r => r.domain_id === 'tp')
    const extra = tp?.extra?.pipeline as { stages?: Array<{ key: string; status: string }> }
    const adapt = extra?.stages?.find(s => s.key === 'adapt')
    expect(adapt?.status).toBe('done')
    const gerrit = extra?.stages?.find(s => s.key === 'gerrit')
    expect(gerrit?.status).toBe('pending')
  })

  it('emits readable stage cards and prereq snapshot', async () => {
    const base = minimalPipelineRun()
    const run = minimalPipelineRun({
      from_os: 'Android 16',
      to_os: 'Android 17',
      device_id: 'X6879A001',
      domains: base.domains.map(d => d.domain_id === 'tp'
        ? {
          ...d,
          related_skills: ['tp-adapt-bringup'],
          layout_fields: [
            { name: 'debug_project', label: '调试项目名', required: true },
            { name: 'ic_vendor', label: 'IC厂商', required: true },
          ],
          form_data: { debug_project: 'X6879', ic_vendor: 'Goodix' },
        }
        : d),
      stages: {
        ...base.stages,
        prereq: {
          key: 'prereq',
          status: 'done',
          attempt: 1,
          refs: {},
          summary: { domain_count: 2, from_os: 'Android 16', to_os: 'Android 17' },
          finished_at: '2026-08-18T10:05:00.000Z',
        },
        build: {
          key: 'build',
          status: 'done',
          attempt: 1,
          refs: { build_run_id: 'bld-1' },
          summary: {
            artifactsDir: 'Z:\\ea-build\\out',
            durationMs: 120000,
            skillId: 'ez-build',
            notes: 'ea-build tmux=ezb-1 targets=sys,krn,pack',
          },
        },
        flash: { key: 'flash', status: 'done', attempt: 1, refs: {}, summary: '0' },
      },
    })
    const runs = await mapPipelineRunToQualityRuns(run, 'neng.zhou')
    const machine = runs[0]
    const extra = machine.extra?.pipeline as {
      prereq?: { domains?: Array<{ domain_id: string; form_data?: Record<string, string> }> }
      stages?: Array<{
        key: string
        summary: string
        headline?: string
        facts?: Array<{ label: string; value: string }>
        error_brief?: string
      }>
    }
    expect(extra?.prereq?.domains?.some(d => d.domain_id === 'tp' && d.form_data?.ic_vendor === 'Goodix')).toBe(true)
    const prereq = extra?.stages?.find(s => s.key === 'prereq')
    expect(prereq?.headline).toContain('前置完成')
    expect(prereq?.summary.startsWith('{')).toBe(false)
    const build = extra?.stages?.find(s => s.key === 'build')
    expect(build?.headline).toContain('编译通过')
    expect(build?.facts?.some(f => f.label === '产物目录')).toBe(true)
    const flash = extra?.stages?.find(s => s.key === 'flash')
    expect(flash?.headline).toContain('摘要无法解读')
  })

  it('handles terminal run with disabled stages (missing keys, current_node null)', async () => {
    const run = minimalPipelineRun({
      status: 'passed',
      current_node: null,
      domains: [{
        workspace_id: 'adapt-debug',
        domain_id: 'tp',
        domain_label: 'TP触摸屏',
        module: 'kernel-driver',
        related_skills: [],
        form_data: {},
        incomplete_required: [],
        enabled: true,
        status: 'pending',
      }],
      stages: {
        prereq: { key: 'prereq', status: 'done', attempt: 1, refs: {}, summary: { domain_count: 1 } },
        selfcheck: { key: 'selfcheck', status: 'done', attempt: 1, refs: {}, summary: { total: 1, passed: 1, failed: 0 } },
      },
    })
    const runs = await mapPipelineRunToQualityRuns(run, 'neng.zhou')
    expect(runs.length).toBe(1)
    expect(runs[0].run_id).toBe(buildAdaptPipelineMachineRunId('run-test-001'))
    expect(runs[0].status).toBe('pass')
    expect(runs[0].current_node).toBe('selfcheck')
  })
})
