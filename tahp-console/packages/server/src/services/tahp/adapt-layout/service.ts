import { logger } from '../../logger'
import {
  deleteLocalDomainLayout,
  getAdaptLayoutManifestPath,
  readLocalLayoutManifest,
  upsertLocalDomainLayout,
  writeLocalLayoutManifest,
} from './local-backend'
import {
  AdaptLayoutCloudError,
  fetchDomainReview,
  fetchPublishedWorkspaceLayouts,
  isAdaptLayoutCloudConfigured,
  reviewStateOrIdle,
  submitDomainLayoutToCloud,
} from './cloud-backend'
import { isLocalDirty, mergePublishedIntoLocal } from './merge'
import { validateLayoutFields, validateRelatedSkills } from './validate'
import { getLocalActor } from '../runtime-mode'
import {
  ADAPT_LAYOUT_SCHEMA_VERSION,
  ADAPT_WORKSPACE_IDS,
  DEFAULT_ADAPT_WORKSPACE,
  type AdaptDomainLayoutRecord,
  type AdaptLayoutFieldDef,
  type AdaptLayoutManifest,
  type AdaptLayoutPullResult,
  type AdaptLayoutReviewQuery,
  type AdaptLayoutSaveResult,
  type AdaptLayoutSubmitResult,
} from './types'

const PULL_TTL_MS = 20_000
const lastPullOkAt = new Map<string, number>()
const lastPullResult = new Map<string, AdaptLayoutPullResult>()
const pullInflight = new Map<string, Promise<AdaptLayoutPullResult>>()

export function invalidateLayoutPullCache(workspaceId?: string): void {
  if (workspaceId) {
    lastPullOkAt.delete(workspaceId)
    lastPullResult.delete(workspaceId)
    return
  }
  lastPullOkAt.clear()
  lastPullResult.clear()
}

function annotateLayouts(
  layouts: Record<string, AdaptDomainLayoutRecord>,
): Record<string, AdaptDomainLayoutRecord & { local_dirty: boolean }> {
  const out: Record<string, AdaptDomainLayoutRecord & { local_dirty: boolean }> = {}
  for (const [id, record] of Object.entries(layouts)) {
    out[id] = { ...record, local_dirty: isLocalDirty(record) }
  }
  return out
}

/** 启动时 / 打开页面：按模块拉取已发布布局并合并到本地 */
export async function pullPublishedAdaptLayouts(
  workspaceId?: string,
  options: { force?: boolean } = {},
): Promise<AdaptLayoutPullResult> {
  const ws = workspaceId || DEFAULT_ADAPT_WORKSPACE
  const cloudEnabled = isAdaptLayoutCloudConfigured()
  const local = await readLocalLayoutManifest(ws)
  local.sync.cloud_sync_enabled = cloudEnabled

  if (!cloudEnabled) {
    return {
      pulled: false,
      merged_domains: [],
      skipped_dirty_domains: [],
      published_revisions: {},
      error: '云端未配置',
    }
  }

  if (!options.force) {
    const prev = lastPullResult.get(ws)
    const ts = lastPullOkAt.get(ws) || 0
    if (prev && Date.now() - ts < PULL_TTL_MS) return prev
    const inflight = pullInflight.get(ws)
    if (inflight) return inflight
  }

  const job = (async (): Promise<AdaptLayoutPullResult> => {
    try {
      const remote = await fetchPublishedWorkspaceLayouts(ws)
      if (!remote) {
        return {
          pulled: false,
          merged_domains: [],
          skipped_dirty_domains: [],
          published_revisions: {},
          cloud_revision: local.sync.cloud_revision,
        }
      }
      const { merged, updatedDomains, skippedDirtyDomains } = mergePublishedIntoLocal(local, remote)
      merged.sync.cloud_sync_enabled = true
      merged.sync.last_cloud_pull = new Date().toISOString()
      const publishedRevisions: Record<string, number> = {}
      for (const [id, rec] of Object.entries(remote.layouts || {})) {
        publishedRevisions[id] = rec.revision
      }
      await writeLocalLayoutManifest(merged, ws)
      const result: AdaptLayoutPullResult = {
        pulled: true,
        merged_domains: updatedDomains,
        skipped_dirty_domains: skippedDirtyDomains,
        published_revisions: publishedRevisions,
        cloud_revision: merged.sync.cloud_revision,
      }
      lastPullOkAt.set(ws, Date.now())
      lastPullResult.set(ws, result)
      return result
    } catch (err) {
      const message = err instanceof AdaptLayoutCloudError ? err.message : (err as Error).message
      logger.warn({ err: message, workspaceId: ws }, '[adapt-layout] published pull failed')
      return {
        pulled: false,
        merged_domains: [],
        skipped_dirty_domains: [],
        published_revisions: {},
        error: message,
      }
    } finally {
      pullInflight.delete(ws)
    }
  })()

  pullInflight.set(ws, job)
  return job
}

/** @deprecated 使用 pullPublishedAdaptLayouts */
export async function pullAndMergeAdaptLayouts(workspaceId?: string): Promise<AdaptLayoutPullResult> {
  return pullPublishedAdaptLayouts(workspaceId)
}

export async function pullAllWorkspaceLayouts(): Promise<void> {
  await Promise.all(ADAPT_WORKSPACE_IDS.map(async (ws) => {
    try {
      const result = await pullPublishedAdaptLayouts(ws)
      if (result.pulled) {
        logger.info(
          { workspaceId: ws, updated: result.merged_domains, skipped: result.skipped_dirty_domains },
          '[adapt-layout] published pull',
        )
      } else if (result.error && result.error !== '云端未配置') {
        logger.warn({ workspaceId: ws, error: result.error }, '[adapt-layout] published pull skipped')
      }
    } catch (err) {
      logger.warn({ err, workspaceId: ws }, '[adapt-layout] published pull failed')
    }
  }))
}

export async function listAdaptDomainLayouts(workspaceId?: string): Promise<{
  workspace_id: string
  layouts: Record<string, AdaptDomainLayoutRecord & { local_dirty: boolean }>
  sync: AdaptLayoutManifest['sync']
  manifest_path: string
  domain_ids: string[]
}> {
  const ws = workspaceId || DEFAULT_ADAPT_WORKSPACE
  await pullPublishedAdaptLayouts(ws).catch(() => undefined)
  const manifest = await readLocalLayoutManifest(ws)
  manifest.sync.cloud_sync_enabled = isAdaptLayoutCloudConfigured()
  return {
    workspace_id: ws,
    layouts: annotateLayouts(manifest.layouts),
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
    published_revision: existing?.published_revision,
    published_fingerprint: existing?.published_fingerprint,
    review: existing?.review,
  }

  const cloudEnabled = isAdaptLayoutCloudConfigured()
  await upsertLocalDomainLayout(record, cloudEnabled, workspaceId)
  invalidateLayoutPullCache(workspaceId || DEFAULT_ADAPT_WORKSPACE)

  return {
    domain_id: domainId,
    revision: record.revision,
    updated_at: now,
    cloud_pushed: false,
    local_dirty: isLocalDirty(record),
  }
}

export async function resetAdaptDomainLayout(domainId: string, workspaceId?: string): Promise<void> {
  await deleteLocalDomainLayout(domainId, workspaceId)
  invalidateLayoutPullCache(workspaceId || DEFAULT_ADAPT_WORKSPACE)
}

export async function submitAdaptDomainLayout(
  domainId: string,
  workspaceId?: string,
  comment?: string,
): Promise<AdaptLayoutSubmitResult> {
  const ws = workspaceId || DEFAULT_ADAPT_WORKSPACE
  const existing = await getAdaptDomainLayout(domainId, ws)
  if (!existing?.fields?.length) {
    throw new Error('请先保存该模块布局再提交审核')
  }
  if (!isLocalDirty(existing) && existing.review?.status !== 'rejected') {
    throw new Error('没有待提交的本地改动')
  }
  if (existing.review?.status === 'pending_review') {
    const who = existing.review.submitted_by ? `（${existing.review.submitted_by}）` : ''
    const err = new AdaptLayoutCloudError(
      `该模块已有审核中的布局${who}`,
      409,
      'REVIEW_IN_PROGRESS',
      {
        code: 'REVIEW_IN_PROGRESS',
        workspace_id: ws,
        domain_id: domainId,
        submit_id: existing.review.submit_id,
        submitted_by: existing.review.submitted_by,
        submitted_at: existing.review.submitted_at,
      },
    )
    throw err
  }

  if (!existing.related_skills?.length) {
    throw new Error('至少保留一个关联 Skill')
  }
  const relatedSkills = existing.related_skills

  const submitted = await submitDomainLayoutToCloud({
    workspaceId: ws,
    domainId,
    schemaVersion: existing.schema_version ?? ADAPT_LAYOUT_SCHEMA_VERSION,
    baseRevision: existing.published_revision ?? 0,
    fields: existing.fields,
    relatedSkills,
    comment,
  })

  existing.review = {
    status: 'pending_review',
    submit_id: submitted.submit_id,
    submitted_by: submitted.submitted_by || getLocalActor(),
    submitted_at: submitted.submitted_at,
    comment: comment || null,
  }
  existing.source = 'user'
  await upsertLocalDomainLayout(existing, true, ws)
  invalidateLayoutPullCache(ws)
  return submitted
}

export async function getAdaptDomainLayoutReview(
  domainId: string,
  workspaceId?: string,
): Promise<AdaptLayoutReviewQuery> {
  const ws = workspaceId || DEFAULT_ADAPT_WORKSPACE
  const local = await getAdaptDomainLayout(domainId, ws)
  let review = reviewStateOrIdle(local?.review)

  if (isAdaptLayoutCloudConfigured()) {
    try {
      const remote = await fetchDomainReview(ws, domainId)
      if (remote?.review) {
        review = reviewStateOrIdle(remote.review)
        if (remote.review.status === 'approved' || remote.review.status === 'rejected') {
          const needPull = remote.review.status === 'approved'
            && (
              local?.review?.status === 'pending_review'
              || (local?.published_revision ?? 0) !== (remote.published_revision ?? 0)
            )
          if (needPull) {
            await pullPublishedAdaptLayouts(ws, { force: true })
            const refreshed = await getAdaptDomainLayout(domainId, ws)
            return {
              workspace_id: ws,
              domain_id: domainId,
              published_revision: refreshed?.published_revision ?? remote.published_revision ?? 0,
              local_dirty: isLocalDirty(refreshed),
              review: reviewStateOrIdle(refreshed?.review ?? review),
            }
          }
        }
        if (local) {
          local.review = review
          if (typeof remote.published_revision === 'number') {
            local.published_revision = remote.published_revision
          }
          await upsertLocalDomainLayout(local, true, ws)
        }
        return {
          workspace_id: ws,
          domain_id: domainId,
          published_revision: remote.published_revision ?? local?.published_revision ?? 0,
          local_dirty: isLocalDirty(local),
          review,
        }
      }
    } catch (err) {
      logger.warn({ err, workspaceId: ws, domainId }, '[adapt-layout] review query failed')
    }
  }

  return {
    workspace_id: ws,
    domain_id: domainId,
    published_revision: local?.published_revision ?? 0,
    local_dirty: isLocalDirty(local),
    review,
  }
}

/** 整包推送已废弃，改为按模块提交审核 */
export async function forcePushAdaptLayouts(workspaceId?: string): Promise<AdaptLayoutSaveResult & { ok: boolean }> {
  void workspaceId
  return {
    ok: false,
    domain_id: '*',
    revision: 0,
    updated_at: new Date().toISOString(),
    cloud_pushed: false,
    cloud_error: '整包推送已废弃，请对该模块使用「提交审核」',
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

  return rows
}
