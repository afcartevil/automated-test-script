<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import EaLogViewer from '@/components/common/EaLogViewer.vue'
import type { TimelineView } from '@/api/tahp/adapt-pipeline'
import type { useAdaptPipelineStore } from '@/stores/tahp/adapt-pipeline'

const props = defineProps<{
  open: boolean
  timeline: TimelineView
  store: ReturnType<typeof useAdaptPipelineStore>
}>()

const emit = defineEmits<{
  close: []
}>()

const stageFilter = ref('all')
const loading = ref(false)

const enabledNodes = computed(() => props.timeline.nodes.filter(node => node.enabled))

const failedStages = computed(() =>
  enabledNodes.value
    .filter(node => Boolean(props.store.getNodeLogError(props.timeline.run_id, node.key)))
    .map(node => ({
      key: node.key,
      label: node.label,
      message: props.store.getNodeLogError(props.timeline.run_id, node.key) as string,
    })),
)

const visibleFailedStages = computed(() =>
  stageFilter.value === 'all'
    ? failedStages.value
    : failedStages.value.filter(item => item.key === stageFilter.value),
)

const aggregatedLines = computed(() => {
  const nodes = stageFilter.value === 'all'
    ? enabledNodes.value
    : enabledNodes.value.filter(node => node.key === stageFilter.value)
  const lines: string[] = []
  for (const node of nodes) {
    const raw = props.store.getNodeLogs(props.timeline.run_id, node.key)
    for (const line of raw) {
      lines.push(stageFilter.value === 'all' ? `[${node.label}] ${line}` : line)
    }
  }
  return lines
})

watch(
  () => [props.open, props.timeline.run_id, enabledNodes.value.map(node => node.key).join(',')] as const,
  async ([open]) => {
    if (!open) return
    stageFilter.value = 'all'
    loading.value = true
    try {
      await props.store.loadAllNodeLogs(
        props.timeline.run_id,
        enabledNodes.value.map(node => node.key),
      )
    } finally {
      loading.value = false
    }
  },
  { immediate: true },
)
</script>

<template>
  <div v-if="open" class="mask" @click.self="emit('close')">
    <aside class="drawer" role="dialog" aria-label="全部阶段日志">
      <header class="head">
        <div>
          <h3>全部阶段日志</h3>
          <p>{{ timeline.project_code }} · 实时缓冲会随运行更新</p>
        </div>
        <div class="head-tools">
          <label class="stage-filter">
            <span>阶段</span>
            <select v-model="stageFilter">
              <option value="all">全部阶段</option>
              <option v-for="node in enabledNodes" :key="node.key" :value="node.key">
                {{ node.label }}
              </option>
            </select>
          </label>
          <button type="button" class="icon-btn" aria-label="关闭" @click="emit('close')">×</button>
        </div>
      </header>

      <div class="body">
        <div v-if="visibleFailedStages.length" class="errors">
          <p v-for="item in visibleFailedStages" :key="item.key">
            {{ item.label }}：{{ item.message }}
          </p>
        </div>
        <p v-if="loading" class="loading">正在加载各阶段日志…</p>
        <EaLogViewer :lines="aggregatedLines" :height="720" />
      </div>
    </aside>
  </div>
</template>

<style scoped lang="scss">
.mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.28);
  z-index: 90;
  display: grid;
  justify-items: end;
}
.drawer {
  width: min(1100px, 96vw);
  height: 100%;
  background: var(--surface, #fff);
  box-shadow: -12px 0 40px rgba(15, 23, 42, 0.12);
  display: grid;
  grid-template-rows: auto 1fr;
  min-width: 0;
}
.head {
  padding: 16px 18px 12px;
  border-bottom: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  h3 { margin: 0; font-size: 16px; font-weight: 800; }
  p { margin: 6px 0 0; font-size: 12px; color: var(--muted); line-height: 1.55; }
}
.head-tools {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}
.stage-filter {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--muted);
  select {
    padding: 6px 10px;
    border-radius: 8px;
    border: 1px solid var(--line);
    background: var(--surface);
    font-size: 12px;
    color: inherit;
  }
}
.icon-btn {
  border: none;
  background: var(--surface-2, #f1f5f9);
  width: 28px;
  height: 28px;
  border-radius: 8px;
  color: #475569;
  font-size: 16px;
  cursor: pointer;
}
.body {
  --ea-log-height: calc(100dvh - 148px);
  padding: 14px 18px;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.errors {
  margin: 0;
  padding: 8px 10px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--err, #c0392b) 8%, var(--surface));
  color: var(--err, #c0392b);
  font-size: 12px;
  p { margin: 0; }
  p + p { margin-top: 4px; }
}
.loading {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
}
</style>
