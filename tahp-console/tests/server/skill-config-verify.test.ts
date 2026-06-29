import { describe, expect, it } from 'vitest'
import { verifySkillConfig } from '../../packages/server/src/services/tahp/skill-config'
import { tahpPaths } from '../../packages/server/src/services/tahp/paths'

describe('skill config verify', () => {
  it('runs jira-ops setup-check without spawn ENOENT on Windows py launcher', () => {
    expect(tahpPaths.python).toMatch(/py|python/i)
    const result = verifySkillConfig('jira-ops')
    expect(result.detail).not.toMatch(/脚本退出码 null/)
    expect(result.detail).not.toMatch(/脚本启动失败: spawnSync py -3/)
    if (result.ok) {
      expect(result.detail).toContain('setup-check 通过')
    }
  })
})
