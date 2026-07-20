import { afterEach, describe, expect, it, vi } from 'vitest'
import { validateNlUiPlan } from '../../packages/server/src/services/tahp/ai-nl-ui-cases'

describe('validateNlUiPlan', () => {
  it('accepts executable plan with assert step', () => {
    const result = validateNlUiPlan({
      executable: true,
      steps: [
        { op: 'wake' },
        { op: 'tap_text', text: 'WLAN', scroll: true },
        { op: 'assert_text', text: 'WLAN', present: true },
      ],
    })
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.plan.steps).toHaveLength(3)
    }
  })

  it('rejects plan without assert', () => {
    const result = validateNlUiPlan({
      executable: true,
      steps: [{ op: 'wake' }, { op: 'home' }],
    })
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.error).toMatch(/断言/)
    }
  })

  it('rejects unsupported shell command', () => {
    const result = validateNlUiPlan({
      executable: true,
      steps: [
        { op: 'shell', cmd: 'reboot' },
        { op: 'assert_text', text: 'OK' },
      ],
    })
    expect(result.ok).toBe(false)
  })

  it('rejects executable=false plans', () => {
    const result = validateNlUiPlan({
      executable: false,
      reason: '需要插拔 SIM',
      steps: [],
    })
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.error).toMatch(/SIM/)
    }
  })

  it('accepts optional tap and wait_until clickable/text_present', () => {
    const result = validateNlUiPlan({
      executable: true,
      steps: [
        { op: 'tap_text', text: '确认', optional: true },
        { op: 'wait_until', condition: 'clickable', text: '校准', timeout: 30 },
        { op: 'tap_text', text: '校准' },
        { op: 'wait_until', condition: 'text_present', text: '通过', timeout: 10 },
        { op: 'assert_text', text: '通过', present: true },
      ],
    })
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.plan.steps[0]?.optional).toBe(true)
      expect(result.plan.steps[1]?.condition).toBe('clickable')
      expect(result.plan.steps[3]?.condition).toBe('text_present')
    }
  })

  it('accepts dial_keys for engineering codes', () => {
    const result = validateNlUiPlan({
      executable: true,
      steps: [
        { op: 'shell', cmd: 'am start -a android.intent.action.DIAL' },
        { op: 'dial_keys', keys: '*#888#' },
        { op: 'assert_text', text: '通过', present: true },
      ],
    })
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.plan.steps[1]?.keys).toBe('*#888#')
    }
  })

  it('accepts tap_rid for icon-only dial button', () => {
    const result = validateNlUiPlan({
      executable: true,
      steps: [
        { op: 'shell', cmd: 'am start -a android.intent.action.DIAL' },
        { op: 'dial_keys', keys: '18676785952' },
        { op: 'tap_rid', rid: 'dialpad_floating_action_button' },
        { op: 'assert_text', text: '通话中', present: true },
      ],
    })
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.plan.steps[2]?.rid).toBe('dialpad_floating_action_button')
    }
  })

  it('rejects tap_rid without rid', () => {
    const result = validateNlUiPlan({
      executable: true,
      steps: [
        { op: 'tap_rid' },
        { op: 'assert_text', text: '通话中' },
      ],
    })
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.error).toMatch(/tap_rid/)
    }
  })

  it('rejects input text with * or #', () => {
    const result = validateNlUiPlan({
      executable: true,
      steps: [
        { op: 'shell', cmd: 'input text "*#888#"' },
        { op: 'assert_text', text: '通过' },
      ],
    })
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.error).toMatch(/dial_keys/)
    }
  })

  it('rejects dial_keys with unsupported characters', () => {
    const result = validateNlUiPlan({
      executable: true,
      steps: [
        { op: 'dial_keys', keys: '*#abc#' },
        { op: 'assert_text', text: '通过' },
      ],
    })
    expect(result.ok).toBe(false)
  })
})

describe('createManualNlUiCase', () => {
  const createdKeys: string[] = []

  afterEach(async () => {
    if (!createdKeys.length) return
    const { deleteAiGeneratedCases } = await import('../../packages/server/src/services/tahp/gerrit-ai-generated-cases')
    deleteAiGeneratedCases([...createdKeys])
    createdKeys.length = 0
  })

  it('persists nl_ui case when LLM returns valid plan', async () => {
    vi.resetModules()
    vi.doMock('../../packages/server/src/services/tahp/llm-caller', () => ({
      callTahpLLM: vi.fn(async () => JSON.stringify({
        executable: true,
        reason: '',
        steps: [
          { op: 'wake' },
          { op: 'shell', cmd: 'am start -a android.settings.SETTINGS' },
          { op: 'assert_text', text: '设置', present: true },
        ],
      })),
    }))

    const { createManualNlUiCase } = await import('../../packages/server/src/services/tahp/ai-nl-ui-cases')
    const created = await createManualNlUiCase({
      caseName: '打开设置页',
      nlDescription: '亮屏解锁后打开系统设置，并确认进入设置主页',
      expectedResult: '界面出现设置标题',
    })

    expect(created.execMode).toBe('nl_ui')
    expect(created.caseKey).toMatch(/^ai_generated\/generated\/\d+$/)
    expect(created.plan.steps.length).toBeGreaterThanOrEqual(2)
    createdKeys.push(created.caseKey)
  })

  it('throws when LLM marks plan not executable', async () => {
    vi.resetModules()
    vi.doMock('../../packages/server/src/services/tahp/llm-caller', () => ({
      callTahpLLM: vi.fn(async () => JSON.stringify({
        executable: false,
        reason: '需要双机对测',
        steps: [],
      })),
    }))

    const { createManualNlUiCase } = await import('../../packages/server/src/services/tahp/ai-nl-ui-cases')
    await expect(createManualNlUiCase({
      caseName: '双机通话',
      nlDescription: '使用辅测机与测试机互相拨打并验证',
    })).rejects.toThrow(/双机/)
  })
})

describe('updateManualNlUiCase', () => {
  const createdKeys: string[] = []

  afterEach(async () => {
    if (!createdKeys.length) return
    const { deleteAiGeneratedCases } = await import('../../packages/server/src/services/tahp/gerrit-ai-generated-cases')
    deleteAiGeneratedCases([...createdKeys])
    createdKeys.length = 0
  })

  it('overwrites same caseIndex and caseKey', async () => {
    vi.resetModules()
    const plans = [
      JSON.stringify({
        executable: true,
        reason: '',
        steps: [
          { op: 'wake' },
          { op: 'assert_text', text: '设置', present: true },
        ],
      }),
      JSON.stringify({
        executable: true,
        reason: 'updated',
        steps: [
          { op: 'wake' },
          { op: 'home' },
          { op: 'assert_text', text: 'WLAN', present: true },
        ],
      }),
    ]
    vi.doMock('../../packages/server/src/services/tahp/llm-caller', () => ({
      callTahpLLM: vi.fn(async () => plans.shift() || plans[0]),
    }))

    const { createManualNlUiCase, updateManualNlUiCase } = await import(
      '../../packages/server/src/services/tahp/ai-nl-ui-cases'
    )
    const { loadDurableCaseInfo } = await import(
      '../../packages/server/src/services/tahp/ai-generated-case-store'
    )

    const created = await createManualNlUiCase({
      caseName: '打开设置页',
      nlDescription: '亮屏解锁后打开系统设置，并确认进入设置主页',
      expectedResult: '界面出现设置标题',
    })
    createdKeys.push(created.caseKey)

    const updated = await updateManualNlUiCase({
      caseKey: created.caseKey,
      caseName: '验证 WLAN 入口',
      nlDescription: '亮屏解锁后进入设置并打开 WLAN，确认出现开关',
      expectedResult: '界面出现 WLAN',
    })

    expect(updated.caseKey).toBe(created.caseKey)
    expect(updated.caseIndex).toBe(created.caseIndex)
    expect(updated.caseName).toBe('验证 WLAN 入口')
    expect(updated.plan.steps.some(s => s.op === 'assert_text' && s.text === 'WLAN')).toBe(true)

    const caseInfo = loadDurableCaseInfo()
    const entry = caseInfo[created.caseIndex - 1]
    expect(entry?.['用例名']).toBe('验证 WLAN 入口')
    expect(entry?.['测试步骤']).toContain('WLAN')
  })

  it('rejects unknown caseKey', async () => {
    vi.resetModules()
    vi.doMock('../../packages/server/src/services/tahp/llm-caller', () => ({
      callTahpLLM: vi.fn(async () => JSON.stringify({
        executable: true,
        steps: [{ op: 'wake' }, { op: 'assert_text', text: 'OK' }],
      })),
    }))

    const { updateManualNlUiCase } = await import('../../packages/server/src/services/tahp/ai-nl-ui-cases')
    await expect(updateManualNlUiCase({
      caseKey: 'ai_generated/generated/999999',
      caseName: '不存在',
      nlDescription: '这是一段足够长的自然语言描述用于覆盖校验',
    })).rejects.toThrow(/不存在/)
  })
})
