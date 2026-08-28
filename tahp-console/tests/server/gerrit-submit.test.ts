import { describe, expect, it } from 'vitest'
import {
  buildConflictChanges,
  detectDomainFileConflicts,
  parseGerritSubmitResult,
} from '../../packages/server/src/services/tahp/gerrit-submit'
import type { PipelineDomain } from '../../packages/server/src/services/tahp/adapt-pipeline/types'

function domain(id: string, files: string[]): Pick<PipelineDomain, 'domain_id' | 'changed_files'> {
  return { domain_id: id, changed_files: files }
}

describe('detectDomainFileConflicts', () => {
  it('returns empty when domains touch different files', () => {
    const conflicts = detectDomainFileConflicts([
      domain('telephony', ['vendor/foo.c']),
      domain('kernel', ['kernel/bar.c']),
    ])
    expect(conflicts).toEqual([])
  })

  it('detects shared file across domains', () => {
    const conflicts = detectDomainFileConflicts([
      domain('telephony', ['vendor/shared.c', 'vendor/a.c']),
      domain('kernel', ['vendor/shared.c']),
    ])
    expect(conflicts).toHaveLength(1)
    expect(conflicts[0].file).toBe('vendor/shared.c')
    expect(conflicts[0].domain_ids.sort()).toEqual(['kernel', 'telephony'])
  })

  it('normalizes Windows path separators', () => {
    const conflicts = detectDomainFileConflicts([
      domain('a', ['vendor\\foo.c']),
      domain('b', ['vendor/foo.c']),
    ])
    expect(conflicts).toHaveLength(1)
  })
})

describe('buildConflictChanges', () => {
  it('marks conflicting domains as blocked_conflict', () => {
    const domains: PipelineDomain[] = [
      {
        workspace_id: 'ws-a',
        domain_id: 'a',
        domain_label: 'A',
        module: 'm',
        related_skills: [],
        form_data: {},
        incomplete_required: [],
        enabled: true,
        status: 'done',
        changed_files: ['shared.c'],
      },
      {
        workspace_id: 'ws-b',
        domain_id: 'b',
        domain_label: 'B',
        module: 'm',
        related_skills: [],
        form_data: {},
        incomplete_required: [],
        enabled: true,
        status: 'done',
        changed_files: ['shared.c', 'b-only.c'],
      },
    ]
    const conflicts = detectDomainFileConflicts(domains)
    const changes = buildConflictChanges(domains, conflicts)
    expect(changes).toHaveLength(2)
    expect(changes.every(c => c.status === 'blocked_conflict')).toBe(true)
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
})
