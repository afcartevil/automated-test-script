import { mkdir, mkdtemp, writeFile } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { shortHash } from '../../packages/server/src/services/tahp/sync/hash'

const tempDirs: string[] = []

async function tempDir(prefix: string): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), prefix))
  tempDirs.push(dir)
  return dir
}

afterEach(async () => {
  vi.resetModules()
  const { rm } = await import('fs/promises')
  await Promise.all(tempDirs.splice(0).map(dir => rm(dir, { recursive: true, force: true })))
})

describe('skill sync hash', () => {
  it('matches central shortHash (sha256 slice 16)', () => {
    expect(shortHash('hello')).toBe('2cf24dba5fb0a30e')
    expect(shortHash('')).toBe('e3b0c44298fc1c14')
  })
})

describe('getSkillSyncStatus (unconfigured)', () => {
  it('returns configured=false and marks local skills as local_only', async () => {
    const root = await tempDir('skill-sync-status-')
    const skillsDir = join(root, 'skills', '.claude', 'skills', 'demo-skill')
    await mkdir(skillsDir, { recursive: true })
    await writeFile(
      join(skillsDir, 'SKILL.md'),
      '---\nname: demo\nfunc_type: 通信\nmodule: 诊断\n---\n\n# demo\n',
      'utf-8',
    )

    vi.doMock('../../packages/server/src/services/tahp/paths', () => ({
      tahpPaths: {
        projectRoot: root,
        skillsDir: join(root, 'skills', '.claude', 'skills'),
        knowledgeDir: join(root, 'knowledge-base'),
      },
    }))
    vi.doMock('../../packages/server/src/config', () => ({
      config: { tahp: { centralUrl: '', centralToken: '', role: 'local', syncIntervalMs: 0 } },
    }))
    vi.doMock('../../packages/server/src/services/tahp/runtime-mode', () => ({
      isCentralConfigured: () => false,
      getRuntimeModeInfo: () => ({ role: 'local', central_configured: false, central_url: null }),
    }))

    const { getSkillSyncStatus } = await import('../../packages/server/src/services/tahp/sync/status')
    const status = await getSkillSyncStatus()
    expect(status.configured).toBe(false)
    expect(status.connected).toBe(false)
    expect(status.skills.some(s => s.id === 'demo-skill' && s.state === 'local_only')).toBe(true)
    expect(status.groups.some(g => g.label === '通信')).toBe(true)
  })
})
