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
})
