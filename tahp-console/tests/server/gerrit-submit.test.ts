import { describe, expect, it } from 'vitest'
import {
  buildAsfBridgeEncodedCmd,
  buildGerritCommitMessage,
  buildGerritProbeScript,
  buildGerritSubmitExecutionDirective,
  buildGerritSubmitScript,
  buildGerritSubmitUserMessage,
  extractGerritScriptFatal,
  gerritRemoteBashCommand,
  isGerritSubmitStreamFatal,
  isGerritSubmitTimedOut,
  parseGerritSubmitResult,
} from '../../packages/server/src/services/tahp/gerrit-submit'
import {
  fillMappedWorkspaceIfMissing,
  toLinuxWorkCodePath,
  winPathRelativeToMappedRoot,
} from '../../packages/server/src/services/tahp/adapt-pipeline/mapped-workspace'
import { groupChangedFilesByRepo } from '../../packages/server/src/services/tahp/adapt-pipeline/repo-groups'

describe('groupChangedFilesByRepo', () => {
  it('unions overlapping files from two domains into one repo group', () => {
    const groups = groupChangedFilesByRepo([
      { domain_id: 'tp', changed_files: ['Z:\\project\\KM9_NEW\\kernel\\shared.dtsi', 'Z:\\project\\KM9_NEW\\kernel\\tp.c'] },
      { domain_id: 'vib', changed_files: ['Z:\\project\\KM9_NEW\\kernel\\shared.dtsi'] },
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0].domain_ids.sort()).toEqual(['tp', 'vib'])
    expect(groups[0].files).toHaveLength(2)
  })
})

describe('parseGerritSubmitResult', () => {
  it('extracts change URL and number', () => {
    const text = `
      Push successful.
      https://gerrit.transsion.com/c/platform/vendor/+/1234567
      Change-Id: Iabc123def456
    `
    const parsed = parseGerritSubmitResult(text)
    expect(parsed.changeUrl).toBe('https://gerrit.transsion.com/c/platform/vendor/+/1234567')
    expect(parsed.changeNumber).toBe('1234567')
    expect(parsed.changeId).toBe('Iabc123def456')
  })

  it('extracts Change-Id without URL', () => {
    const parsed = parseGerritSubmitResult('Change-Id: Ideadbeef')
    expect(parsed.changeId).toBe('Ideadbeef')
    expect(parsed.changeUrl).toBeUndefined()
  })

  it('prefers the reported GERRIT_CHANGE_URL line over quoted history', () => {
    const text = [
      '之前那个单是 https://gerrit.transsion.com/c/platform/vendor/+/1111111',
      'remote: SUCCESS',
      'remote:   https://gerrit.transsion.com/c/platform/vendor/+/2222222 [NEW]',
      'GERRIT_CHANGE_URL: https://gerrit.transsion.com/c/platform/vendor/+/2222222',
    ].join('\n')
    const parsed = parseGerritSubmitResult(text)
    expect(parsed.changeUrl).toBe('https://gerrit.transsion.com/c/platform/vendor/+/2222222')
    expect(parsed.changeNumber).toBe('2222222')
  })

  it('falls back to the last URL when no report line is present', () => {
    const text = [
      '参考历史 CR https://gerrit.transsion.com/c/a/+/1111111',
      'remote:   https://gerrit.transsion.com/c/a/+/3333333 [NEW]',
    ].join('\n')
    expect(parseGerritSubmitResult(text).changeNumber).toBe('3333333')
  })

  it('flags no-new-changes push as already submitted', () => {
    const text = [
      ' ! [remote rejected] HEAD -> refs/for/tOS_mtk_A16_trunk (no new changes)',
      'GERRIT_CHANGE_URL: https://gerrit.transsion.com/c/a/+/1592130',
    ].join('\n')
    const parsed = parseGerritSubmitResult(text)
    expect(parsed.alreadySubmitted).toBe(true)
    expect(parsed.changeNumber).toBe('1592130')
  })

  it('does not flag a normal success as already submitted', () => {
    const parsed = parseGerritSubmitResult('remote: SUCCESS\nGERRIT_CHANGE_URL: https://gerrit.transsion.com/c/a/+/9/')
    expect(parsed.alreadySubmitted).toBeUndefined()
  })

  it('repairs host dots stripped by tr -d', () => {
    const parsed = parseGerritSubmitResult(
      'GERRIT_CHANGE_URL: https://gerrittranssioncom/c/MTK_CODE/alps/vendor/mediatek/proprietary/packages/apps/agpsInterface/+/1594606',
    )
    expect(parsed.changeUrl).toBe(
      'https://gerrit.transsion.com/c/MTK_CODE/alps/vendor/mediatek/proprietary/packages/apps/agpsInterface/+/1594606',
    )
    expect(parsed.changeNumber).toBe('1594606')
  })
})

describe('buildGerritSubmitExecutionDirective', () => {
  const base = {
    skillPath: 'D:/code/tahp/skills/.claude/skills/gerrit-submit/SKILL.md',
    remoteHarnessPath: 'D:/code/tahp/skills/.claude/skills/gerrit-submit/remote-harness.md',
    skillsDir: 'D:/code/tahp/skills/.claude/skills',
  }

  it('pins BFF session and forbids claiming slot 1', () => {
    const text = buildGerritSubmitExecutionDirective({ ...base, session: 3 })
    expect(text).toContain('--session 3')
    expect(text).toContain('不要 claim slot 1')
    expect(text).toContain('bridge ls')
    expect(text).toContain('remote-harness.md')
    expect(text).toContain('execute_code')
    expect(text).toContain('clarify')
    expect(text).toContain('不要**为走流程去 Read `transsion-coding-standards-review`')
    expect(text).not.toContain('必须 Read `~/.claude/skills/asf-bridge/SKILL.md`')
  })

  it('without a pinned session still forbids ghost slot 1', () => {
    const text = buildGerritSubmitExecutionDirective(base)
    expect(text).toContain('禁止 claim slot 1')
    expect(text).toContain('bridge up --session 2')
  })
})

describe('mapped workspace paths', () => {
  it('strips Z:\\ mapped root to POSIX rel and Linux work path', () => {
    expect(winPathRelativeToMappedRoot(
      'Z:\\project\\old_vnd_6850\\vendor\\apps\\agpsInterface\\a.txt',
      'Z:\\',
    )).toBe('project/old_vnd_6850/vendor/apps/agpsInterface/a.txt')
    expect(toLinuxWorkCodePath(
      'Z:\\project\\old_vnd_6850\\vendor\\foo.c',
      { mappedRoot: 'Z:\\', linuxRoot: '/work/code/qing.li3' },
    )).toBe('/work/code/qing.li3/project/old_vnd_6850/vendor/foo.c')
  })

  it('strips UNC share to the same rel as mapped drive', () => {
    expect(winPathRelativeToMappedRoot(
      '\\\\10.205.0.143\\qing.li3\\project\\old_vnd_6850\\a.txt',
    )).toBe('project/old_vnd_6850/a.txt')
  })

  it('fills linux_root default without clobbering mapped_root', () => {
    const filled = fillMappedWorkspaceIfMissing({
      mapped_root: 'Z:\\',
      workspace: 'ws',
      variant: 'userdebug',
    }, null)
    expect(filled.mapped_root).toBe('Z:\\')
    expect(filled.linux_root).toContain('/work/code/')
  })

  it('reads inferred_remote_workspace from the approved discover candidate', () => {
    const filled = fillMappedWorkspaceIfMissing({
      mapped_root: '',
      workspace: '',
      variant: 'userdebug',
    }, {
      candidates: [
        {
          mapped_root: 'Z:\\',
          approved_for_runner: true,
          inferred_remote_workspace: '/work/code/qing.li3',
        },
      ],
    })
    expect(filled.mapped_root).toBe('Z:\\')
    expect(filled.linux_root).toBe('/work/code/qing.li3')
  })
})

describe('gerrit commit scripts', () => {
  it('builds UTF-8 commit message with ID and TYPE=test for agent-test files', () => {
    const msg = buildGerritCommitMessage({
      issueId: 'TOS163-46271',
      files: ['vendor/apps/agpsInterface/agent-test-output/comm.txt'],
      domainLabel: '通信框架',
    })
    expect(msg).toContain('ID:TOS163-46271')
    expect(msg).toContain('TYPE:test')
    expect(msg).toContain('DESCRIPTION:')
  })

  it('encodes PROBE/SUBMIT as ASCII asf commands with pinned session', () => {
    const probe = buildGerritProbeScript({
      relFiles: ['project/a.txt'],
      linuxRoot: '/work/code/qing.li3',
      nonce: 'abcd',
    })
    const submit = buildGerritSubmitScript({
      relFiles: ['project/a.txt'],
      linuxRoot: '/work/code/qing.li3',
      nonce: 'abcd',
      message: 'ID:TOS1\nDESCRIPTION:新增 中文说明\nTYPE:test\nAFFECT_PROJECTS:ALL\nTEST_SUGGESTIONS:x\n[是否自检]：是\n[是否影响其它项目]:否\n[是否影响其它平台]:否\n[是否chery-pick其它分支]:否',
      branch: 'tOS15.1.2_mtk_A12_vnd_release',
    })
    expect(probe).toContain('PROBE_BEGIN_')
    expect(submit).toContain('base64 -d')
    expect(submit).not.toContain('中文说明')
    expect(submit).toContain("sed 's/[.,;)]*$//'")
    expect(submit).not.toContain("tr -d '.,;'")
    const b64 = submit.match(/MSG_B64='([^']+)'/)?.[1]
    expect(b64).toBeTruthy()
    expect(Buffer.from(b64!, 'base64').toString('utf8')).toContain('中文说明')
    const cmd = buildAsfBridgeEncodedCmd({ session: 2, waitSec: 12, script: submit })
    expect(cmd).toMatch(/^asf --json bridge cmd --session 2 --wait 12 /)
    expect(cmd).not.toMatch(/[\u4e00-\u9fff]/)
    expect(cmd).toContain("echo '")
  })

  it('extracts FATAL from script output and wraps UTF-8 as remote bash', () => {
    expect(extractGerritScriptFatal('ok\nFATAL: cannot infer refs/for branch\nend')).toBe(
      'FATAL: cannot infer refs/for branch',
    )
    const cmd = gerritRemoteBashCommand('echo 中文')
    expect(cmd.startsWith("echo '")).toBe(true)
    expect(cmd).toContain('base64 -d | bash')
    expect(cmd).not.toMatch(/[\u4e00-\u9fff]/)
  })

  it('user message lists Linux paths and ready asf commands', () => {
    const text = buildGerritSubmitUserMessage({
      runId: 'r1',
      projectCode: 'LK7',
      repo: 'Z:\\project',
      repoLabel: 'project',
      files: ['Z:\\project\\a.txt'],
      domainIds: ['comm-framework'],
      domainLabels: ['通信框架'],
      buildContext: {
        mapped_root: 'Z:\\',
        linux_root: '/work/code/qing.li3',
        workspace: '',
        variant: 'userdebug',
        gerrit_issue_id: 'TOS163-46271',
      },
    }, {
      linuxFiles: [{
        win: 'Z:\\project\\a.txt',
        linux: '/work/code/qing.li3/project/a.txt',
        rel: 'project/a.txt',
      }],
      commitMessage: 'ID:TOS163-46271\nDESCRIPTION:x',
      probeCmd: 'asf --json bridge cmd --session 2 --wait 12 "echo ABC | base64 -d | bash"',
      submitCmd: 'asf --json bridge cmd --session 2 --wait 180 "echo DEF | base64 -d | bash"',
      session: 2,
    })
    expect(text).toContain('/work/code/qing.li3/project/a.txt')
    expect(text).toContain('--session 2')
    expect(text).toContain('禁止再扫 Z:\\')
    expect(text).toContain('本仓库变更文件')
    expect(text).not.toContain('adapt_debug')
  })
})

describe('gerrit stream fatal / timeout', () => {
  it('treats Qizhi password UI as fatal and ignores BFF ghost-skip logs', () => {
    expect(isGerritSubmitStreamFatal("qing.li3@10.205.0.143's password:")).toBe(true)
    expect(isGerritSubmitStreamFatal('请选择登录账号')).toBe(true)
    expect(isGerritSubmitStreamFatal('跳过幽灵 mux，up --session 2')).toBe(false)
    expect(isGerritSubmitStreamFatal('已认领 ASF Bridge session 2，Agent 不得改槽')).toBe(false)
  })

  it('flags submit as timed out after the stale window', () => {
    const started = new Date(1_700_000_000_000).toISOString()
    expect(isGerritSubmitTimedOut(started, 1_700_000_000_000 + 13 * 60_000)).toBe(true)
    expect(isGerritSubmitTimedOut(started, 1_700_000_000_000 + 60_000)).toBe(false)
  })
})
