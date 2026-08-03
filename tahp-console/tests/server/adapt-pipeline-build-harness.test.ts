import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join, normalize } from 'path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  defaultBuildSkillId,
  listHarnessSkillRoots,
  listHarnessSkills,
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
    ]))
    expect(ids).not.toContain('unrelated-skill')
    expect(listHarnessSkills('build').some(s => s.id === 'harness-build-whole-device')).toBe(true)
    expect(listHarnessSkills('flash').some(s => s.id === 'harness-device')).toBe(true)
  })

  it('defaultBuildSkillId maps kind', () => {
    expect(defaultBuildSkillId('whole_device')).toBe('harness-build-whole-device')
    expect(defaultBuildSkillId('native_module')).toBe('harness-build-native')
    expect(defaultBuildSkillId(undefined)).toBe('harness-build')
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
  it('groups by top-level path when git root unavailable', () => {
    const root = 'Z:\\ws'
    const groups = groupChangedFilesByRepo(root, [
      {
        domain_id: 'tp',
        status: 'done',
        enabled: true,
        changed_files: ['vendor/a/x.c', 'vendor/a/y.c', 'kernel/b.c'],
      },
    ])
    expect(groups.map(g => g.repo_label).sort()).toEqual(['kernel', 'vendor'])
    expect(groups.find(g => g.repo_label === 'vendor')?.files).toHaveLength(2)
  })

  it('filters files by selected repos', () => {
    const root = 'Z:\\ws'
    const selected = [join(root, 'vendor')]
    const kept = filterFilesBySelectedRepos(
      root,
      ['vendor/a.c', 'kernel/b.c'],
      selected,
    )
    expect(kept).toEqual(['vendor/a.c'])
  })
})

describe('workspace-changed-files', () => {
  it('resolves aosp workspace under mapped_root', async () => {
    const {
      resolveAospWorkspaceRoot,
      filterFilesUnderWorkspace,
      mergeAbsolutePaths,
    } = await import('../../packages/server/src/services/tahp/adapt-pipeline/workspace-changed-files')

    expect(resolveAospWorkspaceRoot('Z:\\map', 'aosp')).toBe(normalize(join('Z:\\map', 'aosp')))

    const tree = resolveAospWorkspaceRoot('Z:\\map', 'aosp')
    const merged = mergeAbsolutePaths(
      [
        join(tree, 'kernel', 'foo.c'),
        'vendor/bar.c',
        'D:\\outside\\x.c',
      ],
      tree,
    )
    expect(merged).toHaveLength(3)

    const filtered = filterFilesUnderWorkspace(
      [
        join(tree, 'kernel', 'foo.c'),
        'vendor/bar.c',
        'D:\\outside\\x.c',
        join('Z:\\map', 'other', 'skip.c'),
      ],
      'Z:\\map',
      'aosp',
    )
    expect(filtered).toEqual([
      normalize(join(tree, 'kernel', 'foo.c')),
      normalize(join(tree, 'vendor', 'bar.c')),
    ])
  })

  it('domainsWithWorkspaceChanges drops empty and out-of-tree files', async () => {
    const { domainsWithWorkspaceChanges } = await import(
      '../../packages/server/src/services/tahp/adapt-pipeline/workspace-changed-files'
    )
    const tree = normalize(join('Z:\\map', 'aosp'))
    const domains = domainsWithWorkspaceChanges(
      [
        {
          domain_id: 'tp',
          enabled: true,
          status: 'done',
          changed_files: [join(tree, 'drivers', 'a.c'), 'D:\\old\\ref.c'],
        },
        {
          domain_id: 'lcm',
          enabled: true,
          status: 'done',
          changed_files: ['D:\\old\\only.c'],
        },
      ],
      'Z:\\map',
      'aosp',
    )
    expect(domains).toHaveLength(1)
    expect(domains[0].domain_id).toBe('tp')
    expect(domains[0].changed_files).toEqual([normalize(join(tree, 'drivers', 'a.c'))])
  })
})
