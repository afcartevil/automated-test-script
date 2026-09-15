/** 新建向导进入「选择工作区与适配模块」时，任何模块都不默认勾选。克隆由 overlay 覆盖。 */
export const WIZARD_DOMAIN_DEFAULT_ENABLED = false

export function syncWizardDomainEnabledWithWorkspaces<T extends { workspace_id: string; enabled: boolean }>(
  domains: T[],
  selectedWorkspaces: readonly string[],
): void {
  const selected = new Set(selectedWorkspaces)
  for (const domain of domains) {
    if (!selected.has(domain.workspace_id)) {
      domain.enabled = false
    }
  }
}
