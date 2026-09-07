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
    hoisted.fetchMyVerifyTasks.mockResolvedValue(TASKS)
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
    hoisted.fetchMyVerifyTasks.mockResolvedValue([])
    const wrapper = mountOverview()
    await flushPromises()

    expect(wrapper.text()).toContain('暂无未完成的验测任务')
    expect(wrapper.findAll('.item-row').length).toBe(0)
    wrapper.unmount()
  })

  it('中心标记完成后，下一轮轮询即从卡片移除', async () => {
    vi.useFakeTimers()
    try {
      hoisted.fetchMyVerifyTasks
        .mockResolvedValueOnce(TASKS)
        .mockResolvedValue([TASKS[1]])
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
})
