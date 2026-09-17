import { describe, expect, it } from 'vitest'
import {
  formatUnfilledFieldsHint,
  isConfigSetupTab,
  isTestDomainCredential,
  listUnfilledFormFields,
  parseConfigTab,
  summarizeSkillSetup,
} from '@/utils/config-navigation'

const fields = [
  { key: 'domain_account', label: '域账号', group: '域账号' },
  { key: 'domain_password', label: '域密码', group: '域账号' },
  { key: 'feishu_app_id', label: 'App ID', group: '飞书 OpenAPI（可选）' },
]

describe('listUnfilledFormFields', () => {
  it('treats every field as required, including groups named 可选', () => {
    const missing = listUnfilledFormFields(
      { domain_account: 'alice', domain_password: '  ', feishu_app_id: '' },
      fields,
    )
    expect(missing.map(f => f.key)).toEqual(['domain_password', 'feishu_app_id'])
  })

  it('returns empty when all fields have non-blank values', () => {
    expect(listUnfilledFormFields(
      { domain_account: 'alice', domain_password: 'secret', feishu_app_id: 'cli_x' },
      fields,
    )).toEqual([])
  })
})

describe('formatUnfilledFieldsHint', () => {
  it('lists group and label, stripping 可选 from group names', () => {
    const hint = formatUnfilledFieldsHint([
      { group: '飞书 OpenAPI（可选）', label: 'App ID' },
      { group: '域账号', label: '域密码' },
    ])
    expect(hint).toContain('缺 2 项')
    expect(hint).toContain('飞书 OpenAPI · App ID')
    expect(hint).toContain('域账号 · 域密码')
    expect(hint).not.toContain('（可选）')
  })
})

describe('isTestDomainCredential', () => {
  it('matches only test- prefixed accounts with the fixed test password', () => {
    expect(isTestDomainCredential({ domain_account: 'test-alice', domain_password: '12345678' })).toBe(true)
  })

  it('ignores surrounding blanks and account letter case', () => {
    expect(isTestDomainCredential({ domain_account: '  TEST-alice ', domain_password: ' 12345678 ' })).toBe(true)
  })

  it('rejects test- accounts with any other password', () => {
    expect(isTestDomainCredential({ domain_account: 'test-alice', domain_password: '123456789' })).toBe(false)
    expect(isTestDomainCredential({ domain_account: 'test-alice', domain_password: '' })).toBe(false)
  })

  it('rejects normal accounts even with the test password', () => {
    expect(isTestDomainCredential({ domain_account: 'alice', domain_password: '12345678' })).toBe(false)
    expect(isTestDomainCredential({ domain_account: 'alice.test', domain_password: '12345678' })).toBe(false)
  })

  it('rejects empty credentials so the required-field check still applies', () => {
    expect(isTestDomainCredential({})).toBe(false)
    expect(isTestDomainCredential({ domain_account: '', domain_password: '' })).toBe(false)
  })
})

describe('parseConfigTab', () => {
  it('maps the old skills tab into 一键配置 form step', () => {
    expect(parseConfigTab('skills')).toBe('form')
    expect(parseConfigTab('form')).toBe('form')
    expect(parseConfigTab('batch')).toBe('batch')
    expect(parseConfigTab(undefined)).toBe('models')
  })

  it('treats form and check steps as the same 一键配置 tab', () => {
    expect(isConfigSetupTab('form')).toBe(true)
    expect(isConfigSetupTab('batch')).toBe(true)
    expect(isConfigSetupTab('models')).toBe(false)
  })
})

describe('summarizeSkillSetup', () => {
  const all = [
    { status: 'configured' },
    { status: 'configured' },
  ]
  const mixed = [
    { status: 'configured' },
    { status: 'not_configured' },
  ]

  it('prefers live batch over last_check', () => {
    const s = summarizeSkillSetup({ skills: mixed, batchRunning: true, lastCheckOk: false })
    expect(s.kind).toBe('running')
    expect(s.showLiveHint).toBe(true)
    expect(s.label).toContain('进行中')
  })

  it('reports all configured even if last check failed', () => {
    const s = summarizeSkillSetup({ skills: all, lastCheckOk: false })
    expect(s.kind).toBe('all')
    expect(s.label).toContain('已全部配置完')
  })

  it('reports last check failure when some skills remain open', () => {
    const s = summarizeSkillSetup({ skills: mixed, lastCheckOk: false })
    expect(s.kind).toBe('failed')
    expect(s.tone).toBe('err')
    expect(s.label).toContain('上次检查失败')
  })

  it('reports partial when some skills are configured', () => {
    const s = summarizeSkillSetup({ skills: mixed })
    expect(s.kind).toBe('partial')
    expect(s.label).toBe('部分已配置（1/2）')
  })

  it('reports none when nothing is configured yet', () => {
    const s = summarizeSkillSetup({ skills: [{ status: 'not_configured' }] })
    expect(s.kind).toBe('none')
    expect(s.label).toBe('尚未完成 Skill 配置')
  })
})
