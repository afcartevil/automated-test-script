// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const hoisted = vi.hoisted(() => ({
  routerPush: vi.fn(),
  fetchMock: vi.fn(),
  mockAppStore: {
    connected: true,
    serverVersion: 'test',
    latestVersion: '',
    updateAvailable: false,
    updating: false,
    selectedModel: 'claude-sonnet',
    selectedProvider: 'anthropic',
    profileModelGroups: [{
      profile: 'default',
      groups: [{
        provider: 'anthropic',
        label: 'Anthropic',
        models: ['claude-sonnet'],
        model_meta: {},
      }],
    }],
    displayModelName: (m: string) => m,
    switchModel: vi.fn(),
    loadModels: vi.fn(),
    doUpdate: vi.fn(),
  },
}))

vi.mock('@/stores/hermes/app', () => ({
  useAppStore: () => hoisted.mockAppStore,
}))

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<any>()
  return {
    ...actual,
    useRoute: () => ({ name: 'tahp.dashboard', path: '/tahp/dashboard', meta: {}, query: {} }),
    useRouter: () => ({ push: hoisted.routerPush, replace: vi.fn() }),
  }
})

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

vi.mock('@/composables/useTheme', () => ({
  useTheme: () => ({ isDark: false }),
}))

vi.mock('@/components/layout/ModelSelector.vue', () => ({
  default: { template: '<div class="model-selector-stub" />' },
}))

vi.mock('naive-ui', async () => {
  const actual = await vi.importActual<any>('naive-ui')
  return {
    ...actual,
    useMessage: () => ({ success: vi.fn(), error: vi.fn() }),
    NDropdown: { template: '<div class="dropdown-stub"><slot /></div>' },
  }
})

import EaShell from '@/components/layout/EaShell.vue'

const INBOX = {
  packages: [
    { package_id: 'vt_1', notice_type: 'verify-task', title: '验测任务指派：周版本测试', unread: true },
    { package_id: 'ntf_1', notice_type: 'modem-patch', title: 'Modem 基线通知', unread: true },
  ],
  unread: 1,
}

function stubFetch() {
  hoisted.fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/tahp/task-inbox/ack')) {
      return { json: async () => ({ success: true }) } as Response
    }
    if (url.includes('/api/tahp/task-inbox')) {
      return { json: async () => ({ success: true, data: INBOX }) } as Response
    }
    return { json: async () => ({ success: true, data: {} }) } as Response
  })
  vi.stubGlobal('fetch', hoisted.fetchMock)
}

describe('EaShell 验测任务通知', () => {
  beforeEach(() => {
    hoisted.routerPush.mockClear()
    hoisted.fetchMock.mockReset()
    stubFetch()
  })

  it('verify-task 通知计入红点，patch 通知不计', async () => {
    const wrapper = mount(EaShell, { slots: { default: '<div />' } })
    await flushPromises()
    const dot = wrapper.find('.ck-task-dot')
    expect(dot.exists()).toBe(true)
    expect(dot.text()).toBe('1')
  })

  it('弹层展示验测任务分区与「打开验测」，点击后 ack 并跳转测试执行', async () => {
    const wrapper = mount(EaShell, { slots: { default: '<div />' } })
    await flushPromises()

    await wrapper.find('button[title="我的任务"]').trigger('click')
    const text = wrapper.text()
    expect(text).toContain('验测任务')
    expect(text).toContain('验测任务指派：周版本测试')
    expect(text).toContain('PATCH 通知')

    const openBtn = wrapper.findAll('button').find(b => b.text() === '打开验测')
    expect(openBtn).toBeTruthy()
    await openBtn!.trigger('click')
    await flushPromises()

    expect(hoisted.fetchMock.mock.calls.some(c => String(c[0]).includes('/api/tahp/task-inbox/ack'))).toBe(true)
    expect(hoisted.routerPush).toHaveBeenCalledWith({ name: 'tahp.self-check', query: { tab: 'devices' } })
    // 点击后本地收件箱立即移除该通知，红点归零
    expect(wrapper.find('.ck-task-dot').exists()).toBe(false)
  })
})
