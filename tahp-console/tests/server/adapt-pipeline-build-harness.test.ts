import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join, normalize } from 'path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  defaultBuildSkillId,
  defaultFlashSkillId,
  listHarnessSkillRoots,
  listHarnessSkills,
  listUserHarnessSkillRoots,
  pickPreferredSkillId,
  resolveUserHarnessSkillPath,
} from '../../packages/server/src/services/tahp/adapt-pipeline/harness-skill-registry'
import {
  normalizeBuildResult,
  parseBuildResultFromText,
  writeBuildResult,
  readBuildResultFile,
  buildResultFilePath,
  looksLikeBackgroundWaitWithoutResult,
} from '../../packages/server/src/services/tahp/adapt-pipeline/build-result-contract'
import {
  filterFilesBySelectedRepos,
  groupChangedFilesByRepo,
} from '../../packages/server/src/services/tahp/adapt-pipeline/repo-groups'

describe('harness-skill-registry', () => {
  let root = ''
  const prev = process.env.TAHP_HARNESS_SKILL_ROOTS

  beforeEach(() => {
    root = mkdtempSync(join(tmpdir(), 'harness-skills-'))
    mkdirSync(join(root, 'harness-build-whole-device'))
    writeFileSync(
      join(root, 'harness-build-whole-device', 'SKILL.md'),
      '---\nname: harness-build-whole-device\ndescription: whole\n---\n',
    )
    mkdirSync(join(root, 'harness-build-native'))
    writeFileSync(
      join(root, 'harness-build-native', 'SKILL.md'),
      '---\nname: harness-build-native\ndescription: native\n---\n',
    )
    mkdirSync(join(root, 'harness-device'))
    writeFileSync(
      join(root, 'harness-device', 'SKILL.md'),
      '---\nname: harness-device\ndescription: flash\n---\n',
    )
    mkdirSync(join(root, 'asf-device'))
    writeFileSync(
      join(root, 'asf-device', 'SKILL.md'),
      '---\nname: asf-device\ndescription: flash asf\n---\n',
    )
    mkdirSync(join(root, 'unrelated-skill'))
    writeFileSync(join(root, 'unrelated-skill', 'SKILL.md'), '---\nname: x\n---\n')
    process.env.TAHP_HARNESS_SKILL_ROOTS = root
  })

  afterEach(() => {
    if (prev === undefined) delete process.env.TAHP_HARNESS_SKILL_ROOTS
    else process.env.TAHP_HARNESS_SKILL_ROOTS = prev
    rmSync(root, { recursive: true, force: true })
  })

  it('lists build/flash skills from configured roots', () => {
    expect(listHarnessSkillRoots()).toContain(root)
    const all = listHarnessSkills()
    const ids = all.map(s => s.id)
    expect(ids).toEqual(expect.arrayContaining([
      'harness-build-native',
      'harness-build-whole-device',
      'harness-device',
      'asf-device',
    ]))
    expect(ids).not.toContain('unrelated-skill')
    expect(listHarnessSkills('build').some(s => s.id === 'harness-build-whole-device')).toBe(true)
    expect(listHarnessSkills('flash').some(s => s.id === 'harness-device')).toBe(true)
    expect(listHarnessSkills('flash').some(s => s.id === 'asf-device')).toBe(true)
  })

  it('pickPreferredSkillId prefers asf-* when both prefixes are installed', () => {
    expect(pickPreferredSkillId('flash', ['harness-device', 'asf-device'])).toBe('asf-device')
    expect(pickPreferredSkillId('flash', ['harness-device'])).toBe('harness-device')
    expect(pickPreferredSkillId('build', ['harness-build-whole-device', 'asf-build-whole-device'], 'whole_device'))
      .toBe('asf-build-whole-device')
    expect(pickPreferredSkillId('build', ['harness-build-whole-device'], 'whole_device'))
      .toBe('harness-build-whole-device')
    expect(pickPreferredSkillId('build', ['harness-build-native'], 'native_module')).toBe('harness-build-native')
    expect(pickPreferredSkillId('build', ['harness-build'], undefined)).toBe('harness-build')
  })

  it('default skill ids stay within scanned lists', () => {
    const flashIds = listHarnessSkills('flash').map(s => s.id)
    const buildIds = listHarnessSkills('build').map(s => s.id)
    expect(flashIds).toContain(defaultFlashSkillId())
    expect(['asf-build-whole-device', 'harness-build-whole-device', ...buildIds])
      .toContain(defaultBuildSkillId('whole_device'))
    expect(['asf-build-native', 'harness-build-native', ...buildIds])
      .toContain(defaultBuildSkillId('native_module'))
  })

  it('resolveUserHarnessSkillPath reads user skill roots excluding project skills dir', () => {
    expect(listUserHarnessSkillRoots()).toContain(root)
    expect(resolveUserHarnessSkillPath('asf-device')?.replace(/\\/g, '/')).toMatch(/(asf|harness)-device\/SKILL\.md$/)
    expect(resolveUserHarnessSkillPath('harness-device')?.replace(/\\/g, '/')).toMatch(/(asf|harness)-device\/SKILL\.md$/)
    const onlyInTemp = 'harness-flash-registry-test'
    mkdirSync(join(root, onlyInTemp))
    writeFileSync(
      join(root, onlyInTemp, 'SKILL.md'),
      `---\nname: ${onlyInTemp}\ndescription: test\n---\n`,
    )
    const resolved = resolveUserHarnessSkillPath(onlyInTemp)
    expect(resolved).not.toBeNull()
    expect(resolved!.replace(/\\/g, '/')).toContain(`${root.replace(/\\/g, '/')}/${onlyInTemp}/SKILL.md`)
    expect(resolveUserHarnessSkillPath('missing-skill-xyz')).toBeNull()
  })
})

describe('build-result-contract', () => {
  it('parses fenced TAHP_BUILD_RESULT', () => {
    const text = `
done
\`\`\`json
TAHP_BUILD_RESULT
{"schema_version":1,"status":"pass","artifacts_dir":"Z:/out","pkg_path":"Z:/out/rom.zip"}
\`\`\`
`
    const parsed = parseBuildResultFromText(text)
    expect(parsed?.status).toBe('pass')
    expect(parsed?.artifacts_dir).toBe('Z:/out')
    expect(parsed?.pkg_path).toBe('Z:/out/rom.zip')
  })

  it('round-trips result file', () => {
    const dir = mkdtempSync(join(tmpdir(), 'build-result-'))
    try {
      const file = buildResultFilePath(dir)
      writeBuildResult(file, normalizeBuildResult({
        status: 'fail',
        error: 'boom',
        failed_stage: 'package',
      }))
      const read = readBuildResultFile(file)
      expect(read?.status).toBe('fail')
      expect(read?.error).toBe('boom')
    } finally {
      rmSync(dir, { recursive: true, force: true })
    }
  })

  it('detects background-wait endings without TAHP_BUILD_RESULT', () => {
    expect(looksLikeBackgroundWaitWithoutResult(
      '基础组件编译已提交后台。等待完成通知',
    )).toBe(true)
    expect(looksLikeBackgroundWaitWithoutResult(
      '三个组件正在并行编译中。等待完成',
    )).toBe(true)
    expect(looksLikeBackgroundWaitWithoutResult(
      '等待完成通知\n```json\nTAHP_BUILD_RESULT\n{"status":"fail"}\n```',
    )).toBe(false)
    expect(looksLikeBackgroundWaitWithoutResult('编译成功')).toBe(false)
  })
})

describe('repo-groups', () => {
  it('groups by parent directory when git root unavailable', () => {
    const groups = groupChangedFilesByRepo([
      {
        domain_id: 'tp',
        status: 'done',
        enabled: true,
        changed_files: [
          'Q:\\adapt-test\\vendor\\a\\x.c',
          'Q:\\adapt-test\\vendor\\a\\y.c',
          'Q:\\adapt-test\\kernel\\b.c',
        ],
      },
    ])
    expect(groups.map(g => g.repo_label).sort()).toEqual(['a', 'kernel'])
    expect(groups.find(g => g.repo_label === 'a')?.files).toHaveLength(2)
  })

  it('filters files by selected repos', () => {
    const selected = [normalize('Q:\\adapt-test\\vendor')]
    const kept = filterFilesBySelectedRepos(
      ['Q:\\adapt-test\\vendor\\a.c', 'Q:\\adapt-test\\kernel\\b.c'],
      selected,
    )
    expect(kept).toEqual(['Q:\\adapt-test\\vendor\\a.c'])
  })

  it('drops relative paths when grouping', () => {
    const groups = groupChangedFilesByRepo([
      {
        domain_id: 'tp',
        status: 'done',
        enabled: true,
        changed_files: ['vendor/a.c', 'Q:\\adapt-test\\kernel\\b.c'],
      },
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0].files).toEqual(['Q:\\adapt-test\\kernel\\b.c'])
  })
})

describe('workspace-changed-files', () => {
  it('keeps only absolute paths and dedupes', async () => {
    const { mergeAbsolutePaths } = await import(
      '../../packages/server/src/services/tahp/adapt-pipeline/workspace-changed-files'
    )
    const merged = mergeAbsolutePaths([
      'Q:\\adapt-test\\kernel\\foo.c',
      'vendor/bar.c',
      'D:\\outside\\x.c',
      'Q:\\adapt-test\\kernel\\foo.c',
    ])
    expect(merged).toEqual([
      normalize('Q:\\adapt-test\\kernel\\foo.c'),
      normalize('D:\\outside\\x.c'),
    ])
  })

  it('domainsWithChangedFiles keeps all absolute paths', async () => {
    const { domainsWithChangedFiles } = await import(
      '../../packages/server/src/services/tahp/adapt-pipeline/workspace-changed-files'
    )
    const domains = domainsWithChangedFiles([
      {
        domain_id: 'tp',
        enabled: true,
        status: 'done',
        changed_files: ['Q:\\adapt-test\\drivers\\a.c', 'relative/skip.c'],
      },
      {
        domain_id: 'lcm',
        enabled: true,
        status: 'done',
        changed_files: ['D:\\old\\only.c'],
      },
      {
        domain_id: 'fp',
        enabled: true,
        status: 'done',
        changed_files: ['vendor/only-rel.c'],
      },
    ])
    expect(domains.map(d => d.domain_id).sort()).toEqual(['lcm', 'tp'])
    expect(domains.find(d => d.domain_id === 'tp')?.changed_files).toEqual([
      normalize('Q:\\adapt-test\\drivers\\a.c'),
    ])
  })
})
