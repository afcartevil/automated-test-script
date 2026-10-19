<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import {
  triggerSync,
  reinjectSkills,
  publishSkillPackage,
  publishSkillPackages,
  fetchSkillPackageHistory,
  deleteLocalSkill,
  requestSkillDelete,
  type SkillSyncStatusItem,
  type SkillUpdateRecord,
  type SkillSyncResult,
} from '@/api/hermes/skills'
import { useSkillSyncStore } from '@/stores/hermes/skill-sync'

const { t, locale } = useI18n()
const message = useMessage()
const syncStore = useSkillSyncStore()
const { status, loading, refreshing, selectedGroupId } = storeToRefs(syncStore)

const syncing = ref(false)
const reinjecting = ref(false)
const lastResult = ref<{
  skills: number
  reinjected: number
  reinjectError?: string
  requirementsChanged: string[]
  skippedDirty: string[]
  failed: Array<{ id: string; error: string }>
} | null>(null)
/** 进行中的单条操作按 id 集合跟踪：仅当前行置灰，其它行可继续点 */
const publishingIds = ref<Set<string>>(new Set())
const publishingBatch = ref(false)
const overwritingIds = ref<Set<string>>(new Set())
const updatingIds = ref<Set<string>>(new Set())
const deletingIds = ref<Set<string>>(new Set())
const requestingDeleteIds = ref<Set<string>>(new Set())

function busyAdd(set: { value: Set<string> }, id: string): boolean {
  if (set.value.has(id)) return false
  const next = new Set(set.value)
  next.add(id)
  set.value = next
  return true
}

function busyRemove(set: { value: Set<string> }, id: string) {
  if (!set.value.has(id)) return
  const next = new Set(set.value)
  next.delete(id)
  set.value = next
}
const historySkillId = ref<string | null>(null)
const historyLoading = ref(false)
const historyRecords = ref<SkillUpdateRecord[]>([])
const historyCurrentVersion = ref<number | null>(null)
const historyFilter = ref<'all' | 'passed' | 'waiting' | 'returned'>('all')
const historyOpenId = ref<string | null>(null)
const historyFilters = [
  ['all', 'historyFilterAll'],
  ['passed', 'historyFilterPassed'],
  ['waiting', 'historyFilterWaiting'],
  ['returned', 'historyFilterReturned'],
] as const
/** 勾选待提交的 skill id */
const selectedIds = ref<Set<string>>(new Set())
/** 驳回原因弹层 */
const rejectDetail = ref<{ id: string; reason: string; submit_id?: string } | null>(null)

const connectionLabel = computed(() => {
  if (!status.value) return ''
  if (!status.value.configured) return t('skills.sync.notConfigured')
  if (!status.value.connected) return t('skills.sync.disconnected')
  return t('skills.sync.connected')
})

const connectionClass = computed(() => {
  if (!status.value?.configured) return 'is-warn'
  if (!status.value.connected) return 'is-err'
  return 'is-ok'
})

const activeSkills = computed<SkillSyncStatusItem[]>(() => {
  if (!status.value) return []
  if (!selectedGroupId.value) return status.value.skills
  const g = status.value.groups.find(x => x.id === selectedGroupId.value)
  if (!g) return status.value.skills
  const set = new Set(g.skill_ids)
  return status.value.skills.filter(s => set.has(s.id))
})

/** 本机有内容且未与服务器对齐时可提交（排除 synced / 待更新 / 待审 / 删除待审） */
function canPublish(s: SkillSyncStatusItem): boolean {
  if (!status.value?.connected) return false
  if (!s.local_hash) return false
  if (
    s.state === 'synced'
    || s.state === 'behind'
    || s.state === 'unknown'
    || s.state === 'submitted_pending'
    || s.state === 'delete_pending'
  ) return false
  return s.state === 'local_only' || s.state === 'ahead' || s.state === 'rejected'
}

function canUpdate(s: SkillSyncStatusItem): boolean {
  return s.state === 'behind' && !!status.value?.configured
}

function canDeleteLocal(s: SkillSyncStatusItem): boolean {
  return s.state === 'local_only' && !!s.local_hash
}

function canRequestDelete(s: SkillSyncStatusItem): boolean {
  if (!status.value?.connected) return false
  if (s.state === 'delete_pending' || s.state === 'submitted_pending' || s.state === 'local_only') return false
  // 中心有条目，或曾与中心对齐过的状态
  return !!s.central_hash
    || s.state === 'synced'
    || s.state === 'behind'
    || s.state === 'ahead'
    || (s.state === 'rejected' && !!s.central_hash)
}

const publishableSkills = computed(() => activeSkills.value.filter(canPublish))

const selectedPublishIds = computed(() => {
  const allow = new Set(publishableSkills.value.map(s => s.id))
  return [...selectedIds.value].filter(id => allow.has(id))
})

const allPublishableSelected = computed(() => {
  const list = publishableSkills.value
  if (!list.length) return false
  return list.every(s => selectedIds.value.has(s.id))
})

function stateLabel(state: string): string {
  if (state === 'synced') return t('skills.sync.stateSynced')
  if (state === 'behind') return t('skills.sync.stateBehind')
  if (state === 'ahead') return t('skills.sync.stateAhead')
  if (state === 'local_only') return t('skills.sync.stateLocalOnly')
  if (state === 'submitted_pending') return t('skills.sync.statePending')
  if (state === 'delete_pending') return t('skills.sync.stateDeletePending')
  if (state === 'rejected') return t('skills.sync.stateRejected')
  return t('skills.sync.stateUnknown')
}

function publishTitleFor(s: SkillSyncStatusItem): string {
  if (s.state === 'rejected') return t('skills.sync.publishTitleRejected')
  if (s.state === 'ahead') return t('skills.sync.publishTitleBehind')
  return t('skills.sync.publishTitle')
}

function publishLabelFor(s: SkillSyncStatusItem): string {
  return s.state === 'rejected' ? t('skills.sync.publishRetry') : t('skills.sync.publish')
}

function openRejectReason(s: SkillSyncStatusItem) {
  if (!s.reject_reason?.trim()) return
  rejectDetail.value = {
    id: s.id,
    reason: s.reject_reason.trim(),
    submit_id: s.submit_id,
  }
}

function closeRejectReason() {
  rejectDetail.value = null
}

function formatTime(iso: string | null): string {
  if (!iso) return t('skills.sync.neverSynced')
  try {
    return t('skills.sync.lastSynced', { time: new Date(iso).toLocaleString() })
  } catch {
    return t('skills.sync.lastSynced', { time: iso })
  }
}

function pruneSelection() {
  const allow = new Set(
    (status.value?.skills || []).filter(canPublish).map(s => s.id),
  )
  const next = new Set<string>()
  for (const id of selectedIds.value) {
    if (allow.has(id)) next.add(id)
  }
  selectedIds.value = next
}

function toggleSelect(id: string, checked: boolean) {
  const next = new Set(selectedIds.value)
  if (checked) next.add(id)
  else next.delete(id)
  selectedIds.value = next
}

function toggleSelectAll(checked: boolean) {
  const next = new Set(selectedIds.value)
  for (const s of publishableSkills.value) {
    if (checked) next.add(s.id)
    else next.delete(s.id)
  }
  selectedIds.value = next
}

function clearSelection() {
  selectedIds.value = new Set()
}

async function loadStatus(force = false, opts?: { afterMutation?: boolean }): Promise<boolean> {
  try {
    await syncStore.load({ force })
    pruneSelection()
    return true
  } catch (err: any) {
    if (opts?.afterMutation) {
      message.warning(t('skills.sync.refreshAfterMutationFailed'))
    } else {
      message.error(err?.message || t('skills.sync.loadFailed'))
    }
    return false
  }
}

function pullOutcome(res: SkillSyncResult) {
  return {
    skills: res.pull?.skills ?? 0,
    reinjected: res.reinjected?.length ?? 0,
    reinjectError: res.reinject_error || res.pull?.reinject_error,
    requirementsChanged: res.requirements_changed || res.pull?.requirements_changed || [],
    skippedDirty: res.pull?.skipped_dirty || [],
    failed: res.pull?.failed || [],
  }
}

function toastSyncBatch(stats: {
  skills: number
  skippedDirty: string[]
  failed: Array<{ id: string; error: string }>
  requirementsChanged: string[]
  reinjectError?: string
  bundleId?: string
}) {
  if (stats.requirementsChanged.length) {
    message.warning(t('skills.sync.requirementsHint', {
      ids: stats.requirementsChanged.join(', '),
    }))
    return
  }
  if (stats.reinjectError) {
    message.warning(t('skills.sync.reinjectWarn'))
    return
  }
  if (stats.failed.length) {
    message.warning(t('skills.sync.syncSuccessPartial', {
      n: stats.skills,
      skip: stats.skippedDirty.length,
      fail: stats.failed.length,
    }))
    return
  }
  if (stats.skippedDirty.length) {
    const ids = stats.skippedDirty.slice(0, 8).join(', ')
    message.warning(t('skills.sync.syncSuccessWithSkip', {
      n: stats.skills,
      skip: stats.skippedDirty.length,
    }))
    message.info(t('skills.sync.skipDirtyHint', { ids }))
    return
  }
  if (stats.bundleId) {
    message.success(t('skills.sync.syncBundleSuccess', { id: stats.bundleId, n: stats.skills }))
    return
  }
  message.success(t('skills.sync.syncSuccess'))
}

function rowState(skillId: string): string | undefined {
  return status.value?.skills.find(s => s.id === skillId)?.state
}

function toastSinglePull(
  skillId: string,
  res: SkillSyncResult,
  kind: 'update' | 'overwrite',
) {
  const stats = pullOutcome(res)
  const failed = stats.failed.find(f => f.id === skillId)
  if (stats.skippedDirty.includes(skillId)) {
    message.warning(t('skills.sync.forceOverwriteFailed'))
    return
  }
  if (failed) {
    if (failed.error.includes('写入后仍未与服务器对齐')) {
      message.error(t('skills.sync.updateStillBehind', { id: skillId }))
    } else {
      message.error(failed.error || t(kind === 'update' ? 'skills.sync.updateFailed' : 'skills.sync.forceOverwriteFailed'))
    }
    return
  }
  if (rowState(skillId) === 'behind') {
    message.error(t('skills.sync.updateStillBehind', { id: skillId }))
    return
  }
  message.success(
    kind === 'update'
      ? t('skills.sync.updateSuccess', { id: skillId })
      : t('skills.sync.syncSuccess'),
  )
}

async function onSyncAll() {
  if (syncing.value) return
  syncing.value = true
  lastResult.value = null
  try {
    const res = await triggerSync()
    const stats = pullOutcome(res)
    lastResult.value = {
      skills: stats.skills,
      reinjected: stats.reinjected,
      reinjectError: stats.reinjectError,
      requirementsChanged: stats.requirementsChanged,
      skippedDirty: stats.skippedDirty,
      failed: stats.failed,
    }
    const refreshed = await loadStatus(true, { afterMutation: true })
    if (!refreshed) return
    toastSyncBatch(stats)
  } catch (err: any) {
    message.error(err?.message || t('skills.sync.syncFailed'))
  } finally {
    syncing.value = false
  }
}

const selectedBundleId = computed(() => {
  const g = selectedGroupId.value
  if (!g?.startsWith('bundle:')) return null
  const id = g.slice('bundle:'.length)
  return id === '__other__' ? null : id
})

async function onSyncBundle() {
  const bid = selectedBundleId.value
  if (!bid || syncing.value) return
  syncing.value = true
  lastResult.value = null
  try {
    const res = await triggerSync(undefined, { bundle_id: bid })
    const stats = pullOutcome(res)
    lastResult.value = {
      skills: stats.skills,
      reinjected: stats.reinjected,
      reinjectError: stats.reinjectError,
      requirementsChanged: stats.requirementsChanged,
      skippedDirty: stats.skippedDirty,
      failed: stats.failed,
    }
    const refreshed = await loadStatus(true, { afterMutation: true })
    if (!refreshed) return
    toastSyncBatch({ ...stats, bundleId: bid })
  } catch (err: any) {
    message.error(err?.message || t('skills.sync.syncFailed'))
  } finally {
    syncing.value = false
  }
}

async function onForceOverwrite(skillId: string) {
  if (syncing.value || overwritingIds.value.has(skillId)) return
  if (!window.confirm(t('skills.sync.forceOverwriteConfirm', { id: skillId }))) return
  if (!busyAdd(overwritingIds, skillId)) return
  try {
    const res = await triggerSync([skillId], { force: true })
    const refreshed = await loadStatus(true, { afterMutation: true })
    if (!refreshed) return
    toastSinglePull(skillId, res, 'overwrite')
  } catch (err: any) {
    message.error(err?.message || t('skills.sync.forceOverwriteFailed'))
  } finally {
    busyRemove(overwritingIds, skillId)
  }
}

async function onUpdate(skillId: string) {
  if (syncing.value || updatingIds.value.has(skillId)) return
  if (!busyAdd(updatingIds, skillId)) return
  try {
    const res = await triggerSync([skillId])
    const refreshed = await loadStatus(true, { afterMutation: true })
    if (!refreshed) return
    toastSinglePull(skillId, res, 'update')
  } catch (err: any) {
    message.error(err?.message || t('skills.sync.updateFailed'))
  } finally {
    busyRemove(updatingIds, skillId)
  }
}

async function onDeleteLocal(skillId: string) {
  if (deletingIds.value.has(skillId)) return
  if (!window.confirm(t('skills.sync.deleteLocalConfirm', { id: skillId }))) return
  if (!busyAdd(deletingIds, skillId)) return
  try {
    await deleteLocalSkill(skillId)
    message.success(t('skills.sync.deleteLocalSuccess', { id: skillId }))
    await loadStatus(true, { afterMutation: true })
  } catch (err: any) {
    message.error(err?.message || t('skills.sync.deleteLocalFailed'))
  } finally {
    busyRemove(deletingIds, skillId)
  }
}

async function onRequestDelete(skillId: string) {
  if (requestingDeleteIds.value.has(skillId)) return
  if (!window.confirm(t('skills.sync.requestDeleteConfirm', { id: skillId }))) return
  if (!busyAdd(requestingDeleteIds, skillId)) return
  try {
    const res = await requestSkillDelete(skillId)
    message.success(t('skills.sync.requestDeleteSuccess', {
      id: skillId,
      submit: res.submit_id || '-',
    }))
    await loadStatus(true, { afterMutation: true })
  } catch (err: any) {
    message.error(err?.message || t('skills.sync.requestDeleteFailed'))
  } finally {
    busyRemove(requestingDeleteIds, skillId)
  }
}

async function onReinject() {
  if (reinjecting.value) return
  reinjecting.value = true
  try {
    const ids = status.value?.skills.filter(s => s.state === 'behind' || s.state === 'synced').map(s => s.id)
    await reinjectSkills(ids?.length ? ids : undefined)
    message.success(t('skills.sync.reinjectSuccess'))
    lastResult.value = null
  } catch (err: any) {
    message.error(err?.message || t('skills.sync.reinjectFailed'))
  } finally {
    reinjecting.value = false
  }
}

async function onPublish(skillId: string) {
  if (publishingBatch.value || publishingIds.value.has(skillId)) return
  const row = status.value?.skills.find(s => s.id === skillId)
  if (!row || !canPublish(row)) return
  if (!busyAdd(publishingIds, skillId)) return
  try {
    const res = await publishSkillPackage(skillId)
    message.success(t('skills.sync.publishPendingSuccess', {
      id: res.id,
      n: res.file_count,
      submit: res.submit_id || '-',
    }))
    await loadStatus(true, { afterMutation: true })
  } catch (err: any) {
    message.error(err?.message || t('skills.sync.publishFailed'))
  } finally {
    busyRemove(publishingIds, skillId)
  }
}

async function onPublishBatch() {
  if (publishingBatch.value || publishingIds.value.size > 0) return
  const ids = selectedPublishIds.value
  if (!ids.length) {
    message.info(
      publishableSkills.value.length
        ? t('skills.sync.publishBatchNeedSelect')
        : t('skills.sync.publishBatchEmpty'),
    )
    return
  }
  if (!window.confirm(t('skills.sync.publishBatchConfirm', { n: ids.length }))) return

  publishingBatch.value = true
  try {
    const res = await publishSkillPackages(ids)
    if (res.failed_count > 0) {
      const sample = res.failed.slice(0, 3).map(f => `${f.id}: ${f.error}`).join('；')
      message.warning(t('skills.sync.publishBatchPartial', {
        ok: res.ok_count,
        fail: res.failed_count,
        sample,
      }))
    } else {
      message.success(t('skills.sync.publishBatchSuccess', { n: res.ok_count }))
    }
    clearSelection()
    await loadStatus(true, { afterMutation: true })
  } catch (err: any) {
    message.error(err?.message || t('skills.sync.publishBatchFailed'))
  } finally {
    publishingBatch.value = false
  }
}

function historyResult(row: SkillUpdateRecord): 'passed' | 'waiting' | 'returned' | 'offline' | 'git' | 'baseline' {
  if (row.kind === 'baseline') return 'baseline'
  if (row.kind === 'git') return 'git'
  if (row.kind === 'delete' && row.status === 'approved') return 'offline'
  if (row.status === 'approved') return 'passed'
  if (row.status === 'rejected') return 'returned'
  return 'waiting'
}

function historyResultLabel(row: SkillUpdateRecord): string {
  const result = historyResult(row)
  if (result === 'passed') return t('skills.sync.historyResultPassed')
  if (result === 'waiting') return t('skills.sync.historyResultWaiting')
  if (result === 'returned') return t('skills.sync.historyResultReturned')
  if (result === 'git') return t('skills.sync.historyResultGit')
  if (result === 'baseline') return t('skills.sync.historyResultBaseline')
  return t('skills.sync.historyResultOffline')
}

const historyBaselineOnly = computed(() => (
  historyRecords.value.length > 0 && historyRecords.value.every(row => row.kind === 'baseline')
))

const historyHasReview = computed(() => (
  historyRecords.value.some(row => row.kind === 'package' || row.kind === 'delete')
))

const visibleHistory = computed(() => historyRecords.value.filter(row => {
  const result = historyResult(row)
  if (historyFilter.value === 'all') return true
  if (historyFilter.value === 'passed') return result === 'passed' || result === 'git' || result === 'baseline'
  if (historyFilter.value === 'waiting') return result === 'waiting'
  return result === 'returned'
}))

function formatHistoryStamp(iso?: string): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(locale.value || undefined, {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function historyVersionLabel(row: SkillUpdateRecord): string {
  if (row.kind === 'baseline') return t('skills.sync.historyBaselineVersion')
  if (row.kind === 'git') {
    if (row.version && row.in_use) return t('skills.sync.historyVersionInUse', { n: row.version })
    if (row.version) return t('skills.sync.historyVersion', { n: row.version })
    return row.hash || 'Git'
  }
  if (row.kind === 'delete' && row.status === 'approved') {
    return row.version
      ? t('skills.sync.historyOfflineVersion', { n: row.version })
      : t('skills.sync.historyOffline')
  }
  if (row.version && row.in_use) return t('skills.sync.historyVersionInUse', { n: row.version })
  if (row.version && row.version_bumped === false) return t('skills.sync.historyVersionSame', { n: row.version })
  if (row.version) return t('skills.sync.historyVersion', { n: row.version })
  return t('skills.sync.historyNotAVersion')
}

function historyReviewLabel(row: SkillUpdateRecord): string {
  if (row.kind === 'baseline') return t('skills.sync.historyBaselineReview')
  if (row.kind === 'git') return t('skills.sync.historyReviewGit', { name: row.submitted_by || '—' })
  if (row.status === 'pending_review') return t('skills.sync.historyReviewPending')
  const name = row.reviewed_by || '—'
  const time = formatHistoryStamp(row.reviewed_at)
  if (row.kind === 'delete' && row.status === 'approved') {
    return t('skills.sync.historyReviewOffline', { name, time })
  }
  if (row.status === 'rejected') return t('skills.sync.historyReviewReturned', { name, time })
  return t('skills.sync.historyReviewPassed', { name, time })
}

function historyNote(row: SkillUpdateRecord): string {
  if (row.kind === 'baseline') {
    return row.time_source === 'updated'
      ? t('skills.sync.historyBaselineUpdated')
      : t('skills.sync.historyBaselineCreated')
  }
  if (row.message) return row.message
  if (row.status === 'rejected' && row.comment) return row.comment
  const result = historyResult(row)
  if (result === 'offline') return t('skills.sync.historyOfflineNote')
  if (result === 'passed') return t('skills.sync.historyPassedNote')
  if (result === 'waiting') return t('skills.sync.historyWaitingNote')
  return '—'
}

function historyOpinion(row: SkillUpdateRecord): string {
  return row.comment || row.message || historyNote(row)
}

function changeActionLabel(action: SkillUpdateRecord['changes'][number]['action']): string {
  if (action === 'added') return t('skills.sync.historyChangeAdded')
  if (action === 'modified') return t('skills.sync.historyChangeModified')
  return t('skills.sync.historyChangeRemoved')
}

function toggleHistoryRow(submitId: string) {
  historyOpenId.value = historyOpenId.value === submitId ? null : submitId
}

async function onShowHistory(skillId: string) {
  if (!status.value?.configured) return
  historySkillId.value = skillId
  historyLoading.value = true
  historyRecords.value = []
  historyCurrentVersion.value = null
  historyFilter.value = 'all'
  historyOpenId.value = null
  try {
    const data = await fetchSkillPackageHistory(skillId)
    historyRecords.value = data.records || []
    historyCurrentVersion.value = data.current_version ?? null
    historyOpenId.value = historyRecords.value.find(row => row.in_use)?.submit_id
      ?? historyRecords.value[0]?.submit_id
      ?? null
  } catch (err: any) {
    message.error(err?.message || t('skills.sync.historyFailed'))
    historySkillId.value = null
  } finally {
    historyLoading.value = false
  }
}

function closeHistory() {
  historySkillId.value = null
  historyRecords.value = []
  historyCurrentVersion.value = null
  historyOpenId.value = null
  historyFilter.value = 'all'
}

onMounted(loadStatus)
</script>

<template>
  <div class="skill-sync-center">
    <div class="sync-toolbar">
      <div class="sync-status-line">
        <span class="dot" :class="connectionClass" />
        <span class="conn-text">{{ connectionLabel }}</span>
        <span v-if="status?.central_url" class="muted mono">{{ status.central_url }}</span>
        <span class="muted">{{ formatTime(status?.last_pulled_at ?? null) }}</span>
      </div>
      <div class="sync-actions">
        <button
          type="button"
          class="ea-btn-ghost ea-btn-sm"
          :disabled="loading || refreshing || publishingBatch"
          @click="loadStatus(true)"
        >
          {{ t('skills.sync.checkNow') }}
        </button>
        <button
          v-if="selectedBundleId"
          type="button"
          class="ea-btn-ghost ea-btn-sm"
          :disabled="syncing || publishingBatch || !status?.configured"
          :title="t('skills.sync.syncBundleTitle')"
          @click="onSyncBundle"
        >
          {{ syncing ? '...' : t('skills.sync.syncBundle') }}
        </button>
        <button
          type="button"
          class="ea-btn-primary ea-btn-sm"
          :disabled="syncing || publishingBatch || !status?.configured"
          @click="onSyncAll"
        >
          {{ syncing ? '...' : t('skills.sync.syncAll') }}
        </button>
        <button
          type="button"
          class="ea-btn-ghost ea-btn-sm"
          :disabled="!publishableSkills.length || publishingBatch"
          :title="t('skills.sync.selectAllUnsyncedTitle')"
          @click="toggleSelectAll(!allPublishableSelected)"
        >
          {{ allPublishableSelected ? t('skills.sync.clearSelection') : t('skills.sync.selectAllUnsynced') }}
        </button>
        <button
          type="button"
          class="ea-btn-ghost ea-btn-sm"
          :disabled="publishingBatch || publishingIds.size > 0 || !status?.configured || !status?.connected"
          :title="t('skills.sync.publishBatchTitle')"
          @click="onPublishBatch"
        >
          {{ publishingBatch ? t('skills.sync.publishBatchRunning') : t('skills.sync.publishBatch') }}
          <span v-if="!publishingBatch && selectedPublishIds.length" class="btn-cnt">{{ selectedPublishIds.length }}</span>
        </button>
        <button
          type="button"
          class="ea-btn-ghost ea-btn-sm"
          :disabled="reinjecting || publishingBatch"
          @click="onReinject"
        >
          {{ reinjecting ? '...' : t('skills.sync.applyAgent') }}
        </button>
      </div>
    </div>

    <div v-if="loading && !status" class="sync-banner info">
      {{ t('skills.sync.scanning') }}
    </div>
    <div v-else-if="refreshing" class="sync-banner info">
      {{ t('skills.sync.refreshing') }}
    </div>
    <div v-if="status && !status.configured" class="sync-banner warn">
      {{ t('skills.sync.notConfiguredHint') }}
    </div>
    <div v-else-if="status && !status.connected" class="sync-banner err">
      {{ status.error || t('skills.sync.disconnected') }}
    </div>
    <div v-else-if="status && (status.rejected_count || 0) > 0" class="sync-banner warn">
      {{ t('skills.sync.rejectedCount', { n: status.rejected_count }) }}
    </div>
    <div v-else-if="status && (status.delete_pending_count || 0) > 0" class="sync-banner warn">
      {{ t('skills.sync.deletePendingCount', { n: status.delete_pending_count }) }}
    </div>
    <div v-else-if="status && (status.pending_count || 0) > 0" class="sync-banner info">
      {{ t('skills.sync.pendingCount', { n: status.pending_count }) }}
    </div>
    <div v-else-if="status && (status.ahead_count || 0) > 0" class="sync-banner warn">
      {{ t('skills.sync.aheadCount', { n: status.ahead_count }) }}
    </div>
    <div v-else-if="status && status.behind_count > 0" class="sync-banner info">
      {{ t('skills.sync.behindCount', { n: status.behind_count }) }}
    </div>
    <div v-else-if="status && !refreshing" class="sync-banner ok">
      {{ t('skills.sync.upToDate') }}
    </div>

    <div v-if="loading && !status" class="sync-empty">{{ t('skills.sync.scanning') }}</div>
    <div v-else-if="status" class="sync-body">
      <aside class="sync-groups">
        <button
          type="button"
          class="group-item"
          :class="{ active: selectedGroupId === null }"
          @click="selectedGroupId = null"
        >
          <span>{{ t('skills.sync.allGroups') }}</span>
          <span class="cnt">{{ status.skills.length }}</span>
        </button>
        <button
          v-for="g in status.groups"
          :key="g.id"
          type="button"
          class="group-item"
          :class="{ active: selectedGroupId === g.id }"
          @click="selectedGroupId = g.id"
        >
          <span class="label">{{ g.label }}</span>
          <span v-if="g.behind_count" class="badge">{{ t('skills.sync.groupBehind', { n: g.behind_count }) }}</span>
          <span class="cnt">{{ g.skill_ids.length }}</span>
        </button>
      </aside>

      <div class="sync-table-wrap">
        <table v-if="activeSkills.length" class="sync-table">
          <thead>
            <tr>
              <th class="col-check">
                <input
                  type="checkbox"
                  :checked="allPublishableSelected"
                  :disabled="!publishableSkills.length || publishingBatch"
                  :title="t('skills.sync.selectAllUnsyncedTitle')"
                  @change="toggleSelectAll(($event.target as HTMLInputElement).checked)"
                >
              </th>
              <th>ID</th>
              <th>{{ t('skills.sync.stateSynced') }}</th>
              <th>func_type</th>
              <th>hash</th>
              <th>{{ t('skills.sync.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in activeSkills" :key="s.id">
              <td class="col-check">
                <input
                  v-if="canPublish(s)"
                  type="checkbox"
                  :checked="selectedIds.has(s.id)"
                  :disabled="publishingBatch"
                  @change="toggleSelect(s.id, ($event.target as HTMLInputElement).checked)"
                >
              </td>
              <td class="mono">{{ s.id }}</td>
              <td>
                <div class="state-cell">
                  <span
                    class="state-pill"
                    :class="`st-${s.state}`"
                    :title="s.reject_reason || (s.submit_id ? `submit: ${s.submit_id}` : undefined)"
                  >{{ stateLabel(s.state) }}</span>
                  <button
                    v-if="s.state === 'rejected' && s.reject_reason"
                    type="button"
                    class="reason-link"
                    :title="t('skills.sync.viewRejectReasonTitle')"
                    @click="openRejectReason(s)"
                  >
                    {{ t('skills.sync.viewRejectReason') }}
                  </button>
                </div>
              </td>
              <td>{{ s.func_type || '—' }}</td>
              <td class="mono muted">
                <span v-if="s.central_hash">C:{{ s.central_hash.slice(0, 8) }}</span>
                <span v-if="s.local_hash"> L:{{ s.local_hash.slice(0, 8) }}</span>
              </td>
              <td>
                <button
                  v-if="canUpdate(s)"
                  type="button"
                  class="ea-btn-ghost ea-btn-sm"
                  :disabled="syncing || updatingIds.has(s.id) || publishingBatch || !status?.configured"
                  :title="t('skills.sync.updateTitle')"
                  @click="onUpdate(s.id)"
                >
                  {{ updatingIds.has(s.id) ? '...' : t('skills.sync.update') }}
                </button>
                <button
                  v-if="s.state === 'ahead'"
                  type="button"
                  class="ea-btn-ghost ea-btn-sm"
                  :disabled="syncing || overwritingIds.has(s.id) || publishingBatch || !status?.configured"
                  :title="t('skills.sync.forceOverwriteTitle')"
                  @click="onForceOverwrite(s.id)"
                >
                  {{ overwritingIds.has(s.id) ? '...' : t('skills.sync.forceOverwrite') }}
                </button>
                <button
                  v-if="canPublish(s)"
                  type="button"
                  class="ea-btn-ghost ea-btn-sm"
                  :disabled="publishingIds.has(s.id) || publishingBatch || !status?.configured"
                  :title="publishTitleFor(s)"
                  @click="onPublish(s.id)"
                >
                  {{ publishingIds.has(s.id) ? '...' : publishLabelFor(s) }}
                </button>
                <button
                  v-if="canDeleteLocal(s)"
                  type="button"
                  class="ea-btn-ghost ea-btn-sm danger-btn"
                  :disabled="deletingIds.has(s.id)"
                  :title="t('skills.sync.deleteLocalTitle')"
                  @click="onDeleteLocal(s.id)"
                >
                  {{ deletingIds.has(s.id) ? '...' : t('skills.sync.deleteLocal') }}
                </button>
                <button
                  v-if="canRequestDelete(s)"
                  type="button"
                  class="ea-btn-ghost ea-btn-sm danger-btn"
                  :disabled="requestingDeleteIds.has(s.id) || !status?.configured"
                  :title="t('skills.sync.requestDeleteTitle')"
                  @click="onRequestDelete(s.id)"
                >
                  {{ requestingDeleteIds.has(s.id) ? '...' : t('skills.sync.requestDelete') }}
                </button>
                <button
                  type="button"
                  class="ea-btn-ghost ea-btn-sm"
                  :disabled="!status?.configured || historyLoading"
                  :title="t('skills.sync.historyTitle')"
                  @click="onShowHistory(s.id)"
                >
                  {{ t('skills.sync.history') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="sync-empty">{{ t('skills.sync.empty') }}</div>
      </div>
    </div>

    <div v-if="rejectDetail" class="reject-modal-overlay" @click.self="closeRejectReason">
      <div class="reject-modal" role="dialog" aria-modal="true">
        <div class="reject-modal-head">
          <div>
            <strong>{{ t('skills.sync.rejectReasonTitle') }}</strong>
            <div class="mono muted reject-modal-id">{{ rejectDetail.id }}</div>
          </div>
          <button type="button" class="ea-btn-ghost ea-btn-sm" @click="closeRejectReason">
            {{ t('skills.sync.rejectReasonClose') }}
          </button>
        </div>
        <p v-if="rejectDetail.submit_id" class="muted reject-modal-meta">
          {{ t('skills.sync.rejectSubmitId', { id: rejectDetail.submit_id }) }}
        </p>
        <div class="reject-modal-body">{{ rejectDetail.reason }}</div>
        <div class="reject-modal-foot">
          <button type="button" class="ea-btn-primary ea-btn-sm" @click="closeRejectReason">
            {{ t('skills.sync.rejectReasonClose') }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="historySkillId" class="history-panel">
      <div class="history-head">
        <div>
          <strong>{{ t('skills.sync.historyFor', { id: historySkillId }) }}</strong>
          <p v-if="!historyLoading && historyHasReview && historyCurrentVersion" class="history-sub">
            {{ t('skills.sync.historyCurrent', { n: historyCurrentVersion }) }}
          </p>
          <p v-else-if="!historyLoading && historyBaselineOnly" class="history-sub">
            {{ t('skills.sync.historyBaselineSub') }}
          </p>
          <p v-else-if="!historyLoading && historyRecords.length && !historyHasReview" class="history-sub">
            {{ t('skills.sync.historyGitOnly') }}
          </p>
          <p v-else-if="!historyLoading && historyRecords.length" class="history-sub">
            {{ t('skills.sync.historyNoLive') }}
          </p>
          <p v-else-if="!historyLoading" class="history-sub">{{ t('skills.sync.historyEmpty') }}</p>
        </div>
        <button type="button" class="ea-btn-ghost ea-btn-sm" @click="closeHistory">{{ t('skills.sync.historyClose') }}</button>
      </div>
      <p v-if="historyLoading" class="muted">{{ t('skills.sync.historyLoading') }}</p>
      <p v-else-if="!historyRecords.length" class="muted">{{ t('skills.sync.historyEmptyHint') }}</p>
      <template v-else>
        <div class="history-filters">
          <button
            v-for="item in historyFilters"
            :key="item[0]"
            type="button"
            class="ea-btn-ghost ea-btn-sm"
            :class="{ 'is-on': historyFilter === item[0] }"
            @click="historyFilter = item[0]"
          >
            {{ t(`skills.sync.${item[1]}`) }}
          </button>
        </div>
        <div class="history-table">
          <div class="history-cols">
            <span>{{ t('skills.sync.historyColVersion') }}</span>
            <span>{{ t('skills.sync.historyColResult') }}</span>
            <span>{{ t('skills.sync.historyColSubmitter') }}</span>
            <span>{{ t('skills.sync.historyColTime') }}</span>
            <span>{{ t('skills.sync.historyColReview') }}</span>
            <span>{{ t('skills.sync.historyColNote') }}</span>
          </div>
          <p v-if="!visibleHistory.length" class="muted">{{ t('skills.sync.historyFilterEmpty') }}</p>
          <div v-for="row in visibleHistory" :key="row.submit_id" class="history-block">
            <div class="history-row" :class="{ open: historyOpenId === row.submit_id }">
              <button type="button" class="history-ver" @click="toggleHistoryRow(row.submit_id)">
                {{ historyVersionLabel(row) }}
              </button>
              <span :class="'hr-' + historyResult(row)">{{ historyResultLabel(row) }}</span>
              <span>{{ row.submitted_by }}</span>
              <span>{{ formatHistoryStamp(row.submitted_at) }}</span>
              <span class="muted">{{ historyReviewLabel(row) }}</span>
              <span class="history-note">{{ historyNote(row) }}</span>
            </div>
            <div v-if="historyOpenId === row.submit_id" class="history-detail">
              <p>{{ historyOpinion(row) }}</p>
              <div v-for="change in row.changes" :key="change.action + change.path" class="history-change">
                <span>{{ changeActionLabel(change.action) }}</span>
                <span class="mono">{{ change.path }}</span>
              </div>
              <p v-if="row.changes_omitted" class="muted">{{ t('skills.sync.historyChangesOmitted', { n: row.changes_omitted }) }}</p>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped lang="scss">
.skill-sync-center {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sync-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.sync-status-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #94a3b8;
  &.is-ok { background: #16a34a; }
  &.is-warn { background: #d97706; }
  &.is-err { background: #dc2626; }
}

.muted { color: #64748b; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }

.sync-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.btn-cnt {
  margin-left: 4px;
  color: #64748b;
  font-size: 12px;
}

.sync-banner {
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  &.warn { background: #fff7ed; color: #9a3412; }
  &.err { background: #fef2f2; color: #991b1b; }
  &.info { background: #eff6ff; color: #1e40af; }
  &.ok { background: #f0fdf4; color: #166534; }
}

.sync-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 12px;
  overflow: hidden;
}

.sync-groups {
  overflow: auto;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 6px;
  background: #fff;
}

.group-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border: 0;
  background: transparent;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  text-align: left;
  &:hover { background: #f8fafc; }
  &.active { background: #eef2ff; color: #3730a3; }
  .label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .badge {
    font-size: 11px;
    color: #c2410c;
    background: #ffedd5;
    padding: 1px 6px;
    border-radius: 999px;
  }
  .cnt { color: #94a3b8; font-size: 12px; }
}

.sync-table-wrap {
  overflow: auto;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fff;
}

.sync-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  th, td {
    padding: 8px 10px;
    border-bottom: 1px solid #f1f5f9;
    text-align: left;
  }
  th { color: #64748b; font-weight: 600; background: #f8fafc; position: sticky; top: 0; }
  .col-check {
    width: 36px;
    text-align: center;
    vertical-align: middle;
  }
}

.state-pill {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  &.st-synced { background: #dcfce7; color: #166534; }
  &.st-behind { background: #ffedd5; color: #9a3412; }
  &.st-ahead { background: #fef3c7; color: #92400e; }
  &.st-local_only { background: #f1f5f9; color: #475569; }
  &.st-unknown { background: #e2e8f0; color: #334155; }
  &.st-submitted_pending { background: #dbeafe; color: #1d4ed8; }
  &.st-delete_pending { background: #ffe4e6; color: #be123c; }
  &.st-rejected { background: #fee2e2; color: #b91c1c; }
}

.danger-btn {
  color: #b91c1c !important;
}

.state-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.reason-link {
  border: none;
  background: transparent;
  padding: 0;
  font-size: 12px;
  color: #b91c1c;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
  opacity: 0.85;
}
.reason-link:hover { opacity: 1; }

.reject-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(15, 23, 42, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.reject-modal {
  width: min(480px, 100%);
  background: #fff;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.18);
  padding: 16px 18px;
}
.reject-modal-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
}
.reject-modal-id { margin-top: 4px; font-size: 12px; }
.reject-modal-meta { margin: 0 0 10px; font-size: 12px; }
.reject-modal-body {
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  padding: 12px 14px;
  color: #7f1d1d;
  font-size: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 40vh;
  overflow: auto;
}
.reject-modal-foot {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

.history-panel {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fff;
  padding: 12px;
  max-height: 360px;
  overflow: auto;
}
.history-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 8px;
}
.history-sub {
  margin: 2px 0 0;
  color: #64748b;
  font-size: 12px;
}
.history-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
  button.is-on {
    background: #eef2ff;
    color: #3730a3;
    border-color: #c7d2fe;
  }
}
.history-cols,
.history-row {
  display: grid;
  grid-template-columns: 132px 72px 110px 148px 180px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
}
.history-cols {
  padding: 0 8px 6px;
  color: #64748b;
  font-size: 12px;
  border-bottom: 1px solid #f1f5f9;
}
.history-row {
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 13px;
  &.open { background: #eef2ff; }
}
.history-ver {
  justify-self: start;
  max-width: 100%;
  border: 1px solid #e2e8f0;
  background: #fff;
  border-radius: 6px;
  padding: 2px 8px;
  font-size: 12px;
  cursor: pointer;
  text-align: left;
}
.history-row.open .history-ver {
  background: #e0e7ff;
  border-color: #c7d2fe;
}
.history-note {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.history-detail {
  margin: 2px 0 8px 8px;
  padding: 8px 12px;
  border-left: 2px solid #4f46e5;
  font-size: 13px;
  p { margin: 0 0 4px; }
}
.history-change {
  display: flex;
  gap: 8px;
  color: #64748b;
  font-size: 12px;
}
.hr-passed { color: #166534; }
.hr-waiting { color: #b45309; }
.hr-returned { color: #b91c1c; }
.hr-offline { color: #64748b; }
.hr-git { color: #3730a3; }
.hr-baseline { color: #166534; }

.sync-empty {
  padding: 24px;
  color: #94a3b8;
  text-align: center;
}

@media (max-width: 900px) {
  .sync-body { grid-template-columns: 1fr; }
}
</style>
