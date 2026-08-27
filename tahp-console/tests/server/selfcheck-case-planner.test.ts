import { beforeAll, describe, it, expect } from 'vitest'
import {
  buildMustTestItems,
  listPipelineAdaptCaseKeys,
  listSmokeCaseKeys,
  mapDomainToPipelineAdaptModule,
  planCases,
  resolvePipelineAdaptModules,
} from '../../packages/server/src/services/tahp/selfcheck-case-planner'
import { initDeviceSelfCheck } from '../../packages/server/src/services/tahp/device-self-check'
import type { PipelineRun } from '../../packages/server/src/services/tahp/adapt-pipeline/types'

function makeRun(overrides: Partial<PipelineRun> = {}): PipelineRun {
  return {
    run_id: 'test-run',
    project_code: 'X6876_DEV',
    status: 'running',
    current_node: 'selfcheck',
    iteration: 1,
    max_iterations: 3,
    adapt_max_retries: 3,
    started_at: new Date().toISOString(),
    domains: [],
    stages: {},
    iterations: [],
    artifacts: {},
    build_context: {
      mapped_root: 'Z:\\project',
      workspace: 'test-ws',
      components: [],
      variant: 'userdebug',
    },
    ...overrides,
  }
}

describe('buildMustTestItems', () => {
  it('returns empty for no domains', () => {
    const run = makeRun({ domains: [] })
    expect(buildMustTestItems(run)).toEqual([])
  })

  it('extracts domain labels from done domains', () => {
    const run = makeRun({
      domains: [
        {
          domain_id: 'telephony', domain_label: '通信', module: 'telephony',
          enabled: true, status: 'done', workspace_id: 'ws1', form_data: {},
          related_skills: [],
        },
        {
          domain_id: 'audio', domain_label: '音频', module: 'telephony',
          enabled: true, status: 'skipped', workspace_id: 'ws1', form_data: {},
          related_skills: [],
        },
      ],
    })
    const items = buildMustTestItems(run)
    expect(items).toContain('通信')
    expect(items).not.toContain('音频')
  })

  it('extracts keywords from changed_files', () => {
    const run = makeRun({
      domains: [
        {
          domain_id: 'kernel', domain_label: '内核', module: 'kernel',
          enabled: true, status: 'done', workspace_id: 'ws1', form_data: {},
          related_skills: [],
          changed_files: ['drivers/spi_driver.c', 'include/dt.h'],
        },
      ],
    })
    const items = buildMustTestItems(run)
    expect(items).toContain('内核')
    expect(items).toContain('spi_driver')
  })

  it('deduplicates items', () => {
    const run = makeRun({
      domains: [
        {
          domain_id: 'd1', domain_label: '通信', module: 'telephony',
          enabled: true, status: 'done', workspace_id: 'ws1', form_data: {},
          related_skills: [],
          changed_files: ['a/Foo.java'],
        },
        {
          domain_id: 'd2', domain_label: '通信', module: 'telephony',
          enabled: true, status: 'done', workspace_id: 'ws1', form_data: {},
          related_skills: [],
          changed_files: ['b/Foo.java'],
        },
      ],
    })
    const items = buildMustTestItems(run)
    expect(items.filter(i => i === '通信').length).toBe(1)
    expect(items.filter(i => i === 'Foo').length).toBe(1)
  })

  it('skips short filenames (<3 chars)', () => {
    const run = makeRun({
      domains: [
        {
          domain_id: 'd1', domain_label: '测试', module: 'test',
          enabled: true, status: 'done', workspace_id: 'ws1', form_data: {},
          related_skills: [],
          changed_files: ['a/b.c'],
        },
      ],
    })
    const items = buildMustTestItems(run)
    expect(items).not.toContain('b')
  })

  it('ignores disabled domains', () => {
    const run = makeRun({
      domains: [
        {
          domain_id: 'd1', domain_label: '禁用域', module: 'test',
          enabled: false, status: 'done', workspace_id: 'ws1', form_data: {},
          related_skills: [],
        },
      ],
    })
    expect(buildMustTestItems(run)).toEqual([])
  })
})

describe('planCases smoke mode', () => {
  beforeAll(() => {
    initDeviceSelfCheck()
  })

  it('lists smoke catalog keys', () => {
    const cases = listSmokeCaseKeys()
    expect(cases.length).toBeGreaterThan(0)
    expect(cases.every(c => c.caseKey.startsWith('smoke/'))).toBe(true)
    expect(cases.some(c => c.caseKey === 'smoke/usd/1')).toBe(true)
  })

  it('plans only smoke cases when mode=smoke', async () => {
    const run = makeRun({
      test_plan: { mode: 'smoke' },
      domains: [
        {
          domain_id: 'telephony', domain_label: '通信', module: 'telephony',
          enabled: true, status: 'done', workspace_id: 'ws1', form_data: {},
          related_skills: [],
        },
      ],
    })
    const result = await planCases(run)
    expect(result.source).toBe('smoke')
    expect(result.plan.mode).toBe('smoke')
    expect(result.plan.test_type).toBe('smoke')
    expect(result.cases.length).toBeGreaterThan(0)
    expect(result.plan.selected_cases).toEqual(result.cases.map(c => c.caseKey))
    expect(result.cases.every(c => c.caseKey.startsWith('smoke/'))).toBe(true)
    expect(result.cases.every(c => !c.caseKey.startsWith('week/') && !c.caseKey.startsWith('str4/'))).toBe(true)
  })
})

describe('planCases pipeline_adapt mode', () => {
  beforeAll(() => {
    initDeviceSelfCheck()
  })

  it('lists pipeline_adapt catalog keys', () => {
    const cases = listPipelineAdaptCaseKeys()
    expect(cases.map(c => c.caseKey)).toEqual([
      'pipeline_adapt/tp/1',
      'pipeline_adapt/vibrator/1',
      'pipeline_adapt/audio/1',
      'pipeline_adapt/lcm/1',
      'pipeline_adapt/fingerprint/1',
      'pipeline_adapt/tdd/1',
      'pipeline_adapt/tdd/2',
      'pipeline_adapt/tdd/3',
      'pipeline_adapt/tdd/4',
      'pipeline_adapt/tdd/5',
    ])
    expect(cases.map(c => c.caseName)).toEqual([
      'TP适配检查',
      '马达适配检查',
      '音频适配检查',
      'LCM适配检查',
      '指纹/人脸适配检查',
      '基带版本号检查',
      'IMEI号检查',
      '拨打运营商服务号码',
      '检查收发短信',
      '检查上网',
    ])
  })

  it('maps debug domain ids to pipeline_adapt modules', () => {
    expect(mapDomainToPipelineAdaptModule('tp')).toBe('tp')
    expect(mapDomainToPipelineAdaptModule('vib')).toBe('vibrator')
    expect(mapDomainToPipelineAdaptModule('audio')).toBe('audio')
    expect(mapDomainToPipelineAdaptModule('lcm')).toBe('lcm')
    expect(mapDomainToPipelineAdaptModule('fp')).toBe('fingerprint')
    expect(mapDomainToPipelineAdaptModule('modem')).toBe('tdd')
    expect(mapDomainToPipelineAdaptModule('comm-framework')).toBe('tdd')
    expect(mapDomainToPipelineAdaptModule('telephony')).toBe('tdd')
    expect(mapDomainToPipelineAdaptModule('charging')).toBeUndefined()
  })

  it('resolves modules from enabled domains only, in catalog order', () => {
    const run = makeRun({
      domains: [
        {
          domain_id: 'audio', domain_label: '音频', module: 'kernel-driver',
          enabled: true, status: 'pending', workspace_id: 'ws1', form_data: {},
          related_skills: [],
        },
        {
          domain_id: 'tp', domain_label: 'TP触摸屏', module: 'kernel-driver',
          enabled: true, status: 'pending', workspace_id: 'ws1', form_data: {},
          related_skills: [],
        },
        {
          domain_id: 'vib', domain_label: '振动马达', module: 'kernel-driver',
          enabled: false, status: 'pending', workspace_id: 'ws1', form_data: {},
          related_skills: [],
        },
        {
          domain_id: 'charging', domain_label: '充电', module: 'kernel-driver',
          enabled: true, status: 'pending', workspace_id: 'ws1', form_data: {},
          related_skills: [],
        },
      ],
    })
    expect(resolvePipelineAdaptModules(run)).toEqual(['tp', 'audio'])
  })

  it('plans only cases for enabled debug domains', async () => {
    const run = makeRun({
      test_plan: { mode: 'pipeline_adapt' },
      domains: [
        {
          domain_id: 'tp', domain_label: 'TP触摸屏', module: 'kernel-driver',
          enabled: true, status: 'done', workspace_id: 'ws1', form_data: {},
          related_skills: [],
        },
        {
          domain_id: 'lcm', domain_label: 'LCM', module: 'kernel-driver',
          enabled: true, status: 'done', workspace_id: 'ws1', form_data: {},
          related_skills: [],
        },
        {
          domain_id: 'audio', domain_label: '音频', module: 'kernel-driver',
          enabled: false, status: 'pending', workspace_id: 'ws1', form_data: {},
          related_skills: [],
        },
      ],
    })
    const result = await planCases(run)
    expect(result.source).toBe('pipeline_adapt')
    expect(result.plan.mode).toBe('pipeline_adapt')
    expect(result.plan.test_type).toBe('pipeline_adapt')
    expect(result.plan.selected_cases).toEqual(['pipeline_adapt/tp/1', 'pipeline_adapt/lcm/1'])
    expect(result.cases.map(c => c.caseKey)).toEqual(['pipeline_adapt/tp/1', 'pipeline_adapt/lcm/1'])
  })

  it('maps vib/fp domain ids to vibrator/fingerprint cases', async () => {
    const run = makeRun({
      test_plan: { mode: 'pipeline_adapt' },
      domains: [
        {
          domain_id: 'vib', domain_label: '振动马达', module: 'kernel-driver',
          enabled: true, status: 'done', workspace_id: 'ws1', form_data: {},
          related_skills: [],
        },
        {
          domain_id: 'fp', domain_label: '指纹', module: 'kernel-driver',
          enabled: true, status: 'done', workspace_id: 'ws1', form_data: {},
          related_skills: [],
        },
      ],
    })
    const result = await planCases(run)
    expect(result.plan.selected_cases).toEqual([
      'pipeline_adapt/vibrator/1',
      'pipeline_adapt/fingerprint/1',
    ])
  })

  it('does not run all modules when no enabled domain maps to pipeline_adapt', async () => {
    const run = makeRun({
      test_plan: { mode: 'pipeline_adapt' },
      domains: [
        {
          domain_id: 'charging', domain_label: '充电', module: 'kernel-driver',
          enabled: true, status: 'done', workspace_id: 'ws1', form_data: {},
          related_skills: [],
        },
      ],
    })
    const result = await planCases(run)
    expect(result.source).toBe('pipeline_adapt_empty')
    expect(result.cases).toEqual([])
    expect(result.plan.selected_cases).toEqual([])
  })
})
