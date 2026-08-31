<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NSelect } from 'naive-ui'
import type { GkiAnalysisTaskSummary, GkiUpgradeJobSummary } from '@/api/tahp/gki-patch'

export type GkiHistoryKind = 'upgrade' | 'analysis'

const props = defineProps<{
  kind: GkiHistoryKind
  jobs: GkiUpgradeJobSummary[]
  tasks: GkiAnalysisTaskSummary[]
  selectedId?: string
  loading?: boolean
  limit?: number
}>()

const emit = defineEmits<{
  'update:kind': [kind: GkiHistoryKind]
  select: [id: string]
  refresh: []
  create: []
  open: [id: string]
}>()

type StatusFilter = 'all' | 'running' | 'conflicts' | 'failed' | 'completed' | 'other'

const statusFilter = ref<StatusFilter>('all')

watch(
  () => props.kind,
  () => {
    statusFilter.value = 'all'
  },
)

const upgradeFilterOptions = [
  { label: '全部', value: 'all' },
  { label: '进行中', value: 'running' },
  { label: '冲突', value: 'conflicts' },
  { label: '失败', value: 'failed' },
  { label: '已完成', value: 'completed' },
]

const analysisFilterOptions = [
  { label: '全部', value: 'all' },
  { label: '进行中', value: 'running' },
  { label: '失败', value: 'failed' },
  { label: '已完成', value: 'completed' },
]

const filterOptions = computed(() =>
  props.kind === 'upgrade' ? upgradeFilterOptions : analysisFilterOptions,
)

function normalizeStatus(status?: string) {
  const s = String(status || '').toLowerCase()
  if (['running', 'pending', 'awaiting_ssh', 'awaiting_otp', 'applied', 'committed', 'analyzing'].includes(s)) {
    return 'running'
  }
  if (s === 'conflicts' || s.includes('conflict')) return 'conflicts'
  if (s.includes('fail') || s === 'cancelled' || s === 'error') return 'failed'
  if (s === 'completed' || s === 'success' || s === 'done') return 'completed'
  return 'other'
}

type ListItem = {
  id: string
  title: string
  subtitle?: string
  status?: string
}

const listItems = computed<ListItem[]>(() => {
  const limit = props.limit ?? 50
  if (props.kind === 'upgrade') {
    const list = statusFilter.value === 'all'
      ? props.jobs
      : props.jobs.filter(item => normalizeStatus(item.status) === statusFilter.value)
    return list.slice(0, limit).map(item => ({
      id: String(item.id || ''),
      title: `${item.from_tag || '—'} → ${item.to_tag || '—'}`,
      subtitle: item.phase ? `阶段：${item.phase}` : undefined,
      status: item.status,
    }))
  }
  const list = statusFilter.value === 'all'
    ? props.tasks
    : props.tasks.filter(item => normalizeStatus(item.status) === statusFilter.value)
  return list.slice(0, limit).map(item => {
    const title = item.type === 'single'
      ? (item.sha || '单笔分析')
      : `${item.from_tag || '—'} → ${item.to_tag || '—'}`
    return {
      id: String(item.id || ''),
      title,
      subtitle: item.type === 'single' ? '单笔' : '区间',
      status: item.status,
    }
  })
})

const sectionTitle = computed(() =>
  props.kind === 'upgrade' ? '历史升级任务' : '历史分析任务',
)

const emptyHint = computed(() => {
  if (statusFilter.value !== 'all') return '当前筛选条件下暂无任务。'
  return props.kind === 'upgrade'
    ? '暂无升级任务。可采用外部通知或右侧填写 Tag 后前往合入。'
    : '暂无分析任务。可前往 patch 分析创建任务。'
})

function toneClass(status?: string) {
  switch (normalizeStatus(status)) {
    case 'completed':
      return 'ea-pill-ok'
    case 'conflicts':
      return 'ea-pill-warn'
    case 'failed':
      return 'ea-pill-err'
    case 'running':
      return 'ea-pill-info'
    default:
      return 'ea-pill-muted'
  }
}

function statusLabel(status?: string) {
  const s = String(status || '').trim()
  if (!s) return '未知'
  return s
}

function shortId(id: string) {
  return id.length > 18 ? `${id.slice(0, 8)}…${id.slice(-6)}` : id
}

function middleEllipsis(text: string, head = 18, tail = 12) {
  const value = String(text || '').trim()
  if (!value) return '—'
  if (value.length <= head + tail + 1) return value
  return `${value.slice(0, head)}…${value.slice(-tail)}`
}

function onOpen(event: Event, id: string) {
  event.stopPropagation()
  emit('open', id)
}

function setKind(kind: GkiHistoryKind) {
  if (kind === props.kind) return
  emit('update:kind', kind)
}
</script>

<template>
  <div class="ea-card history-panel">
    <div class="panel-head">
      <div>
        <div class="ea-section-title">任务列表</div>
        <h3 class="panel-title">{{ sectionTitle }} · {{ listItems.length }}</h3>
      </div>
      <div class="panel-actions">
        <NSelect
          v-model:value="statusFilter"
          size="small"
          :options="filterOptions"
          class="status-filter"
        />
        <NButton
          v-if="kind === 'upgrade'"
          type="primary"
          size="small"
          title="打开右侧新建合入"
          @click="emit('create')"
        >
          新建合入
        </NButton>
        <NButton
          v-else
          type="primary"
          size="small"
          title="前往 patch 分析"
          @click="emit('create')"
        >
          新建分析
        </NButton>
        <NButton secondary size="small" :loading="loading" @click="emit('refresh')">刷新</NButton>
      </div>
    </div>

    <div class="kind-tabs" role="tablist" aria-label="任务类型">
      <button
        type="button"
        class="kind-tab"
        role="tab"
        :aria-selected="kind === 'upgrade'"
        :class="{ active: kind === 'upgrade' }"
        @click="setKind('upgrade')"
      >
        升级任务
        <span class="kind-count">{{ jobs.length }}</span>
      </button>
      <button
        type="button"
        class="kind-tab"
        role="tab"
        :aria-selected="kind === 'analysis'"
        :class="{ active: kind === 'analysis' }"
        @click="setKind('analysis')"
      >
        分析任务
        <span class="kind-count">{{ tasks.length }}</span>
      </button>
    </div>

    <div v-if="listItems.length" class="task-list">
      <button
        v-for="item in listItems"
        :key="item.id"
        type="button"
        class="task-item"
        :class="{ active: item.id === selectedId }"
        @click="emit('select', item.id)"
      >
        <div class="task-main">
          <strong :title="item.title">{{ middleEllipsis(item.title) }}</strong>
          <span class="task-id">{{ shortId(item.id) }}</span>
          <span v-if="item.subtitle" class="task-line">{{ item.subtitle }}</span>
        </div>
        <div class="task-side">
          <span :class="toneClass(item.status)">{{ statusLabel(item.status) }}</span>
          <NButton size="tiny" secondary @click="onOpen($event, item.id)">
            打开
          </NButton>
        </div>
      </button>
    </div>
    <div v-else class="empty-note">{{ emptyHint }}</div>
  </div>
</template>

<style scoped lang="scss">
.history-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
  padding: 12px 14px;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex: 0 0 auto;
}

.panel-title {
  margin: 2px 0 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--head);
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.status-filter {
  width: 110px;
}

.kind-tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  flex: 0 0 auto;
  padding: 4px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--sky-bg) 55%, var(--surface, #fff));
  border: 1px solid color-mix(in srgb, var(--sky-ic) 12%, var(--line));
}

.kind-tab {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 7px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;

  &:hover {
    color: var(--sky-fg);
  }

  &.active {
    color: var(--sky-fg);
    background: var(--surface, #fff);
    box-shadow: 0 1px 2px color-mix(in srgb, var(--sky-ic) 12%, transparent);
  }
}

.kind-count {
  min-width: 1.4em;
  padding: 0 5px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  background: color-mix(in srgb, var(--sky-ic) 12%, transparent);
}

.task-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface, #fff);
  text-align: left;
  cursor: pointer;
  font: inherit;
  color: inherit;

  &:hover {
    border-color: color-mix(in srgb, var(--sky-ic) 30%, var(--line));
  }

  &.active {
    border-color: color-mix(in srgb, var(--accent) 40%, var(--line));
    background: color-mix(in srgb, var(--accent) 6%, var(--surface, #fff));
  }
}

.task-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;

  strong {
    font-size: 13px;
    color: var(--head);
  }
}

.task-id,
.task-line {
  font-size: 11px;
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.task-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  flex: 0 0 auto;
}

.empty-note {
  flex: 1;
  display: grid;
  place-items: center;
  font-size: 13px;
  color: var(--muted);
  padding: 20px 8px;
}
</style>
