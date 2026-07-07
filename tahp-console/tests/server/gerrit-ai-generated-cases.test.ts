import { describe, expect, it, afterEach } from 'vitest'
import {
  DEFAULT_AI_CASE_LLM_TIMEOUT_MS,
  findReusableHistoricalAiCases,
  resolveAiCaseGenerationTimeoutMs,
  textCoversP0Item,
  validatePythonSource,
  type AiGeneratedCase,
} from '../../packages/server/src/services/tahp/gerrit-ai-generated-cases'

describe('gerrit-ai-generated-cases historical reuse', () => {
  const historical: AiGeneratedCase[] = [
    {
      caseKey: 'ai_generated/generated/1',
      caseIndex: 1,
      caseName: 'USB 插拔 SAR 校准验证',
      moduleLabel: 'AI生成用例',
      coveredP0Items: ['USB 插拔触发 SAR 校准'],
      reason: '覆盖 USB 校准',
      manualSteps: '1. 插拔 USB',
      expectedResult: '触发校准',
    },
    {
      caseKey: 'ai_generated/generated/2',
      caseIndex: 2,
      caseName: '长时间充电稳定性',
      moduleLabel: 'AI生成用例',
      coveredP0Items: ['长时间充电温升'],
      reason: '覆盖充电稳定性',
      manualSteps: '1. 长时间充电',
      expectedResult: '无异常',
    },
  ]

  it('matches historical cases to coverage gaps by token overlap', () => {
    const { reusable, remainingGaps } = findReusableHistoricalAiCases(
      ['USB 插拔触发 SAR 校准', 'SIM 卡识别异常'],
      historical,
    )

    expect(reusable).toHaveLength(1)
    expect(reusable[0]?.caseKey).toBe('ai_generated/generated/1')
    expect(reusable[0]?.reason).toContain('复用历史 AI 用例')
    expect(reusable[0]?.coveredP0Items).toEqual(['USB 插拔触发 SAR 校准'])
    expect(remainingGaps).toEqual(['SIM 卡识别异常'])
  })

  it('returns all gaps when no historical case matches', () => {
    const { reusable, remainingGaps } = findReusableHistoricalAiCases(
      ['完全不相关的场景 xyz'],
      historical,
    )

    expect(reusable).toEqual([])
    expect(remainingGaps).toEqual(['完全不相关的场景 xyz'])
  })

  it('textCoversP0Item supports mixed Chinese and English tokens', () => {
    expect(textCoversP0Item('USB 插拔触发 SAR 校准', 'USB功能正常充电 SAR sensor')).toBe(true)
    expect(textCoversP0Item('完全不相关', 'USB 插拔')).toBe(false)
  })
})

describe('gerrit-ai-generated-cases validatePythonSource', () => {
  const validSource = `def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get('step_update')
    manual_confirm = context.get('manual_confirm')
    step_update('Step 1')
    if manual_confirm('ok?'):
        return {'status': 'pass', 'message': 'ok', 'full_automation': False}
    return {'status': 'fail', 'message': 'no', 'full_automation': False}`

  it('accepts manual_confirm pattern without imports', () => {
    expect(validatePythonSource(validSource)).toEqual({ ok: true })
  })

  it('rejects any import statement', () => {
    const withImport = `import os\ndef run(category=None, case_index=None, device_info=None, **context):\n    return {'status': 'pass', 'message': 'x', 'full_automation': False}`
    const result = validatePythonSource(withImport)
    expect(result.ok).toBe(false)
    expect(result.error).toContain('禁止 import')
  })

  it('rejects from-import statements', () => {
    const withFrom = `from os import path\ndef run(category=None, case_index=None, device_info=None, **context):\n    return {'status': 'pass', 'message': 'x', 'full_automation': False}`
    const result = validatePythonSource(withFrom)
    expect(result.ok).toBe(false)
    expect(result.error).toContain('禁止 from')
  })
})

describe('gerrit-ai-generated-cases timeout', () => {
  const prevTimeout = process.env.GERRIT_AI_CASE_LLM_TIMEOUT_MS

  afterEach(() => {
    if (prevTimeout === undefined) delete process.env.GERRIT_AI_CASE_LLM_TIMEOUT_MS
    else process.env.GERRIT_AI_CASE_LLM_TIMEOUT_MS = prevTimeout
  })

  it('uses 120s default timeout when env is unset', () => {
    delete process.env.GERRIT_AI_CASE_LLM_TIMEOUT_MS
    expect(DEFAULT_AI_CASE_LLM_TIMEOUT_MS).toBe(120_000)
    expect(resolveAiCaseGenerationTimeoutMs()).toBe(120_000)
  })

  it('respects GERRIT_AI_CASE_LLM_TIMEOUT_MS override', () => {
    process.env.GERRIT_AI_CASE_LLM_TIMEOUT_MS = '180000'
    expect(resolveAiCaseGenerationTimeoutMs()).toBe(180_000)
  })
})
