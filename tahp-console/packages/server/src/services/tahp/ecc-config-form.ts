/** ECC 配置域：三平台代码仓路径至少填一项（服务端校验与提示词共用） */
export const ECC_REPO_PATH_FIELDS = [
  'repo_path_mtk',
  'repo_path_unisoc',
  'repo_path_qualcomm',
] as const

export const ECC_ENTRY_FIELD_NAMES = [
  'number',
  'with_sim',
  'without_sim',
  'display_name',
  'block',
  'user_notes',
] as const

export function hasEccRepoPath(formData: Record<string, unknown>): boolean {
  return ECC_REPO_PATH_FIELDS.some((k) => String(formData[k] ?? '').trim().length > 0)
}

export function validateEccConfigForm(formData: Record<string, unknown>): string | null {
  if (!hasEccRepoPath(formData)) {
    return '请至少填写 MTK / 展锐 / 高通 其中一个代码仓路径'
  }
  return null
}

/** CarrierConfig / SPN 为人机协同域；ECC / APN 为无人值守 */
export const INTERACTIVE_CARRIER_DOMAIN_IDS = new Set(['carrierconfig-tools', 'spn-config'])

export function isInteractiveCarrierDomain(domainId: string, interactionMode?: boolean): boolean {
  return interactionMode === true || INTERACTIVE_CARRIER_DOMAIN_IDS.has(domainId)
}

/** ECC 配置：危险命令立即自动同意，不弹窗 */
export function shouldAutoApproveAdaptCommands(domainId: string): boolean {
  return domainId === 'ecc-config'
}

/**
 * ECC 默认关联：去掉 jira-ops，保证 ecc-config + gerrit-submit。
 * 用于覆盖历史 layout 中仍带 jira-ops 的配置。
 */
export function normalizeEccRelatedSkills(skills: string[]): string[] {
  const out = skills.filter((s) => s && s !== 'jira-ops')
  if (!out.includes('ecc-config')) out.unshift('ecc-config')
  if (!out.includes('gerrit-submit')) out.push('gerrit-submit')
  return out
}

export const SPN_PRIMARY_SKILL_ID = 'spn-workflow-2-2-0'

export function isSpnWorkflowSkillId(id: string): boolean {
  const s = String(id || '').trim()
  return s === SPN_PRIMARY_SKILL_ID || s === 'spn-workflow' || s.startsWith('spn-workflow-')
}

export function normalizeSpnRelatedSkills(skills: string[]): string[] {
  const mapped = skills.filter(Boolean).map((s) => (s === 'spn-workflow' ? SPN_PRIMARY_SKILL_ID : s))
  if (!mapped.some(isSpnWorkflowSkillId)) mapped.unshift(SPN_PRIMARY_SKILL_ID)
  return [...new Set(mapped)]
}

export function validateSpnConfigForm(formData: Record<string, unknown>): string | null {
  if (!String(formData.jira_key ?? '').trim()) return '请填写 Jira 单号或链接'
  if (!String(formData.log_path ?? '').trim()) return '请填写日志文件、目录或压缩包路径'
  return null
}
