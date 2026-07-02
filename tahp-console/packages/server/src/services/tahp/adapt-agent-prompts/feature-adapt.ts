import type { AdaptAgentPromptInput, AdaptWorkspacePromptProfile } from './types'
import { buildGenericWorkflowHint } from './shared'

function buildFeatureAdaptWorkflowHint(domainId: string, primarySkill: string): string {
  if (domainId === 'comm-framework') {
    return [
      '# 主控 Skill 工作流（通信框架 · 特性交付）',
      '- 校验 `prj_path` 是否有效且符合项目规范',
      '- 按 Skill SOP 完成特性适配与必要验证',
      '- 输出可交付的文件修改清单与验证结论',
      '- **交付模式**：结论须可复现、可审计，避免仅做探索性尝试',
    ].join('\n')
  }
  if (domainId === 'modem') {
    return [
      '# 主控 Skill 工作流（MODEM P1 · 特性交付）',
      '- 校验 4 个全局路径 + BOM 名称 + 变更后 BOM + RF 目标仓',
      '- 调度 RF 移植子技能 → 获取上下文变量 X、Y',
      '- 调度宏控移植子技能 → 汇总可交付报告',
      '- **交付模式**：按 Skill 检查清单逐项勾选，缺失项写入「风险与待用户确认项」',
    ].join('\n')
  }
  if (domainId === 'charging') {
    return [
      '# 主控 Skill 工作流（充电特性适配）',
      '- 根据表单 `mode` / `pillar_required` 确定适配范围（老升新 / 绿场 / 部分功能）',
      '- Read 主控 Skill 全文后按 Pillar 流程执行',
      '- 核对 `project_full`、`aosp_root`、`old_tran_root` 等路径有效性',
      '- 输出结构化适配总结与文件修改清单',
    ].join('\n')
  }
  return [
    buildGenericWorkflowHint(primarySkill),
    '- **特性适配工作区**：以可交付、可回归验证为完成标准',
  ].join('\n')
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

本任务来自 **特性适配** 工作区：按正式 SOP 完成适配与自检，输出可交付的结构化报告。`
  },

  buildWorkflowHint: buildFeatureAdaptWorkflowHint,

  buildUserTitle(input) {
    return `# ${input.domainLabel} — 特性适配任务`
  },

  buildUserClosingLines(_input, interactive) {
    const lines = [
      '请立即开始：Read 主控 Skill，输出任务规划与检查清单，然后按 SOP 执行特性适配。',
    ]
    if (!interactive) {
      lines.push(
        '全部适配完成后，必须 Read `transsion-coding-standards-review`，在报告末尾先输出「## 审核结果概览」三行 PASS/FAIL 表，再写详细审核章节。',
        '报告须满足特性交付要求：任务规划回顾、文件修改清单、升级/适配结果摘要、风险项缺一不可。',
      )
    } else {
      lines.push('需要用户确认时，使用 TAHP_USER_INPUT 块暂停并等待 Console 弹窗。')
    }
    return lines
  },
}
