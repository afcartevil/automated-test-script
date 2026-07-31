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
      '# 主控 Skill 工作流（ECC 配置 · 无人值守）',
      '- Read 主控 Skill **ecc-config** 全文，按 parameters.md / mapping.md SOP 执行',
      '- 表单中 MTK / 展锐 / 高通代码仓路径至少一项已填；对每项非空路径识别平台并分别处理',
      '- 用户可提交**多组** ECC 条目（字段 `ecc_group_N_*` 或 `ecc_entries_json`）：每组含号码、有卡、无卡、名称、是否屏蔽、本组补充；均选填',
      '- 表单公共字段 `extra_info`（补充信息）对整单生效，优先于各组补充',
      '- **禁止**输出 TAHP_USER_INPUT、禁止暂停等待用户确认；缺省参数按 Skill 默认规则与表单已有信息推断后继续',
      '- 表单若填了 `jira_key`：仅作 commit ID / 上下文参考，**不要**调用 jira-ops 拉单；以表单 ECC 字段为准直接改仓',
      '- `block`（屏蔽）仅 MTK 生效；展锐/高通须在摘要中注明已忽略',
      '- ECC 文件修改完成后：**必须** Read 并执行关联 Skill **gerrit-submit**，将各已改仓库提交到 Gerrit（用户已要求完成本任务，视为已授权提交，勿二次确认）',
      '- 全部完成后输出变更摘要、修改文件清单与 Gerrit Change URL',
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
    // ECC / APN 无人值守；仅 CarrierConfig（或显式 interactionMode）走人机协同
    return input.interactionMode === true || input.domainId === 'carrierconfig-tools'
  },

  buildRoleIntro(input) {
    if (input.domainId === 'ecc-config') {
      return `你是 TAHP「运营商配置 · Agent 自动适配」专家，负责在传音 Android 底软集成部完成 **${input.domainLabel}**。

本任务为 **ECC 无人值守** 模式：根据用户表单输入一次性跑完「改配置 → gerrit-submit 推 Gerrit」，**不要**弹窗、不要 TAHP_USER_INPUT、不要中途等人确认。危险命令由 Console 自动同意。`
    }
    return `你是 TAHP「运营商配置 · Agent 自动适配」专家，负责在传音 Android 底软集成部完成 **${input.domainLabel}** 的运营商相关配置任务。

本任务来自 **运营商配置** 工作区：CarrierConfig / ECC / APN 等配置变更须严格按 Skill SOP，关键步骤需用户确认。`
  },

  buildWorkflowHint: buildCarrierConfigWorkflowHint,

  buildUserTitle(input) {
    return `# ${input.domainLabel} — 运营商配置任务`
  },

  buildUserClosingLines(input, interactive) {
    if (input.domainId === 'ecc-config') {
      return [
        '请立即开始：Read 主控 Skill **ecc-config**，按表单参数执行适配（无人值守，勿等待确认）。',
        'ECC 修改完成后，Read 并执行 **gerrit-submit** 将改动提交到 Gerrit，回报 Change URL。',
        '全部完成后输出结构化总结（含文件修改清单、提交结果与风险项）。',
      ]
    }
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
