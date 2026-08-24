import { afterEach, describe, expect, it } from 'vitest'
import {
  TASK_CONTEXT_TTL_MS,
  clearTaskContext,
  getTaskContext,
  preferTaskContextProject,
  setTaskContext,
} from '../../packages/server/src/services/tahp/task-context'

describe('task-context', () => {
  afterEach(() => {
    clearTaskContext()
  })

  it('pipeline keeps campaign', () => {
    const saved = setTaskContext({
      package_id: 'p1',
      project_code: 'LJ9',
      campaign_id: 'v1',
      domain_id: 'TP',
      kind: 'adapt-pipeline',
    })
    expect(saved.domain_id).toBe('tp')
    expect(getTaskContext()?.campaign_id).toBe('v1')
    expect(preferTaskContextProject()?.campaign_id).toBe('v1')
  })

  it('self-check drops campaign even if provided', () => {
    setTaskContext({
      package_id: 'p1',
      project_code: 'LJ9',
      campaign_id: 'v1',
      domain_id: 'tp',
      kind: 'self-check',
      node_rule_id: 'rule_1',
    })
    expect(getTaskContext()?.campaign_id).toBe('')
    expect(getTaskContext()?.node_rule_id).toBe('rule_1')
    expect(preferTaskContextProject()?.campaign_id).toBeUndefined()
    expect(preferTaskContextProject()?.project_code).toBe('LJ9')
  })

  it('D3 prefers context when candidate empty or same project', () => {
    setTaskContext({ project_code: 'LJ9', campaign_id: 'v1', domain_id: 'tp', kind: 'adapt-pipeline', package_id: 'p1' })
    expect(preferTaskContextProject()?.project_code).toBe('LJ9')
    expect(preferTaskContextProject('LJ9')?.campaign_id).toBe('v1')
  })

  it('D4 different candidate does not override user pick', () => {
    setTaskContext({ project_code: 'LJ9', campaign_id: 'v1', domain_id: 'tp', kind: 'adapt-pipeline', package_id: 'p1' })
    expect(preferTaskContextProject('CM8')).toBeNull()
  })

  it('D4 no context is a no-op', () => {
    expect(getTaskContext()).toBeNull()
    expect(preferTaskContextProject('LJ9')).toBeNull()
  })

  it('expires after TTL', () => {
    setTaskContext({ project_code: 'LJ9', campaign_id: 'v1', domain_id: 'tp', kind: 'adapt-pipeline', package_id: 'p1' })
    const later = Date.now() + TASK_CONTEXT_TTL_MS + 1
    expect(getTaskContext(later)).toBeNull()
    expect(preferTaskContextProject(undefined, later)).toBeNull()
  })
})
