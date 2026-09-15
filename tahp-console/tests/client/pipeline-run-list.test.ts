// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PipelineRunList from '@/components/tahp/pipeline/PipelineRunList.vue'
import { mergePipelineRunItems, useAdaptPipelineStore } from '@/stores/tahp/adapt-pipeline'
import type { RunSummary, TimelineView } from '@/api/tahp/adapt-pipeline'

function run(overrides: Partial<RunSummary> = {}): RunSummary {
  return {
    run_id: 'run-1',
    project_code: 'KM9',
    status: 'failed',
    iteration: 1,
    current_node: 'build',
    created_at: '2026-08-25T00:00:00.000Z',
    updated_at: '2026-08-25T00:00:00.000Z',
    ...overrides,
  }
}

describe('mergePipelineRunItems', () => {
  it('keeps the current session order and prepends newly created runs', () => {
    const current = [
      run({ run_id: 'old', project_code: 'OLD', updated_at: '2026-01-01T00:00:00.000Z' }),
      run({ run_id: 'mid', project_code: 'MID', updated_at: '2026-06-01T00:00:00.000Z' }),
    ]
    const incoming = [
      run({ run_id: 'new', project_code: 'NEW', updated_at: '2026-09-01T00:00:00.000Z' }),
      run({ run_id: 'mid', project_code: 'MID2', status: 'passed', updated_at: '2026-09-02T00:00:00.000Z' }),
      run({ run_id: 'old', project_code: 'OLD2', updated_at: '2026-09-03T00:00:00.000Z' }),
    ]

    const merged = mergePipelineRunItems(current, incoming)
    expect(merged.map(item => item.run_id)).toEqual(['new', 'old', 'mid'])
    expect(merged[1].project_code).toBe('OLD2')
    expect(merged[2].status).toBe('passed')
  })
})

describe('PipelineRunList clone action', () => {
  it('emits clone for any status without selecting the run', async () => {
    const wrapper = mount(PipelineRunList, {
      props: {
        items: [
          run({ run_id: 'a', status: 'running', project_code: 'KM9' }),
          run({ run_id: 'b', status: 'draft', project_code: 'LJ9' }),
        ],
        selectedId: null,
      },
    })

    const cloneButtons = wrapper.findAll('.btn-clone')
    expect(cloneButtons).toHaveLength(2)
    await cloneButtons[0].trigger('click')
    expect(wrapper.emitted('clone')).toEqual([['a']])
    expect(wrapper.emitted('select')).toBeUndefined()
  })
})

describe('PipelineRunList board layout', () => {
  it('renders items in the given order instead of sorting by updated_at', async () => {
    const wrapper = mount(PipelineRunList, {
      props: {
        items: [
          run({ run_id: 'old', project_code: 'OLD', updated_at: '2026-01-01T00:00:00.000Z' }),
          run({ run_id: 'new', project_code: 'NEW', updated_at: '2026-09-01T00:00:00.000Z' }),
        ],
        selectedId: 'old',
      },
    })

    expect(wrapper.findAll('.run-item strong').map(node => node.text())).toEqual(['OLD', 'NEW'])
    await wrapper.findAll('.run-item')[1].trigger('click')
    expect(wrapper.emitted('select')).toEqual([['new']])
    expect(wrapper.findAll('.run-item strong').map(node => node.text())).toEqual(['OLD', 'NEW'])
  })

  it('formats Android-suffixed project codes as code-tOSN', () => {
    const wrapper = mount(PipelineRunList, {
      props: {
        items: [run({ run_id: 'a', project_code: 'X6879Android17' })],
        selectedId: 'a',
      },
    })
    expect(wrapper.get('.run-item strong').text()).toBe('X6879-tOS17')
  })

  it('emits discard once from the card action', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = mount(PipelineRunList, {
      props: {
        items: [run({ run_id: 'run-1', status: 'failed' })],
        selectedId: 'run-1',
      },
    })

    await wrapper.find('.btn-discard').trigger('click')
    expect(wrapper.emitted('discard')).toEqual([['run-1']])
    expect(wrapper.emitted('select')).toBeUndefined()
    confirm.mockRestore()
  })

  it('shows status dots and a selected hint when collapsed', async () => {
    const wrapper = mount(PipelineRunList, {
      props: {
        items: [
          run({ run_id: 'a', status: 'running', project_code: 'KM9' }),
          run({ run_id: 'b', status: 'failed', project_code: 'LJ9' }),
        ],
        selectedId: 'b',
        collapsed: true,
      },
    })

    expect(wrapper.find('.collapse-btn').exists()).toBe(true)
    expect(wrapper.findAll('.run-item.rail')).toHaveLength(2)
    expect(wrapper.find('.btn-discard').exists()).toBe(false)
    expect(wrapper.find('.selected-hint').text()).toBe('LJ9')
    expect(wrapper.find('.run-item.selected').attributes('title')).toContain('LJ9')

    await wrapper.find('.collapse-btn').trigger('click')
    expect(wrapper.emitted('toggle')).toHaveLength(1)
  })
})

function timelineView(overrides: Partial<TimelineView> = {}): TimelineView {
  return {
    run_id: 'run-1',
    project_code: 'KM9',
    status: 'waiting_human',
    iteration: 1,
    max_iterations: 3,
    current_node: 'build',
    started_at: '2026-09-14T00:00:00.000Z',
    duration_ms: 1,
    nodes: [],
    iterations: [],
    pending_human_count: 0,
    ...overrides,
  }
}

describe('pending human badge ignores finished runs', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('does not count aborted or failed timelines in the page-head badge', () => {
    const store = useAdaptPipelineStore()
    store.timelines = {
      aborted: timelineView({
        run_id: 'aborted',
        status: 'aborted',
        pending_human_count: 2,
      }),
      failed: timelineView({
        run_id: 'failed',
        status: 'failed',
        pending_human_count: 3,
      }),
      waiting: timelineView({
        run_id: 'waiting',
        status: 'waiting_human',
        pending_human_count: 1,
      }),
    }
    store.runItems = [
      run({ run_id: 'aborted', status: 'aborted' }),
      run({ run_id: 'failed', status: 'failed' }),
      run({ run_id: 'waiting', status: 'waiting_human' }),
    ]

    expect(store.pendingHumanTotal).toBe(1)
    expect(store.pendingHumanRunIds).toEqual(['waiting'])
  })
})
