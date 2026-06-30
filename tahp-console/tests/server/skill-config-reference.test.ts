import { describe, expect, it } from 'vitest'
import {
  buildConfiguredSkillsReferenceBlock,
  getConfiguredPeerSkills,
} from '../../packages/server/src/services/tahp/skill-config'

describe('skill config configured peer reference', () => {
  it('lists jira-ops as peer when configuring modem-analysis-local', () => {
    const { peers, missingDependencies } = getConfiguredPeerSkills('modem-analysis-local')
    const jiraPeer = peers.find(p => p.id === 'jira-ops')
    if (jiraPeer) {
      expect(jiraPeer.isDependency).toBe(true)
      expect(jiraPeer.configLocations.some(l => l.includes('jira-ops'))).toBe(true)
    }
    if (!jiraPeer) {
      expect(missingDependencies.some(d => d.id === 'jira-ops')).toBe(true)
    }
  })

  it('builds reference block with reuse guidance for first-time config', () => {
    const block = buildConfiguredSkillsReferenceBlock('modem-analysis-local', {
      id: 'modem-analysis-local',
      label: 'Modem 故障分析',
      depends_on: ['jira-ops'],
    })
    if (!block) return
    expect(block).toContain('参考已配置 Skill')
    expect(block).toContain('禁止')
    expect(block).toContain('jira-user-config.json')
    expect(block).toMatch(/JIRA_|WORKSPACE_ROOT/)
  })

  it('returns empty block when no peers and no missing deps', () => {
    const block = buildConfiguredSkillsReferenceBlock('jira-ops', {
      id: 'jira-ops',
      label: 'Jira 操作与日志下载',
    })
    expect(block).toBe('')
  })
})
