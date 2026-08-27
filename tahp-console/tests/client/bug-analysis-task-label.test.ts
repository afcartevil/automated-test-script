import { describe, expect, it } from 'vitest'
import {
  bugTaskCardPhase,
  bugTaskDefaultDetailTab,
  bugTaskListTitle,
  bugTaskStatusPhase,
} from '../../packages/client/src/utils/bug-analysis-task-label'

describe('bugTaskCardPhase', () => {
  it('maps completed/cancelled to terminal phases even when phase is empty', () => {
    expect(bugTaskCardPhase('completed', undefined)).toBe('COMPLETED')
    expect(bugTaskCardPhase('cancelled', 'QUEUED')).toBe('CANCELLED')
    expect(bugTaskCardPhase('failed', '')).toBe('FAILED')
  })

  it('keeps live phase for running tasks', () => {
    expect(bugTaskCardPhase('running', 'DOWNLOAD_JIRA_LOGS')).toBe('DOWNLOAD_JIRA_LOGS')
    expect(bugTaskStatusPhase('pending')).toBe('QUEUED')
  })
})

describe('bugTaskListTitle', () => {
  it('does not keep 等待获取标题 after the task has finished', () => {
    expect(bugTaskListTitle({ status: 'completed', jira_key: 'TOS163-48949' })).toBe('TOS163-48949')
    expect(bugTaskListTitle({ status: 'cancelled', jira_key: 'LJ90S16-276' })).toBe('LJ90S16-276')
  })

  it('prefers real title and keeps placeholder while still running', () => {
    expect(bugTaskListTitle({ title: 'kernel panic', status: 'completed', jira_key: 'X-1' })).toBe('kernel panic')
    expect(bugTaskListTitle({ status: 'running', jira_key: 'X-1' })).toBe('(等待获取标题)')
  })
})

describe('bugTaskDefaultDetailTab', () => {
  it('opens the report tab for finished analysis', () => {
    expect(bugTaskDefaultDetailTab('completed')).toBe('report')
    expect(bugTaskDefaultDetailTab('failed')).toBe('report')
  })

  it('keeps live progress for running or cancelled tasks', () => {
    expect(bugTaskDefaultDetailTab('running')).toBe('live')
    expect(bugTaskDefaultDetailTab('cancelled')).toBe('live')
    expect(bugTaskDefaultDetailTab('pending')).toBe('live')
  })
})
