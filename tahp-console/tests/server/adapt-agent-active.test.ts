import { describe, expect, it } from 'vitest'
import {
  isActiveStandaloneAdaptTask,
  listActiveAdaptAgentTasks,
  toAdaptAgentTaskSummary,
  type AdaptAgentTaskCtx,
} from '../../packages/server/src/services/tahp/adapt-agent'

function sample(overrides: Partial<AdaptAgentTaskCtx> = {}): AdaptAgentTaskCtx {
  return {
    taskId: 'task-1',
    workspaceId: 'adapt-debug',
    domainId: 'comm-framework',
    domainLabel: '通信框架',
    module: 'telephony',
    relatedSkills: ['comm-framework-agent-test'],
    formData: {},
    startedAt: '2026-09-16T09:00:00.000Z',
    status: 'running',
    skillsUsed: [],
    toolsUsed: [],
    fileChanges: [],
    planNotes: [],
    ...overrides,
  }
}

describe('isActiveStandaloneAdaptTask', () => {
  it('keeps independent adapt-debug runs that are still in progress', () => {
    expect(isActiveStandaloneAdaptTask(sample({ status: 'running' }))).toBe(true)
    expect(isActiveStandaloneAdaptTask(sample({ status: 'waiting_user_input' }))).toBe(true)
    expect(isActiveStandaloneAdaptTask(sample({ status: 'waiting_user' }))).toBe(true)
  })

  it('hides finished tasks and pipeline-owned agent runs', () => {
    expect(isActiveStandaloneAdaptTask(sample({ status: 'completed' }))).toBe(false)
    expect(isActiveStandaloneAdaptTask(sample({ status: 'failed' }))).toBe(false)
    expect(isActiveStandaloneAdaptTask(sample({ skipQualityUpload: true }))).toBe(false)
  })
})

describe('toAdaptAgentTaskSummary', () => {
  it('maps live ctx to a restore payload without transcript', () => {
    const summary = toAdaptAgentTaskSummary(sample({
      phase: 'EXECUTING',
      llmResponse: 'should not leak',
    }))
    expect(summary).toEqual({
      task_id: 'task-1',
      workspace_id: 'adapt-debug',
      domain_id: 'comm-framework',
      domain_label: '通信框架',
      status: 'running',
      phase: 'EXECUTING',
      started_at: '2026-09-16T09:00:00.000Z',
    })
  })
})

describe('listActiveAdaptAgentTasks', () => {
  it('starts empty when no adapt-debug agent is running', () => {
    expect(listActiveAdaptAgentTasks()).toEqual([])
  })
})
