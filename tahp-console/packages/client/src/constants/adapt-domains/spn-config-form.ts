/** SPN 配置域：工程内主控 Skill 目录 `skills/.claude/skills/spn-workflow-2-2-0` */

export const SPN_PRIMARY_SKILL_ID = 'spn-workflow-2-2-0'

export function isSpnWorkflowSkillId(id: string): boolean {
  const s = (id || '').trim()
  return s === SPN_PRIMARY_SKILL_ID || s === 'spn-workflow' || s.startsWith('spn-workflow-')
}

export function normalizeSpnRelatedSkills(skills: string[]): string[] {
  const mapped = skills.filter(Boolean).map((s) => (s === 'spn-workflow' ? SPN_PRIMARY_SKILL_ID : s))
  if (!mapped.some(isSpnWorkflowSkillId)) mapped.unshift(SPN_PRIMARY_SKILL_ID)
  return [...new Set(mapped)]
}