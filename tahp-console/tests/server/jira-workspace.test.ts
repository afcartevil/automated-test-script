import { describe, expect, it } from 'vitest'
import { shouldRewriteWorkspaceRoot } from '../../packages/server/src/services/tahp/jira-workspace'

describe('jira-workspace', () => {
  const canonical = 'E:/TAHP/easyadapter/jira_workspace'

  it('rewrites empty and legacy paths', () => {
    expect(shouldRewriteWorkspaceRoot('', canonical)).toBe(true)
    expect(shouldRewriteWorkspaceRoot('E:/jira_workspace', canonical)).toBe(true)
    expect(shouldRewriteWorkspaceRoot('D:/Code/tahp/.tahp/jira_workspace', canonical)).toBe(true)
    expect(
      shouldRewriteWorkspaceRoot('C:/Users/me/AppData/Local/hermes/skills/jira-ops/jira_workspace', canonical),
    ).toBe(true)
  })

  it('keeps canonical project workspace', () => {
    expect(shouldRewriteWorkspaceRoot(canonical, canonical)).toBe(false)
    expect(shouldRewriteWorkspaceRoot(`${canonical}/TOS163-41628`, canonical)).toBe(false)
  })
})
