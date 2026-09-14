<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NPopconfirm, NTag } from 'naive-ui'
import type { GkiExternalNotice } from '@/api/tahp/gki-upgrade-notices'

export type GkiNoticeFilter = 'pending' | 'done'

const props = defineProps<{
  notices: GkiExternalNotice[]
  loading?: boolean
  syncing?: boolean
  syncMeta?: string
  syncHint?: string
  applyingId?: string
  confirmingId?: string
  dismissingId?: string
  restoringId?: string
  deletingId?: string
  filledIds?: string[]
  highlightId?: string
}>()

const emit = defineEmits<{
  refresh: []
  syncAlerts: []
  apply: [noticeId: string]
  confirm: [noticeId: string]
  dismiss: [noticeId: string]
  restore: [noticeId: string]
  remove: [noticeId: string]
}>()

const filter = ref<GkiNoticeFilter>('pending')

const pendingCount = computed(() =>
  props.notices.filter(item => item.status === 'pending').length,
)

const doneCount = computed(() =>
  props.notices.filter(item => item.status === 'applied' || item.status === 'dismissed').length,
)

const visibleNotices = computed(() => {
  const list = props.notices.filter((item) => {
    if (filter.value === 'pending') return item.status === 'pending'
    return item.status === 'applied' || item.status === 'dismissed'
  })
  return [...list].sort((a, b) => {
    const ta = Date.parse(a.updatedAt || a.receivedAt || '') || 0
    const tb = Date.parse(b.updatedAt || b.receivedAt || '') || 0
    return tb - ta
  })
})

const isEmpty = computed(() => visibleNotices.value.length === 0)

function formatTime(value?: string) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function isFilled(filledIds: string[] | undefined, noticeId: string) {
  return Boolean(filledIds?.includes(noticeId))
}

function taskKindLabel(kind?: string) {
  if (kind === 'analysis') return '分析'
  if (kind === 'upgrade') return '合入'
  if (kind === 'both') return '分析/合入'
  return ''
}

function statusLabel(status?: string) {
  if (status === 'applied') return '已确认'
  if (status === 'dismissed') return '已忽略'
  return '待处理'
}

function statusTagType(status?: string): 'success' | 'default' | 'warning' {
  if (status === 'applied') return 'success'
  if (status === 'dismissed') return 'default'
  return 'warning'
}

function hasTagPair(item: GkiExternalNotice) {
  return Boolean(item.fromTag && item.toTag)
}

function isPending(item: GkiExternalNotice) {
  return item.status === 'pending'
}

function isDismissed(item: GkiExternalNotice) {
  return item.status === 'dismissed'
}

function isBusy() {
  return Boolean(
    props.applyingId
    || props.confirmingId
    || props.dismissingId
    || props.restoringId
    || props.deletingId,
  )
}

function requestRestore(noticeId: string) {
  emit('restore', noticeId)
  filter.value = 'pending'
}

function isAlertNotice(item: GkiExternalNotice) {
  return item.kind === 'alert' || Boolean(item.currentGkiVersion || item.platform || item.alertRule)
}

function alertFields(item: GkiExternalNotice) {
  return [
    { label: '分支', value: item.branches },
    { label: '平台', value: item.platform },
    { label: '项目', value: item.projects },
    { label: '当前GKI版本', value: item.currentGkiVersion || item.fromTag },
    { label: 'kernel版本', value: item.kernelVersion },
    { label: 'SOC厂商', value: item.socVendor },
    { label: '启动日期', value: item.startDate },
    { label: '完成日期', value: item.dueDate },
  ].filter(row => Boolean(row.value))
}

function isHighlighted(item: GkiExternalNotice) {
  const id = String(props.highlightId || '').trim()
  if (!id) return false
  return (
    item.noticeId === id
    || item.sourceId === id
    || item.parentSourceId === id
    || Boolean(item.sourceId && item.sourceId.startsWith(`${id}#`))
  )
}

const lastFilterSync = ref('')

watch(
  () => [props.highlightId, props.notices] as const,
  () => {
    const found = props.notices.find(isHighlighted)
    if (!found) return
    const key = `${found.noticeId}:${found.status}`
    if (lastFilterSync.value === key) return
    lastFilterSync.value = key
    filter.value = found.status === 'pending' ? 'pending' : 'done'
  },
  { immediate: true },
)
</script>

<template>
  <div class="ea-card pending-card">
    <div class="cfg-head">
      <div>
        <div class="ea-section-title">外部通知</div>
        <h3>通知收件箱</h3>
        <p v-if="filter === 'pending'">采用后选择次新月 To Tag；启动分析后再点「确认完成」。</p>
        <p v-else>已确认 / 已忽略的通知。忽略的可放回待处理；不需要的可删除。</p>
        <p v-if="syncMeta" class="sync-meta">{{ syncMeta }}</p>
        <p v-if="syncHint" class="sync-hint">{{ syncHint }}</p>
      </div>
      <div class="cfg-actions">
        <NButton
          secondary
          size="small"
          :loading="syncing"
          @click="emit('syncAlerts')"
        >
          同步飞书告警
        </NButton>
        <NButton secondary size="small" :loading="loading" @click="emit('refresh')">刷新</NButton>
      </div>
    </div>

    <div class="filter-tabs" role="tablist">
      <button
        type="button"
        class="filter-tab"
        :class="{
          active: filter === 'pending',
          'has-pending': pendingCount > 0,
        }"
        role="tab"
        :aria-selected="filter === 'pending'"
        @click="filter = 'pending'"
      >
        待处理
        <span class="count">{{ pendingCount }}</span>
      </button>
      <button
        type="button"
        class="filter-tab"
        :class="{ active: filter === 'done' }"
        role="tab"
        :aria-selected="filter === 'done'"
        @click="filter = 'done'"
      >
        已处理
        <span class="count">{{ doneCount }}</span>
      </button>
    </div>

    <div v-if="isEmpty" class="empty">
      {{ filter === 'pending' ? '暂无待处理通知' : '暂无已处理通知' }}
    </div>

    <div v-else class="notice-list">
      <div
        v-for="item in visibleNotices"
        :key="item.noticeId"
        class="notice-item"
        :class="{ highlight: isHighlighted(item) }"
      >
        <div class="notice-top">
          <div class="notice-badges">
            <NTag size="small" :type="statusTagType(item.status)" :bordered="false">
              {{ statusLabel(item.status) }}
            </NTag>
            <NTag v-if="item.kind === 'alert'" size="small" type="error" :bordered="false">
              异常告警
            </NTag>
            <NTag v-if="taskKindLabel(item.taskKind)" size="small" :bordered="false">
              {{ taskKindLabel(item.taskKind) }}
            </NTag>
            <NTag v-if="isFilled(filledIds, item.noticeId)" size="small" type="success" :bordered="false">
              已填入
            </NTag>
          </div>
          <div class="notice-meta">
            <span>{{ item.source }}</span>
            <span>{{ formatTime(item.updatedAt || item.receivedAt) }}</span>
          </div>
        </div>

        <p v-if="item.title && isAlertNotice(item)" class="notice-title">{{ item.title }}</p>
        <p v-if="item.alertRule" class="notice-rule">{{ item.alertRule }}</p>

        <div v-if="alertFields(item).length" class="tag-pair">
          <div v-for="row in alertFields(item)" :key="row.label" class="tag-line alert-line">
            <span class="tag-label">{{ row.label }}</span>
            <code class="tag-value">{{ row.value }}</code>
          </div>
        </div>
        <div v-else-if="hasTagPair(item)" class="tag-pair">
          <div class="tag-line">
            <span class="tag-label">From</span>
            <code class="tag-value">{{ item.fromTag }}</code>
          </div>
          <div class="tag-line">
            <span class="tag-label">To</span>
            <code class="tag-value">{{ item.toTag }}</code>
          </div>
        </div>

        <p
          v-if="!isAlertNotice(item)"
          class="notice-text"
          :class="{ secondary: hasTagPair(item) }"
        >{{ item.text }}</p>

        <p v-if="item.status === 'dismissed' && item.dismissReason" class="dismiss-reason">
          忽略原因：{{ item.dismissReason }}
        </p>

        <div class="notice-actions">
          <template v-if="isPending(item)">
            <NButton
              type="primary"
              size="small"
              :loading="applyingId === item.noticeId"
              :disabled="isBusy()"
              @click="emit('apply', item.noticeId)"
            >
              采用并填入
            </NButton>
            <NButton
              type="success"
              secondary
              size="small"
              :loading="confirmingId === item.noticeId"
              :disabled="isBusy()"
              @click="emit('confirm', item.noticeId)"
            >
              确认完成
            </NButton>
            <NButton
              secondary
              size="small"
              :loading="dismissingId === item.noticeId"
              :disabled="isBusy()"
              @click="emit('dismiss', item.noticeId)"
            >
              忽略
            </NButton>
          </template>
          <template v-else>
            <NButton
              v-if="isDismissed(item)"
              type="primary"
              secondary
              size="small"
              :loading="restoringId === item.noticeId"
              :disabled="isBusy()"
              @click="requestRestore(item.noticeId)"
            >
              放回待处理
            </NButton>
            <NPopconfirm
              :positive-button-props="{ type: 'error' }"
              @positive-click="emit('remove', item.noticeId)"
            >
              <template #trigger>
                <NButton
                  type="error"
                  secondary
                  size="small"
                  :loading="deletingId === item.noticeId"
                  :disabled="isBusy()"
                >
                  删除
                </NButton>
              </template>
              删除后无法恢复，确定删除这条通知？
            </NPopconfirm>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.pending-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  flex: 1 1 0;
  min-height: 0;
  overflow: hidden;
}

.cfg-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
  flex: 0 0 auto;

  h3 {
    font-size: 15px;
    font-weight: 700;
    color: var(--head);
    margin: 2px 0 4px;
  }

  p {
    margin: 0;
    font-size: 12px;
    color: var(--muted);
    line-height: 1.45;
  }

  .sync-meta,
  .sync-hint {
    margin-top: 4px;
  }

  .sync-hint {
    color: var(--head);
  }
}

.cfg-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
}

.filter-tabs {
  display: flex;
  gap: 6px;
  flex: 0 0 auto;
}

.filter-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;

  .count {
    min-width: 16px;
    padding: 0 5px;
    border-radius: 999px;
    background: color-mix(in srgb, var(--line) 55%, transparent);
    font-variant-numeric: tabular-nums;
  }

  &.has-pending .count {
    color: #d92d20;
    font-weight: 700;
  }

  &.active {
    color: var(--head);
    border-color: color-mix(in srgb, var(--accent, #5b6cff) 35%, var(--line));
    background: color-mix(in srgb, var(--accent, #5b6cff) 10%, var(--surface));

    .count {
      background: color-mix(in srgb, var(--accent, #5b6cff) 18%, transparent);
    }
  }

  &.active.has-pending .count {
    color: #d92d20;
    font-weight: 700;
  }
}

.empty {
  font-size: 13px;
  color: var(--muted);
  padding: 8px 0;
}

.notice-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.notice-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface);
  min-width: 0;

  &.highlight {
    border-color: color-mix(in srgb, var(--accent, #5b6cff) 45%, var(--line));
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent, #5b6cff) 22%, transparent);
    background: color-mix(in srgb, var(--accent, #5b6cff) 6%, var(--surface));
  }
}

.notice-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}

.notice-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}

.notice-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  font-size: 11px;
  color: var(--muted);
  flex-shrink: 0;
}

.tag-pair {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--line) 35%, transparent);
}

.tag-line {
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr);
  gap: 8px;
  align-items: baseline;
  min-width: 0;

  &.alert-line {
    grid-template-columns: 88px minmax(0, 1fr);
  }
}

.tag-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
}

.tag-value {
  margin: 0;
  min-width: 0;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--head);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  overflow-wrap: anywhere;
  word-break: break-word;
  white-space: pre-wrap;
}

.notice-title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: var(--head);
  line-height: 1.4;
}

.notice-rule {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.4;
}

.dismiss-reason {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.45;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.notice-text {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--head);
  line-height: 1.45;
  overflow-wrap: anywhere;
  word-break: break-word;

  &.secondary {
    font-size: 12px;
    font-weight: 400;
    color: var(--muted);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
}

.notice-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
