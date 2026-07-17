<script setup lang="ts">
import { computed } from 'vue'
import type { ModemBaselineRunMeta } from '@/api/tahp/modem-baseline'

const props = defineProps<{
  runs: ModemBaselineRunMeta[]
  selectedRunId: string
}>()

const emit = defineEmits<{
  select: [runId: string]
}>()

const visibleRuns = computed(() => props.runs.slice(0, 5))

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
      return '合并中'
    default:
      return '待启动'
  }
}
</script>

<template>
  <div class="ea-card ea-stack">
    <div>
      <div class="ea-section-title">最近任务</div>
      <h3 class="panel-title">运行历史</h3>
      <p class="panel-sub">保留原独立工具中的历史感知能力，但视觉统一到 EasyAdapter。</p>
    </div>

    <div class="ea-tasklist">
      <button
        v-for="item in visibleRuns"
        :key="item.runId"
        type="button"
        class="ea-task-item"
        :class="{ active: item.runId === selectedRunId }"
        @click="emit('select', item.runId)"
      >
        <div class="task-head">
          <strong>{{ item.runId }}</strong>
          <span :class="toneClass(item.status)">{{ statusLabel(item.status) }}</span>
        </div>
        <span class="task-line">{{ item.config.JIRAID || item.config.AP_lable }}</span>
        <span class="task-line muted">{{ item.config.NODE_BRANCH }} -> {{ item.config.target_BRANCH }}</span>
        <span class="task-line muted">{{ item.finishedAt || item.startedAt || item.createdAt }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.panel-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--head);
}

.panel-sub {
  font-size: 13px;
  color: var(--muted);
  margin-top: 4px;
}

.task-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.task-line {
  font-size: 12.5px;
  color: var(--text);

  &.muted {
    color: var(--muted);
  }
}
</style>
