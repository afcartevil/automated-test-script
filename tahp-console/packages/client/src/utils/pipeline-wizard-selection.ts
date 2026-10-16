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
  oemUnlockConfirmed: boolean
  oemAutoUnlock: boolean
  oemProbeStatus: 'idle' | 'loading' | 'error' | 'ready'
  oemGate: 'unlocked' | 'block_user' | 'offer_auto_unlock' | 'unknown' | null
  gerritIssueId: string
}

/** 当前编排下会展示、但仍未满足的必填项。 */
export function listWizardStep3Blockers(
  sections: WizardStep3Sections,
  values: WizardStep3Values,
): string[] {
  const blockers: string[] = []
  if (sections.build) {
    if (!values.systemRoot.trim()) blockers.push('请填写系统源码路径')
    if (!values.variant.trim()) blockers.push('请选择 variant')
    if (!values.buildFlag.trim()) blockers.push('请选择 build_flag')
    if (!values.buildTargets.length && !values.needPack) blockers.push('请选择编译 target 或开启打包')
  }
  if (sections.flash && !values.flashVersionFromBuild && !values.flashPkgPath.trim()) {
    blockers.push('请填写烧录版本路径')
  }
  if ((sections.flash || sections.selfcheck) && !String(values.deviceId ?? '').trim()) {
    blockers.push('请选择目标设备')
  }
  if (sections.flash && String(values.deviceId ?? '').trim()) {
    if (values.oemProbeStatus === 'idle' || values.oemProbeStatus === 'loading') {
      blockers.push('正在检测设备 OEM 解锁状态')
    } else if (values.oemProbeStatus === 'error') {
      blockers.push('无法读取设备 OEM 状态，请重新检测')
    } else if (values.oemGate === 'block_user') {
      blockers.push('样机为 user 且 OEM lock，无法刷写，请先解锁')
    } else if (values.oemGate === 'offer_auto_unlock' && !values.oemAutoUnlock) {
      blockers.push('样机 OEM lock，请自行解锁或勾选工具自动解锁')
    } else if (values.oemGate === 'unknown' && !values.oemUnlockConfirmed) {
      blockers.push('请勾选确认设备已 OEM 解锁')
    }
  }
  if (sections.gerrit && !values.gerritIssueId.trim()) {
    blockers.push('请填写 Gerrit 提交 ID')
  }
  return blockers
}

export function canProceedWizardStep3(
  sections: WizardStep3Sections,
  values: WizardStep3Values,
): boolean {
  return listWizardStep3Blockers(sections, values).length === 0
}
