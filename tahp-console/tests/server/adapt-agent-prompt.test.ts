import { describe, expect, it } from 'vitest'
import {
  ADAPT_AUDIT_SKILL_ID,
  buildAdaptAgentPrompts,
  extractAdaptAuditReport,
} from '../../packages/server/src/services/tahp/adapt-agent'

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

  it('requires self-audit skill at end of adapt report', () => {
    const { systemPrompt, userPrompt } = buildAdaptAgentPrompts({
      domainId: 'fp',
      domainLabel: '指纹',
      module: 'kernel-driver',
      relatedSkills: ['drv-fp-adapt'],
      formData: { ic_model: 'GW9598' },
    })
    expect(systemPrompt).toContain(ADAPT_AUDIT_SKILL_ID)
    expect(systemPrompt).toContain('审核结果概览')
    expect(systemPrompt).toContain('Skill 遵从性自检')
    expect(systemPrompt).toContain('编码规范审核报告')
    expect(userPrompt).toContain(ADAPT_AUDIT_SKILL_ID)
  })

  it('extractAdaptAuditReport pulls trailing audit section', () => {
    const body = '## 升级/适配结果摘要\nok\n\n## Skill 遵从性自检\n- Read 主控 Skill: pass\n\n# 编码规范审核报告\n## 概览\n- 总体结论：通过'
    const audit = extractAdaptAuditReport(body)
    expect(audit).toContain('Skill 遵从性自检')
    expect(audit).toContain('编码规范审核报告')
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

  it('includes interactive protocol for carrierconfig-tools', () => {
    const { systemPrompt, userPrompt } = buildAdaptAgentPrompts({
      domainId: 'carrierconfig-tools',
      domainLabel: 'CarrierConfig配置',
      module: 'telephony',
      relatedSkills: ['carrierconfig-tools', 'jira-ops'],
      formData: { description: 'JIRA-123 修改 key foo' },
      formFields: [{ name: 'description', label: '描述', required: true }],
      interactionMode: true,
    })
    expect(systemPrompt).toContain('carrierconfig-tools')
    expect(systemPrompt).toContain('TAHP_USER_INPUT')
    expect(systemPrompt).toContain('CarrierConfig')
    expect(userPrompt).toContain('描述')
    expect(userPrompt).toContain('JIRA-123')
  })
})
