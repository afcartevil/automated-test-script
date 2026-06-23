import { describe, expect, it } from 'vitest'
import { routeIntent, parseSlashIntent } from '../../packages/server/src/services/tahp/chat-retrieval/intent-router'

describe('intent-router', () => {
  it('routes historical_case from symptom title (port burn)', () => {
    const r = routeIntent('插入充电器充电，小板NTC加热至70°C触发端口防烧，但通知栏不显示通知')
    expect(r.intent).toBe('historical_case')
  })

  it('routes historical_case from keywords', () => {
    const r = routeIntent('有没有类似的 VozWiFi 历史 Bug')
    expect(r.intent).toBe('historical_case')
    expect(r.confidence).toBeGreaterThan(0.5)
  })

  it('routes concept_reference from 是什么', () => {
    const r = routeIntent('VozWiFi 是什么')
    expect(r.intent).toBe('concept_reference')
  })

  it('routes analysis_sop from 怎么分析', () => {
    const r = routeIntent('通信 VoWiFi 问题怎么分析')
    expect(r.intent).toBe('analysis_sop')
  })

  it('routes direct_lookup from JIRA key', () => {
    const r = routeIntent('TOS163-37004 详情')
    expect(r.intent).toBe('direct_lookup')
  })

  it('respects explicit retrieval mode', () => {
    const r = routeIntent('任意问题', { retrieval_mode: 'sop' })
    expect(r.intent).toBe('analysis_sop')
    expect(r.explicit_override).toBe(true)
  })

  it('parseSlashIntent strips command', () => {
    const { intent, rest } = parseSlashIntent('/历史 VozWiFi')
    expect(intent).toBe('historical_case')
    expect(rest).toBe('VozWiFi')
  })
})
