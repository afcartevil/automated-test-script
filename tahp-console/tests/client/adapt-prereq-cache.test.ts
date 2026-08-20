// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'

const tahpGet = vi.fn()

vi.mock('../../packages/client/src/api/tahp/client', () => ({
  tahpGet: (...args: unknown[]) => tahpGet(...args),
  tahpPost: vi.fn(),
  tahpPut: vi.fn(),
  tahpDelete: vi.fn(),
}))

vi.mock('@/router', () => ({
  default: {
    currentRoute: { value: { name: 'hermes.chat' } },
    replace: vi.fn(),
  },
}))

import {
  clearAdaptPrereqCache,
  fetchPrereqProjects,
  peekPrereqProjects,
  resolvePrereqsFromCenter,
} from '../../packages/client/src/api/tahp/adapt'
import { fetchPipelinePrereqs } from '../../packages/client/src/api/tahp/adapt-pipeline'

const SAMPLE_PROJECTS = [
  { code: 'KM9', name: 'KM9', updated_at: '2026-08-13T00:00:00Z' },
]

const SAMPLE_RESOLVE = {
  project_code: 'KM9',
  campaign_id: 'C1',
  from_os: '16.0',
  to_os: '17.0',
  domains: [
    {
      workspace_id: 'adapt-debug',
      domain_id: 'tp',
      revision: 1,
      schema: [],
      form_data: { project: 'KM9' },
      stale_fields: [],
      incomplete_required: [],
    },
    {
      workspace_id: 'feature-adapt',
      domain_id: 'audio',
      revision: 1,
      schema: [],
      form_data: {},
      stale_fields: [],
      incomplete_required: [],
    },
  ],
}

describe('adapt prereq session cache', () => {
  beforeEach(() => {
    clearAdaptPrereqCache()
    tahpGet.mockReset()
  })

  it('force refresh bypasses project list cache', async () => {
    tahpGet.mockResolvedValueOnce(SAMPLE_PROJECTS)
    await fetchPrereqProjects()
    tahpGet.mockResolvedValueOnce([
      { code: 'KM9', name: 'KM9-new', updated_at: '2026-08-13T01:00:00Z' },
    ])
    const refreshed = await fetchPrereqProjects({ force: true })
    expect(refreshed[0].name).toBe('KM9-new')
    expect(tahpGet).toHaveBeenCalledTimes(2)
  })

  it('shares project list between first and second caller without a second request', async () => {
    tahpGet.mockResolvedValue(SAMPLE_PROJECTS)

    const first = await fetchPrereqProjects()
    const second = await fetchPrereqProjects()

    expect(first).toEqual(SAMPLE_PROJECTS)
    expect(second).toEqual(SAMPLE_PROJECTS)
    expect(peekPrereqProjects()).toEqual(SAMPLE_PROJECTS)
    expect(tahpGet).toHaveBeenCalledTimes(1)
    expect(tahpGet).toHaveBeenCalledWith('/api/tahp/adapt/prereqs/projects')
  })

  it('dedupes in-flight project list fetches', async () => {
    let resolveList: (value: typeof SAMPLE_PROJECTS) => void = () => {}
    tahpGet.mockReturnValue(new Promise(resolve => { resolveList = resolve }))

    const a = fetchPrereqProjects()
    const b = fetchPrereqProjects()
    resolveList(SAMPLE_PROJECTS)

    expect(await a).toEqual(SAMPLE_PROJECTS)
    expect(await b).toEqual(SAMPLE_PROJECTS)
    expect(tahpGet).toHaveBeenCalledTimes(1)
  })

  it('pipeline resolve reuses a prior full resolve from the debug path', async () => {
    tahpGet.mockResolvedValue(SAMPLE_RESOLVE)

    await resolvePrereqsFromCenter({ project_code: 'KM9' })
    const pipeline = await fetchPipelinePrereqs('KM9', 'C1')

    expect(pipeline.project_code).toBe('KM9')
    expect(pipeline.campaign_id).toBe('C1')
    expect(pipeline.domains).toHaveLength(2)
    expect(tahpGet).toHaveBeenCalledTimes(1)
  })

  it('does not reuse another prerequisite set for the same project code', async () => {
    tahpGet.mockResolvedValueOnce(SAMPLE_RESOLVE)
    await resolvePrereqsFromCenter({ project_code: 'KM9' })

    const otherSet = {
      ...SAMPLE_RESOLVE,
      campaign_id: 'C2',
      from_os: '17.0',
      to_os: '18.0',
    }
    tahpGet.mockResolvedValueOnce(otherSet)
    const next = await fetchPipelinePrereqs('KM9', 'C2')

    expect(next.campaign_id).toBe('C2')
    expect(next.from_os).toBe('17.0')
    expect(tahpGet).toHaveBeenCalledTimes(2)
  })

  it('debug workspace resolve can filter from a cached full resolve', async () => {
    tahpGet.mockResolvedValue(SAMPLE_RESOLVE)
    await resolvePrereqsFromCenter({ project_code: 'KM9' })

    const scoped = await resolvePrereqsFromCenter({
      project_code: 'KM9',
      workspace_id: 'adapt-debug',
    })

    expect(scoped.domains).toHaveLength(1)
    expect(scoped.domains[0].domain_id).toBe('tp')
    expect(tahpGet).toHaveBeenCalledTimes(1)
  })
})
