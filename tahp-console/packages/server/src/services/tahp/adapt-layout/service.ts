import { logger } from '../../logger'
import {
  deleteLocalDomainLayout,
  getAdaptLayoutManifestPath,
  readLocalLayoutManifest,
  upsertLocalDomainLayout,
  writeLocalLayoutManifest,
} from './local-backend'
import {
  fetchCloudLayoutManifest,
  isAdaptLayoutCloudConfigured,
  pushCloudLayoutManifest,
} from './cloud-backend'
import { validateLayoutFields, validateRelatedSkills } from './validate'
import {
  ADAPT_LAYOUT_SCHEMA_VERSION,
  DEFAULT_ADAPT_WORKSPACE,
  type AdaptDomainLayoutRecord,
  type AdaptLayoutFieldDef,
  type AdaptLayoutManifest,
  type AdaptLayoutPullResult,
  type AdaptLayoutSaveResult,
} from './types'

function mergeManifests(
  local: AdaptLayoutManifest,
  remote: AdaptLayoutManifest,
): { merged: AdaptLayoutManifest; updatedDomains: string[] } {
  const merged: AdaptLayoutManifest = {
    schema_version: ADAPT_LAYOUT_SCHEMA_VERSION,
    layouts: { ...local.layouts },
    sync: {
      ...local.sync,
      cloud_sync_enabled: isAdaptLayoutCloudConfigured(),
      last_cloud_pull: new Date().toISOString(),
      cloud_revision: remote.sync?.cloud_revision,
    },
  }
  const updatedDomains: string[] = []

  for (const [domainId, remoteRecord] of Object.entries(remote.layouts || {})) {
    const localRecord = local.layouts[domainId]
    const remoteRev = remoteRecord?.revision ?? 0
    const localRev = localRecord?.revision ?? 0
    const remoteTime = Date.parse(remoteRecord?.updated_at || '') || 0
    const localTime = Date.parse(localRecord?.updated_at || '') || 0

    if (!localRecord || remoteRev > localRev || (remoteRev === localRev && remoteTime >= localTime)) {
      merged.layouts[domainId] = {
        ...remoteRecord,
        related_skills: Array.isArray(remoteRecord.related_skills) ? remoteRecord.related_skills : [],
        source: 'cloud',
      }
      updatedDomains.push(domainId)
    }
  }

  return { merged, updatedDomains }
}

async function tryPushCloud(
  manifest: AdaptLayoutManifest,
  workspaceId?: string,
): Promise<{
  pushed: boolean
  cloud_revision?: string
  error?: string
}> {
  if (!isAdaptLayoutCloudConfigured()) return { pushed: false }
  if (workspaceId && workspaceId !== DEFAULT_ADAPT_WORKSPACE) return { pushed: false }
  try {
    const { cloud_revision } = await pushCloudLayoutManifest(manifest)
    manifest.sync.last_cloud_push = new Date().toISOString()
    manifest.sync.cloud_revision = cloud_revision
    await writeLocalLayoutManifest(manifest, workspaceId)
    return { pushed: true, cloud_revision }
  } catch (err) {
    const msg = (err as Error).message
    logger.warn({ err: msg, workspaceId }, '[adapt-layout] cloud push failed')
    return { pushed: false, error: msg }
  }
}

/** 启动时拉取：云端优先合并到本地（revision 高者胜） */
export async function pullAndMergeAdaptLayouts(workspaceId?: string): Promise<AdaptLayoutPullResult> {
  const ws = workspaceId || DEFAULT_ADAPT_WORKSPACE
  const cloudEnabled = isAdaptLayoutCloudConfigured()
  const local = await readLocalLayoutManifest(ws)
  local.sync.cloud_sync_enabled = cloudEnabled

  if (!cloudEnabled || ws !== DEFAULT_ADAPT_WORKSPACE) {
    return { pulled: false, merged_domains: [], error: ws !== DEFAULT_ADAPT_WORKSPACE ? '非默认工作区跳过云端' : '云端未配置' }
  }

  try {
    const remote = await fetchCloudLayoutManifest()
    if (!remote) {
      return { pulled: false, merged_domains: [], cloud_revision: local.sync.cloud_revision }
    }
    const { merged, updatedDomains } = mergeManifests(local, remote)
    await writeLocalLayoutManifest(merged, ws)
    return {
      pulled: true,
      merged_domains: updatedDomains,
      cloud_revision: merged.sync.cloud_revision,
    }
  } catch (err) {
    return { pulled: false, merged_domains: [], error: (err as Error).message }
  }
}

export async function listAdaptDomainLayouts(workspaceId?: string): Promise<{
  workspace_id: string
  layouts: Record<string, AdaptDomainLayoutRecord>
  sync: AdaptLayoutManifest['sync']
  manifest_path: string
  domain_ids: string[]
}> {
  const ws = workspaceId || DEFAULT_ADAPT_WORKSPACE
  await pullAndMergeAdaptLayouts(ws).catch(() => undefined)
  const manifest = await readLocalLayoutManifest(ws)
  return {
    workspace_id: ws,
    layouts: manifest.layouts,
    sync: manifest.sync,
    manifest_path: getAdaptLayoutManifestPath(ws),
    domain_ids: Object.keys(manifest.layouts),
  }
}

/** @deprecated 使用 saveAdaptDomainConfig */
export async function saveAdaptDomainLayout(
  domainId: string,
  fieldsInput: unknown,
  workspaceId?: string,
): Promise<AdaptLayoutSaveResult> {
  return saveAdaptDomainConfig(domainId, { fields: fieldsInput }, workspaceId)
}

export async function getAdaptDomainLayout(
  domainId: string,
  workspaceId?: string,
): Promise<AdaptDomainLayoutRecord | null> {
  const manifest = await readLocalLayoutManifest(workspaceId)
  return manifest.layouts[domainId] ?? null
}

export async function saveAdaptDomainConfig(
  domainId: string,
  config: { fields?: unknown; related_skills?: unknown },
  workspaceId?: string,
): Promise<AdaptLayoutSaveResult> {
  const existing = await getAdaptDomainLayout(domainId, workspaceId)
  const fields = config.fields !== undefined
    ? validateLayoutFields(config.fields)
    : (existing?.fields?.length ? existing.fields : [])
  if (!fields.length) throw new Error('fields 不能为空')

  let relatedSkills: string[] | undefined
  if (config.related_skills !== undefined) {
    relatedSkills = validateRelatedSkills(config.related_skills)
  } else if (existing?.related_skills?.length) {
    relatedSkills = existing.related_skills
  }

  const now = new Date().toISOString()
  const record: AdaptDomainLayoutRecord = {
    schema_version: ADAPT_LAYOUT_SCHEMA_VERSION,
    domain_id: domainId,
    fields,
    ...(relatedSkills ? { related_skills: relatedSkills } : {}),
    revision: (existing?.revision ?? 0) + 1,
    updated_at: now,
    source: 'user',
  }

  const cloudEnabled = isAdaptLayoutCloudConfigured()
  const manifest = await upsertLocalDomainLayout(record, cloudEnabled, workspaceId)
  const push = await tryPushCloud(manifest, workspaceId)

  return {
    domain_id: domainId,
    revision: record.revision,
    updated_at: now,
    cloud_pushed: push.pushed,
    cloud_error: push.error,
  }
}

export async function resetAdaptDomainLayout(domainId: string, workspaceId?: string): Promise<void> {
  const manifest = await deleteLocalDomainLayout(domainId, workspaceId)
  manifest.sync.cloud_sync_enabled = isAdaptLayoutCloudConfigured()
  await tryPushCloud(manifest, workspaceId)
}

export async function forcePushAdaptLayouts(workspaceId?: string): Promise<AdaptLayoutSaveResult & { ok: boolean }> {
  const manifest = await readLocalLayoutManifest(workspaceId)
  manifest.sync.cloud_sync_enabled = isAdaptLayoutCloudConfigured()
  const push = await tryPushCloud(manifest, workspaceId)
  return {
    ok: push.pushed,
    domain_id: '*',
    revision: 0,
    updated_at: new Date().toISOString(),
    cloud_pushed: push.pushed,
    cloud_error: push.error,
  }
}

export function resolveFormFieldLabels(
  formData: Record<string, string>,
  formFields?: AdaptLayoutFieldDef[] | Array<{ name: string; label: string }>,
): Array<{ name: string; label: string; value: string }> {
  const labelMap = new Map<string, string>()
  if (formFields?.length) {
    for (const f of formFields) labelMap.set(f.name, f.label)
  }
  const order = formFields?.map(f => f.name) ?? Object.keys(formData)
  const seen = new Set<string>()
  const rows: Array<{ name: string; label: string; value: string }> = []

  for (const name of order) {
    if (seen.has(name)) continue
    seen.add(name)
    const value = String(formData[name] ?? '').trim()
    if (!value) continue
    rows.push({ name, label: labelMap.get(name) || name, value })
  }

  for (const [name, value] of Object.entries(formData)) {
    if (seen.has(name)) continue
    const v = String(value ?? '').trim()
    if (!v) continue
    rows.push({ name, label: labelMap.get(name) || name, value: v })
  }

  return rows
}
