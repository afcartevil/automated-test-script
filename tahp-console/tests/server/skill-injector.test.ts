import { mkdir, mkdtemp, readFile, rm, writeFile } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, describe, expect, it, vi } from 'vitest'

const tempDirs: string[] = []
const originalHermesHome = process.env.HERMES_HOME
const originalSkillsDir = process.env.HERMES_WEB_UI_SKILLS_DIR

async function tempDir(prefix: string): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), prefix))
  tempDirs.push(dir)
  return dir
}

afterEach(async () => {
  vi.resetModules()
  if (originalHermesHome === undefined) delete process.env.HERMES_HOME
  else process.env.HERMES_HOME = originalHermesHome
  if (originalSkillsDir === undefined) delete process.env.HERMES_WEB_UI_SKILLS_DIR
  else process.env.HERMES_WEB_UI_SKILLS_DIR = originalSkillsDir
  await Promise.all(tempDirs.splice(0).map(dir => rm(dir, { recursive: true, force: true })))
})

describe('HermesSkillInjector', () => {
  it('resolves source directories for override, production bundle, and development layouts', async () => {
    const root = await tempDir('hermes-skill-injector-paths-')
    const override = join(root, 'override-skills')
    const distSkills = join(root, 'dist', 'skills')
    const devSkills = join(root, 'packages', 'skills')
    await mkdir(override, { recursive: true })
    await mkdir(distSkills, { recursive: true })
    await mkdir(devSkills, { recursive: true })

    // 本仓运行时 hasTahpProject() 为真会短路到工程 skills；路径候选分支需隔离 mock
    vi.doMock('../../packages/server/src/services/tahp/paths', () => ({
      hasTahpProject: () => false,
      tahpPaths: { projectRoot: root, skillsDir: join(root, 'skills') },
    }))

    const { HermesSkillInjector } = await import('../../packages/server/src/services/hermes/skill-injector')

    expect(HermesSkillInjector.resolveSourceDir({ HERMES_WEB_UI_SKILLS_DIR: override } as any, join(root, 'dist', 'server'))).toBe(override)
    expect(HermesSkillInjector.resolveSourceDir({} as any, join(root, 'dist', 'server'))).toBe(distSkills)
    expect(HermesSkillInjector.resolveSourceDir({} as any, join(root, 'packages', 'server', 'src', 'services', 'hermes'))).toBe(devSkills)
  })

  it('syncs bundled skills and replaces existing bundled copies', async () => {
    const source = await tempDir('hermes-skill-source-')
    const hermesHome = await tempDir('hermes-skill-home-')
    process.env.HERMES_HOME = hermesHome

    await mkdir(join(source, 'new-skill'), { recursive: true })
    await writeFile(join(source, 'new-skill', 'SKILL.md'), '# New Skill\n', 'utf-8')
    await mkdir(join(source, 'existing-skill'), { recursive: true })
    await writeFile(join(source, 'existing-skill', 'SKILL.md'), '# Bundled Existing\n', 'utf-8')

    await mkdir(join(hermesHome, 'skills', 'existing-skill'), { recursive: true })
    await writeFile(join(hermesHome, 'skills', 'existing-skill', 'SKILL.md'), '# User Existing\n', 'utf-8')

    const { HermesSkillInjector } = await import('../../packages/server/src/services/hermes/skill-injector')
    const result = await new HermesSkillInjector(source).injectMissingSkills()

    expect(result.injected).toEqual(['new-skill'])
    expect(result.updated).toEqual(['existing-skill'])
    expect(result.skipped).toEqual([])
    await expect(readFile(join(hermesHome, 'skills', 'new-skill', 'SKILL.md'), 'utf-8')).resolves.toBe('# New Skill\n')
    await expect(readFile(join(hermesHome, 'skills', 'existing-skill', 'SKILL.md'), 'utf-8')).resolves.toBe('# Bundled Existing\n')
  })

  it('skips unchanged bundled skills on subsequent sync', async () => {
    const source = await tempDir('hermes-skill-source-skip-')
    const hermesHome = await tempDir('hermes-skill-home-skip-')
    process.env.HERMES_HOME = hermesHome

    await mkdir(join(source, 'stable-skill'), { recursive: true })
    await writeFile(join(source, 'stable-skill', 'SKILL.md'), '# Stable\n', 'utf-8')

    const { HermesSkillInjector } = await import('../../packages/server/src/services/hermes/skill-injector')
    const injector = new HermesSkillInjector(source)

    const first = await injector.injectMissingSkills()
    expect(first.injected).toEqual(['stable-skill'])
    expect(first.skipped).toEqual([])

    const second = await injector.injectMissingSkills()
    expect(second.injected).toEqual([])
    expect(second.updated).toEqual([])
    expect(second.skipped).toEqual(['stable-skill'])
  })

  it('only syncs requested skillIds when filter is provided', async () => {
    const source = await tempDir('hermes-skill-source-filter-')
    const hermesHome = await tempDir('hermes-skill-home-filter-')
    process.env.HERMES_HOME = hermesHome

    await mkdir(join(source, 'keep-a'), { recursive: true })
    await writeFile(join(source, 'keep-a', 'SKILL.md'), '# A\n', 'utf-8')
    await mkdir(join(source, 'skip-b'), { recursive: true })
    await writeFile(join(source, 'skip-b', 'SKILL.md'), '# B\n', 'utf-8')

    const { HermesSkillInjector } = await import('../../packages/server/src/services/hermes/skill-injector')
    const result = await new HermesSkillInjector(source).injectMissingSkills(['keep-a'])

    expect(result.injected).toEqual(['keep-a'])
    expect(result.skipped).toEqual([])
    await expect(readFile(join(hermesHome, 'skills', 'keep-a', 'SKILL.md'), 'utf-8')).resolves.toBe('# A\n')
    const { existsSync } = await import('fs')
    expect(existsSync(join(hermesHome, 'skills', 'skip-b'))).toBe(false)
  })
})
