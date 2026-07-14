import { mkdir, mkdtemp, writeFile, rm } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, describe, expect, it, vi } from 'vitest'

const tempDirs: string[] = []

async function tempDir(prefix: string): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), prefix))
  tempDirs.push(dir)
  return dir
}

afterEach(async () => {
  vi.resetModules()
  await Promise.all(tempDirs.splice(0).map(dir => rm(dir, { recursive: true, force: true })))
})

describe('skill package hash', () => {
  it('computes stable package hash from file set', async () => {
    const root = await tempDir('skill-pkg-')
    const skillDir = join(root, 'skills', '.claude', 'skills', 'demo-pack')
    await mkdir(join(skillDir, 'scripts'), { recursive: true })
    await writeFile(join(skillDir, 'SKILL.md'), '---\nname: demo\n---\n\n# demo\n', 'utf-8')
    await writeFile(join(skillDir, 'scripts', 'run.py'), 'print(1)\n', 'utf-8')

    vi.doMock('../../packages/server/src/services/tahp/paths', () => ({
      tahpPaths: {
        projectRoot: root,
        skillsDir: join(root, 'skills', '.claude', 'skills'),
        knowledgeDir: join(root, 'knowledge-base'),
      },
    }))

    const {
      listLocalSkillFiles,
      computePackageHash,
      getLocalPackageHash,
      buildLocalSkillZipBuffer,
      applySkillZipToLocal,
    } = await import('../../packages/server/src/services/tahp/sync/skill-package')

    const files = listLocalSkillFiles('demo-pack')
    expect(files.map(f => f.rel_path).sort()).toEqual(['SKILL.md', 'scripts/run.py'])
    const hash1 = computePackageHash(files)
    expect(getLocalPackageHash('demo-pack')).toBe(hash1)

    const zip = buildLocalSkillZipBuffer('demo-pack')
    expect(zip.length).toBeGreaterThan(20)

    // overwrite and restore via zip
    await writeFile(join(skillDir, 'SKILL.md'), 'changed\n', 'utf-8')
    expect(getLocalPackageHash('demo-pack')).not.toBe(hash1)
    applySkillZipToLocal('demo-pack', zip)
    expect(getLocalPackageHash('demo-pack')).toBe(hash1)
  })
})
