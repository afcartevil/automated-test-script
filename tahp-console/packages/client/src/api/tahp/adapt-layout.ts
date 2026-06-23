import { tahpGet, tahpPost, tahpPut, tahpRequest } from './client'
import type { AdaptWorkspaceId } from '@/constants/adapt-domains'
import { DEFAULT_ADAPT_WORKSPACE } from '@/constants/adapt-domains'

export type AdaptFieldType = 'text' | 'select' | 'textarea'

export interface AdaptLayoutFieldDef {
  name: string
  label: string
  type: AdaptFieldType
  placeholder?: string
  required: boolean
  options?: Array<{ label: string; value: string }>
}

export interface AdaptDomainLayoutRecord {
  domain_id: string
  fields: AdaptLayoutFieldDef[]
  related_skills?: string[]
  revision: number
  updated_at: string
  source?: string
}

export interface AdaptLayoutSyncMeta {
  last_local_save?: string
  last_cloud_pull?: string
  last_cloud_push?: string
  cloud_revision?: string
  cloud_sync_enabled: boolean
}

export interface AdaptLayoutsResponse {
  workspace_id?: string
  layouts: Record<string, AdaptDomainLayoutRecord>
  sync: AdaptLayoutSyncMeta
  manifest_path: string
  domain_ids?: string[]
}

export interface AdaptDomainConfigSaveResult {
  domain_id: string
  revision: number
  updated_at: string
  cloud_pushed: boolean
  cloud_error?: string
}

function workspaceBase(workspaceId: AdaptWorkspaceId = DEFAULT_ADAPT_WORKSPACE): string {
  return `/api/tahp/adapt/workspaces/${encodeURIComponent(workspaceId)}`
}

export function fetchAdaptLayouts(workspaceId: AdaptWorkspaceId = DEFAULT_ADAPT_WORKSPACE): Promise<AdaptLayoutsResponse> {
  return tahpGet<AdaptLayoutsResponse>(`${workspaceBase(workspaceId)}/layouts`)
}

export function saveAdaptDomainConfig(
  domainId: string,
  config: { fields: AdaptLayoutFieldDef[]; related_skills: string[] },
  workspaceId: AdaptWorkspaceId = DEFAULT_ADAPT_WORKSPACE,
): Promise<AdaptDomainConfigSaveResult> {
  return tahpPut(`${workspaceBase(workspaceId)}/layouts/${encodeURIComponent(domainId)}`, config)
}

/** @deprecated 使用 saveAdaptDomainConfig */
export function saveAdaptDomainLayout(
  domainId: string,
  fields: AdaptLayoutFieldDef[],
  workspaceId: AdaptWorkspaceId = DEFAULT_ADAPT_WORKSPACE,
): Promise<AdaptDomainConfigSaveResult> {
  return tahpPut(`${workspaceBase(workspaceId)}/layouts/${encodeURIComponent(domainId)}`, { fields })
}

export function resetAdaptDomainLayout(
  domainId: string,
  workspaceId: AdaptWorkspaceId = DEFAULT_ADAPT_WORKSPACE,
): Promise<{ deleted: string }> {
  return tahpRequest(`${workspaceBase(workspaceId)}/layouts/${encodeURIComponent(domainId)}`, {
    method: 'DELETE',
  })
}

export function pullAdaptLayoutsFromCloud(workspaceId: AdaptWorkspaceId = DEFAULT_ADAPT_WORKSPACE): Promise<{
  pulled: boolean
  merged_domains: string[]
  cloud_revision?: string
  error?: string
}> {
  return tahpPost(`${workspaceBase(workspaceId)}/layouts/sync/pull`, {})
}

export function pushAdaptLayoutsToCloud(workspaceId: AdaptWorkspaceId = DEFAULT_ADAPT_WORKSPACE): Promise<{
  ok: boolean
  cloud_pushed: boolean
  cloud_error?: string
}> {
  return tahpPost(`${workspaceBase(workspaceId)}/layouts/sync/push`, {})
}
