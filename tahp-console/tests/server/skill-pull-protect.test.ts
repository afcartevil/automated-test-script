import { mkdir, mkdtemp, writeFile, readFile, rm } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { shortHashBuffer } from '../../packages/server/src/services/tahp/sync/hash'

const tempDirs: string[] = []

async function tempDir(prefix: string): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), prefix))
  tempDirs.push(dir)
  return dir
}

function packageHashOf(files: Array<{ rel_path: string; content: Buffer }>): string {
  const metas = files
    .map(f => ({
      rel_path: f.rel_path,
      hash: shortHashBuffer(f.content),
      size: f.content.length,
    }))
    .sort((a, b) => a.rel_path.localeCompare(b.rel_path, 'en'))
  const payload = metas.map(f => `${f.rel_path}\0${f.hash}\n`).join('')
  return shortHashBuffer(Buffer.from(payload, 'utf-8'))
}

afterEach(async () => {
  vi.resetModules()
  await Promise.all(tempDirs.splice(0).map(dir => rm(dir, { recursive: true, force: true })))
})

async function setupPullEnv(root: string) {
  vi.doMock('../../packages/server/src/services/tahp/paths', () => ({
    tahpPaths: {
      projectRoot: root,
      skillsDir: join(root, 'skills', '.claude', 'skills'),
      knowledgeDir: join(root, 'knowledge-base'),
    },
  }))
  vi.doMock('../../packages/server/src/services/hermes/skill-injector', () => ({
    HermesSkillInjector: class {
      async injectMissingSkills() {
        return { injected: [], updated: [] }
      }
    },
  }))
}

describe('applyPull local protection', () => {
  it('does not overwrite a locally edited skill', async () => {
    const root = await tempDir('skill-pull-dirty-')
    const skillDir = join(root, 'skills', '.claude', 'skills', 'demo-pack')
    await mkdir(skillDir, { recursive: true })
    await writeFile(join(skillDir, 'SKILL.md'), '---\nname: local\n---\n\n# local edit\n', 'utf-8')
    await writeFile(join(skillDir, 'notes.md'), 'keep me\n', 'utf-8')

    await setupPullEnv(root)
    const { getLocalPackageHash } = await import('../../packages/server/src/services/tahp/sync/skill-package')
    const { applyPull } = await import('../../packages/server/src/services/tahp/sync/pull')
    const localHash = getLocalPackageHash('demo-pack')
    expect(localHash).toBeTruthy()

    const remoteMd = Buffer.from('---\nname: remote\n---\n\n# remote\n', 'utf-8')
    const result = await applyPull({
      generated_at: new Date().toISOString(),
      entries: [],
      configs: [],
      skills: [{
        id: 'demo-pack',
        rel_path: 'skills/.claude/skills/demo-pack/SKILL.md',
        content: '',
        updated_at: new Date().toISOString(),
        hash: 'remote-hash-not-local',
        files: [{
          rel_path: 'SKILL.md',
          content_b64: remoteMd.toString('base64'),
          hash: 'x',
        }],
      }],
    })

    expect(result.skipped_dirty).toEqual(['demo-pack'])
    expect(result.skill_ids).toEqual([])
    expect(result.failed).toEqual([])
    expect(await readFile(join(skillDir, 'notes.md'), 'utf-8')).toBe('keep me\n')
    expect(await readFile(join(skillDir, 'SKILL.md'), 'utf-8')).toContain('# local edit')
  })

  it('force overwrites a locally edited skill', async () => {
    const root = await tempDir('skill-pull-force-')
    const skillDir = join(root, 'skills', '.claude', 'skills', 'demo-pack')
    await mkdir(skillDir, { recursive: true })
    await writeFile(join(skillDir, 'SKILL.md'), '---\nname: local\n---\n\n# local edit\n', 'utf-8')
    await writeFile(join(skillDir, 'notes.md'), 'keep me\n', 'utf-8')

    await setupPullEnv(root)
    const { applyPull } = await import('../../packages/server/src/services/tahp/sync/pull')
    const remoteMd = Buffer.from('---\nname: remote\n---\n\n# remote\n', 'utf-8')
    const remoteHash = packageHashOf([{ rel_path: 'SKILL.md', content: remoteMd }])
    const result = await applyPull({
      generated_at: new Date().toISOString(),
      entries: [],
      configs: [],
      skills: [{
        id: 'demo-pack',
        rel_path: 'skills/.claude/skills/demo-pack/SKILL.md',
        content: '',
        updated_at: new Date().toISOString(),
        hash: remoteHash,
        files: [{
          rel_path: 'SKILL.md',
          content_b64: remoteMd.toString('base64'),
          hash: 'x',
        }],
      }],
    }, { force: true })

    expect(result.skill_ids).toEqual(['demo-pack'])
    expect(result.skipped_dirty).toEqual([])
    expect(result.failed).toEqual([])
    expect(await readFile(join(skillDir, 'SKILL.md'), 'utf-8')).toContain('# remote')
  })
})

describe('applyPull apply result', () => {
  it('records failed when written package hash still mismatches central', async () => {
    const root = await tempDir('skill-pull-hash-mismatch-')
    const skillDir = join(root, 'skills', '.claude', 'skills', 'demo-pack')
    await mkdir(skillDir, { recursive: true })
    await writeFile(join(skillDir, 'SKILL.md'), '---\nname: local\n---\n\n# local\n', 'utf-8')

    await setupPullEnv(root)
    const { applyPull } = await import('../../packages/server/src/services/tahp/sync/pull')
    const remoteMd = Buffer.from('---\nname: remote\n---\n\n# remote\n', 'utf-8')
    const result = await applyPull({
      generated_at: new Date().toISOString(),
      entries: [],
      configs: [],
      skills: [{
        id: 'demo-pack',
        rel_path: 'skills/.claude/skills/demo-pack/SKILL.md',
        content: '',
        updated_at: new Date().toISOString(),
        hash: 'deadbeefdeadbeef',
        files: [{
          rel_path: 'SKILL.md',
          content_b64: remoteMd.toString('base64'),
          hash: 'x',
        }],
      }],
    }, { force: true })

    expect(result.skill_ids).toEqual([])
    expect(result.failed).toHaveLength(1)
    expect(result.failed[0].id).toBe('demo-pack')
    expect(result.failed[0].error).toContain('写入后仍未与服务器对齐')
    expect(await readFile(join(skillDir, 'SKILL.md'), 'utf-8')).toContain('# remote')
  })

  it('marks specified skill missing from pull payload as failed', async () => {
    const root = await tempDir('skill-pull-missing-')
    await mkdir(join(root, 'skills', '.claude', 'skills'), { recursive: true })
    await setupPullEnv(root)
    const { applyPull } = await import('../../packages/server/src/services/tahp/sync/pull')
    const result = await applyPull({
      generated_at: new Date().toISOString(),
      entries: [],
      configs: [],
      skills: [],
    }, { onlySkillIds: ['com-comm-sop-source-archive'] })

    expect(result.failed).toEqual([{
      id: 'com-comm-sop-source-archive',
      error: '中心拉取结果中无该 Skill',
    }])
    expect(result.skill_ids).toEqual([])
  })

  it('applies when local still equals last applied and central hash matches written files', async () => {
    const root = await tempDir('skill-pull-behind-apply-')
    const skillDir = join(root, 'skills', '.claude', 'skills', 'demo-pack')
    await mkdir(skillDir, { recursive: true })
    await writeFile(join(skillDir, 'SKILL.md'), '---\nname: old\n---\n\n# old\n', 'utf-8')

    await setupPullEnv(root)
    const { getLocalPackageHash } = await import('../../packages/server/src/services/tahp/sync/skill-package')
    const { recordLastAppliedHash } = await import('../../packages/server/src/services/tahp/sync/status')
    const { applyPull } = await import('../../packages/server/src/services/tahp/sync/pull')
    const oldHash = getLocalPackageHash('demo-pack', true)
    expect(oldHash).toBeTruthy()
    recordLastAppliedHash('demo-pack', oldHash!)

    const remoteMd = Buffer.from('---\nname: remote\n---\n\n# remote\n', 'utf-8')
    const remoteHash = packageHashOf([{ rel_path: 'SKILL.md', content: remoteMd }])
    const result = await applyPull({
      generated_at: new Date().toISOString(),
      entries: [],
      configs: [],
      skills: [{
        id: 'demo-pack',
        rel_path: 'skills/.claude/skills/demo-pack/SKILL.md',
        content: '',
        updated_at: new Date().toISOString(),
        hash: remoteHash,
        files: [{
          rel_path: 'SKILL.md',
          content_b64: remoteMd.toString('base64'),
          hash: 'x',
        }],
      }],
    })

    expect(result.failed).toEqual([])
    expect(result.skill_ids).toEqual(['demo-pack'])
    expect(result.skipped_dirty).toEqual([])
    expect(await readFile(join(skillDir, 'SKILL.md'), 'utf-8')).toContain('# remote')
  })
})
