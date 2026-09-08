// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const hoisted = vi.hoisted(() => ({
  fetchMyVerifyTasks: vi.fn(),
}))

vi.mock('@/api/tahp/verify-tasks', () => ({
  fetchMyVerifyTasks: (...args: unknown[]) => hoisted.fetchMyVerifyTasks(...args),
}))

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
