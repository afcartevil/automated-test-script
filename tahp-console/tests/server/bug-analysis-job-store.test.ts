import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync, existsSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import {
  bugJobDir,
  failedJobTasks,
  isSafeJobId,
  isTerminalPersistedStatus,
  listPersistedBugJobs,
  readPersistedBugJob,
  saveBugJob,
  unfinishedJobTasks,
  type PersistedBugJob,
} from '../../packages/server/src/services/tahp/bug-analysis-job-store'

function makeJob(overrides: Partial<PersistedBugJob> = {}): PersistedBugJob {
  return {
    job_id: 'task-bugjob-1-aaa',
    type: 'batch',
    jql: 'project = FOO',
    started_at: '2026-08-26T00:00:00.000Z',
    updated_at: '2026-08-26T00:00:00.000Z',
    status: 'running',
    total: 4,
    completed: 1,
    failed: 1,
    tasks: [
      { task_id: 't1', jira_key: 'FOO-1', jira_url: 'http://j/FOO-1', status: 'completed' },
      { task_id: 't2', jira_key: 'FOO-2', jira_url: 'http://j/FOO-2', status: 'failed', error: 'boom' },
      { task_id: 't3', jira_key: 'FOO-3', jira_url: 'http://j/FOO-3', status: 'pending' },
      { task_id: 't4', jira_key: 'FOO-4', jira_url: 'http://j/FOO-4', status: 'waiting_user_input' },
    ],
    ...overrides,
  }
}

describe('bug-analysis-job-store', () => {
  let reportsDir: string

  beforeEach(() => {
    reportsDir = mkdtempSync(join(tmpdir(), 'tahp-bugjob-'))
  })

  afterEach(() => {
    rmSync(reportsDir, { recursive: true, force: true })
  })

  it('rejects unsafe job ids to keep writes inside the jobs dir', () => {
    expect(isSafeJobId('task-bugjob-1-aaa')).toBe(true)
    expect(isSafeJobId('../escape')).toBe(false)
    expect(isSafeJobId('a/b')).toBe(false)
    expect(isSafeJobId('')).toBe(false)
  })

  it('round-trips a persisted job', () => {
    saveBugJob(reportsDir, makeJob())
    const loaded = readPersistedBugJob(reportsDir, 'task-bugjob-1-aaa')
    expect(loaded?.job_id).toBe('task-bugjob-1-aaa')
    expect(loaded?.jql).toBe('project = FOO')
    expect(loaded?.tasks).toHaveLength(4)
    expect(existsSync(join(bugJobDir(reportsDir), 'task-bugjob-1-aaa.json'))).toBe(true)
  })

  it('round-trips auto_post_comment_and_dup', () => {
    saveBugJob(reportsDir, makeJob({ auto_post_comment_and_dup: true }))
    const loaded = readPersistedBugJob(reportsDir, 'task-bugjob-1-aaa')
    expect(loaded?.auto_post_comment_and_dup).toBe(true)
  })

  it('refreshes updated_at on every save', () => {
    saveBugJob(reportsDir, makeJob({ updated_at: '2000-01-01T00:00:00.000Z' }))
    const loaded = readPersistedBugJob(reportsDir, 'task-bugjob-1-aaa')
    expect(loaded?.updated_at).not.toBe('2000-01-01T00:00:00.000Z')
  })

  it('returns null for a missing job instead of throwing', () => {
    expect(readPersistedBugJob(reportsDir, 'task-bugjob-missing')).toBeNull()
  })

  it('never writes outside the jobs dir for a traversal job id', () => {
    saveBugJob(reportsDir, makeJob({ job_id: '../../evil' }))
    expect(existsSync(join(reportsDir, '..', '..', 'evil.json'))).toBe(false)
    expect(listPersistedBugJobs(reportsDir)).toHaveLength(0)
  })

  it('skips corrupt job files when listing', () => {
    saveBugJob(reportsDir, makeJob())
    mkdirSync(bugJobDir(reportsDir), { recursive: true })
    writeFileSync(join(bugJobDir(reportsDir), 'broken.json'), '{ not json', 'utf-8')
    const jobs = listPersistedBugJobs(reportsDir)
    expect(jobs).toHaveLength(1)
    expect(jobs[0].job_id).toBe('task-bugjob-1-aaa')
  })

  it('sorts listed jobs newest first', () => {
    saveBugJob(reportsDir, makeJob({ job_id: 'job-old', started_at: '2026-01-01T00:00:00.000Z' }))
    saveBugJob(reportsDir, makeJob({ job_id: 'job-new', started_at: '2026-08-01T00:00:00.000Z' }))
    expect(listPersistedBugJobs(reportsDir).map(j => j.job_id)).toEqual(['job-new', 'job-old'])
  })

  it('treats only completed/failed/cancelled as terminal', () => {
    expect(isTerminalPersistedStatus('completed')).toBe(true)
    expect(isTerminalPersistedStatus('failed')).toBe(true)
    expect(isTerminalPersistedStatus('cancelled')).toBe(true)
    expect(isTerminalPersistedStatus('pending')).toBe(false)
    expect(isTerminalPersistedStatus('running')).toBe(false)
    expect(isTerminalPersistedStatus('waiting_user_input')).toBe(false)
  })

  it('picks pending and paused tasks as resume candidates', () => {
    const keys = unfinishedJobTasks(makeJob()).map(t => t.jira_key)
    expect(keys).toEqual(['FOO-3', 'FOO-4'])
  })

  it('picks only failed tasks for retry', () => {
    const keys = failedJobTasks(makeJob()).map(t => t.jira_key)
    expect(keys).toEqual(['FOO-2'])
  })

  it('returns no candidates for a fully completed job', () => {
    const job = makeJob({
      status: 'completed',
      tasks: [
        { task_id: 't1', jira_key: 'FOO-1', jira_url: '', status: 'completed' },
        { task_id: 't2', jira_key: 'FOO-2', jira_url: '', status: 'completed' },
      ],
    })
    expect(unfinishedJobTasks(job)).toHaveLength(0)
    expect(failedJobTasks(job)).toHaveLength(0)
  })
})
