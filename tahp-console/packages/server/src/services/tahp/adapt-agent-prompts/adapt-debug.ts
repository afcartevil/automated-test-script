import type { AdaptAgentPromptInput, AdaptWorkspacePromptProfile } from './types'
import { buildGenericWorkflowHint } from './shared'

function buildAdaptDebugWorkflowHint(domainId: string, primarySkill: string): string {
  if (domainId === 'comm-framework') {
    return [
      '# 主控 Skill 工作流（通信框架测试 · 调试）',
      '- 校验 `prj_path` 是否有效',
      '- 在 `prj_path` 下创建测试文件',
      '- 按步骤多次写入（步骤、时间、地点、天气）',
      '- 输出最终文件路径与写入结果',
      '- **调试模式**：允许记录中间失败与重试步骤，便于问题定位',
    ].join('\n')
  }
  if (domainId === 'modem') {
    return [
      '# 主控 Skill 工作流（MODEM P1 参考 · 调试）',
      '- 校验 4 个全局路径 + BOM 名称 + 变更后 BOM + RF 目标仓',
      '- 调度 RF 移植子技能 → 获取上下文变量 X、Y',
      '- 调度宏控移植子技能 → 汇总报告',
      '- **调试模式**：分阶段输出日志摘要，便于在 Console 中跟踪',
    ].join('\n')
  }
  return buildGenericWorkflowHint(primarySkill)
}

export const adaptDebugPromptProfile: AdaptWorkspacePromptProfile = {
  workspaceId: 'adapt-debug',
  workspaceLabel: '单项适配',
  contextScenario: 'adapt_debug',

  isInteractive(input: AdaptAgentPromptInput) {
    return input.interactionMode === true
  },

  buildRoleIntro(input) {
    return `你是 TAHP「单项适配 · Agent 自动适配」专家，负责在传音 Android 底软集成部完成 **${input.domainLabel}** 的适配调试任务。

本任务来自 **单项适配** 工作区：侧重联调、验证与问题定位，可按 Skill SOP 分步执行并保留中间结论。`
  },

  buildWorkflowHint: buildAdaptDebugWorkflowHint,

  buildUserTitle(input) {
    return `# ${input.domainLabel} — 单项适配任务`
  },

  buildUserClosingLines(_input, interactive) {
    const lines = [
      '请立即开始：Read 主控 Skill，输出任务规划，然后按 SOP 执行适配调试。',
    ]
    if (!interactive) {
      lines.push(
        `全部适配完成后，必须 Read \`transsion-coding-standards-review\`，在报告末尾先输出「## 审核结果概览」三行 PASS/FAIL 表，再写详细审核章节。`,
      )
    } else {
      lines.push('需要用户确认时，使用 TAHP_USER_INPUT 块暂停并等待 Console 弹窗。')
    }
    return lines
  },
}
