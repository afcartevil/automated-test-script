import { buildFullTahpSystemContext, getTahpSkillsRoot, tahpSkillMdPath } from '../context-injector'
import { resolveFormFieldLabels } from '../adapt-layout/service'
import { DEFAULT_ADAPT_WORKSPACE } from '../adapt-layout/types'
import { ADAPT_AUDIT_SKILL_ID } from './constants'
import type { AdaptAgentPromptInput } from './types'
import type { AdaptWorkspacePromptProfile } from './types'

export { ADAPT_AUDIT_SKILL_ID } from './constants'

export function normalizeWorkspaceId(workspaceId?: string): string {
  return workspaceId?.trim() || DEFAULT_ADAPT_WORKSPACE
}

export function buildSkillPathsList(relatedSkills: string[]): string {
  return relatedSkills
    .map((id, idx) => `- ${idx === 0 ? '**主控**' : '关联'} **${id}**: \`${tahpSkillMdPath(id)}\``)
    .join('\n')
}

export function buildFormParamsSection(input: AdaptAgentPromptInput): string[] {
  const lines: string[] = [
    '## 用户已填写的表单参数（必须使用，勿重复询问已有项）',
  ]
  const rows = resolveFormFieldLabels(input.formData, input.formFields)
  for (const row of rows) {
    lines.push(`- **${row.label}** (\`${row.name}\`): ${row.value}`)
  }
  return lines
}

export function buildSkillsSection(input: AdaptAgentPromptInput): string[] {
  const lines: string[] = [
    '',
    '## 关联 Skills（须按主控 Skill 调度）',
    `**主控 Skill**: ${input.relatedSkills[0]}`,
  ]
  if (input.relatedSkills.length > 1) {
    lines.push(`**协同 Skill**: ${input.relatedSkills.slice(1).join(', ')}`)
  }
  lines.push(`**关联 Skills**: ${input.relatedSkills.join(', ')}`)
  return lines
}

export function buildUserNotesSection(input: AdaptAgentPromptInput): string[] {
  if (!input.userNotes?.trim()) return []
  return ['', '## 用户补充说明', input.userNotes.trim()]
}

export function buildUserInputProtocol(): string {
  return `
# 人机协同：结构化用户确认/配置输入

当需要用户确认落点、diff、路径或补充参数时：

1. **先输出**以下标记块，**然后停止本轮输出**，等待用户在 Console 弹窗提交：
\`\`\`
=== TAHP_USER_INPUT ===
request_id: <唯一 ID>
title: <弹窗标题>
message: <向用户说明>
timeout_sec: 300
field.<name>.label: <字段显示名>
field.<name>.type: text|textarea|password|number
field.<name>.required: true|false
field.<name>.placeholder: <占位提示>
=== END_TAHP_USER_INPUT ===
\`\`\`

2. 用户提交后，BFF 会以「用户已提交配置」消息继续对话；请据此执行后续步骤。
3. 同一 \`request_id\` 不要重复请求。
`
}

export function buildInteractiveCompletionRules(auditSkillPath: string): string {
  return `5. 适配工作**全部完成**后（经用户确认且无待办项），输出结构化总结，必须包含以下章节：
   - ## 任务规划回顾
   - ## 已使用的 Skill
   - ## 文件修改清单（每条必须是本机绝对路径 + 修改说明；禁止相对路径；若无修改写「无」）
   - ## 升级/适配结果摘要
   - ## 风险与待用户确认项
6. **最后一步（全流程完成时）— 自检审核**：Read 审核 Skill 全文 \`${auditSkillPath}\`（\`${ADAPT_AUDIT_SKILL_ID}\`），在**全部适配总结之后**追加审核章节（格式同下）。
7. 中间步骤需要用户确认或补充参数时，**必须**输出 \`=== TAHP_USER_INPUT ===\` 块后停止本轮，等待 Console 弹窗提交。`
}

export function buildStandardCompletionRules(auditSkillPath: string): string {
  return `5. 适配工作全部完成后，输出结构化总结，必须包含以下章节：
   - ## 任务规划回顾
   - ## 已使用的 Skill
   - ## 文件修改清单（每条必须是本机绝对路径 + 修改说明；禁止相对路径；若无修改写「无」）
   - ## 升级/适配结果摘要
   - ## 风险与待用户确认项
6. **最后一步（不得跳过）— 自检审核**：Read 审核 Skill 全文 \`${auditSkillPath}\`（\`${ADAPT_AUDIT_SKILL_ID}\`），在**全部适配总结之后**追加，且**必须严格按下列顺序与格式**：`
}

export function buildStandardAuditBlock(): string {
  return `   - **先输出固定概览表** \`## 审核结果概览\`（系统据此解析，禁止省略或改列名）：
     \`\`\`
     ## 审核结果概览

     | 检查环节 | 结果 | 说明 |
     |----------|------|------|
     | Skill 遵从性自检 | PASS 或 FAIL 或 WARN | 一行精简说明 |
     | 编码规范审核报告 | PASS 或 FAIL 或 WARN | 一行精简说明 |
     | AOSP 流程风险评估 | PASS 或 FAIL 或 WARN 或 N/A | 一行精简说明 |
     \`\`\`
   - 再输出 \`## Skill 遵从性自检\` 详情（须含 \`**结论**:\` 行，写 PASS/FAIL 及一句总结）
   - 再输出 \`# 编码规范审核报告\`（含 \`## 概览\` 与 \`**总体结论**:\`，严格按 \`${ADAPT_AUDIT_SKILL_ID}\` 模板）
7. 最终回复顺序：**适配总结 → 审核结果概览表 → Skill 遵从性自检 → 编码规范审核报告**。`
}

export function buildGenericWorkflowHint(primarySkill: string): string {
  return [
    `# 主控 Skill 工作流（${primarySkill}）`,
    `- 先 Read 主控 Skill：\`${primarySkill}\` 全文，严格按其中 SOP 执行`,
    '- 用户表单参数已提供则核对后使用，勿重复询问已有项',
    '- 按主控 Skill 调度下列关联 Skill（顺序执行，必要时 Read 全文）',
    '- 输出结构化总结与文件修改清单',
  ].join('\n')
}

export function buildSystemPrompt(
  profile: AdaptWorkspacePromptProfile,
  input: AdaptAgentPromptInput,
  userMessage: string,
): string {
  const primarySkill = input.relatedSkills[0]
  const skillsDir = getTahpSkillsRoot()
  const skillPaths = buildSkillPathsList(input.relatedSkills)
  const auditSkillPath = tahpSkillMdPath(ADAPT_AUDIT_SKILL_ID)
  const workflowHint = profile.buildWorkflowHint(input.domainId, primarySkill)
  const interactive = profile.isInteractive(input)

  const completionRules = interactive
    ? buildInteractiveCompletionRules(auditSkillPath)
    : buildStandardCompletionRules(auditSkillPath)

  const auditBlock = interactive ? '' : buildStandardAuditBlock()
  const userInputProtocol = interactive ? buildUserInputProtocol() : ''

  const base = `${profile.buildRoleIntro(input)}

# 必须遵守
1. **先 Read 主控 Skill 全文**：\`${tahpSkillMdPath(primarySkill)}\`，再按其中 SOP 逐步执行，不得跳过「收集参数」类步骤（用户已在表单中提供则核对后使用）。
2. **关联 Skill（按流程调度）**：
${skillPaths}
3. **必须真实调用工具**；每完成一个主要阶段，用简短 Markdown 输出「任务规划 / 当前步骤 / 下一步」。
4. 涉及代码或配置修改时，使用 Write/Edit 等工具；**禁止编造路径**。
${completionRules}
${auditBlock}
8. \`## 文件修改清单\` 中每条路径必须用反引号包裹**本机绝对路径**（Windows 如 \`Z:\\\\code\\\\kernel\\\\foo.c\`，Linux 如 \`/work/kernel/foo.c\`）。禁止 \`vendor/foo.c\` 这类相对路径；系统按该清单收录变更，相对路径会被丢弃。
${userInputProtocol}
${workflowHint}

# 审核 Skill（适配完成后必读）
- **${ADAPT_AUDIT_SKILL_ID}**: \`${auditSkillPath}\`

# 工程 Skill 根目录
\`${skillsDir}\`
`

  const tahpCtx = buildFullTahpSystemContext(userMessage, {
    scenario: profile.contextScenario,
    preferredSkillIds: [...input.relatedSkills, ADAPT_AUDIT_SKILL_ID],
  })
  return tahpCtx ? `${base}\n\n${tahpCtx}` : base
}

export function buildUserPrompt(
  profile: AdaptWorkspacePromptProfile,
  input: AdaptAgentPromptInput,
): string {
  const interactive = profile.isInteractive(input)
  const lines: string[] = [
    profile.buildUserTitle(input),
    '',
    '## 适配域信息',
    `- 工作区: ${normalizeWorkspaceId(input.workspaceId)}（${profile.workspaceLabel}）`,
    `- 域 ID: ${input.domainId}`,
    `- TAHP 模块: ${input.module}`,
    '',
    ...buildFormParamsSection(input),
    ...buildSkillsSection(input),
    ...buildUserNotesSection(input),
    '',
    ...profile.buildUserClosingLines(input, interactive),
  ]
  return lines.join('\n')
}
