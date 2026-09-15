// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import PipelineHumanPanel from '@/components/tahp/pipeline/PipelineHumanPanel.vue'
import type { TimelineNode } from '@/api/tahp/adapt-pipeline'

function node(overrides: Partial<TimelineNode> & Pick<TimelineNode, 'key' | 'label'>): TimelineNode {
  return {
    status: 'waiting_human',
    enabled: true,
    ...overrides,
  }
}

function makeStore() {
  return {
    actionBusy: false,
    resumePoints: null,
    selectedTimeline: { device_id: null },
    loadResumePoints: vi.fn().mockResolvedValue(undefined),
    submitHumanAction: vi.fn().mockResolvedValue(undefined),
    resumeRun: vi.fn(),
  }
}

describe('PipelineHumanPanel', () => {
  it('hides continue/abort buttons when the resume picker is the real continue path', () => {
    const wrapper = mount(PipelineHumanPanel, {
      props: {
        runId: 'run-1',
        store: makeStore() as never,
        nodes: [
          node({
            key: 'adapt',
            label: 'AI 适配',
            human: {
              reason: 'stage_failed',
              message: '阶段失败：用户停止本步。请在下方选择恢复点继续。',
              actions: [
                { id: 'confirm_done', label: '继续' },
                { id: 'abort', label: '终止流水线', danger: true },
              ],
            },
          }),
        ],
      },
      global: {
        stubs: { PipelineResumePicker: true },
      },
    })

    expect(wrapper.find('.actions').exists()).toBe(false)
    expect(wrapper.text()).toContain('请在下方选择恢复点继续')
    expect(wrapper.text()).not.toContain('终止流水线')
    expect(wrapper.find('pipeline-resume-picker-stub').exists()).toBe(true)
  })

  it('rewrites legacy resume/abort copy on historical waiting-human nodes', () => {
    const wrapper = mount(PipelineHumanPanel, {
      props: {
        runId: 'run-old',
        store: makeStore() as never,
        nodes: [
          node({
            key: 'adapt',
            label: 'AI 适配',
            human: {
              reason: 'stage_failed',
              message: '阶段失败：用户停止本步。请选择恢复点继续，或终止流水线。',
              actions: [
                { id: 'confirm_done', label: '继续' },
                { id: 'abort', label: '终止流水线', danger: true },
              ],
            },
          }),
        ],
      },
      global: {
        stubs: { PipelineResumePicker: true },
      },
    })

    expect(wrapper.text()).toContain('请在下方选择恢复点继续')
    expect(wrapper.text()).not.toContain('或终止流水线')
    expect(wrapper.find('.actions').exists()).toBe(false)
  })

  it('keeps real human actions such as skip / confirm filled', async () => {
    const store = makeStore()
    const wrapper = mount(PipelineHumanPanel, {
      props: {
        runId: 'run-1',
        store: store as never,
        nodes: [
          node({
            key: 'prereq',
            label: '前置信息',
            human: {
              reason: 'incomplete_required',
              message: '仍有必填项未填写',
              actions: [
                { id: 'confirm_done', label: '已补填，继续' },
                { id: 'skip', label: '跳过' },
              ],
            },
          }),
        ],
      },
      global: {
        stubs: { PipelineResumePicker: true },
      },
    })

    const labels = wrapper.findAll('.actions button').map(btn => btn.text())
    expect(labels).toEqual(['已补填，继续', '跳过'])
    await wrapper.findAll('.actions button')[0].trigger('click')
    expect(store.submitHumanAction).toHaveBeenCalledWith('run-1', 'prereq', 'confirm_done')
  })
})
