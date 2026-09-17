// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { UnifiedConfigField, UnifiedConfigForm } from '@/api/tahp/skill-config'

const mockMessage = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
}))

const mockFetchUnifiedConfigForm = vi.hoisted(() => vi.fn())
const mockSaveUnifiedConfigForm = vi.hoisted(() => vi.fn())

vi.mock('naive-ui', async (importOriginal) => {
  const actual = await importOriginal<typeof import('naive-ui')>()
  return { ...actual, useMessage: () => mockMessage }
})

vi.mock('@/api/tahp/skill-config', () => ({
  fetchUnifiedConfigForm: mockFetchUnifiedConfigForm,
  saveUnifiedConfigForm: mockSaveUnifiedConfigForm,
}))

import ConfigUnifiedFormPanel from '@/components/tahp/config/ConfigUnifiedFormPanel.vue'
import { TEST_DOMAIN_SAVE_ONLY_HINT } from '@/utils/config-navigation'

const FIELDS: UnifiedConfigField[] = [
  { key: 'domain_account', label: '域账号', type: 'text', group: '域账号' },
  { key: 'domain_password', label: '域密码', type: 'password', group: '域账号' },
  { key: 'linux_server_ip', label: 'Linux 服务器 IP', type: 'text', group: 'harness工具' },
  { key: 'qizhi_totp_secret', label: '齐治 TOTP secret', type: 'password', group: 'harness工具' },
]

function form(values: Record<string, string>): UnifiedConfigForm {
  return { fields: FIELDS, values, saved_values: {} }
}

function filledForm(overrides: Record<string, string> = {}): UnifiedConfigForm {
  return form({
    domain_account: 'alice',
    domain_password: 'secret',
    linux_server_ip: '10.205.0.143',
    qizhi_totp_secret: 'JBSWY3DPEHPK3PXP',
    ...overrides,
  })
}

function findSaveButton(wrapper: ReturnType<typeof mount>) {
  const button = wrapper.findAll('button').find(b => b.text().includes('保存并启动skill配置检查'))
  if (!button) throw new Error('未找到「保存并启动skill配置检查」按钮')
  return button
}

describe('ConfigUnifiedFormPanel 保存并启动skill配置检查', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockSaveUnifiedConfigForm.mockResolvedValue(form({}))
  })

  it('saves a test- account with the fixed test password without starting the check', async () => {
    mockFetchUnifiedConfigForm.mockResolvedValue(filledForm({
      domain_account: 'test-alice',
      domain_password: '12345678',
      linux_server_ip: '',
      qizhi_totp_secret: '',
    }))
    const wrapper = mount(ConfigUnifiedFormPanel)
    await flushPromises()

    await findSaveButton(wrapper).trigger('click')
    await flushPromises()

    expect(mockSaveUnifiedConfigForm).toHaveBeenCalledOnce()
    expect(wrapper.emitted('startBatch')).toBeUndefined()
    expect(mockMessage.warning).toHaveBeenCalledWith(TEST_DOMAIN_SAVE_ONLY_HINT, { duration: 8000 })
    expect(wrapper.text()).toContain('未启动 skill 配置检查')
  })

  it('still blocks a normal account when other required fields are empty', async () => {
    mockFetchUnifiedConfigForm.mockResolvedValue(filledForm({
      linux_server_ip: '',
      qizhi_totp_secret: '',
    }))
    const wrapper = mount(ConfigUnifiedFormPanel)
    await flushPromises()

    await findSaveButton(wrapper).trigger('click')
    await flushPromises()

    expect(mockSaveUnifiedConfigForm).not.toHaveBeenCalled()
    expect(wrapper.emitted('startBatch')).toBeUndefined()
    expect(mockMessage.warning).toHaveBeenCalledOnce()
    expect(String(mockMessage.warning.mock.calls[0][0])).toContain('缺 2 项')
  })

  it('blocks a test- prefixed account that uses a non-test password', async () => {
    mockFetchUnifiedConfigForm.mockResolvedValue(filledForm({
      domain_account: 'test-alice',
      domain_password: 'not-the-test-password',
      linux_server_ip: '',
    }))
    const wrapper = mount(ConfigUnifiedFormPanel)
    await flushPromises()

    await findSaveButton(wrapper).trigger('click')
    await flushPromises()

    expect(mockSaveUnifiedConfigForm).not.toHaveBeenCalled()
    expect(wrapper.emitted('startBatch')).toBeUndefined()
  })

  it('saves and starts the check when every field is filled', async () => {
    mockFetchUnifiedConfigForm.mockResolvedValue(filledForm())
    const wrapper = mount(ConfigUnifiedFormPanel)
    await flushPromises()

    await findSaveButton(wrapper).trigger('click')
    await flushPromises()

    expect(mockSaveUnifiedConfigForm).toHaveBeenCalledOnce()
    expect(wrapper.emitted('startBatch')).toHaveLength(1)
  })
})
