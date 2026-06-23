import { describe, it, expect } from 'vitest'
import {
  buildDistillJiraHeader,
  prependDistillJiraHeader,
  extractJiraFromBugReport,
} from '../../packages/server/src/services/tahp/distill-jira-header'

describe('distill-jira-header', () => {
  it('buildDistillJiraHeader includes key, title, description', () => {
    const header = buildDistillJiraHeader({
      key: 'TOS163-36686',
      summary: 'RedBull operator 3G Only must be removed',
      description: '插入 Red Bull SIM 后 Preferred network type 显示了不应出现的 3G Only 选项',
    })
    expect(header).toContain('**KEY**: TOS163-36686')
    expect(header).toContain('**标题**: RedBull operator 3G Only must be removed')
    expect(header).toContain('**描述**: 插入 Red Bull SIM')
    expect(header).toMatch(/^## JIRA 信息/)
  })

  it('prependDistillJiraHeader adds header once', () => {
    const body = '# 分析报告\n\n内容'
    const once = prependDistillJiraHeader(body, { key: 'ABC-1', summary: 'Title' })
    expect(once.startsWith('## JIRA 信息')).toBe(true)
    expect(once).toContain(body)
    expect(prependDistillJiraHeader(once, { key: 'ABC-1' })).toBe(once)
  })

  it('extractJiraFromBugReport reads report.jira fields', () => {
    const info = extractJiraFromBugReport({
      jira_key: 'TOS163-36686',
      title: 'From title',
      jira: {
        summary: 'From jira.summary',
        description: 'Full description text',
      },
    })
    expect(info.key).toBe('TOS163-36686')
    expect(info.summary).toBe('From title')
    expect(info.description).toBe('Full description text')
  })
})
