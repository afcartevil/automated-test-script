<script setup lang="ts">
import { NButton, NTag } from 'naive-ui'
import type { ModemExternalNotice } from '@/api/tahp/modem-baseline'

defineProps<{
  notices: ModemExternalNotice[]
  loading?: boolean
  applyingId?: string
  confirmingId?: string
  dismissingId?: string
  filledIds?: string[]
}>()

const emit = defineEmits<{
  refresh: []
  apply: [noticeId: string]
  confirm: [noticeId: string]
  dismiss: [noticeId: string]
}>()

function formatTime(value?: string) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function isFilled(filledIds: string[] | undefined, noticeId: string) {
  return Boolean(filledIds?.includes(noticeId))
}
</script>

<template>
  <div class="ea-card ea-stack pending-card">
    <div class="cfg-head">
      <div>
        <div class="ea-section-title">外部通知</div>
        <h3>待确认（{{ notices.length }}）</h3>
        <p>采用并填入后仍保留在此；完成核对/启动后再点「确认完成」才会消失。</p>
      </div>
      <NButton secondary size="small" :loading="loading" @click="emit('refresh')">刷新</NButton>
    </div>

    <div v-if="!notices.length" class="empty">暂无待确认通知</div>

    <div v-for="item in notices" :key="item.noticeId" class="notice-item">
      <div class="notice-main">
        <div class="notice-text-row">
          <div class="notice-text">{{ item.text }}</div>
          <NTag v-if="isFilled(filledIds, item.noticeId)" size="small" type="success" :bordered="false">
            已填入
          </NTag>
        </div>
        <div class="notice-meta">
          <span>{{ item.source }}</span>
          <span v-if="item.platform">{{ item.platform }}</span>
          <span v-if="item.version">{{ item.version }}</span>
          <span>{{ formatTime(item.receivedAt) }}</span>
        </div>
      </div>
      <div class="notice-actions">
        <NButton
          type="primary"
          size="small"
          :loading="applyingId === item.noticeId"
          :disabled="Boolean(dismissingId || confirmingId)"
          @click="emit('apply', item.noticeId)"
        >
          采用并填入
        </NButton>
        <NButton
          type="success"
          secondary
          size="small"
          :loading="confirmingId === item.noticeId"
          :disabled="Boolean(applyingId || dismissingId)"
          @click="emit('confirm', item.noticeId)"
        >
          确认完成
        </NButton>
        <NButton
          secondary
          size="small"
          :loading="dismissingId === item.noticeId"
          :disabled="Boolean(applyingId || confirmingId)"
          @click="emit('dismiss', item.noticeId)"
        >
          忽略
        </NButton>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.pending-card {
  padding: 14px 16px;
}

.cfg-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;

  h3 {
    font-size: 16px;
    font-weight: 700;
    color: var(--head);
  }

  p {
    margin: 4px 0 0;
    font-size: 12px;
    color: var(--muted);
    line-height: 1.45;
  }
}

.empty {
  font-size: 13px;
  color: var(--muted);
  padding: 8px 0 2px;
}

.notice-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  padding: 10px 0;
  border-top: 1px solid var(--line, rgba(0, 0, 0, 0.08));
}

.notice-text-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.notice-text {
  font-size: 13px;
  font-weight: 600;
  color: var(--head);
  line-height: 1.45;
  word-break: break-word;
}

.notice-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--muted);
}

.notice-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex-shrink: 0;
}

@media (max-width: 720px) {
  .notice-item,
  .cfg-head {
    flex-direction: column;
    align-items: stretch;
  }

  .notice-actions {
    flex-direction: row;
    flex-wrap: wrap;
  }
}
</style>
