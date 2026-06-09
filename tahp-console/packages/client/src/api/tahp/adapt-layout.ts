import { tahpGet, tahpPost, tahpPut, tahpRequest } from './client'

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

export function fetchAdaptLayouts(): Promise<AdaptLayoutsResponse> {
  return tahpGet<AdaptLayoutsResponse>('/api/tahp/adapt/layouts')
}

export function saveAdaptDomainConfig(
  domainId: string,
  config: { fields: AdaptLayoutFieldDef[]; related_skills: string[] },
): Promise<AdaptDomainConfigSaveResult> {
  return tahpPut(`/api/tahp/adapt/layouts/${encodeURIComponent(domainId)}`, config)
}

/** @deprecated 使用 saveAdaptDomainConfig */
export function saveAdaptDomainLayout(
  domainId: string,
  fields: AdaptLayoutFieldDef[],
): Promise<AdaptDomainConfigSaveResult> {
  return tahpPut(`/api/tahp/adapt/layouts/${encodeURIComponent(domainId)}`, { fields })
}

export function resetAdaptDomainLayout(domainId: string): Promise<{ deleted: string }> {
  return tahpRequest(`/api/tahp/adapt/layouts/${encodeURIComponent(domainId)}`, {
    method: 'DELETE',
  })
}

export function pullAdaptLayoutsFromCloud(): Promise<{
  pulled: boolean
  merged_domains: string[]
  cloud_revision?: string
  error?: string
}> {
  return tahpPost('/api/tahp/adapt/layouts/sync/pull', {})
}

export function pushAdaptLayoutsToCloud(): Promise<{
  ok: boolean
  cloud_pushed: boolean
  cloud_error?: string
}> {
  return tahpPost('/api/tahp/adapt/layouts/sync/push', {})
}
