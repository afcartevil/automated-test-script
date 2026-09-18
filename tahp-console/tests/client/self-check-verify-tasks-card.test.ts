// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const hoisted = vi.hoisted(() => ({
  fetchMyVerifyTasks: vi.fn(),
  setVerifyAutoRunEnabled: vi.fn(),
  cancelVerifyAutoRunTask: vi.fn(),
}))

vi.mock('@/api/tahp/verify-tasks', async () => {
  const actual = await vi.importActual<typeof import('@/api/tahp/verify-tasks')>('@/api/tahp/verify-tasks')
  return {
    ...actual,
    fetchMyVerifyTasks: (...args: unknown[]) => hoisted.fetchMyVerifyTasks(...args),
    setVerifyAutoRunEnabled: (...args: unknown[]) => hoisted.setVerifyAutoRunEnabled(...args),
    cancelVerifyAutoRunTask: (...args: unknown[]) => hoisted.cancelVerifyAutoRunTask(...args),
  }
})

import SelfCheckOverview from '@/components/tahp/self-check/SelfCheckOverview.vue'

const TASKS = [
  {
    task_id: 'vt_1',
    test_type: 'monkey',
    item_label: 'monkey测试',
    owner: 'owner01',
    project: 'LJ9',
    status: 'pending',
    created_by: 'admin',
    created_at: '2026-09-07T02:30:00.000Z',
  },
  {
    task_id: 'vt_2',
    test_type: 'week',
    item_label: '周版本测试',
    owner: 'owner01',
    project: 'X6885',
    status: 'pending',
    created_by: 'auto-plan',
    created_at: '2026-09-06T09:00:00.000Z',
  },
]

function mountOverview() {
  return mount(SelfCheckOverview, {
    props: {
      devices: [],
      overviewReports: [],
      stats: { runningTests: 0, pendingManual: 0, pendingReports: 0 },
      pipelineStages: [],
    },
  })
}

describe('总览「验测任务」卡片', () => {
  beforeEach(() => {
    hoisted.fetchMyVerifyTasks.mockReset()
    hoisted.setVerifyAutoRunEnabled.mockReset()
    hoisted.cancelVerifyAutoRunTask.mockReset()
  })

  it('展示项目、测试项与指派时间', async () => {
    hoisted.fetchMyVerifyTasks.mockResolvedValue({ tasks: TASKS, degraded: false })
    const wrapper = mountOverview()
    await flushPromises()

    expect(wrapper.text()).toContain('验测任务')
    expect(wrapper.text()).toContain('待完成')
    const rows = wrapper.findAll('.item-row')
    expect(rows.length).toBe(2)
    expect(rows[0].text()).toContain('LJ9')
    expect(rows[0].text()).toContain('monkey测试 · 指派于')
    expect(rows[0].text()).toContain('admin')
    expect(rows[1].text()).toContain('X6885')
    expect(rows[1].text()).toContain('周版本测试 · 指派于')
    expect(rows[1].text()).toContain('auto-plan')
    wrapper.unmount()
  })

  it('无未完成任务时显示空态', async () => {
    hoisted.fetchMyVerifyTasks.mockResolvedValue({ tasks: [], degraded: false })
    const wrapper = mountOverview()
    await flushPromises()

    expect(wrapper.text()).toContain('暂无未完成的验测任务')
    expect(wrapper.findAll('.item-row').length).toBe(0)
    wrapper.unmount()
  })

  it('中心不可达时显示红色提示且不显示空态文案', async () => {
    hoisted.fetchMyVerifyTasks.mockResolvedValue({ tasks: [], degraded: true, reason: 'connect refused' })
    const wrapper = mountOverview()
    await flushPromises()

    const hint = wrapper.find('.verify-unreachable')
    expect(hint.exists()).toBe(true)
    expect(hint.text()).toContain('中心不可达')
    expect(wrapper.text()).not.toContain('暂无未完成的验测任务')
    wrapper.unmount()
  })

  it('请求失败同样按中心不可达提示', async () => {
    hoisted.fetchMyVerifyTasks.mockRejectedValue(new Error('network down'))
    const wrapper = mountOverview()
    await flushPromises()

    expect(wrapper.find('.verify-unreachable').exists()).toBe(true)
    wrapper.unmount()
  })

  it('中心标记完成后，下一轮轮询即从卡片移除', async () => {
    vi.useFakeTimers()
    try {
      hoisted.fetchMyVerifyTasks
        .mockResolvedValueOnce({ tasks: TASKS, degraded: false })
        .mockResolvedValue({ tasks: [TASKS[1]], degraded: false })
      const wrapper = mountOverview()
      await vi.advanceTimersByTimeAsync(0)
      expect(wrapper.findAll('.item-row').length).toBe(2)
      expect(wrapper.text()).toContain('LJ9')

      // 模拟中心侧完成 vt_1：下一轮 15s 轮询只返回 vt_2
      await vi.advanceTimersByTimeAsync(15_000)
      expect(wrapper.findAll('.item-row').length).toBe(1)
      expect(wrapper.text()).not.toContain('LJ9')
      expect(wrapper.text()).toContain('X6885')
      wrapper.unmount()
    } finally {
      vi.useRealTimers()
    }
  })

  it('「进入」通过 SSO 打开中心「任务中心 → 质量验测」', async () => {
    hoisted.fetchMyVerifyTasks.mockResolvedValue({ tasks: TASKS, degraded: false })
    const windowOpen = vi.fn()
    vi.stubGlobal('open', windowOpen)
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/tahp/central/sso-url')) {
        return { json: async () => ({ success: true, data: { url: 'http://central:8660/api/tahp/auth/consume?ticket=t1' } }) } as Response
      }
      return { json: async () => ({ success: true, data: {} }) } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    try {
      const wrapper = mountOverview()
      await flushPromises()
      await wrapper.findAll('.card-enter')[0].trigger('click')
      await flushPromises()
      expect(String(fetchMock.mock.calls[0][0])).toContain(encodeURIComponent('/tasks/mine?lane=self-check'))
      expect(windowOpen).toHaveBeenCalledWith('http://central:8660/api/tahp/auth/consume?ticket=t1', '_blank')
      expect(wrapper.emitted('goDevices')).toBeFalsy()
      wrapper.unmount()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('中心不可达时「进入」回落到本机「测试执行」', async () => {
    hoisted.fetchMyVerifyTasks.mockResolvedValue({ tasks: TASKS, degraded: false })
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('network') }))
    try {
      const wrapper = mountOverview()
      await flushPromises()
      await wrapper.findAll('.card-enter')[0].trigger('click')
      await flushPromises()
      expect(wrapper.emitted('goDevices')).toBeTruthy()
      wrapper.unmount()
    } finally {
      vi.unstubAllGlobals()
    }
  })
})

const AUTO_RUN = {
  eligible: true,
  enabled: true,
  account: 'test-qa01',
  is_test_account: true,
  active_task_id: 'vt_1',
  poll_ms: 30_000,
  max_wait_device_ms: 14_400_000,
}

const AUTO_STATE = {
  label: '等待设备',
  label_code: 'waiting_device' as const,
  phase: 'waiting_device',
  device_id: undefined,
  last_error: '无项目 LJ9 的空闲设备',
  updated_at: '2026-09-17T10:00:00.000Z',
}

describe('总览「验测任务」卡片 · 测试账号自动执行', () => {
  beforeEach(() => {
    hoisted.fetchMyVerifyTasks.mockReset()
    hoisted.setVerifyAutoRunEnabled.mockReset()
    hoisted.cancelVerifyAutoRunTask.mockReset()
  })

  it('渲染本机执行标签与中心已存标签', async () => {
    hoisted.fetchMyVerifyTasks.mockResolvedValue({
      tasks: [
        { ...TASKS[0], auto: AUTO_STATE },
        { ...TASKS[1], label: '验测执行中', label_code: 'running' },
      ],
      degraded: false,
      auto_run: AUTO_RUN,
    })
    const wrapper = mountOverview()
    await flushPromises()

    const labels = wrapper.findAll('.verify-label')
    expect(labels.length).toBe(2)
    expect(labels[0].text()).toBe('等待设备')
    expect(labels[0].classes()).toContain('verify-label--wait')
    expect(labels[0].attributes('title')).toContain('无项目 LJ9 的空闲设备')
    expect(labels[1].text()).toBe('验测执行中')
    expect(labels[1].classes()).toContain('verify-label--run')
    wrapper.unmount()
  })

  it('测试账号显示自动化状态条，可暂停', async () => {
    hoisted.fetchMyVerifyTasks.mockResolvedValue({ tasks: TASKS, degraded: false, auto_run: AUTO_RUN })
    hoisted.setVerifyAutoRunEnabled.mockResolvedValue({ ...AUTO_RUN, enabled: false, eligible: false, reason: 'paused' })
    const wrapper = mountOverview()
    await flushPromises()

    const bar = wrapper.find('.auto-bar')
    expect(bar.exists()).toBe(true)
    expect(bar.text()).toContain('自动执行中（test-qa01）')
    expect(bar.text()).toContain('暂停自动执行')

    await bar.find('button').trigger('click')
    await flushPromises()
    expect(hoisted.setVerifyAutoRunEnabled).toHaveBeenCalledWith(false)
    wrapper.unmount()
  })

  it('非测试账号不显示自动化状态条', async () => {
    hoisted.fetchMyVerifyTasks.mockResolvedValue({
      tasks: TASKS,
      degraded: false,
      auto_run: { ...AUTO_RUN, is_test_account: false, account: 'alice' },
    })
    const wrapper = mountOverview()
    await flushPromises()

    expect(wrapper.find('.auto-bar').exists()).toBe(false)
    wrapper.unmount()
  })

  it('可取消单个任务的自动执行', async () => {
    hoisted.fetchMyVerifyTasks.mockResolvedValue({
      tasks: [{ ...TASKS[0], auto: AUTO_STATE }],
      degraded: false,
      auto_run: AUTO_RUN,
    })
    hoisted.cancelVerifyAutoRunTask.mockResolvedValue(AUTO_RUN)
    const wrapper = mountOverview()
    await flushPromises()

    const cancel = wrapper.find('.verify-cancel')
    expect(cancel.exists()).toBe(true)
    await cancel.trigger('click')
    await flushPromises()
    expect(hoisted.cancelVerifyAutoRunTask).toHaveBeenCalledWith('vt_1')
    wrapper.unmount()
  })
})
