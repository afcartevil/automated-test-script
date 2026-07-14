import type { AdaptAgentPromptInput, AdaptWorkspacePromptProfile } from './types'
import { buildGenericWorkflowHint } from './shared'

function buildCarrierConfigWorkflowHint(domainId: string, primarySkill: string): string {
  if (domainId === 'carrierconfig-tools') {
    return [
      '# 主控 Skill 工作流（CarrierConfig）',
      '- 从用户「描述」提取 Jira、运营商、mccmnc、变更 key、期望值',
      '- Jira 读单/评论等 API 操作使用 **jira-ops**；业务流程调度 **carrierconfig-tools** 子 Skill',
      '- 典型顺序：jira-reader → carrier-lookup → carrierconfig-edit → carrierconfig-submit',
      '- 需用户确认时用 TAHP_USER_INPUT 块请求，勿在对话中裸问',
      '- 矩阵缺失时提示是否执行 matrix-update',
    ].join('\n')
  }
  if (domainId === 'ecc-config') {
    return [
      '# 主控 Skill 工作流（ECC 配置）',
      '- Read 主控 Skill **ecc-config** 全文，按 parameters.md / mapping.md SOP 执行',
      '- 表单中 MTK / 展锐 / 高通代码仓路径至少一项已填；对每项非空路径识别平台并分别处理',
      '- 用户可提交**多组** ECC 条目（字段 `ecc_group_N_*` 或 `ecc_entries_json`）：每组含号码、有卡、无卡、名称、是否屏蔽；均选填',
      '- 填写了 Jira 单号时：先用 **jira-ops** 拉取工单（描述中的步骤、期望结果、测试结果），再整理目标 ECC 配置',
      '- 落库前输出「当前 vs 目标」差异并请用户确认；需补充 mccmnc、多语言等时用 TAHP_USER_INPUT 块',
      '- `block`（屏蔽）仅 MTK 生效；展锐/高通须提示忽略',
      '- 完成后输出变更摘要与修改文件清单',
    ].join('\n')
  }
  if (domainId === 'apn-config') {
    return [
      '# 主控 Skill 工作流（APN 配置）',
      '- 校验 `repo_path` 指向的代码仓库可访问',
      '- Read 主控 Skill `apn-edit` 全文，按 SOP 定位并修改 APN 配置',
      '- 结合 `extra_info` 中的 MCC/MNC、平台信息执行适配',
      '- 输出修改文件清单与验证建议',
    ].join('\n')
  }
  return buildGenericWorkflowHint(primarySkill)
}

export const carrierConfigPromptProfile: AdaptWorkspacePromptProfile = {
  workspaceId: 'carrier-config',
  workspaceLabel: '运营商配置',
  contextScenario: 'carrier_config',

  isInteractive(input: AdaptAgentPromptInput) {
    return input.interactionMode === true
      || input.domainId === 'carrierconfig-tools'
      || input.domainId === 'ecc-config'
  },

  buildRoleIntro(input) {
    return `你是 TAHP「运营商配置 · Agent 自动适配」专家，负责在传音 Android 底软集成部完成 **${input.domainLabel}** 的运营商相关配置任务。

本任务来自 **运营商配置** 工作区：CarrierConfig / ECC / APN 等配置变更须严格按 Skill SOP，关键步骤需用户确认。`
  },

  buildWorkflowHint: buildCarrierConfigWorkflowHint,

  buildUserTitle(input) {
    return `# ${input.domainLabel} — 运营商配置任务`
  },

  buildUserClosingLines(_input, interactive) {
    if (interactive) {
      return [
        '请立即开始：Read 主控 Skill，解析用户描述中的 Jira/运营商/配置项，输出任务规划。',
        '需要用户确认落点、diff 或补充参数时，**必须**输出 TAHP_USER_INPUT 块并等待 Console 弹窗，勿在对话中裸问。',
        '全部流程经用户确认完成后，输出结构化总结（含文件修改清单与风险项）。',
      ]
    }
    return [
      '请立即开始：Read 主控 Skill，输出任务规划，然后按 SOP 执行 APN/配置适配。',
      '全部完成后输出结构化总结；若 Skill 要求自检，按主控 Skill 说明执行。',
    ]
  },
}
