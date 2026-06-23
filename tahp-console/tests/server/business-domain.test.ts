import { describe, expect, it } from 'vitest'
import {
  inferBusinessDomain,
  resolveEntryBusinessDomain,
  skillSuggestionGroupKey,
  assertHomogeneousBusinessDomain,
} from '../../packages/server/src/services/tahp/business-domain'

describe('inferBusinessDomain', () => {
  it('classifies voice call issues separately from network', () => {
    const voice = inferBusinessDomain({
      content: '用户反馈无法接听来电，VoWiFi 通话建立后自动挂断，log 中有 Telecom InCall 异常。',
      module: 'shared',
    })
    const network = inferBusinessDomain({
      content: '状态栏显示无服务，手动搜网列表为空，radio log 中 DATA_REGISTRATION_STATE 异常。',
      module: 'shared',
    })
    expect(voice.id).toBe('voice_call')
    expect(network.id).toBe('network')
    expect(voice.id).not.toBe(network.id)
  })

  it('classifies data and APN separately', () => {
    const data = inferBusinessDomain({
      content: '移动数据无法上网，DATA_STALL 频繁触发，data call 建立失败。',
      module: 'telephony',
    })
    const apn = inferBusinessDomain({
      content: 'APN 配置界面显示异常，运营商 APN 参数与 MP 不一致。',
      module: 'telephony',
    })
    expect(data.id).toBe('data')
    expect(apn.id).toBe('apn')
  })

  it('respects explicit business domain label in report', () => {
    const r = inferBusinessDomain({
      content: '## 摘要\n业务域：通话\n无法拨号。',
      module: 'shared',
    })
    expect(r.id).toBe('voice_call')
    expect(r.source).toBe('explicit')
  })

  it('uses stored business_domain when present', () => {
    const r = resolveEntryBusinessDomain({
      content: '任意内容',
      module: 'shared',
      business_domain: 'sms',
      business_domain_label: '短信彩信',
    })
    expect(r.id).toBe('sms')
    expect(r.label).toBe('短信彩信')
  })
})

describe('skillSuggestionGroupKey', () => {
  it('produces distinct keys for different business domains under same module', () => {
    const k1 = skillSuggestionGroupKey('shared', 'bug_analysis', 'voice_call')
    const k2 = skillSuggestionGroupKey('shared', 'bug_analysis', 'network')
    expect(k1).not.toBe(k2)
    expect(k1).toBe('shared::bug_analysis::voice_call')
  })
})

describe('assertHomogeneousBusinessDomain', () => {
  it('detects mixed domains in one batch', () => {
    const { homogeneous, dominant } = assertHomogeneousBusinessDomain([
      { content: '用户无法拨号，去电失败', module: 'shared' },
      { content: 'APN 配置错误，接入点参数异常', module: 'shared' },
    ])
    expect(homogeneous).toBe(false)
    expect(['voice_call', 'apn']).toContain(dominant.id)
  })
})
