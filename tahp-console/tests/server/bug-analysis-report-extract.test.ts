import { describe, expect, it } from 'vitest'
import { extractBugAnalysisReportBody } from '../../packages/server/src/services/tahp/bug-analysis-stages'

describe('extractBugAnalysisReportBody', () => {
  it('extracts 8-section report and strips stage markers and tools block', () => {
    const full = `正在拉取 JIRA...

=== TAHP_STAGE:fetch_jira ===
status: success
issue_summary: Test bug
=== END_TAHP_STAGE ===

分析中...

=== TAHP_STAGE:analyze ===
status: success
=== END_TAHP_STAGE ===

### 1. 摘要 / TL;DR
Root cause found.

### 2. 复现路径
Steps here.

=== TOOLS_INVOKED ===
- jira-ops: fetch
=== END ===`

    const body = extractBugAnalysisReportBody(full)
    expect(body).toContain('### 1. 摘要 / TL;DR')
    expect(body).toContain('### 2. 复现路径')
    expect(body).not.toContain('TAHP_STAGE')
    expect(body).not.toContain('TOOLS_INVOKED')
    expect(body).not.toContain('正在拉取 JIRA')
  })

  it('returns stripped text when section 1 heading is missing', () => {
    const full = `=== TAHP_STAGE:fetch_jira ===
status: success
=== END_TAHP_STAGE ===
Only narrative without report headings.`
    expect(extractBugAnalysisReportBody(full)).toBe('Only narrative without report headings.')
  })
})
