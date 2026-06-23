import { describe, expect, it } from 'vitest'
import {
  inferBusinessDomain,
  resolveEntryBusinessDomain,
  skillSuggestionGroupKey,
  assertHomogeneousBusinessDomain,
  loadBusinessDomains,
  listDomainsForModule,
} from '../../packages/server/src/services/tahp/business-domain'

describe('business domain registry', () => {
  it('loads domains from knowledge-base/business-domains.yaml', () => {
    const all = loadBusinessDomains(true)
    expect(all.length).toBeGreaterThan(20)
    expect(all.some(d => d.id === 'tp_touch')).toBe(true)
    expect(all.some(d => d.id === 'standby_drain')).toBe(true)
  })

  it('lists module-scoped domains for kernel-driver', () => {
    const kd = listDomainsForModule('kernel-driver')
    const ids = kd.map(d => d.id)
    expect(ids).toContain('tp_touch')
    expect(ids).toContain('vibrator')
    expect(ids).not.toContain('voice_call')
  })
})

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

  it('classifies TP touch and vibrator separately under kernel-driver', () => {
    const tp = inferBusinessDomain({
      content: 'JIRA (Drv) TP：开机后触摸失效，kernel log 无 tpd_probe，fts 驱动未加载。',
      module: 'kernel-driver',
    })
    const vib = inferBusinessDomain({
      content: '(Drv) Vibrator 部分场景无振动，RichTapVibratorService 未启动，haptic probe failed。',
      module: 'kernel-driver',
    })
    expect(tp.id).toBe('tp_touch')
    expect(vib.id).toBe('vibrator')
    expect(tp.id).not.toBe(vib.id)
  })

  it('classifies standby drain and backlight under power-mgmt', () => {
    const standby = inferBusinessDomain({
      content: '待机耗电异常，灭屏电流 80mA，AP 无法 suspend，wakelock 长持锁。',
      module: 'power-mgmt',
    })
    const backlight = inferBusinessDomain({
      content: '自动背光忽明忽暗，AutomaticBrightnessController lux 跳变，HBM 进入异常。',
      module: 'power-mgmt',
    })
    expect(standby.id).toBe('standby_drain')
    expect(backlight.id).toBe('backlight_power')
  })

  it('classifies port burn charging case', () => {
    const r = inferBusinessDomain({
      content: '端口防烧触发后通知栏不显示提示，NTC 70度，BatteryService 状态异常。',
      module: 'shared',
    })
    expect(r.id).toBe('charging')
  })

  it('respects explicit business domain label in report', () => {
    const r = inferBusinessDomain({
      content: '## 摘要\n业务域：TP触摸\n无触摸。',
      module: 'shared',
    })
    expect(r.id).toBe('tp_touch')
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
    const k1 = skillSuggestionGroupKey('kernel-driver', 'bug_analysis', 'tp_touch')
    const k2 = skillSuggestionGroupKey('kernel-driver', 'bug_analysis', 'vibrator')
    expect(k1).not.toBe(k2)
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
