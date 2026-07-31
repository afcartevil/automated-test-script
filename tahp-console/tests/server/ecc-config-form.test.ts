import { describe, expect, it } from 'vitest'
import {
  hasEccRepoPath,
  validateEccConfigForm,
  isInteractiveCarrierDomain,
  shouldAutoApproveAdaptCommands,
  normalizeEccRelatedSkills,
} from '../../packages/server/src/services/tahp/ecc-config-form'
import {
  isEccConfigFormComplete,
  packEccEntriesForAgent,
  createEmptyEccEntry,
} from '../../packages/client/src/constants/adapt-domains/ecc-config-form'

describe('ecc-config-form', () => {
  it('hasEccRepoPath requires at least one platform path', () => {
    expect(hasEccRepoPath({})).toBe(false)
    expect(hasEccRepoPath({ repo_path_mtk: 'D:\\ecc\\mtk' })).toBe(true)
    expect(hasEccRepoPath({ repo_path_unisoc: '  ' })).toBe(false)
  })

  it('validateEccConfigForm only requires repo path (number optional)', () => {
    expect(validateEccConfigForm({ number: '998' })).toMatch(/代码仓路径/)
    expect(validateEccConfigForm({
      repo_path_qualcomm: 'D:\\ecc\\qcom',
    })).toBeNull()
    expect(validateEccConfigForm({
      number: '',
      repo_path_mtk: 'D:\\ecc',
    })).toBeNull()
  })

  it('isEccConfigFormComplete matches client completeness', () => {
    expect(isEccConfigFormComplete({})).toBe(false)
    expect(isEccConfigFormComplete({ repo_path_mtk: 'D:\\a' })).toBe(true)
    expect(isEccConfigFormComplete({ number: '110' })).toBe(false)
  })

  it('packEccEntriesForAgent expands multi groups for prompt', () => {
    const packed = packEccEntriesForAgent([
      { ...createEmptyEccEntry(), number: '110', with_sim: '真紧急', user_notes: 'mccmnc 46001' },
      { ...createEmptyEccEntry(), number: '119', block: 'yes' },
    ])
    expect(packed.formData.ecc_entry_count).toBe('2')
    expect(packed.formData.ecc_group_1_number).toBe('110')
    expect(packed.formData.ecc_group_1_user_notes).toBe('mccmnc 46001')
    expect(packed.formData.ecc_group_2_number).toBe('119')
    expect(packed.formData.ecc_group_2_block).toBe('yes')
    expect(JSON.parse(packed.formData.ecc_entries_json)).toHaveLength(2)
    expect(packed.formFields.some(f => f.label.includes('ECC组2 · 号码'))).toBe(true)
    expect(packed.formFields.some(f => f.label.includes('ECC组1 · 本组补充'))).toBe(true)
  })

  it('isInteractiveCarrierDomain excludes ecc-config (unattended)', () => {
    expect(isInteractiveCarrierDomain('ecc-config', false)).toBe(false)
    expect(isInteractiveCarrierDomain('carrierconfig-tools', false)).toBe(true)
    expect(isInteractiveCarrierDomain('apn-config', false)).toBe(false)
    expect(isInteractiveCarrierDomain('apn-config', true)).toBe(true)
  })

  it('shouldAutoApproveAdaptCommands only for ecc-config', () => {
    expect(shouldAutoApproveAdaptCommands('ecc-config')).toBe(true)
    expect(shouldAutoApproveAdaptCommands('carrierconfig-tools')).toBe(false)
    expect(shouldAutoApproveAdaptCommands('apn-config')).toBe(false)
  })

  it('normalizeEccRelatedSkills drops jira-ops and ensures gerrit-submit', () => {
    expect(normalizeEccRelatedSkills(['ecc-config', 'jira-ops'])).toEqual([
      'ecc-config',
      'gerrit-submit',
    ])
    expect(normalizeEccRelatedSkills(['ecc-config', 'gerrit-submit', 'extra'])).toEqual([
      'ecc-config',
      'gerrit-submit',
      'extra',
    ])
  })
})
