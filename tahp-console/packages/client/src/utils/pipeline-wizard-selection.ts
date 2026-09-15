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

export function workflowStageEnabled(
  nodes: Array<{ key: string; enabled?: boolean }>,
  key: string,
): boolean {
  return nodes.some(node => node.key === key && node.enabled !== false)
}

export interface WizardStep3Sections {
  build: boolean
  flash: boolean
  selfcheck: boolean
  gerrit: boolean
}

export function resolveWizardStep3Sections(
  nodes: Array<{ key: string; enabled?: boolean }>,
): WizardStep3Sections {
  return {
    build: workflowStageEnabled(nodes, 'build'),
    flash: workflowStageEnabled(nodes, 'flash'),
    selfcheck: workflowStageEnabled(nodes, 'selfcheck'),
    gerrit: workflowStageEnabled(nodes, 'gerrit'),
  }
}

export interface WizardStep3Values {
  systemRoot: string
  variant: string
  buildFlag: string
  buildTargets: string[]
  needPack: boolean
  flashPkgPath: string
  flashVersionFromBuild: boolean
  deviceId: string | null | undefined
  gerritIssueId: string
}

/** 仅校验当前编排下会展示的必填项。 */
export function canProceedWizardStep3(
  sections: WizardStep3Sections,
  values: WizardStep3Values,
): boolean {
  if (sections.build) {
    if (!values.systemRoot.trim()) return false
    if (!values.variant.trim()) return false
    if (!values.buildFlag.trim()) return false
    if (!values.buildTargets.length && !values.needPack) return false
  }
  if (sections.flash && !values.flashVersionFromBuild && !values.flashPkgPath.trim()) return false
  if ((sections.flash || sections.selfcheck) && !String(values.deviceId ?? '').trim()) return false
  if (sections.gerrit && !values.gerritIssueId.trim()) return false
  return true
}
