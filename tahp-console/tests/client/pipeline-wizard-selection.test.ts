import { describe, expect, it } from 'vitest'
import {
  WIZARD_DOMAIN_DEFAULT_ENABLED,
  canProceedWizardStep3,
  resolveWizardStep3Sections,
  syncWizardDomainEnabledWithWorkspaces,
  workflowStageEnabled,
} from '@/utils/pipeline-wizard-selection'

const defaultNodes = [
  { key: 'prereq', enabled: true },
  { key: 'adapt', enabled: true },
  { key: 'build', enabled: true },
  { key: 'flash', enabled: true },
  { key: 'selfcheck', enabled: true },
  { key: 'gerrit', enabled: true },
]

function values(overrides: Partial<Parameters<typeof canProceedWizardStep3>[1]> = {}) {
  return {
    systemRoot: 'Z:\\sys',
    variant: 'userdebug',
    buildFlag: 'staging',
    buildTargets: ['sys'],
    needPack: true,
    flashPkgPath: '',
    flashVersionFromBuild: true,
    deviceId: 'SN1',
    gerritIssueId: 'TOS1501-1',
    ...overrides,
  }
}

describe('pipeline wizard module selection', () => {
  it('does not check any module by default', () => {
    expect(WIZARD_DOMAIN_DEFAULT_ENABLED).toBe(false)
  })

  it('does not auto-check modules when adding a workspace', () => {
    const domains = [
      { workspace_id: 'adapt-debug', domain_id: 'tp', enabled: false },
      { workspace_id: 'feature-adapt', domain_id: 'nfc', enabled: false },
    ]
    syncWizardDomainEnabledWithWorkspaces(domains, ['adapt-debug', 'feature-adapt'])
    expect(domains.every(d => d.enabled === false)).toBe(true)
  })

  it('unchecks modules when their workspace is removed', () => {
    const domains = [
      { workspace_id: 'adapt-debug', domain_id: 'tp', enabled: true },
      { workspace_id: 'feature-adapt', domain_id: 'nfc', enabled: true },
    ]
    syncWizardDomainEnabledWithWorkspaces(domains, ['adapt-debug'])
    expect(domains.find(d => d.domain_id === 'tp')?.enabled).toBe(true)
    expect(domains.find(d => d.domain_id === 'nfc')?.enabled).toBe(false)
  })
})

describe('pipeline wizard step3 sections', () => {
  it('reads enabled stages from the saved workflow', () => {
    expect(resolveWizardStep3Sections(defaultNodes)).toEqual({
      build: true,
      flash: true,
      selfcheck: true,
      gerrit: true,
    })
  })

  it('treats unchecked or missing stages as hidden', () => {
    expect(workflowStageEnabled([{ key: 'build', enabled: false }], 'build')).toBe(false)
    expect(workflowStageEnabled([], 'build')).toBe(false)
    expect(resolveWizardStep3Sections([
      { key: 'build', enabled: false },
      { key: 'flash', enabled: true },
      { key: 'gerrit', enabled: false },
    ])).toEqual({
      build: false,
      flash: true,
      selfcheck: false,
      gerrit: false,
    })
  })
})

describe('pipeline wizard step3 required fields', () => {
  it('requires NEW_SYSTEM_ROOT when compile is enabled', () => {
    const sections = resolveWizardStep3Sections(defaultNodes)
    expect(canProceedWizardStep3(sections, values({ systemRoot: '' }))).toBe(false)
    expect(canProceedWizardStep3(sections, values())).toBe(true)
  })

  it('does not require compile fields when compile is off', () => {
    const sections = resolveWizardStep3Sections([
      { key: 'flash', enabled: true },
      { key: 'gerrit', enabled: true },
    ])
    expect(canProceedWizardStep3(sections, values({
      systemRoot: '',
      variant: '',
      flashVersionFromBuild: false,
      flashPkgPath: 'Z:\\pkg',
    }))).toBe(true)
  })

  it('requires device when flash or selfcheck is enabled', () => {
    expect(canProceedWizardStep3(
      resolveWizardStep3Sections([{ key: 'flash', enabled: true }]),
      values({ deviceId: '', flashVersionFromBuild: false, flashPkgPath: 'Z:\\pkg', gerritIssueId: '' }),
    )).toBe(false)
    expect(canProceedWizardStep3(
      resolveWizardStep3Sections([{ key: 'selfcheck', enabled: true }]),
      values({ deviceId: null, flashPkgPath: '', gerritIssueId: '' }),
    )).toBe(false)
    expect(canProceedWizardStep3(
      resolveWizardStep3Sections([{ key: 'selfcheck', enabled: true }]),
      values({ flashPkgPath: '', gerritIssueId: '' }),
    )).toBe(true)
  })

  it('requires flash package path unless version comes from compile pack', () => {
    const flashOnly = resolveWizardStep3Sections([{ key: 'flash', enabled: true }])
    expect(canProceedWizardStep3(flashOnly, values({
      flashVersionFromBuild: false,
      flashPkgPath: '',
      gerritIssueId: '',
    }))).toBe(false)
    expect(canProceedWizardStep3(flashOnly, values({
      flashVersionFromBuild: true,
      flashPkgPath: '',
      gerritIssueId: '',
    }))).toBe(true)
  })

  it('requires Gerrit issue id only when gerrit is enabled', () => {
    expect(canProceedWizardStep3(
      resolveWizardStep3Sections([{ key: 'gerrit', enabled: true }]),
      values({ gerritIssueId: '  ', deviceId: '', flashPkgPath: '' }),
    )).toBe(false)
    expect(canProceedWizardStep3(
      resolveWizardStep3Sections([{ key: 'build', enabled: true }]),
      values({ gerritIssueId: '', deviceId: '', flashPkgPath: '' }),
    )).toBe(true)
  })
})
