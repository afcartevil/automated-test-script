<script setup lang="ts">
import { computed } from 'vue'
import type { RunSummary } from '@/api/tahp/adapt-pipeline'
import EaPill from '@/components/layout/EaPill.vue'

const props = defineProps<{
  items: RunSummary[]
  selectedId: string | null
  loading?: boolean
  busy?: boolean
}>()

const emit = defineEmits<{
  select: [runId: string]
  create: []
  discard: [runId: string]
}>()

const sortedItems = computed(() =>
  [...props.items].sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
)

function statusVariant(status: RunSummary['status']): 'ok' | 'info' | 'warn' | 'err' | 'muted' {
  switch (status) {
    case 'passed': return 'ok'
    case 'running': return 'info'
    case 'waiting_human': return 'warn'
    case 'failed':
    case 'aborted': return 'err'
    default: return 'muted'
  }
}

function statusLabel(status: RunSummary['status']): string {
  switch (status) {
    case 'draft': return '草稿'
    case 'running': return '运行中'
    case 'waiting_human': return '待人工'
    case 'paused': return '已暂停'
    case 'passed': return '已完成'
    case 'failed': return '失败'
    case 'aborted': return '已终止'
    default: return status
  }
}

function fmtRelTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  return new Date(iso).toLocaleString()
}

function onDiscard(ev: Event, runId: string) {
  ev.stopPropagation()
  if (!window.confirm('确认删除该草稿运行？删除后不可恢复。')) return
  emit('discard', runId)
}
</script>

<template>
  <aside class="pipeline-run-list card">
    <h3>运行列表</h3>

    <div v-if="loading && !items.length" class="list-empty">加载中…</div>
    <div v-else-if="!items.length" class="list-empty">还没有运行记录</div>

    <div
      v-for="item in sortedItems"
      :key="item.run_id"
      class="run-item"
      :class="{ selected: selectedId === item.run_id }"
      role="button"
      tabindex="0"
      @click="emit('select', item.run_id)"
      @keydown.enter="emit('select', item.run_id)"
    >
      <div class="run-main">
        <strong>{{ item.project_code }}</strong>
        <span class="run-meta">第 {{ item.iteration }} 轮 · {{ fmtRelTime(item.updated_at) }}</span>
      </div>
      <div class="run-side">
        <EaPill :variant="statusVariant(item.status)">{{ statusLabel(item.status) }}</EaPill>
        <button
          v-if="item.status === 'draft'"
          type="button"
          class="btn-discard"
          title="删除草稿"
          :disabled="busy"
          @click="onDiscard($event, item.run_id)"
        >
          删除
        </button>
      </div>
    </div>

    <button type="button" class="btn-new" @click="emit('create')">
      + 新建运行
    </button>
  </aside>
</template>

<style scoped lang="scss">
.pipeline-run-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px;
  min-height: 420px;
}

.card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 20px;
  box-shadow: var(--shadow);
}

h3 {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 800;
  color: var(--faint);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.list-empty {
  padding: 24px 8px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}

.run-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid transparent;
  cursor: pointer;
  background: var(--bg);
  text-align: left;
  width: 100%;
  color: inherit;
  font-family: inherit;

  &:hover { border-color: var(--line-strong); }
  &.selected {
    background: var(--accent-soft);
    border-color: color-mix(in srgb, var(--accent) 28%, transparent);
  }
}

.run-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;

  strong {
    font-size: 13px;
    font-weight: 700;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.run-meta {
  font-size: 11.5px;
  color: var(--muted);
}

.run-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  flex-shrink: 0;
}

.btn-discard {
  border: none;
  background: transparent;
  color: var(--err, #c0392b);
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  padding: 0 2px;
  font-family: inherit;

  &:hover:not(:disabled) { text-decoration: underline; }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

.btn-new {
  margin-top: auto;
  border: 1px dashed var(--line-strong);
  background: transparent;
  padding: 12px;
  border-radius: 14px;
  color: var(--muted);
  font-weight: 700;
  cursor: pointer;
  font-family: inherit;

  &:hover {
    border-color: var(--accent);
    color: var(--accent);
    background: var(--accent-soft);
  }
}
</style>
