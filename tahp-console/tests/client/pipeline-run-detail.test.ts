// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import PipelineRunDetail from '@/components/tahp/pipeline/PipelineRunDetail.vue'
import type { TimelineNode, TimelineView } from '@/api/tahp/adapt-pipeline'

function node(overrides: Partial<TimelineNode> & Pick<TimelineNode, 'key' | 'label'>): TimelineNode {
  return {
    status: 'pending',
    enabled: true,
    ...overrides,
  }
}

function timeline(overrides: Partial<TimelineView> = {}): TimelineView {
  return {
    run_id: 'run-1',
    project_code: 'KM9',
    status: 'running',
    iteration: 1,
    max_iterations: 3,
    current_node: 'adapt',
    started_at: '2026-09-14T00:00:00.000Z',
    duration_ms: 12_000,
    nodes: [
      node({ key: 'adapt', label: 'AI 适配', status: 'running' }),
      node({ key: 'build', label: '编译' }),
      node({ key: 'triage', label: '故障分析', enabled: false }),
    ],
    iterations: [],
    pending_human_count: 0,
    ...overrides,
  }
}

function makeStore(opts?: {
  logs?: Record<string, string[]>
  errors?: Record<string, string>
}) {
  const logs = opts?.logs ?? {
    adapt: ['adapt started'],
    build: ['build failed'],
  }
  const errors = opts?.errors ?? {}
  return {
    runActionBusy: false,
    actionBusy: false,
    appendCandidates: null,
    loadNodeLogs: vi.fn().mockResolvedValue(undefined),
    loadAllNodeLogs: vi.fn().mockResolvedValue(undefined),
    getNodeLogs: vi.fn((_runId: string, key: string) => logs[key] ?? []),
    getNodeLogError: vi.fn((_runId: string, key: string) => errors[key]),
    loadAppendCandidates: vi.fn(),
    abortRun: vi.fn(),
    failCurrentStage: vi.fn(),
    appendStages: vi.fn(),
    loadResumePoints: vi.fn(),
    resumePoints: null,
  }
}

beforeEach(() => {
  HTMLElement.prototype.scrollIntoView = vi.fn()
})

describe('PipelineRunDetail board layout', () => {
  it('drops the node column and header delete, while the stepper still switches stages', async () => {
    const store = makeStore()
    const wrapper = mount(PipelineRunDetail, {
      props: {
        timeline: timeline(),
        selectedNodeKey: 'adapt',
        store: store as never,
      },
      global: {
        stubs: {
          PipelineNodePanel: true,
          PipelineHumanPanel: true,
          PipelineIterationBar: true,
          PipelineAppendStagesDrawer: true,
        },
      },
    })

    expect(wrapper.text()).not.toContain('节点')
    expect(wrapper.find('.head-actions').text()).not.toContain('删除')
    expect(wrapper.find('.head-actions').text()).toContain('查看全部日志')
    expect(wrapper.find('.head-actions').text()).toContain('终止')
    expect(wrapper.find('.head-actions').text()).not.toContain('人工介入')
    expect(wrapper.find('.human-col-wrap').exists()).toBe(false)

    await wrapper.get('[data-step-key="build"]').trigger('click')
    expect(wrapper.emitted('selectNode')).toEqual([['build']])
  })

  it('renders project and OS as tOS majors regardless of Android prefix', () => {
    const wrapper = mount(PipelineRunDetail, {
      props: {
        timeline: timeline({
          project_code: 'X6879Android17',
          from_os: 'Android 16',
          to_os: 'Android 17',
        }),
        selectedNodeKey: 'adapt',
        store: makeStore() as never,
      },
      global: {
        stubs: {
          PipelineNodePanel: true,
          PipelineHumanPanel: true,
          PipelineIterationBar: true,
          PipelineAppendStagesDrawer: true,
        },
      },
    })

    const title = wrapper.get('.head-title h2').text()
    expect(title).toContain('X6879-tOS17')
    expect(title).toContain('tOS16 → tOS17')
    expect(title).not.toContain('tOSAndroid')
    expect(title).not.toContain('X6879Android17')
  })

  it('aggregates enabled-stage logs in the all-logs drawer and filters by stage', async () => {
    const store = makeStore({
      logs: {
        adapt: ['adapt started'],
        build: ['build failed'],
      },
      errors: {
        build: '编译日志加载失败',
      },
    })
    const wrapper = mount(PipelineRunDetail, {
      props: {
        timeline: timeline(),
        selectedNodeKey: 'adapt',
        store: store as never,
      },
      global: {
        stubs: {
          PipelineNodePanel: true,
          PipelineHumanPanel: true,
          PipelineIterationBar: true,
          PipelineAppendStagesDrawer: true,
        },
      },
    })

    await wrapper.get('.head-actions .btn-soft').trigger('click')
    await flushPromises()

    expect(store.loadAllNodeLogs).toHaveBeenCalledWith('run-1', ['adapt', 'build'])
    const drawer = wrapper.get('[aria-label="全部阶段日志"]')
    expect(drawer.text()).toContain('[AI 适配] adapt started')
    expect(drawer.text()).toContain('[编译] build failed')
    expect(drawer.text()).toContain('编译：编译日志加载失败')

    await drawer.get('.stage-filter select').setValue('adapt')
    expect(drawer.text()).toContain('adapt started')
    expect(drawer.text()).not.toContain('[AI 适配] adapt started')
    expect(drawer.text()).not.toContain('build failed')
    expect(drawer.text()).not.toContain('编译日志加载失败')
  })

  it('shows a wider human column only when work is pending', async () => {
    const store = makeStore()
    const wrapper = mount(PipelineRunDetail, {
      props: {
        timeline: timeline({
          status: 'waiting_human',
          pending_human_count: 1,
          nodes: [
            node({
              key: 'build',
              label: '编译',
              status: 'waiting_human',
              human: {
                reason: 'stage_failed',
                message: '编译失败，请选择恢复点',
                actions: [{ id: 'abort', label: '终止', danger: true }],
              },
            }),
          ],
        }),
        selectedNodeKey: 'build',
        store: store as never,
      },
      global: {
        stubs: {
          PipelineNodePanel: true,
          PipelineIterationBar: true,
          PipelineAppendStagesDrawer: true,
          PipelineResumePicker: true,
        },
      },
    })

    expect(wrapper.find('.cols').classes()).toContain('has-human')
    expect(wrapper.find('.human-col-wrap').exists()).toBe(true)
    expect(wrapper.find('.head-actions').text()).toContain('人工介入 (1)')
    expect(wrapper.text()).toContain('编译失败，请选择恢复点')
    expect(wrapper.text()).not.toContain('当前无需人工介入')

    vi.mocked(HTMLElement.prototype.scrollIntoView).mockClear()
    await wrapper.get('.head-actions .btn-human').trigger('click')
    expect(HTMLElement.prototype.scrollIntoView).toHaveBeenCalled()
    expect(wrapper.emitted('openHuman')).toBeUndefined()
  })

  it('opens the human drawer from the header on narrow screens', async () => {
    const store = makeStore()
    const wrapper = mount(PipelineRunDetail, {
      props: {
        timeline: timeline({ pending_human_count: 2 }),
        selectedNodeKey: 'adapt',
        store: store as never,
        humanDrawer: true,
      },
      global: {
        stubs: {
          PipelineNodePanel: true,
          PipelineHumanPanel: true,
          PipelineIterationBar: true,
          PipelineAppendStagesDrawer: true,
        },
      },
    })

    expect(wrapper.find('.human-col-wrap').exists()).toBe(false)
    await wrapper.get('.head-actions .btn-human').trigger('click')
    expect(wrapper.emitted('openHuman')).toEqual([[]])
  })
})
