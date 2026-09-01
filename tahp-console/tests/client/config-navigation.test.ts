import { describe, expect, it } from 'vitest'
import {
  formatUnfilledFieldsHint,
  isConfigSetupTab,
  listUnfilledFormFields,
  parseConfigTab,
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
