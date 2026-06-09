import { describe, expect, it } from 'vitest'
import { buildAdaptAgentPrompts } from '../../packages/server/src/services/tahp/adapt-agent'

describe('adapt-agent prompts', () => {
  it('buildAdaptAgentPrompts omits legacy project context fields', () => {
    const { systemPrompt, userPrompt } = buildAdaptAgentPrompts({
      domainId: 'comm-framework',
      domainLabel: '通信框架',
      module: 'telephony',
      relatedSkills: ['comm-framework-agent-test'],
      formData: { prj_path: 'D:\\project\\test' },
    })
    expect(systemPrompt).toContain('comm-framework-agent-test')
    expect(userPrompt).toContain('prj_path')
    expect(userPrompt).not.toContain('项目代码')
    expect(userPrompt).not.toContain('升级路径')
    expect(userPrompt).toContain('域 ID: comm-framework')
  })
})
