<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import {
  fetchSyncStatus,
  triggerSync,
  reinjectSkills,
  publishSkillPackage,
  publishSkillPackages,
  type SkillSyncStatus,
  type SkillSyncStatusItem,
} from '@/api/hermes/skills'

const { t } = useI18n()
const message = useMessage()

const loading = ref(false)
const syncing = ref(false)
const reinjecting = ref(false)
const status = ref<SkillSyncStatus | null>(null)
const selectedGroupId = ref<string | null>(null)
const lastResult = ref<{
  skills: number
  reinjected: number
  reinjectError?: string
  requirementsChanged: string[]
} | null>(null)
const publishingId = ref<string | null>(null)
const publishingBatch = ref(false)

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

const publishableSkills = computed(() =>
  activeSkills.value.filter(s => s.state === 'local_only' || s.state === 'behind' || s.state === 'synced'),
)

function stateLabel(state: string): string {
  if (state === 'synced') return t('skills.sync.stateSynced')
  if (state === 'behind') return t('skills.sync.stateBehind')
  if (state === 'local_only') return t('skills.sync.stateLocalOnly')
  return t('skills.sync.stateUnknown')
}

function formatTime(iso: string | null): string {
  if (!iso) return t('skills.sync.neverSynced')
  try {
    return t('skills.sync.lastSynced', { time: new Date(iso).toLocaleString() })
  } catch {
    return t('skills.sync.lastSynced', { time: iso })
  }
}

async function loadStatus() {
  loading.value = true
  try {
    status.value = await fetchSyncStatus()
    if (selectedGroupId.value && !status.value.groups.some(g => g.id === selectedGroupId.value)) {
      selectedGroupId.value = null
    }
  } catch (err: any) {
    message.error(err?.message || t('skills.sync.loadFailed'))
  } finally {
    loading.value = false
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
    await loadStatus()
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
  publishingId.value = skillId
  try {
    const res = await publishSkillPackage(skillId)
    message.success(t('skills.sync.publishSuccess', { id: res.id, n: res.file_count }))
    await loadStatus()
  } catch (err: any) {
    message.error(err?.message || t('skills.sync.publishFailed'))
  } finally {
    publishingId.value = null
  }
}

async function onPublishBatch() {
  if (publishingBatch.value || publishingId.value) return
  const ids = publishableSkills.value.map(s => s.id)
  if (!ids.length) {
    message.info(t('skills.sync.publishBatchEmpty'))
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
    await loadStatus()
  } catch (err: any) {
    message.error(err?.message || t('skills.sync.publishBatchFailed'))
  } finally {
    publishingBatch.value = false
  }
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
        <button type="button" class="ea-btn-ghost ea-btn-sm" :disabled="loading || publishingBatch" @click="loadStatus">
          {{ t('skills.sync.checkNow') }}
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
          :disabled="publishingBatch || !!publishingId || !status?.configured || !status?.connected"
          :title="t('skills.sync.publishBatchTitle')"
          @click="onPublishBatch"
        >
          {{ publishingBatch ? t('skills.sync.publishBatchRunning') : t('skills.sync.publishBatch') }}
          <span v-if="!publishingBatch && publishableSkills.length" class="btn-cnt">{{ publishableSkills.length }}</span>
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

    <div v-if="!status?.configured" class="sync-banner warn">
      {{ t('skills.sync.notConfiguredHint') }}
    </div>
    <div v-else-if="status && !status.connected" class="sync-banner err">
      {{ status.error || t('skills.sync.disconnected') }}
    </div>
    <div v-else-if="status && status.behind_count > 0" class="sync-banner info">
      {{ t('skills.sync.behindCount', { n: status.behind_count }) }}
    </div>
    <div v-else-if="status" class="sync-banner ok">
      {{ t('skills.sync.upToDate') }}
    </div>

    <div v-if="lastResult" class="sync-banner info">
      pull skills={{ lastResult.skills }} · reinjected={{ lastResult.reinjected }}
      <span v-if="lastResult.reinjectError"> · {{ lastResult.reinjectError }}</span>
      <span v-if="lastResult.requirementsChanged.length">
        · requirements: {{ lastResult.requirementsChanged.join(', ') }} → npm run setup
      </span>
    </div>

    <div v-if="loading && !status" class="sync-empty">{{ t('common.loading') }}</div>
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
              <th>ID</th>
              <th>{{ t('skills.sync.stateSynced') }}</th>
              <th>func_type</th>
              <th>hash</th>
              <th>{{ t('skills.sync.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in activeSkills" :key="s.id">
              <td class="mono">{{ s.id }}</td>
              <td>
                <span class="state-pill" :class="`st-${s.state}`">{{ stateLabel(s.state) }}</span>
              </td>
              <td>{{ s.func_type || '—' }}</td>
              <td class="mono muted">
                <span v-if="s.central_hash">C:{{ s.central_hash.slice(0, 8) }}</span>
                <span v-if="s.local_hash"> L:{{ s.local_hash.slice(0, 8) }}</span>
              </td>
              <td>
                <button
                  v-if="s.state === 'local_only' || s.state === 'behind' || s.state === 'synced'"
                  type="button"
                  class="ea-btn-ghost ea-btn-sm"
                  :disabled="!!publishingId || publishingBatch || !status?.configured"
                  :title="t('skills.sync.publishTitle')"
                  @click="onPublish(s.id)"
                >
                  {{ publishingId === s.id ? '...' : t('skills.sync.publish') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="sync-empty">{{ t('skills.sync.empty') }}</div>
      </div>
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
