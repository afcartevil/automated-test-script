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
  type SkillSyncStatusItem,
  type SkillHistoryCommit,
} from '@/api/hermes/skills'
import { useSkillSyncStore } from '@/stores/hermes/skill-sync'

const { t } = useI18n()
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
} | null>(null)
const publishingId = ref<string | null>(null)
const publishingBatch = ref(false)
const historySkillId = ref<string | null>(null)
const historyLoading = ref(false)
const historyCommits = ref<SkillHistoryCommit[]>([])
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

/** 本机有内容且未与服务器对齐时可提交（排除 synced / 待审 / 仅服务器有） */
function canPublish(s: SkillSyncStatusItem): boolean {
  if (!status.value?.connected) return false
  if (!s.local_hash) return false
  if (s.state === 'synced' || s.state === 'unknown' || s.state === 'submitted_pending') return false
  return s.state === 'local_only' || s.state === 'behind' || s.state === 'rejected'
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
  if (state === 'local_only') return t('skills.sync.stateLocalOnly')
  if (state === 'submitted_pending') return t('skills.sync.statePending')
  if (state === 'rejected') return t('skills.sync.stateRejected')
  return t('skills.sync.stateUnknown')
}

function publishTitleFor(s: SkillSyncStatusItem): string {
  if (s.state === 'rejected') return t('skills.sync.publishTitleRejected')
  if (s.state === 'behind') return t('skills.sync.publishTitleBehind')
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

async function loadStatus(force = false) {
  try {
    await syncStore.load({ force })
    pruneSelection()
  } catch (err: any) {
    if (!status.value) {
      message.error(err?.message || t('skills.sync.loadFailed'))
    }
  }
}

async function onSyncAll() {
  if (syncing.value) return
  syncing.value = true
  lastResult.value = null
  try {
    const res = await triggerSync()
    lastResult.value = {
      skills: res.pull?.skills ?? 0,
      reinjected: res.reinjected?.length ?? 0,
      reinjectError: res.reinject_error || res.pull?.reinject_error,
      requirementsChanged: res.requirements_changed || res.pull?.requirements_changed || [],
    }
    if (lastResult.value.requirementsChanged.length) {
      message.warning(t('skills.sync.requirementsHint', {
        ids: lastResult.value.requirementsChanged.join(', '),
      }))
    } else if (lastResult.value.reinjectError) {
      message.warning(t('skills.sync.reinjectWarn'))
    } else {
      message.success(t('skills.sync.syncSuccess'))
    }
    await loadStatus(true)
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
    lastResult.value = {
      skills: res.pull?.skills ?? 0,
      reinjected: res.reinjected?.length ?? 0,
      reinjectError: res.reinject_error || res.pull?.reinject_error,
      requirementsChanged: res.requirements_changed || res.pull?.requirements_changed || [],
    }
    message.success(t('skills.sync.syncBundleSuccess', { id: bid, n: lastResult.value.skills }))
    await loadStatus(true)
  } catch (err: any) {
    message.error(err?.message || t('skills.sync.syncFailed'))
  } finally {
    syncing.value = false
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
  if (publishingId.value || publishingBatch.value) return
  const row = status.value?.skills.find(s => s.id === skillId)
  if (!row || !canPublish(row)) return
  publishingId.value = skillId
  try {
    const res = await publishSkillPackage(skillId)
    message.success(t('skills.sync.publishPendingSuccess', {
      id: res.id,
      n: res.file_count,
      submit: res.submit_id || '-',
    }))
    await loadStatus(true)
  } catch (err: any) {
    message.error(err?.message || t('skills.sync.publishFailed'))
  } finally {
    publishingId.value = null
  }
}

async function onPublishBatch() {
  if (publishingBatch.value || publishingId.value) return
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
    await loadStatus(true)
  } catch (err: any) {
    message.error(err?.message || t('skills.sync.publishBatchFailed'))
  } finally {
    publishingBatch.value = false
  }
}

async function onShowHistory(skillId: string) {
  if (!status.value?.configured) return
  historySkillId.value = skillId
  historyLoading.value = true
  historyCommits.value = []
  try {
    const data = await fetchSkillPackageHistory(skillId)
    historyCommits.value = data.commits || []
  } catch (err: any) {
    message.error(err?.message || t('skills.sync.historyFailed'))
    historySkillId.value = null
  } finally {
    historyLoading.value = false
  }
}

function closeHistory() {
  historySkillId.value = null
  historyCommits.value = []
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
          :disabled="!publishableSkills.length || publishingBatch || !!publishingId"
          :title="t('skills.sync.selectAllUnsyncedTitle')"
          @click="toggleSelectAll(!allPublishableSelected)"
        >
          {{ allPublishableSelected ? t('skills.sync.clearSelection') : t('skills.sync.selectAllUnsynced') }}
        </button>
        <button
          type="button"
          class="ea-btn-ghost ea-btn-sm"
          :disabled="publishingBatch || !!publishingId || !status?.configured || !status?.connected"
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
    <div v-else-if="status && (status.pending_count || 0) > 0" class="sync-banner info">
      {{ t('skills.sync.pendingCount', { n: status.pending_count }) }}
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
                  :disabled="publishingBatch || !!publishingId"
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
                  v-if="canPublish(s)"
                  type="button"
                  class="ea-btn-ghost ea-btn-sm"
                  :disabled="!!publishingId || publishingBatch || !status?.configured"
                  :title="publishTitleFor(s)"
                  @click="onPublish(s.id)"
                >
                  {{ publishingId === s.id ? '...' : publishLabelFor(s) }}
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
        <strong>{{ t('skills.sync.historyFor', { id: historySkillId }) }}</strong>
        <button type="button" class="ea-btn-ghost ea-btn-sm" @click="closeHistory">{{ t('skills.sync.historyClose') }}</button>
      </div>
      <p v-if="historyLoading" class="muted">{{ t('skills.sync.historyLoading') }}</p>
      <p v-else-if="!historyCommits.length" class="muted">{{ t('skills.sync.historyEmpty') }}</p>
      <ul v-else class="history-list">
        <li v-for="c in historyCommits" :key="c.sha">
          <span class="mono">{{ c.short_sha }}</span>
          <span>{{ c.title }}</span>
          <span class="muted">{{ c.author_name }} · {{ c.committed_at }}</span>
          <a v-if="c.web_url" :href="c.web_url" target="_blank" rel="noopener">GitLab</a>
        </li>
      </ul>
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
  &.st-local_only { background: #f1f5f9; color: #475569; }
  &.st-unknown { background: #e2e8f0; color: #334155; }
  &.st-submitted_pending { background: #dbeafe; color: #1d4ed8; }
  &.st-rejected { background: #fee2e2; color: #b91c1c; }
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
}
.history-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.history-list {
  list-style: none;
  margin: 0;
  padding: 0;
  li {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding: 6px 0;
    border-bottom: 1px solid #f1f5f9;
    font-size: 13px;
  }
}

.sync-empty {
  padding: 24px;
  color: #94a3b8;
  text-align: center;
}

@media (max-width: 900px) {
  .sync-body { grid-template-columns: 1fr; }
}
</style>
