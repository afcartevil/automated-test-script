<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NTag } from 'naive-ui'
import type { ModemExternalNotice, ModemPlatformTask, ModemPlatformTaskStatus } from '@/api/tahp/modem-baseline'

const props = defineProps<{
  notices: ModemExternalNotice[]
  loading?: boolean
  applyingId?: string
  confirmingId?: string
  dismissingId?: string
  filledIds?: string[]
  /** 正在按平台采用并填入的 {noticeId, platform} */
  applyingPlatform?: { noticeId: string; platform: string } | null
}>()

const emit = defineEmits<{
  refresh: []
  apply: [noticeId: string, platform?: string]
  confirm: [noticeId: string]
  dismiss: [noticeId: string]
  setPlatformTaskStatus: [noticeId: string, platform: string, status: ModemPlatformTaskStatus]
}>()

const isEmpty = computed(() => props.notices.length === 0)

function formatTime(value?: string) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function isFilled(filledIds: string[] | undefined, noticeId: string) {
  return Boolean(filledIds?.includes(noticeId))
}

function platformTaskTagType(status: ModemPlatformTaskStatus) {
  switch (status) {
    case 'done': return 'success'
    case 'failed': return 'error'
    case 'in_progress': return 'info'
    case 'skipped': return 'default'
    default: return 'warning'
  }
}

function platformTaskTagText(status: ModemPlatformTaskStatus) {
  switch (status) {
    case 'pending': return '待升级'
    case 'in_progress': return '进行中'
    case 'done': return '已完成'
    case 'failed': return '失败'
    case 'skipped': return '已跳过'
  }
}

function isPlatformApplying(noticeId: string, platform: string) {
  return props.applyingPlatform?.noticeId === noticeId && props.applyingPlatform?.platform === platform
}

/** 该通知是否所有平台任务完结（可确认完成）。 */
function isNoticeComplete(notice: ModemExternalNotice) {
  if (!notice.platformTasks || !notice.platformTasks.length) return true
  return notice.platformTasks.every(t => t.status === 'done' || t.status === 'skipped')
}

function canApplyPlatform(task: ModemPlatformTask) {
  return task.status === 'pending' || task.status === 'failed'
}
</script>

<template>
  <div class="ea-card pending-card">
    <div class="cfg-head">
      <div>
        <div class="ea-section-title">外部通知</div>
        <h3>待确认（{{ notices.length }}）</h3>
        <p v-if="!isEmpty">采用并填入后仍保留；核对并启动后再点「确认完成」才会消失。</p>
      </div>
      <NButton secondary size="small" :loading="loading" @click="emit('refresh')">刷新</NButton>
    </div>

    <div v-if="isEmpty" class="empty">暂无待确认通知</div>

    <div v-else class="notice-list">
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
            <span v-if="item.sourceId">{{ item.sourceId }}</span>
            <span v-if="item.version">{{ item.version }}</span>
            <span>{{ formatTime(item.receivedAt) }}</span>
          </div>

          <!-- 平台任务列表（AP 分支拆解） -->
          <div v-if="item.platformTasks && item.platformTasks.length" class="platform-tasks">
            <div class="platform-tasks-hint">该 AP 分支对应多个 modem 平台，逐个升级：</div>
            <div v-for="task in item.platformTasks" :key="task.platform" class="platform-task-row">
              <span class="platform-name">{{ task.platform }}</span>
              <NTag size="small" :type="platformTaskTagType(task.status)" :bordered="false">
                {{ platformTaskTagText(task.status) }}
              </NTag>
              <div class="platform-task-actions">
                <NButton
                  size="tiny"
                  type="primary"
                  :loading="isPlatformApplying(item.noticeId, task.platform)"
                  :disabled="!canApplyPlatform(task) || Boolean(confirmingId || dismissingId)"
                  @click="emit('apply', item.noticeId, task.platform)"
                >
                  采用并填入
                </NButton>
                <NButton
                  v-if="task.status === 'pending' || task.status === 'failed'"
                  size="tiny"
                  secondary
                  :disabled="Boolean(applyingId || confirmingId || dismissingId)"
                  @click="emit('setPlatformTaskStatus', item.noticeId, task.platform, 'skipped')"
                >
                  跳过
                </NButton>
                <NButton
                  v-if="task.status === 'skipped'"
                  size="tiny"
                  secondary
                  :disabled="Boolean(applyingId || confirmingId || dismissingId)"
                  @click="emit('setPlatformTaskStatus', item.noticeId, task.platform, 'pending')"
                >
                  恢复
                </NButton>
              </div>
            </div>
          </div>
        </div>

        <div class="notice-actions">
          <NButton
            v-if="!item.platformTasks || !item.platformTasks.length"
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
            :disabled="Boolean(applyingId || dismissingId) || (item.platformTasks ? !isNoticeComplete(item) : false)"
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
  </div>
</template>

<style scoped lang="scss">
.pending-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
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
  }

  p {
    margin: 4px 0 0;
    font-size: 12px;
    color: var(--muted);
    line-height: 1.45;
  }
}

.empty {
  flex: 1;
  display: grid;
  place-items: center;
  min-height: 0;
  font-size: 13px;
  color: var(--muted);
  border: 1px dashed var(--line);
  border-radius: 10px;
  background: color-mix(in srgb, var(--surface) 70%, transparent);
}

.notice-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 2px;
}

.notice-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  padding: 10px 0;
  border-top: 1px solid var(--line, rgba(0, 0, 0, 0.08));

  &:first-child {
    border-top: none;
    padding-top: 0;
  }
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
  white-space: pre-wrap;
}

.notice-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--muted);
}

.platform-tasks {
  margin-top: 8px;
  padding: 8px 10px;
  border: 1px solid var(--line, rgba(0, 0, 0, 0.08));
  border-radius: 8px;
  background: color-mix(in srgb, var(--surface) 60%, transparent);
}

.platform-tasks-hint {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 6px;
}

.platform-task-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  flex-wrap: wrap;
}

.platform-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--head);
  min-width: 96px;
}

.platform-task-actions {
  display: flex;
  gap: 6px;
  margin-left: auto;
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
