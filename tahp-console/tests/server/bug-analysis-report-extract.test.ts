import { describe, expect, it } from 'vitest'
import {
  BugAnalysisEmptyResultError,
  LLM_RESPONSE_MAX_BYTES,
  MIN_MEANINGFUL_CHARS,
  evaluateRunOutcome,
  extractBugAnalysisReportBody,
  truncateForReport,
} from '../../packages/server/src/services/tahp/bug-analysis-stages'

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

describe('evaluateRunOutcome', () => {
  it('rejects empty response with zero tool calls', () => {
    const out = evaluateRunOutcome('', 0)
    expect(out.ok).toBe(false)
    if (!out.ok) {
      expect(out.failureReason).toBe('empty_response')
      expect(out.message).toContain('0 工具调用')
    }
    expect(new BugAnalysisEmptyResultError('x').failureReason).toBe('empty_response')
  })

  it('rejects short output without report body', () => {
    const short = `=== TAHP_STAGE:fetch_jira ===
status: success
=== END_TAHP_STAGE ===`
    expect(short.trim().length).toBeLessThan(MIN_MEANINGFUL_CHARS)
    expect(extractBugAnalysisReportBody(short)).toBe('')
    const out = evaluateRunOutcome(short, 0)
    expect(out.ok).toBe(false)
    if (!out.ok) expect(out.failureReason).toBe('empty_response')
  })

  it('accepts long narrative even without section 1 heading', () => {
    const long = 'x'.repeat(MIN_MEANINGFUL_CHARS)
    expect(evaluateRunOutcome(long, 0).ok).toBe(true)
  })

  it('accepts a normal report with section 1 heading', () => {
    const full = `### 1. 摘要 / TL;DR
Root cause is a null pointer in the sensor driver.

### 2. 复现路径
Reboot and wait.`
    expect(evaluateRunOutcome(full, 0).ok).toBe(true)
  })

  it('accepts empty output when tools were invoked', () => {
    expect(evaluateRunOutcome('', 1).ok).toBe(true)
  })

  it('accepts short marker-only output when tools were invoked', () => {
    const short = `=== TAHP_STAGE:fetch_jira ===
status: success
=== END_TAHP_STAGE ===`
    expect(evaluateRunOutcome(short, 2).ok).toBe(true)
  })
})

describe('truncateForReport', () => {
  it('returns original text when under the byte cap', () => {
    expect(truncateForReport('hello', 100)).toBe('hello')
  })

  it('truncates by UTF-8 bytes without splitting a multibyte character', () => {
    const text = '测'.repeat(10)
    const cut = truncateForReport(text, 8)
    expect(Buffer.byteLength(cut, 'utf8')).toBeLessThanOrEqual(8 + Buffer.byteLength('\n\n[... 已截断]', 'utf8'))
    expect(cut).toContain('[... 已截断]')
    expect(cut).not.toContain('\uFFFD')
  })

  it('uses LLM_RESPONSE_MAX_BYTES as default cap', () => {
    expect(LLM_RESPONSE_MAX_BYTES).toBe(65536)
    expect(truncateForReport('ok').length).toBe(2)
  })
})
