<script setup lang="ts">
import { computed } from 'vue'
import { NButton } from 'naive-ui'
import type { ModemBaselineRunMeta } from '@/api/tahp/modem-baseline'

const props = defineProps<{
  runs: ModemBaselineRunMeta[]
  selectedRunId: string
  loading?: boolean
  limit?: number
}>()

const emit = defineEmits<{
  select: [runId: string]
  refresh: []
}>()

const visibleRuns = computed(() => props.runs.slice(0, props.limit ?? 50))

function toneClass(status: ModemBaselineRunMeta['status']) {
  switch (status) {
    case 'success':
      return 'ea-pill-ok'
    case 'conflict':
      return 'ea-pill-warn'
    case 'failed':
      return 'ea-pill-err'
    case 'running':
      return 'ea-pill-info'
    default:
      return 'ea-pill-muted'
  }
}

function statusLabel(status: ModemBaselineRunMeta['status']) {
  switch (status) {
    case 'success':
      return '已完成'
    case 'conflict':
      return '冲突停驻'
    case 'failed':
      return '执行失败'
    case 'running':
      return '执行中'
    default:
      return '待启动'
  }
}

function shortId(runId: string) {
  return runId.length > 18 ? `${runId.slice(0, 8)}…${runId.slice(-6)}` : runId
}
</script>

<template>
  <div class="ea-card history-panel">
    <div class="panel-head">
      <div>
        <div class="ea-section-title">历史升级任务</div>
        <h3 class="panel-title">最近 {{ visibleRuns.length }} 条</h3>
      </div>
      <NButton secondary size="small" :loading="loading" @click="emit('refresh')">刷新</NButton>
    </div>

    <div v-if="visibleRuns.length" class="task-list">
      <button
        v-for="item in visibleRuns"
        :key="item.runId"
        type="button"
        class="task-item"
        :class="{ active: item.runId === selectedRunId }"
        @click="emit('select', item.runId)"
      >
        <div class="task-main">
          <strong>{{ item.config.NODE_BRANCH || '—' }} → {{ item.config.target_BRANCH || '—' }}</strong>
          <span class="task-id">{{ shortId(item.runId) }}</span>
          <span class="task-line">{{ item.config.JIRAID || item.config.AP_lable || '未填写标识' }}</span>
        </div>
        <span :class="toneClass(item.status)">{{ statusLabel(item.status) }}</span>
      </button>
    </div>
    <div v-else class="empty-note">暂无历史升级任务，填写配置后启动首个基线任务。</div>
  </div>
</template>

<style scoped lang="scss">
.history-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex: 0 0 auto;
}

.panel-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--head);
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-right: 2px;
}

.task-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--bg);
  cursor: pointer;
  text-align: left;
  font: inherit;
  transition: border-color 0.18s, background 0.18s;

  &:hover {
    border-color: var(--line-strong);
  }

  &.active {
    border-color: color-mix(in srgb, var(--accent) 35%, var(--line));
    background: var(--accent-soft);
  }
}

.task-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;

  strong {
    font-size: 13px;
    color: var(--text);
    word-break: break-word;
  }
}

.task-id {
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: var(--muted);
}

.task-line {
  font-size: 12px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-note {
  flex: 1;
  display: grid;
  place-items: center;
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px dashed var(--line);
  color: var(--muted);
  font-size: 13px;
  background: color-mix(in srgb, var(--surface) 70%, transparent);
}
</style>
