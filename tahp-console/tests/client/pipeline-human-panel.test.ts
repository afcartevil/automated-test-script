// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PipelineHumanPanel from '@/components/tahp/pipeline/PipelineHumanPanel.vue'
import type { TimelineNode } from '@/api/tahp/adapt-pipeline'

const mockMessage = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
}))

vi.mock('naive-ui', async (importOriginal) => {
  const actual = await importOriginal<typeof import('naive-ui')>()
  return { ...actual, useMessage: () => mockMessage }
})

vi.mock('@/api/tahp/device-self-check', () => ({
  listDevices: vi.fn().mockResolvedValue([]),
}))

function node(overrides: Partial<TimelineNode> & Pick<TimelineNode, 'key' | 'label'>): TimelineNode {
  return {
    status: 'waiting_human',
    enabled: true,
    ...overrides,
  }
}

function failedAdaptNode(): TimelineNode {
  return node({
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
  })
}

function makeStore() {
  return {
    actionBusy: false,
    resumePoints: {
      points: [{ node: 'prereq', label: '前置信息', safety: 'safe' as const }],
      recommended: 'prereq',
    },
    selectedTimeline: { device_id: null },
    loadResumePoints: vi.fn().mockResolvedValue(undefined),
    submitHumanAction: vi.fn().mockResolvedValue(undefined),
    resumeRun: vi.fn(),
  }
}

describe('PipelineHumanPanel', () => {
  beforeEach(() => {
    mockMessage.success.mockReset()
    mockMessage.error.mockReset()
  })

  it('hides continue/abort buttons when the resume picker is the real continue path', () => {
    const wrapper = mount(PipelineHumanPanel, {
      props: {
        runId: 'run-1',
        store: makeStore() as never,
        nodes: [failedAdaptNode()],
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

  it('shows loading then success when refreshing resume points', async () => {
    let resolveLoad: (() => void) | undefined
    const store = makeStore()
    store.loadResumePoints = vi.fn()
      .mockResolvedValueOnce(undefined)
      .mockImplementationOnce(() => new Promise<void>(resolve => { resolveLoad = resolve }))

    const wrapper = mount(PipelineHumanPanel, {
      props: {
        runId: 'run-1',
        store: store as never,
        nodes: [failedAdaptNode()],
      },
    })
    await flushPromises()

    const reloadBtn = wrapper.get('.resume-picker .head .link-btn')
    await reloadBtn.trigger('click')
    await flushPromises()
    expect(reloadBtn.text()).toBe('刷新中…')
    expect(reloadBtn.attributes('disabled')).toBeDefined()

    resolveLoad?.()
    await flushPromises()
    expect(reloadBtn.text()).toBe('刷新')
    expect(mockMessage.success).toHaveBeenCalledWith('恢复点已刷新')
    expect(store.loadResumePoints).toHaveBeenCalledTimes(2)
  })

  it('shows an error when refreshing resume points fails', async () => {
    const store = makeStore()
    store.loadResumePoints = vi.fn()
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error('网络错误'))

    const wrapper = mount(PipelineHumanPanel, {
      props: {
        runId: 'run-1',
        store: store as never,
        nodes: [failedAdaptNode()],
      },
    })
    await flushPromises()

    await wrapper.get('.resume-picker .head .link-btn').trigger('click')
    await flushPromises()
    expect(mockMessage.error).toHaveBeenCalledWith('网络错误')
    expect(mockMessage.success).not.toHaveBeenCalled()
  })

  function gerritSelectNode(): TimelineNode {
    return node({
      key: 'gerrit',
      label: '提交 Gerrit',
      progress: {
        state: 'awaiting_repo_selection',
        repos: [{
          repo: 'Z:\\project\\KM9_NEW\\kernel',
          repo_label: 'kernel',
          files: [
            'Z:\\project\\KM9_NEW\\kernel\\tp.c',
            'Z:\\project\\KM9_NEW\\kernel\\shared.dtsi',
          ],
          domain_ids: ['tp'],
        }],
      },
      human: {
        reason: 'select_repos',
        message: '请勾选要提交到 Gerrit 的仓库',
        actions: [
          { id: 'submit_all_repos', label: '全部仓库入库' },
          { id: 'submit_selected_repos', label: '提交所选仓库' },
          { id: 'skip', label: '跳过提交', danger: true },
        ],
      },
    })
  }

  it('lists changed files and asks for a second confirm before submitting repos', async () => {
    const store = makeStore()
    const wrapper = mount(PipelineHumanPanel, {
      props: {
        runId: 'run-gerrit',
        store: store as never,
        nodes: [gerritSelectNode()],
      },
      global: {
        stubs: { PipelineResumePicker: true },
      },
    })

    expect(wrapper.text()).toContain('tp.c')
    expect(wrapper.text()).toContain('shared.dtsi')

    const submitBtn = wrapper.findAll('.actions button').find(btn => btn.text() === '提交所选仓库')
    expect(submitBtn).toBeTruthy()
    await submitBtn!.trigger('click')
    await flushPromises()

    expect(store.submitHumanAction).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('确认提交到 Gerrit？')
    expect(wrapper.text()).toContain('1 个仓库 · 2 个文件')

    const confirmBtn = wrapper.findAll('.confirm-box button').find(btn => btn.text() === '确认提交')
    expect(confirmBtn).toBeTruthy()
    await confirmBtn!.trigger('click')
    await flushPromises()

    expect(store.submitHumanAction).toHaveBeenCalledWith(
      'run-gerrit',
      'gerrit',
      'submit_selected_repos',
      { selected_repos: ['Z:\\project\\KM9_NEW\\kernel'] },
    )
  })

  it('asks for a second confirm before skipping gerrit submit', async () => {
    const store = makeStore()
    const wrapper = mount(PipelineHumanPanel, {
      props: {
        runId: 'run-gerrit',
        store: store as never,
        nodes: [gerritSelectNode()],
      },
      global: {
        stubs: { PipelineResumePicker: true },
      },
    })

    const skipBtn = wrapper.findAll('.actions button').find(btn => btn.text() === '跳过提交')
    expect(skipBtn).toBeTruthy()
    await skipBtn!.trigger('click')
    await flushPromises()

    expect(store.submitHumanAction).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('确认跳过 Gerrit 提交？')

    const confirmSkip = wrapper.findAll('.confirm-box button').find(btn => btn.text() === '确认跳过')
    expect(confirmSkip).toBeTruthy()
    await confirmSkip!.trigger('click')
    await flushPromises()

    expect(store.submitHumanAction).toHaveBeenCalledWith('run-gerrit', 'gerrit', 'skip')
  })
})
