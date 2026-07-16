import { describe, expect, it } from 'vitest'
import {
  buildBugActivityLog,
  formatBugActivityLine,
  lastBugActivityHint,
} from '../../packages/client/src/utils/bug-analysis-activity'

describe('bug-analysis-activity', () => {
  it('formats tool and phase events', () => {
    const line = formatBugActivityLine({
      type: 'task.skill_use',
      ts: Date.UTC(2026, 0, 1, 8, 30, 5),
      payload: { skill_id: 'jira-ops', message: 'get-issue OS162-1' },
    })
    expect(line).toMatch(/调用 jira-ops/)
    expect(line).toMatch(/\[\d{2}:\d{2}:\d{2}\]/)
  })

  it('builds chronological activity log', () => {
    const log = buildBugActivityLog([
      {
        type: 'task.phase',
        ts: 1,
        payload: { phase: 'ANALYZING', message: 'Agent 执行中' },
      },
      {
        type: 'task.skill_use',
        ts: 2,
        payload: { skill_id: 'Bash', message: 'python scripts/api_jira.py' },
      },
    ])
    expect(log).toContain('分析中')
    expect(log).toContain('Bash')
  })

  it('returns last activity hint', () => {
    const hint = lastBugActivityHint([
      { type: 'task.phase', ts: 1, payload: { phase: 'PREPARING', message: '准备' } },
      { type: 'task.message', ts: 2, payload: { level: 'activity', text: '正在调用工具 Read' } },
    ])
    expect(hint).toBe('正在调用工具 Read')
  })
})
