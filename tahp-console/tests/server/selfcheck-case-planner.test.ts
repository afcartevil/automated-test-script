import { beforeAll, describe, it, expect } from 'vitest'
import {
  buildMustTestItems,
  listSmokeCaseKeys,
  planCases,
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
