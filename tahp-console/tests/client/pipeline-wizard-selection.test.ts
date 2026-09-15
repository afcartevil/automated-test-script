import { describe, expect, it } from 'vitest'
import {
  WIZARD_DOMAIN_DEFAULT_ENABLED,
  syncWizardDomainEnabledWithWorkspaces,
} from '@/utils/pipeline-wizard-selection'

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
