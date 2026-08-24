import { mkdir, mkdtemp, readFile, rm, writeFile } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, describe, expect, it } from 'vitest'
import {
  findSkillDirInProfile,
  listImprovedSkills,
  parseCuratorLedger,
  removeImprovedProfileCopy,
  taskIdFromSessionId,
  taskSkillsFromLedger,
} from '../../packages/server/src/services/hermes/skill-improve-registry'

const tempDirs: string[] = []

async function tempDir(prefix: string): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), prefix))
  tempDirs.push(dir)
  return dir
}

afterEach(async () => {
  await Promise.all(tempDirs.splice(0).map(dir => rm(dir, { recursive: true, force: true })))
})

describe('taskIdFromSessionId', () => {
  it('strips tahp-bug- prefix', () => {
    expect(taskIdFromSessionId('tahp-bug-task-bug-1787549871790-a4c496'))
      .toBe('task-bug-1787549871790-a4c496')
  })

  it('returns null for empty or unrelated ids', () => {
    expect(taskIdFromSessionId('')).toBeNull()
    expect(taskIdFromSessionId('session-xyz')).toBeNull()
  })
})

describe('parseCuratorLedger', () => {
  it('aggregates valid lines and skips corrupt ones', () => {
    const text = [
      '{"id":"1","ts":"2026-08-24T05:00:00Z","actor":"curator","action":"create","skill":"leakdetect-memory-analysis","evidence":{"session_id":"tahp-bug-task-bug-1"},"before":[],"after":[{"path":"D:\\\\hermes\\\\skills\\\\stability\\\\leakdetect-memory-analysis\\\\SKILL.md","sha256":"abc"}]}',
      'not-json',
      '{"skill":".hidden","action":"create"}',
      '{"id":"2","ts":"2026-08-24T06:00:00Z","actor":"curator","action":"write_file","skill":"leakdetect-memory-analysis","evidence":{"session_id":"tahp-bug-task-bug-2"},"after":[]}',
    ].join('\n')
    const entries = parseCuratorLedger(text)
    expect(entries).toHaveLength(2)
    expect(entries.map(e => e.action)).toEqual(['create', 'write_file'])
    const byTask = taskSkillsFromLedger(entries)
    expect(byTask.get('task-bug-1')).toEqual(['leakdetect-memory-analysis'])
    expect(byTask.get('task-bug-2')).toEqual(['leakdetect-memory-analysis'])
  })
})

describe('findSkillDirInProfile / listImprovedSkills', () => {
  it('prefers flat path over category when both exist', async () => {
    const profile = await tempDir('improve-profile-')
    await mkdir(join(profile, 'stability', 'demo-skill'), { recursive: true })
    await writeFile(join(profile, 'stability', 'demo-skill', 'SKILL.md'), '# nested\n', 'utf-8')
    await mkdir(join(profile, 'demo-skill'), { recursive: true })
    await writeFile(join(profile, 'demo-skill', 'SKILL.md'), '# flat\n', 'utf-8')

    expect(findSkillDirInProfile(profile, 'demo-skill')).toEqual({
      abs: join(profile, 'demo-skill'),
      rel: 'demo-skill',
    })
  })

  it('finds categorized skills when flat copy is absent', async () => {
    const profile = await tempDir('improve-cat-')
    await mkdir(join(profile, 'android', 'android-anr-log-analysis'), { recursive: true })
    await writeFile(join(profile, 'android', 'android-anr-log-analysis', 'SKILL.md'), '# anr\n', 'utf-8')
    const found = findSkillDirInProfile(profile, 'android-anr-log-analysis')
    expect(found?.rel).toBe('android/android-anr-log-analysis')
  })

  it('marks agent_only vs at_risk vs promoted', async () => {
    const root = await tempDir('improve-status-')
    const profile = join(root, 'profile')
    const repo = join(root, 'repo')
    await mkdir(join(profile, 'stability', 'new-skill'), { recursive: true })
    await writeFile(join(profile, 'stability', 'new-skill', 'SKILL.md'), '# new\n', 'utf-8')
    await mkdir(join(profile, 'jira-ops'), { recursive: true })
    await writeFile(join(profile, 'jira-ops', 'SKILL.md'), '# patched\n', 'utf-8')
    await mkdir(join(profile, 'telephony', 'promoted-skill'), { recursive: true })
    await writeFile(join(profile, 'telephony', 'promoted-skill', 'SKILL.md'), '# cat\n', 'utf-8')
    await mkdir(join(repo, 'jira-ops'), { recursive: true })
    await writeFile(join(repo, 'jira-ops', 'SKILL.md'), '# repo\n', 'utf-8')
    await mkdir(join(repo, 'promoted-skill'), { recursive: true })
    await writeFile(join(repo, 'promoted-skill', 'SKILL.md'), '# repo\n', 'utf-8')

    const ledger = [
      JSON.stringify({ ts: '2026-08-24T01:00:00Z', action: 'create', skill: 'new-skill', evidence: { session_id: 'tahp-bug-task-a' }, after: [] }),
      JSON.stringify({ ts: '2026-08-24T02:00:00Z', action: 'patch', skill: 'jira-ops', evidence: { session_id: 'tahp-bug-task-b' }, after: [] }),
      JSON.stringify({ ts: '2026-08-24T03:00:00Z', action: 'create', skill: 'promoted-skill', after: [] }),
    ].join('\n')
    const ledgerPath = join(profile, '.curator_ledger.jsonl')
    await writeFile(ledgerPath, ledger, 'utf-8')

    const listed = listImprovedSkills({
      profileSkillsDir: profile,
      repoSkillsDir: repo,
      ledgerPath,
    })
    const byName = Object.fromEntries(listed.map(s => [s.name, s]))
    expect(byName['new-skill'].status).toBe('agent_only')
    expect(byName['new-skill'].overwrite_risk).toBe('none')
    expect(byName['new-skill'].profile_rel_path).toBe('stability/new-skill')
    expect(byName['jira-ops'].status).toBe('at_risk')
    expect(byName['jira-ops'].overwrite_risk).toBe('will_be_overwritten')
    expect(byName['promoted-skill'].status).toBe('promoted')
    expect(byName['promoted-skill'].overwrite_risk).toBe('none')
  })

  it('refuses to delete the only copy before promote', async () => {
    const root = await tempDir('improve-del-')
    const profile = join(root, 'profile')
    const repo = join(root, 'repo')
    await mkdir(join(profile, 'only-skill'), { recursive: true })
    await writeFile(join(profile, 'only-skill', 'SKILL.md'), '# x\n', 'utf-8')
    await mkdir(repo, { recursive: true })
    await writeFile(join(profile, '.curator_ledger.jsonl'), JSON.stringify({
      ts: '2026-08-24T01:00:00Z', action: 'create', skill: 'only-skill', after: [],
    }), 'utf-8')

    const denied = removeImprovedProfileCopy('only-skill', {
      profileSkillsDir: profile,
      repoSkillsDir: repo,
      ledgerPath: join(profile, '.curator_ledger.jsonl'),
    })
    expect(denied.ok).toBe(false)
    expect(denied.error).toMatch(/尚未固化/)
  })
})
