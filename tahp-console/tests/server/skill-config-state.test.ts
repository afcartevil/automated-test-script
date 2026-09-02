import { describe, expect, it } from 'vitest'
import { parseSkillConfigStateFile } from '../../packages/server/src/services/tahp/skill-config'

describe('parseSkillConfigStateFile', () => {
  it('reads legacy flat skill-id map', () => {
    const parsed = parseSkillConfigStateFile({
      'jira-ops': { status: 'configured', note: 'ok' },
      leftover: { foo: 1 },
    })
    expect(parsed.skills['jira-ops']?.status).toBe('configured')
    expect(parsed.skills.leftover).toBeUndefined()
    expect(parsed.last_check).toBeUndefined()
  })

  it('reads v2 envelope with last_check', () => {
    const parsed = parseSkillConfigStateFile({
      version: 2,
      last_check: { ok: false, at: '2026-09-02T01:00:00.000Z', task_id: 'task-1' },
      skills: {
        'jira-ops': { status: 'configured' },
      },
    })
    expect(parsed.last_check).toEqual({
      ok: false,
      at: '2026-09-02T01:00:00.000Z',
      task_id: 'task-1',
    })
    expect(Object.keys(parsed.skills)).toEqual(['jira-ops'])
  })
})
