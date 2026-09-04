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

const APPLY_PROMPT = {
  run: {
    run_id: 'run-km9-1',
    project_code: 'KM9',
    status: 'pass',
    dimension: 'self-check',
    domain_id: 'charging',
  },
  packages: [
    {
      package_id: 'pkg-ch',
      title: 'KM9 · 充电',
      domain_label: '充电',
      pending_items: [
        { line_id: 'l-p1', item_id: 'adapt-p1-charging-0001', title: '充电 IC 识别' },
        { line_id: 'l-sw', item_id: 'adapt-software-charging-0001', title: '电量曲线' },
      ],
    },
    {
      package_id: 'pkg-tp',
      title: 'KM9 · TP触摸屏',
      domain_label: 'TP触摸屏',
      pending_items: [
        { line_id: 'l-tp', item_id: 'adapt-p1-tp-0001', title: 'TP IC 识别' },
      ],
    },
  ],
  domain_unspecified: false,
  campaign_unspecified: false,
}

function stubFetchWithApply(prompt = APPLY_PROMPT) {
  hoisted.fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/tahp/task-inbox/ack')) {
      return { json: async () => ({ success: true }) } as Response
    }
    if (url.includes('/api/tahp/task-inbox')) {
      return { json: async () => ({ success: true, data: { ...INBOX, apply_prompt: prompt } }) } as Response
    }
    return { json: async () => ({ success: true, data: {} }) } as Response
  })
  vi.stubGlobal('fetch', hoisted.fetchMock)
}

describe('EaShell 我的任务下拉', () => {
  beforeEach(() => {
    hoisted.routerPush.mockClear()
    hoisted.fetchMock.mockReset()
    stubFetch()
  })

  it('任务列表在下拉内部滚动，底栏保持可见', async () => {
    const wrapper = mount(EaShell, { slots: { default: '<div />' } })
    await flushPromises()
    await wrapper.find('button[title="我的任务"]').trigger('click')
    expect(wrapper.find('.ck-task-list').exists()).toBe(true)
    expect(wrapper.find('.ck-task-foot').exists()).toBe(true)
    expect(wrapper.text()).toContain('验测')
    expect(wrapper.text()).toContain('Patch')
  })

  it('按类型 Chip 只显示对应任务', async () => {
    const wrapper = mount(EaShell, { slots: { default: '<div />' } })
    await flushPromises()
    await wrapper.find('button[title="我的任务"]').trigger('click')
    const chips = wrapper.findAll('.ck-task-chip')
    const verifyChip = chips.find(b => b.text().includes('验测'))
    expect(verifyChip).toBeTruthy()
    await verifyChip!.trigger('click')
    expect(wrapper.text()).toContain('验测任务指派：周版本测试')
    expect(wrapper.text()).not.toContain('PATCH 通知')
  })
})

describe('EaShell 用本报告勾选', () => {
  beforeEach(() => {
    hoisted.routerPush.mockClear()
    hoisted.fetchMock.mockReset()
    stubFetchWithApply()
  })

  it('弹层限高并按 P1/软件分组，预选报告匹配域', async () => {
    const wrapper = mount(EaShell, { slots: { default: '<div />' } })
    await flushPromises()
    expect(wrapper.find('.ck-apply-panel').exists()).toBe(true)
    expect(wrapper.find('.ck-apply-list').exists()).toBe(true)
    expect(wrapper.text()).toContain('P1')
    expect(wrapper.text()).toContain('软件')
    expect(wrapper.text()).toContain('已按报告自动关联')
    expect(wrapper.findAll('.ck-apply-row input').filter(i => (i.element as HTMLInputElement).checked).length).toBe(2)
    expect(wrapper.text()).toContain('充电')
    expect(wrapper.text()).toContain('TP触摸屏')
  })

  it('报告未标域时不预选检查项', async () => {
    stubFetchWithApply({ ...APPLY_PROMPT, domain_unspecified: true })
    const wrapper = mount(EaShell, { slots: { default: '<div />' } })
    await flushPromises()
    expect(wrapper.text()).toContain('报告未标域')
    const checked = wrapper.findAll('.ck-apply-row input').filter(i => (i.element as HTMLInputElement).checked)
    expect(checked.length).toBe(0)
  })
})
