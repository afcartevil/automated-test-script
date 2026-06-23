import { describe, expect, it } from 'vitest'
import {
  findDuplicateDistillEntry,
  normalizeEntryContent,
  pickCanonicalDistillEntry,
  resolveDistillJiraKey,
} from '../../packages/server/src/services/tahp/kb-entry-dedup'

describe('kb-entry-dedup', () => {
  const base = {
    content: '## 摘要\n端口防烧',
    status: 'pending_review',
    created_at: '2026-06-01T00:00:00.000Z',
    source_type: 'bug_distill' as const,
  }

  it('matches by jira_key', () => {
    const entries = [
      { id: 'kb-old', jira_key: 'LJ9OS16-74', source_file: 'JIRA LJ9OS16-74', ...base },
      { id: 'kb-new', jira_key: 'ABC-9', ...base, content: 'other' },
    ]
    const hit = findDuplicateDistillEntry(entries, {
      jira_key: 'LJ9OS16-74',
      content: 'updated report',
    })
    expect(hit?.id).toBe('kb-old')
  })

  it('matches by source_task_id', () => {
    const entries = [
      { id: 'kb-task', source_task_id: 'task-1', ...base },
    ]
    const hit = findDuplicateDistillEntry(entries, {
      source_task_id: 'task-1',
      content: 'new content',
    })
    expect(hit?.id).toBe('kb-task')
  })

  it('pickCanonical prefers non-archived and oldest', () => {
    const picked = pickCanonicalDistillEntry([
      { id: 'kb-arch', status: 'archived', created_at: '2026-06-01', content: '', source_type: 'bug_distill' },
      { id: 'kb-old', status: 'pending_review', created_at: '2026-06-01', content: '', source_type: 'bug_distill' },
      { id: 'kb-new', status: 'pending_review', created_at: '2026-06-02', content: '', source_type: 'bug_distill' },
    ])
    expect(picked.id).toBe('kb-old')
  })

  it('resolveDistillJiraKey from content', () => {
    expect(resolveDistillJiraKey({ content: 'JIRA TOS163-37004 详情' })).toBe('TOS163-37004')
  })

  it('normalizeEntryContent collapses whitespace', () => {
    expect(normalizeEntryContent('a\n\n b')).toBe('a b')
  })
})
