import { describe, expect, it } from 'vitest'
import { spawnSync } from 'child_process'
import { tahpPaths, resolvePythonSpawn } from '../../packages/server/src/services/tahp/paths'
import {
  pythonCandidatesForScripts,
  spawnPythonScript,
  spawnOutputText,
} from '../../packages/server/src/services/tahp/python-spawn'
import { runJiraOpsAddComment } from '../../packages/server/src/services/tahp/jira-ops-runner'

describe('python-spawn', () => {
  it('prefers python with jira over py -3.12 when tahpPaths.python is py launcher', () => {
    const candidates = pythonCandidatesForScripts()
    expect(candidates[0]).toMatch(/python/i)
    if (/^py\b/.test(tahpPaths.python)) {
      expect(candidates[0]).not.toBe(tahpPaths.python)
    }
  })

  it('does not spawn ENOENT when using resolved python command', () => {
    const { command, prefixArgs } = resolvePythonSpawn(tahpPaths.python)
    const r = spawnSync(command, [...prefixArgs, '--version'], { encoding: 'utf-8', windowsHide: true })
    expect(r.status).not.toBeNull()
    expect(r.error).toBeUndefined()
  })

  it('runs jira-ops setup-check via script spawn without null exit', () => {
    const root = `${tahpPaths.skillsDir}/jira-ops`
    const r = spawnPythonScript({
      cwd: root,
      args: ['scripts/api_jira.py', 'setup-check'],
      preferJsonOutput: true,
      timeout: 60_000,
    })
    const out = spawnOutputText(r)
    expect(r.status).not.toBeNull()
    expect(out).toMatch(/"ok"/)
  })
})

describe('jira-ops-runner', () => {
  it('returns JSON jira error instead of exit code null for add-comment', () => {
    const result = runJiraOpsAddComment('TEST-99999', 'tahp dry-run comment')
    expect(result.error || '').not.toMatch(/退出码 null/)
    expect(result.error || '').not.toMatch(/启动失败: spawnSync py -3/)
    expect(result.error || '').not.toMatch(/arguments are required:\s*--comment/)
    // 脚本已执行：应为 JIRA 业务错误或成功，而非 spawn 失败
    if (!result.ok) {
      expect(result.error?.length).toBeGreaterThan(5)
    }
  })
})
