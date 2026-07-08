import type { AdaptAgentPromptInput, AdaptWorkspacePromptProfile } from './types'
import { buildGenericWorkflowHint } from './shared'

const FEATURE_ADAPT_SCMP_WORKFLOW = [
  '# 特性适配通用工作流',
  '- 解析表单「特性清单」与各输入字段，明确待交付特性及编码（SF-…）',
  '- **若用户输入（任意表单字段）中包含项目名称**：必须先 Read `tones-scmp` Skill，查询特性清单中各编码在对应项目策略/SPD 下的支持情况',
  '- 结合 SCMP 支持结论与关联 Skill（主控优先），仅对需适配项执行 SOP；不支持或无需适配项记入「跳过/风险项」',
  '- 输出可交付报告：SCMP 核对摘要、适配动作、验证结论',
].join('\n')

function buildFeatureAdaptWorkflowHint(domainId: string, primarySkill: string): string {
  const lines = [FEATURE_ADAPT_SCMP_WORKFLOW]

  if (domainId === 'charging') {
    lines.push(
      '',
      '# 主控 Skill 工作流（充电特性适配）',
      '- 根据表单路径与「特性清单」确定适配范围（老升新 / 绿场 / 部分功能）',
      '- Read 主控 Skill 全文后按 Pillar 流程执行',
      '- 输出结构化适配总结与文件修改清单',
    )
  } else if (domainId === 'audio') {
    lines.push(
      '',
      '# 主控 Skill 工作流（音频特性适配）',
      '- 按 `audio-feature-adaptation` 完成特性移植；完成后可用 `audio-feature-selfcheck` 做只读自检',
      '- 核对 vnd 路径、编译选项与 ADSP 选项后再动手',
    )
  } else {
    lines.push(
      '',
      buildGenericWorkflowHint(primarySkill),
      '- **特性适配工作区**：以可交付、可回归验证为完成标准',
    )
  }

  return lines.join('\n')
}

export const featureAdaptPromptProfile: AdaptWorkspacePromptProfile = {
  workspaceId: 'feature-adapt',
  workspaceLabel: '特性适配',
  contextScenario: 'feature_adapt',

  isInteractive(input: AdaptAgentPromptInput) {
    return input.interactionMode === true
  },

  buildRoleIntro(input) {
    return `你是 TAHP「特性适配 · Agent 自动适配」专家，负责在传音 Android 底软集成部完成 **${input.domainLabel}** 的特性适配交付任务。

本任务来自 **特性适配** 工作区：按正式 SOP 完成适配与自检，输出可交付的结构化报告。若表单或补充说明中出现项目名称，须通过 \`tones-scmp\` 核对特性清单中各编码的支持情况后再执行适配。`
  },

  buildWorkflowHint: buildFeatureAdaptWorkflowHint,

  buildUserTitle(input) {
    return `# ${input.domainLabel} — 特性适配任务`
  },

  buildUserClosingLines(_input, interactive) {
    const lines = [
      '请立即开始：若输入含项目名称，先 Read `tones-scmp` 核对特性清单支持情况；再 Read 主控 Skill，输出任务规划与检查清单，按 SOP 执行特性适配。',
    ]
    if (!interactive) {
      lines.push(
        '全部适配完成后，必须 Read `transsion-coding-standards-review`，在报告末尾先输出「## 审核结果概览」三行 PASS/FAIL 表，再写详细审核章节。',
        '报告须满足特性交付要求：SCMP 核对摘要（如有项目名）、任务规划回顾、文件修改清单、升级/适配结果摘要、风险项缺一不可。',
      )
    } else {
      lines.push('需要用户确认时，使用 TAHP_USER_INPUT 块暂停并等待 Console 弹窗。')
    }
    return lines
  },
}
