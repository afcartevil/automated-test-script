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
    expect(systemPrompt).toContain('单项适配')
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

  it('includes interactive protocol for carrierconfig-tools in carrier-config workspace', () => {
    const { systemPrompt, userPrompt } = buildAdaptAgentPrompts({
      workspaceId: 'carrier-config',
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
    expect(systemPrompt).toContain('运营商配置')
    expect(systemPrompt).toContain('CarrierConfig')
    expect(userPrompt).toContain('描述')
    expect(userPrompt).toContain('JIRA-123')
    expect(userPrompt).toContain('运营商配置')
  })

  it('feature-adapt workspace uses distinct product title and SCMP workflow', () => {
    const { systemPrompt, userPrompt } = buildAdaptAgentPrompts({
      workspaceId: 'feature-adapt',
      domainId: 'charging',
      domainLabel: '充电',
      module: 'kernel-driver',
      relatedSkills: [
        'mtk-adapt-pillar3-router',
        'mtk-adapt-template-feature-factory-mode',
        'mtk-adapt-template-feature-kpoc-charging',
        'mtk-adapt-template-feature-placeholder',
        'transsion-sunmao40-customization-features-adapt',
        'tones-scmp',
      ],
      formData: { repo_path: 'D:\\project\\km9' },
    })
    expect(systemPrompt).toContain('特性适配')
    expect(systemPrompt).toContain('tones-scmp')
    expect(systemPrompt).toContain('可交付')
    expect(systemPrompt).toContain('当前场景**: 特性适配')
    expect(userPrompt).toContain('特性适配任务')
    expect(userPrompt).toContain('feature-adapt')
    expect(userPrompt).toContain('tones-scmp')
  })

  it('ecc-config runs unattended without interactive protocol and guides gerrit-submit', () => {
    const { systemPrompt, userPrompt } = buildAdaptAgentPrompts({
      workspaceId: 'carrier-config',
      domainId: 'ecc-config',
      domainLabel: 'ECC配置',
      module: 'telephony',
      relatedSkills: ['ecc-config', 'gerrit-submit'],
      formData: {
        repo_path_mtk: 'D:\\ecc\\mtk',
        ecc_group_1_number: '998',
        ecc_group_1_with_sim: '真紧急',
        ecc_entry_count: '1',
      },
      formFields: [
        { name: 'repo_path_mtk', label: 'MTK 代码仓路径', required: false },
        { name: 'ecc_group_1_number', label: 'ECC组1 · 号码', required: false },
      ],
    })
    expect(systemPrompt).toContain('ecc-config')
    expect(systemPrompt).toContain('gerrit-submit')
    expect(systemPrompt).toContain('无人值守')
    expect(systemPrompt).not.toContain('=== TAHP_USER_INPUT ===')
    expect(systemPrompt).toContain('运营商配置')
    expect(userPrompt).toContain('ECC配置')
    expect(userPrompt).toContain('998')
    expect(userPrompt).toContain('gerrit-submit')
  })

  it('spn-config is interactive and requires jira/log workflow', () => {
    const { systemPrompt, userPrompt } = buildAdaptAgentPrompts({
      workspaceId: 'carrier-config',
      domainId: 'spn-config',
      domainLabel: 'SPN配置',
      module: 'telephony',
      relatedSkills: ['spn-workflow-2-2-0'],
      formData: {
        jira_key: 'OS162-12345',
        log_path: 'D:\\logs\\radio.zip',
        task_goal: 'analyze',
      },
      formFields: [
        { name: 'jira_key', label: 'Jira 单号/链接', required: true },
        { name: 'log_path', label: '日志路径', required: true },
      ],
      interactionMode: true,
    })
    expect(systemPrompt).toContain('spn-workflow-2-2-0')
    expect(systemPrompt).toContain('TAHP_USER_INPUT')
    expect(systemPrompt).toContain('INTAKE')
    expect(systemPrompt).toContain('运营商配置')
    expect(userPrompt).toContain('OS162-12345')
    expect(userPrompt).toContain('SPN配置')
  })

  it('adapt-debug comm-framework emphasizes debug workflow', () => {
    const { systemPrompt } = buildAdaptAgentPrompts({
      workspaceId: 'adapt-debug',
      domainId: 'comm-framework',
      domainLabel: '通信框架',
      module: 'telephony',
      relatedSkills: ['comm-framework-agent-test'],
      formData: { prj_path: 'D:\\test' },
    })
    expect(systemPrompt).toContain('调试模式')
  })
})
