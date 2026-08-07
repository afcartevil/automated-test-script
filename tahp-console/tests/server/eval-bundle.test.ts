import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mkdtempSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import {
  EVAL_BUNDLE_FORMAT,
  exportEvalBundle,
  importEvalBundle,
  redactEvalCase,
  validateEvalBundle,
} from '../../packages/server/src/services/tahp/eval/bundle'
import { saveEvalCase, listEvalCases } from '../../packages/server/src/services/tahp/eval/store'
import type { EvalCase } from '../../packages/server/src/services/tahp/eval/types'

const sample: EvalCase = {
  id: 'bundle-demo-001',
  suite: 'bug-analysis',
  title: '端口防烧通知缺失',
  source: {
    type: 'jira',
    jira_key: 'TOS163-37004',
    log_path: 'E:\\jira_workspace\\TOS163-37004\\modem.log',
    problem_description: '联系 user@transsion.com 看 E:\\data\\bug\\a.log，参考 TOS163-37004',
    workspace_id: 'ws-secret',
    origin_task_id: 'task-abc',
  },
  rubric: [{ id: 'root_cause', weight: 1, must: true, criterion: '根因正确' }],
  created_at: '2026-08-07T00:00:00.000Z',
}

describe('redactEvalCase', () => {
  it('redacts jira, paths, emails and omits frozen signals', () => {
    const { case: next, notes } = redactEvalCase({
      ...sample,
      source: {
        ...sample.source,
        frozen_signals: { adapt_completed: true, files_modified_count: 1 } as any,
      },
    })
    expect(next.source.jira_key).toBe('TOS163-[REDACTED]')
    expect(next.source.log_path).toContain('[REDACTED_DIR]')
    expect(next.source.problem_description).toContain('[REDACTED_EMAIL]')
    expect(next.source.problem_description).toContain('[REDACTED_PATH]')
    expect(next.source.problem_description).toContain('TOS163-[REDACTED]')
    expect(next.source.workspace_id).toBe('[REDACTED_WORKSPACE]')
    expect(next.source.frozen_signals).toBeUndefined()
    expect(notes.length).toBeGreaterThan(0)
  })
})

describe('export/import eval bundle', () => {
  let prevEvalDir: string | undefined
  let tempRoot: string

  beforeEach(() => {
    tempRoot = mkdtempSync(join(tmpdir(), 'tahp-eval-bundle-'))
    prevEvalDir = process.env.TAHP_EVAL_DIR
    process.env.TAHP_EVAL_DIR = tempRoot
    saveEvalCase(sample, 'bug-analysis')
  })

  afterEach(() => {
    if (prevEvalDir === undefined) delete process.env.TAHP_EVAL_DIR
    else process.env.TAHP_EVAL_DIR = prevEvalDir
    rmSync(tempRoot, { recursive: true, force: true })
  })

  it('exports a redacted bundle', () => {
    const result = exportEvalBundle('bug-analysis')
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.bundle.format).toBe(EVAL_BUNDLE_FORMAT)
    expect(result.bundle.redacted).toBe(true)
    expect(result.bundle.cases).toHaveLength(1)
    expect(result.bundle.cases[0].source.jira_key).toBe('TOS163-[REDACTED]')
  })

  it('imports skipping existing by default', () => {
    const exported = exportEvalBundle('bug-analysis')
    expect(exported.ok).toBe(true)
    if (!exported.ok) return
    const again = importEvalBundle(exported.bundle, { suite: 'bug-analysis' })
    expect(again.ok).toBe(true)
    expect(again.skipped).toEqual(['bundle-demo-001'])
    expect(again.imported).toEqual([])
  })

  it('imports new ids and validates format', () => {
    const exported = exportEvalBundle('bug-analysis')
    expect(exported.ok).toBe(true)
    if (!exported.ok) return
    exported.bundle.cases[0].id = 'bundle-demo-002'
    const result = importEvalBundle(exported.bundle, { suite: 'bug-analysis' })
    expect(result.imported).toEqual(['bundle-demo-002'])
    expect(listEvalCases('bug-analysis').map(c => c.id).sort()).toEqual([
      'bundle-demo-001',
      'bundle-demo-002',
    ])
  })

  it('rejects wrong format', () => {
    const bad = validateEvalBundle({ format: 'nope', suite: 'bug-analysis', cases: [sample] })
    expect(bad.ok).toBe(false)
  })
})
