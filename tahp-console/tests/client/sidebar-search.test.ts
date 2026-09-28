// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const mockAppStore = vi.hoisted(() => ({
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
}))

vi.mock('@/stores/hermes/app', () => ({
  useAppStore: () => mockAppStore,
}))

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<any>()
  return {
    ...actual,
    useRoute: () => ({ name: 'tahp.dashboard', meta: {} }),
    useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  }
})

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
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
    NDropdown: {
      template: '<div class="dropdown-stub"><slot /></div>',
    },
  }
})

import EaShell from '@/components/layout/EaShell.vue'

describe('EaShell', () => {
  beforeEach(() => {
    mockAppStore.updateAvailable = false
    mockAppStore.doUpdate.mockClear()
  })

  it('renders V26 brand and core navigation tabs', () => {
    const wrapper = mount(EaShell, {
      slots: { default: '<div class="page-content">Home</div>' },
    })

    expect(wrapper.find('.ck-brand').text()).toContain('EasyAdapter')
    expect(wrapper.find('.page-content').exists()).toBe(true)

    const tabs = wrapper.findAll('.ck-tab').map(node => node.text())
    expect(tabs).toContain('首页')
    expect(tabs).toContain('AI 适配流水线')
    // 智能诊断 / 质量验测 位于「公共能力」下拉中，顶栏只渲染触发按钮
    expect(tabs.some(text => text.includes('公共能力'))).toBe(true)
    expect(tabs).not.toContain('智能诊断')
  })

  it('shows update button when server reports update available', async () => {
    mockAppStore.updateAvailable = true
    const wrapper = mount(EaShell, {
      slots: { default: '<div />' },
    })

    const updateBtn = wrapper.find('.ck-sys-btn.update')
    expect(updateBtn.exists()).toBe(true)
    await updateBtn.trigger('click')
    expect(mockAppStore.doUpdate).toHaveBeenCalledTimes(1)
  })
})
