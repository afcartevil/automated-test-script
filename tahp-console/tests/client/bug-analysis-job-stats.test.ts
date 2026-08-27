import { describe, expect, it } from 'vitest'
import {
  bugJobSettledCount,
  countBugJobQueue,
  overlayBugJobCounts,
} from '../../packages/client/src/utils/bug-analysis-job-stats'

describe('countBugJobQueue', () => {
  it('counts cancelled separately from failed (interrupted batch)', () => {
    const ids = Array.from({ length: 15 }, (_, i) => `t${i}`)
    const counts = countBugJobQueue(ids, () => 'cancelled')
    expect(counts).toEqual({
      all: 15,
      pending: 0,
      running: 0,
      completed: 0,
      failed: 0,
      cancelled: 15,
    })
    expect(bugJobSettledCount(counts)).toBe(15)
  })

  it('does not lump cancelled into failed', () => {
    const counts = countBugJobQueue(
      ['ok', 'fail', 'cancel', 'wait', 'run', 'queued'],
      (id) => ({
        ok: 'completed',
        fail: 'failed',
        cancel: 'cancelled',
        wait: 'waiting_user_input',
        run: 'running',
        queued: 'pending',
      }[id]),
    )
    expect(counts.completed).toBe(1)
    expect(counts.failed).toBe(1)
    expect(counts.cancelled).toBe(1)
    expect(counts.running).toBe(2)
    expect(counts.pending).toBe(1)
    expect(bugJobSettledCount(counts)).toBe(3)
  })

  it('treats missing task status as pending', () => {
    const counts = countBugJobQueue(['a', 'b'], () => undefined)
    expect(counts.pending).toBe(2)
    expect(counts.all).toBe(2)
  })
})

describe('overlayBugJobCounts', () => {
  it('rewrites stale job.completed while the batch is still running', () => {
    const job = {
      job_id: 'job-1',
      task_ids: ['t1', 't2', 't3'],
      completed: 0,
      failed: 0,
    }
    const statuses: Record<string, string> = {
      t1: 'completed',
      t2: 'completed',
      t3: 'running',
    }
    const next = overlayBugJobCounts(job, id => statuses[id])
    expect(next.completed).toBe(2)
    expect(next.failed).toBe(0)
  })

  it('keeps API counters when no child statuses are loaded yet', () => {
    const job = {
      job_id: 'job-1',
      task_ids: ['t1', 't2'],
      completed: 7,
      failed: 1,
    }
    expect(overlayBugJobCounts(job, () => undefined)).toEqual(job)
  })
})
