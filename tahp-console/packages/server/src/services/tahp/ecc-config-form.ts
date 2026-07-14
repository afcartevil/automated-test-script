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

export const INTERACTIVE_CARRIER_DOMAIN_IDS = new Set(['carrierconfig-tools', 'ecc-config'])

export function isInteractiveCarrierDomain(domainId: string, interactionMode?: boolean): boolean {
  return interactionMode === true || INTERACTIVE_CARRIER_DOMAIN_IDS.has(domainId)
}
