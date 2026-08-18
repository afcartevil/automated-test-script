import { ADAPT_DEBUG_DOMAINS } from './adapt-debug-domains'
import { CARRIER_ADAPT_DOMAINS } from './carrier-config-domains'
import { FEATURE_ADAPT_DOMAINS } from './feature-adapt-domains'
import type { AdaptDomainDef, AdaptWorkspaceDef, AdaptWorkspaceId } from './types'
import { ADAPT_WORKSPACE_IDS, DEFAULT_ADAPT_WORKSPACE, isAdaptWorkspaceId } from './types'

export * from './types'
export { ADAPT_DEBUG_DOMAINS } from './adapt-debug-domains'
export { FEATURE_ADAPT_DOMAINS } from './feature-adapt-domains'
export { CARRIER_ADAPT_DOMAINS } from './carrier-config-domains'
/** @deprecated 使用 ADAPT_DEBUG_DOMAINS */
export { FULL_ADAPT_DOMAINS } from './full-domains'

export const ADAPT_WORKSPACES: AdaptWorkspaceDef[] = [
  {
    id: 'adapt-debug',
    label: '功能适配',
    subtitle: '将源版本的功能改动适配到目标版本',
    allowDynamicDomains: true,
  },
  {
    id: 'feature-adapt',
    label: '特性适配',
    subtitle: '覆盖 TP、LCM、音频、充电、Sensor、内存、调度等特性适配模块',
    allowDynamicDomains: true,
  },
  {
    id: 'carrier-config',
    label: '运营商配置',
    subtitle: '运营商相关配置适配，包含 CarrierConfig、ECC、APN 与 SPN',
    allowDynamicDomains: false,
  },
]

export function getAdaptWorkspace(id: AdaptWorkspaceId): AdaptWorkspaceDef {
  return ADAPT_WORKSPACES.find(w => w.id === id) ?? ADAPT_WORKSPACES[0]
}

export function getBuiltinDomainsForWorkspace(workspaceId: AdaptWorkspaceId): AdaptDomainDef[] {
  if (workspaceId === 'carrier-config') return CARRIER_ADAPT_DOMAINS
  if (workspaceId === 'feature-adapt') return FEATURE_ADAPT_DOMAINS
  return ADAPT_DEBUG_DOMAINS
}

export function cloneAdaptDomains(domains: AdaptDomainDef[]): AdaptDomainDef[] {
  return JSON.parse(JSON.stringify(domains)) as AdaptDomainDef[]
}

export function defaultActiveDomainId(workspaceId: AdaptWorkspaceId): string {
  const domains = getBuiltinDomainsForWorkspace(workspaceId)
  return domains[0]?.id ?? 'tp'
}

export {
  ADAPT_WORKSPACE_IDS,
  DEFAULT_ADAPT_WORKSPACE,
  isAdaptWorkspaceId,
}
