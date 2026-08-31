import { describe, expect, it } from 'vitest'
import type { PipelineRunRecord } from '../../packages/client/src/api/tahp/adapt-pipeline'
import {
  buildWizardCloneSeed,
  isCloneableRunId,
  overlayCloneDomains,
  resolveClonedTestPlanMode,
  workspacesFromCloneDomains,
  type CloneOverlayDomain,
} from '../../packages/client/src/utils/pipeline-clone'

function sampleRun(overrides: Partial<PipelineRunRecord> = {}): PipelineRunRecord {
  return {
    run_id: 'run-1',
    project_code: 'KM9',
    campaign_id: 'camp-1',
    from_os: '15.0',
    to_os: '16.0',
    status: 'failed',
    max_iterations: 4,
    adapt_max_retries: 2,
    domains: [
      {
        workspace_id: 'adapt-debug',
        domain_id: 'tp',
        domain_label: 'TP',
        module: 'kernel-driver',
        related_skills: ['tp-adapt'],
        form_data: { OLD_VENDOR_ROOT: 'Z:\\old', note: 12 },
        incomplete_required: [],
        enabled: true,
      },
      {
        workspace_id: 'carrier-config',
        domain_id: 'apn-config',
        domain_label: 'APN',
        module: 'telephony',
        related_skills: [],
        form_data: {},
        incomplete_required: ['name'],
        enabled: false,
      },
    ],
    build_context: {
      mapped_root: '',
      workspace: '',
      variant: 'user',
      build_flag: 'fooding',
      vendor_path: 'Z:\\new\\vendor',
      system_path: 'Z:\\new\\sys',
      trsys_root_path: 'Z:\\trsys',
      build_targets: ['sys', 'krn'],
      need_pack: false,
      flash_skill_id: 'asf-device',
      target_branch: 'dev/km9',
      gerrit_issue_id: 'TOS1501-1',
    },
    path_params: {
      inputs: {
        project_code: 'KM9',
        OLD_VENDOR_ROOT: 'Z:\\old\\vendor',
        NEW_VENDOR_ROOT: 'Z:\\new\\vendor',
        NEW_SYSTEM_ROOT: 'Z:\\new\\sys',
        NEW_TRSYSTEM_ROOT: 'Z:\\trsys',
        PROJECT_FULL: 'KM9_DEV',
      },
      fields: [
        { key: 'PROJECT_FULL', label: '项目目录', kind: 'select', ok: true, value: 'KM9_DEV' },
      ],
      parsed_at: '2026-08-25T00:00:00.000Z',
    },
    device_id: 'SN123',
    test_plan: { mode: 'pipeline_adapt', test_type: 'pipeline_adapt' },
    ...overrides,
  }
}

describe('pipeline clone seed', () => {
  it('rejects mock preview run ids', () => {
    expect(isCloneableRunId('__mock_preview__')).toBe(false)
    expect(isCloneableRunId('run-abc')).toBe(true)
  })

  it('copies every wizard step field from a persisted run', () => {
    const run = sampleRun()
    const seed = buildWizardCloneSeed(run)
    expect(seed.project_code).toBe('KM9')
    expect(seed.campaign_id).toBe('camp-1')
    expect(seed.from_os).toBe('15.0')
    expect(seed.to_os).toBe('16.0')
    expect(seed.old_vendor_root).toBe('Z:\\old\\vendor')
    expect(seed.new_vendor_root).toBe('Z:\\new\\vendor')
    expect(seed.new_system_root).toBe('Z:\\new\\sys')
    expect(seed.new_trsystem_root).toBe('Z:\\trsys')
    expect(seed.path_params?.fields[0]?.value).toBe('KM9_DEV')
    expect(seed.workspaces).toEqual(['adapt-debug'])
    expect(seed.domains.find(d => d.domain_id === 'tp')?.form_data.note).toBe(12)
    expect(seed.build_context.variant).toBe('user')
    expect(seed.build_context.build_targets).toEqual(['sys', 'krn'])
    expect(seed.build_context.need_pack).toBe(false)
    expect(seed.device_id).toBe('SN123')
    expect(seed.test_plan?.mode).toBe('pipeline_adapt')
    expect(seed.max_iterations).toBe(4)
    expect(seed.adapt_max_retries).toBe(2)
    seed.build_context.build_targets?.push('odm')
    expect(run.build_context.build_targets).toEqual(['sys', 'krn'])
  })

  it('falls back to build_context paths when path_params is missing', () => {
    const seed = buildWizardCloneSeed(sampleRun({ path_params: undefined }))
    expect(seed.old_vendor_root).toBe('')
    expect(seed.new_vendor_root).toBe('Z:\\new\\vendor')
    expect(seed.new_system_root).toBe('Z:\\new\\sys')
    expect(seed.new_trsystem_root).toBe('Z:\\trsys')
  })

  it('defaults adapt_max_retries to 3 when the source run has no value', () => {
    const seed = buildWizardCloneSeed(sampleRun({ adapt_max_retries: undefined }))
    expect(seed.adapt_max_retries).toBe(3)
  })

  it('picks workspaces from enabled domains, then any domain, then default', () => {
    expect(workspacesFromCloneDomains([
      { workspace_id: 'carrier-config', enabled: true },
      { workspace_id: 'feature-adapt', enabled: false },
    ])).toEqual(['carrier-config'])
    expect(workspacesFromCloneDomains([
      { workspace_id: 'feature-adapt', enabled: false },
    ])).toEqual(['feature-adapt'])
    expect(workspacesFromCloneDomains([])).toEqual(['adapt-debug'])
  })

  it('keeps unknown test plan modes as smoke', () => {
    expect(resolveClonedTestPlanMode('pipeline_adapt')).toBe('pipeline_adapt')
    expect(resolveClonedTestPlanMode('nope')).toBe('smoke')
  })

  it('overlays cloned domain enablement and form data onto catalog', () => {
    const catalog: CloneOverlayDomain[] = [
      {
        workspace_id: 'adapt-debug',
        domain_id: 'tp',
        domain_label: 'TP',
        module: 'kernel-driver',
        related_skills: [],
        enabled: false,
        form_data: { note: '' },
        incomplete_required: ['note'],
      },
      {
        workspace_id: 'adapt-debug',
        domain_id: 'lcm',
        domain_label: 'LCM',
        module: 'kernel-driver',
        related_skills: [],
        enabled: true,
        form_data: {},
        incomplete_required: [],
      },
    ]
    overlayCloneDomains(catalog, sampleRun().domains, (src, formData) => ({
      workspace_id: src.workspace_id,
      domain_id: src.domain_id,
      domain_label: src.domain_label,
      module: src.module,
      related_skills: [...src.related_skills],
      enabled: src.enabled,
      form_data: formData,
      incomplete_required: [...src.incomplete_required],
    }))
    expect(catalog.find(d => d.domain_id === 'tp')?.enabled).toBe(true)
    expect(catalog.find(d => d.domain_id === 'tp')?.form_data.note).toBe('12')
    expect(catalog.find(d => d.domain_id === 'lcm')?.enabled).toBe(false)
    expect(catalog.some(d => d.domain_id === 'apn-config')).toBe(true)
  })
})
