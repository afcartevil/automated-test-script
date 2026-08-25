import { describe, expect, it } from 'vitest'
import {
  detectSkillImprove,
  formatSkillImproveSummary,
  mergeLedgerSkillImproves,
  parseSkillImproves,
  skillNameFromPath,
  upsertSkillImprove,
} from '../../packages/server/src/services/tahp/bug-analysis-skill-improve'
import { parseCuratorLedger } from '../../packages/server/src/services/hermes/skill-improve-registry'

describe('skillNameFromPath', () => {
  it('reads Hermes profile skill path', () => {
    expect(skillNameFromPath(
      String.raw`D:\Users\admin\AppData\Local\hermes\skills\tahp-stacktrace-diagnosis\SKILL.md`,
    )).toBe('tahp-stacktrace-diagnosis')
  })

  it('skips .claude segment in TAHP repo skills path', () => {
    expect(skillNameFromPath(
      'E:/easyadapter/skills/.claude/skills/jira-ops/SKILL.md',
    )).toBe('jira-ops')
  })

  it('reads skill directory without a trailing file', () => {
    expect(skillNameFromPath('D:/Users/admin/AppData/Local/hermes/skills/bugfix-analysis')).toBe('bugfix-analysis')
  })

  it('prefers the SKILL.md owner over a category directory', () => {
    expect(skillNameFromPath(
      'E:/easyadapter/hermes-agent-main/skills/software-development/hermes-agent-skill-authoring/SKILL.md',
    )).toBe('hermes-agent-skill-authoring')
  })

  it('reads an attached file inside a flat skill directory', () => {
    expect(skillNameFromPath(
      'D:/Users/admin/AppData/Local/hermes/skills/jira-ops/scripts/fetch.py',
    )).toBe('jira-ops')
  })

  it('returns null when skills is the last segment', () => {
    expect(skillNameFromPath('D:/Users/admin/AppData/Local/hermes/skills')).toBeNull()
  })

  it('returns null for non-skill paths', () => {
    expect(skillNameFromPath('E:/easyadapter/jira_workspace/test_unc.ps1')).toBeNull()
  })
})

describe('detectSkillImprove', () => {
  it('records skill_manage write actions', () => {
    expect(detectSkillImprove('skill_manage', { action: 'patch', name: 'leakdetect-memory-analysis' }))
      .toEqual({ name: 'leakdetect-memory-analysis', action: 'patch' })
  })

  it('ignores skill_manage reads', () => {
    expect(detectSkillImprove('skill_manage', { action: 'view', name: 'jira-ops' })).toBeNull()
  })

  it('records write_file under skills/', () => {
    expect(detectSkillImprove('write_file', {
      path: 'D:/Users/admin/AppData/Local/hermes/skills/bugfix-analysis/SKILL.md',
    })).toEqual({ name: 'bugfix-analysis', action: 'file_write' })
  })

  it('ignores ordinary write_file', () => {
    expect(detectSkillImprove('write_file', {
      path: 'E:/easyadapter/jira_workspace/list_share.bat',
    })).toBeNull()
  })
})

describe('upsertSkillImprove', () => {
  it('merges actions on the same skill', () => {
    const once = upsertSkillImprove([], { name: 'jira-ops', action: 'patch' })
    const twice = upsertSkillImprove(once, { name: 'jira-ops', action: 'file_write' })
    expect(twice).toEqual([{ name: 'jira-ops', actions: ['patch', 'file_write'] }])
  })
})

describe('mergeLedgerSkillImproves', () => {
  const ledger = parseCuratorLedger([
    '{"action":"create","skill":"android-hwr-lk-stage-analysis","evidence":{"session_id":"tahp-bug-task-bug-8ef495"}}',
    '{"action":"patch","skill":"tahp-diagnostic-patterns","evidence":{"session_id":"tahp-bug-task-bug-0152f7"}}',
    '{"action":"write_file","skill":"tahp-diagnostic-patterns","evidence":{"session_id":"tahp-bug-task-bug-0152f7"}}',
    '{"action":"create","skill":"other-skill","evidence":{"session_id":"tahp-bug-task-bug-other"}}',
  ].join('\n'))

  it('fills skills_improved from ledger when tool.started recorded nothing', () => {
    const merged = mergeLedgerSkillImproves([], 'task-bug-8ef495', ledger)
    expect(merged).toEqual([{ name: 'android-hwr-lk-stage-analysis', actions: ['create'] }])
  })

  it('keeps live detect hits and unions ledger actions', () => {
    const live = [{ name: 'tahp-diagnostic-patterns', actions: ['file_write'] }]
    const merged = mergeLedgerSkillImproves(live, 'task-bug-0152f7', ledger)
    expect(merged).toEqual([
      { name: 'tahp-diagnostic-patterns', actions: ['file_write', 'patch', 'write_file'] },
    ])
  })

  it('ignores other tasks and empty ledger', () => {
    expect(mergeLedgerSkillImproves([], 'task-bug-missing', ledger)).toEqual([])
    expect(mergeLedgerSkillImproves(
      [{ name: 'keep-me', actions: ['patch'] }],
      'task-bug-8ef495',
      [],
    )).toEqual([{ name: 'keep-me', actions: ['patch'] }])
  })
})

describe('parse / format', () => {
  it('parses stored records and formats a summary', () => {
    const parsed = parseSkillImproves([
      { name: 'tahp-stacktrace-diagnosis', actions: ['patch', 'file_write'] },
      { name: '' },
    ])
    expect(parsed).toHaveLength(1)
    expect(formatSkillImproveSummary(parsed)).toContain('tahp-stacktrace-diagnosis')
    expect(formatSkillImproveSummary(parsed)).toContain('局部补丁')
  })

  it('keeps snapshot_dir and snapshot_source when present', () => {
    const parsed = parseSkillImproves([
      {
        name: 'leakdetect-memory-analysis',
        actions: ['create'],
        snapshot_dir: 'bug-analysis/skills/task-1/leakdetect-memory-analysis',
        snapshot_source: 'backfill',
      },
    ])
    expect(parsed[0].snapshot_dir).toBe('bug-analysis/skills/task-1/leakdetect-memory-analysis')
    expect(parsed[0].snapshot_source).toBe('backfill')
  })
})
