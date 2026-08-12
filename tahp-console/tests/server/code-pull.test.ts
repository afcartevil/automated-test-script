/**
 * 代码拉取：repo init 校验、路径约定、tmux 命令构造
 */
import { describe, expect, it } from 'vitest'
import {
  buildRepoInitCommand,
  buildRepoSyncTmuxStart,
  codePullLinuxPath,
  codePullWinPath,
  detectRepoSyncFailureInLog,
  formatRepoSyncFailure,
  pickMappedRootFromDiscover,
  validateRepoInitCommand,
} from '../../packages/server/src/services/tahp/code-pull'
import { normalizeMappedRoot } from '../../packages/server/src/services/tahp/code-pull/result-parse'

const SAMPLE_INIT =
  'repo init -u ssh://gerrit.transsion.com:29418/ODC_CODE/platform/manifest -b master -m tOS_od_mtk_A16_trunk.xml --repo-url ssh://gerrit-sw.transsion.com:29418/repo --repo-branch stable-v1 --reference /opt/git/mirror --no-repo-verify'

describe('validateRepoInitCommand', () => {
  it('accepts repo init command', () => {
    expect(validateRepoInitCommand(SAMPLE_INIT, 'system')).toContain('repo init')
  })

  it('rejects non-init', () => {
    expect(() => validateRepoInitCommand('repo sync -c', 'system')).toThrow(/repo init/)
  })
})

describe('path convention A', () => {
  it('builds linux and win paths under code-pull/<runId>', () => {
    const runId = 'cpull-123-abc'
    expect(codePullLinuxPath(runId, 'system')).toBe(
      '/work/code/$(whoami)/code-pull/cpull-123-abc/system',
    )
    expect(codePullWinPath('Z:\\', runId, 'vendor')).toBe(
      'Z:\\code-pull\\cpull-123-abc\\vendor',
    )
    expect(normalizeMappedRoot('Z:')).toBe('Z:\\')
  })
})

describe('repo command builders', () => {
  it('wraps init with mkdir/cd and REPO_INIT_OK', () => {
    const cmd = buildRepoInitCommand(
      '/work/code/$(whoami)/code-pull/r1/system',
      SAMPLE_INIT,
    )
    expect(cmd).toContain('mkdir -p')
    expect(cmd).toContain('REPO_INIT_OK')
    expect(cmd).toContain('repo init -u')
    expect(cmd).toContain('$(whoami)')
  })

  it('starts tmux repo sync -c', () => {
    const cmd = buildRepoSyncTmuxStart({
      session: 'cps-sys-abc',
      linuxPath: '/work/code/$(whoami)/code-pull/r1/system',
    })
    expect(cmd).toContain('TMUX_STARTED')
    expect(cmd).toContain('repo sync -c')
  })
})

describe('pickMappedRootFromDiscover', () => {
  it('prefers approved runner mapped_root', () => {
    const root = pickMappedRootFromDiscover({
      mapped_roots: [
        { mapped_root: 'Y:\\bad', approved_for_runner: false },
        { mapped_root: 'Z:\\', approved_for_runner: true },
      ],
    })
    expect(root).toBe('Z:\\')
  })
})

describe('detectRepoSyncFailureInLog', () => {
  it('prefers No space left over checkout noise', () => {
    const msg = detectRepoSyncFailureInLog([
      '[system] error: unable to write file logo/a.bmp',
      '[system] fatal: cannot create directory at \'logo/wqhd2000\': No space left on device',
      '[system] error: Cannot checkout platform/frameworks/base',
    ])
    expect(msg).toMatch(/No space left on device/i)
  })

  it('formats UI error with disk hint', () => {
    const text = formatRepoSyncFailure({
      kind: 'system',
      lines: ['fatal: cannot create directory at \'logo/wqhd2000\': No space left on device'],
      fallback: 'tmux 已结束但未找到 done 文件',
    })
    expect(text).toContain('No space left on device')
    expect(text).toContain('磁盘空间不足')
    expect(text).not.toContain('done 文件')
  })

  it('falls back when log has no known signal', () => {
    const text = formatRepoSyncFailure({
      kind: 'vendor',
      lines: ['Updating files: 100%'],
      fallback: 'tmux 已结束但未找到 done 文件',
    })
    expect(text).toBe('vendor tmux 已结束但未找到 done 文件')
  })
})
