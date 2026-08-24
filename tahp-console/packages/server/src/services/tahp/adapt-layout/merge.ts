import type {
  AdaptDomainLayoutRecord,
  AdaptLayoutManifest,
  AdaptLayoutReviewState,
  AdaptPublishedDomainLayout,
  AdaptPublishedWorkspaceLayouts,
} from './types'
import { ADAPT_LAYOUT_SCHEMA_VERSION } from './types'

export function fingerprintLayout(
  fields: unknown,
  relatedSkills: unknown,
): string {
  return JSON.stringify({
    fields: fields ?? [],
    related_skills: Array.isArray(relatedSkills) ? relatedSkills : [],
  })
}

export function isLocalDirty(record: AdaptDomainLayoutRecord | null | undefined): boolean {
  if (!record) return false
  const fp = fingerprintLayout(record.fields, record.related_skills)
  if (!record.published_fingerprint) {
    return record.source === 'user'
  }
  return fp !== record.published_fingerprint
}

function idleReview(): AdaptLayoutReviewState {
  return { status: 'idle' }
}

export function publishedToLocalRecord(
  remote: AdaptPublishedDomainLayout,
  review?: AdaptLayoutReviewState,
): AdaptDomainLayoutRecord {
  const related = Array.isArray(remote.related_skills) ? remote.related_skills : []
  const fp = fingerprintLayout(remote.fields, related)
  return {
    schema_version: remote.schema_version ?? ADAPT_LAYOUT_SCHEMA_VERSION,
    domain_id: remote.domain_id,
    fields: remote.fields,
    related_skills: related,
    revision: remote.revision,
    updated_at: remote.updated_at,
    source: 'cloud',
    published_revision: remote.revision,
    published_fingerprint: fp,
    review: review ?? idleReview(),
  }
}

/**
 * 按模块合并已发布布局到本机 manifest。
 * 本机有未提交改动且内容与远端不同 → 跳过该模块（仍可刷新 review 元数据）。
 */
export function mergePublishedIntoLocal(
  local: AdaptLayoutManifest,
  remote: AdaptPublishedWorkspaceLayouts,
): {
  merged: AdaptLayoutManifest
  updatedDomains: string[]
  skippedDirtyDomains: string[]
} {
  const merged: AdaptLayoutManifest = {
    schema_version: ADAPT_LAYOUT_SCHEMA_VERSION,
    layouts: { ...local.layouts },
    sync: { ...local.sync },
  }
  const updatedDomains: string[] = []
  const skippedDirtyDomains: string[] = []
  const remoteLayouts = remote.layouts || {}
  const remoteReviews = remote.reviews || {}

  for (const [domainId, remoteRecord] of Object.entries(remoteLayouts)) {
    if (!remoteRecord?.fields?.length) continue
    const localRecord = merged.layouts[domainId]
    const review = remoteReviews[domainId]
    const remoteFp = fingerprintLayout(remoteRecord.fields, remoteRecord.related_skills)

    if (!localRecord) {
      merged.layouts[domainId] = publishedToLocalRecord(remoteRecord, review)
      updatedDomains.push(domainId)
      continue
    }

    const localFp = fingerprintLayout(localRecord.fields, localRecord.related_skills)
    const dirty = isLocalDirty(localRecord)

    if (dirty && localFp !== remoteFp) {
      skippedDirtyDomains.push(domainId)
      if (review) {
        merged.layouts[domainId] = { ...localRecord, review }
      }
      continue
    }

    merged.layouts[domainId] = publishedToLocalRecord(remoteRecord, review ?? localRecord.review)
    updatedDomains.push(domainId)
  }

  for (const [domainId, review] of Object.entries(remoteReviews)) {
    if (remoteLayouts[domainId]) continue
    const localRecord = merged.layouts[domainId]
    if (!localRecord) continue
    merged.layouts[domainId] = { ...localRecord, review }
  }

  return { merged, updatedDomains, skippedDirtyDomains }
}
