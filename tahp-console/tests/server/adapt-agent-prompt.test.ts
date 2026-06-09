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

  it('uses primary skill workflow for generic domains', () => {
    const { systemPrompt, userPrompt } = buildAdaptAgentPrompts({
      domainId: 'fp',
      domainLabel: '指纹',
      module: 'kernel-driver',
      relatedSkills: ['drv-fp-adapt', 'drv-fp-check'],
      formData: { ic_model: 'GW9598' },
      formFields: [{ name: 'ic_model', label: 'IC型号', required: true }],
    })
    expect(systemPrompt).toContain('drv-fp-adapt')
    expect(systemPrompt).toContain('主控 Skill 工作流（drv-fp-adapt）')
    expect(userPrompt).toContain('**主控 Skill**: drv-fp-adapt')
    expect(userPrompt).toContain('**协同 Skill**: drv-fp-check')
  })

  it('uses form_fields labels in user prompt', () => {
    const { userPrompt } = buildAdaptAgentPrompts({
      domainId: 'comm-framework',
      domainLabel: '通信框架',
      module: 'telephony',
      relatedSkills: ['comm-framework-agent-test'],
      formData: { prj_path: 'D:\\project\\test' },
      formFields: [{ name: 'prj_path', label: 'PRJ Path（项目路径）', required: true }],
    })
    expect(userPrompt).toContain('PRJ Path（项目路径）')
    expect(userPrompt).toContain('prj_path')
  })
})
