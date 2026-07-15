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

describe('applySubmissionOverlay', () => {
  it('maps pending_review → submitted_pending', async () => {
    const { applySubmissionOverlay } = await import('../../packages/server/src/services/tahp/sync/status')
    const row = {
      id: 'demo',
      state: 'local_only' as const,
      local_hash: 'abc',
      bundle_ids: [] as string[],
    }
    const out = applySubmissionOverlay(row, {
      status: 'pending_review',
      submit_id: 'sp-1',
      hash: 'abc',
    })
    expect(out.state).toBe('submitted_pending')
    expect(out.submit_id).toBe('sp-1')
  })

  it('maps rejected → rejected with reason when local hash matches', async () => {
    const { applySubmissionOverlay } = await import('../../packages/server/src/services/tahp/sync/status')
    const row = {
      id: 'demo',
      state: 'local_only' as const,
      local_hash: 'abc',
      bundle_ids: [] as string[],
    }
    const out = applySubmissionOverlay(row, {
      status: 'rejected',
      submit_id: 'sp-2',
      hash: 'abc',
      comment: '缺少说明',
    })
    expect(out.state).toBe('rejected')
    expect(out.reject_reason).toBe('缺少说明')
  })

  it('does not lock rejected when local hash changed after rejection', async () => {
    const { applySubmissionOverlay } = await import('../../packages/server/src/services/tahp/sync/status')
    const row = {
      id: 'demo',
      state: 'local_only' as const,
      local_hash: 'newhash',
      bundle_ids: [] as string[],
    }
    const out = applySubmissionOverlay(row, {
      status: 'rejected',
      hash: 'oldhash',
      comment: '旧原因',
    })
    expect(out.state).toBe('local_only')
    expect(out.reject_reason).toBe('旧原因')
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
