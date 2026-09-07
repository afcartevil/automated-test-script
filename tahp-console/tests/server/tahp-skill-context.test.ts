import { describe, expect, it } from 'vitest'
import {
  extractPreferredSkillIds,
  buildSkillExecutionDirective,
  buildTahpContext,
  buildFullTahpSystemContext,
  invalidateContextIndex,
} from '../../packages/server/src/services/tahp/context-injector'

describe('tahp skill context injector', () => {
  it('extracts preferred skill ids from adapt handoff text', () => {
    const text = [
      '我正在做 TP 适配',
      '**关联 Skills**: vib-adapt-lra-driver, fc-vib-driver, vib-adapt-dts-regulator',
    ].join('\n')
    expect(extractPreferredSkillIds(text)).toEqual([
      'vib-adapt-lra-driver',
      'fc-vib-driver',
      'vib-adapt-dts-regulator',
    ])
  })

  it('buildSkillExecutionDirective lists preferred skill paths', () => {
    const out = buildSkillExecutionDirective({
      preferredSkillIds: ['com-voice-call-dialing'],
      scenario: 'bug_analysis',
    })
    expect(out).toContain('com-voice-call-dialing')
    expect(out).toContain('SKILL.md')
    expect(out).toContain('智能诊断')
  })

  it('jira_dup_judge scenario does not ask for a 9-section analysis report', () => {
    const out = buildSkillExecutionDirective({
      preferredSkillIds: ['jira-dup-judge', 'jira-ops'],
      scenario: 'jira_dup_judge',
    })
    expect(out).toContain('jira-dup-judge')
    expect(out).toContain('Jira 置重')
    expect(out).not.toContain('智能诊断 — 拉取 JIRA 后必须选择')
  })

  it('buildTahpContext does not inject skill body excerpts', () => {
    const out = buildTahpContext('modem rf 适配', {
      includeSkillCatalog: true,
      includeConstraints: false,
      includePlaybooks: false,
      includeKnowledge: false,
    })
    if (!out) return
    expect(out).not.toContain('当前问题相关详细内容')
    expect(out).not.toContain('...(截断)')
    expect(out).toContain('仅索引')
  })

  it('buildFullTahpSystemContext adapt_debug skips skill catalog scan', () => {
    const out = buildFullTahpSystemContext('AI 适配调试 关联 Skills: MODEM_P1_Adapt', {
      scenario: 'adapt_debug',
      preferredSkillIds: ['MODEM_P1_Adapt'],
    })
    if (!out) return
    expect(out).toContain('MODEM_P1_Adapt')
    expect(out).toContain('AI 适配调试')
    expect(out).not.toContain('已扫描到的 Skills（共')
  })

  it('buildTahpContext matches .kb-data entries when indexed', () => {
    invalidateContextIndex()
    const out = buildTahpContext('VozWiFi Movistar Colombia 通话界面显示', {
      includeSkillCatalog: false,
      includeKnowledge: true,
    })
    if (!out) return
    expect(out).toContain('.kb-data/entries')
    if (out.includes('相关知识库条目')) {
      expect(out).toMatch(/vozwifi|VozWIFI|TOS163-37004|Movistar/i)
    }
  })
})
