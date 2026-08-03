<script setup lang="ts">
import { computed, watch } from 'vue'
import EaCard from '@/components/layout/EaCard.vue'
import EaPill from '@/components/layout/EaPill.vue'
import EaStageStepper from '@/components/common/EaStageStepper.vue'
import PipelineNodeList from './PipelineNodeList.vue'
import PipelineNodePanel from './PipelineNodePanel.vue'
import PipelineHumanPanel from './PipelineHumanPanel.vue'
import PipelineIterationBar from './PipelineIterationBar.vue'
import {
  formatDurationMs,
  runStatusLabel,
  type TimelineView,
  type RunStatus,
} from '@/api/tahp/adapt-pipeline'
import type { useAdaptPipelineStore } from '@/stores/tahp/adapt-pipeline'

const props = defineProps<{
  timeline: TimelineView
  selectedNodeKey: string | null
  store: ReturnType<typeof useAdaptPipelineStore>
  humanDrawer?: boolean
}>()

const emit = defineEmits<{
  selectNode: [nodeKey: string]
  openHuman: []
  discarded: [nextRunId: string | null]
}>()

const selectedNode = computed(() =>
  props.timeline.nodes.find(n => n.key === props.selectedNodeKey) ?? props.timeline.nodes[0] ?? null,
)

const selectedNodeLogs = computed(() => {
  if (!selectedNode.value) return []
  return props.store.getNodeLogs(props.timeline.run_id, selectedNode.value.key)
})

const canDiscardDraft = computed(() => props.timeline.status === 'draft')

const canAbort = computed(() =>
  !canDiscardDraft.value
  && !['passed', 'failed', 'aborted'].includes(props.timeline.status),
)

const osLabel = computed(() => {
  if (props.timeline.from_os && props.timeline.to_os) {
    return `tOS${props.timeline.from_os} → tOS${props.timeline.to_os}`
  }
  return ''
})

function statusVariant(status: RunStatus): 'ok' | 'info' | 'warn' | 'err' | 'muted' {
  switch (status) {
    case 'passed': return 'ok'
    case 'running': return 'info'
    case 'waiting_human': return 'warn'
    case 'failed':
    case 'aborted': return 'err'
    default: return 'muted'
  }
}

async function loadLogsForNode(nodeKey: string | null) {
  if (!nodeKey) return
  await props.store.loadNodeLogs(props.timeline.run_id, nodeKey, 500)
}

async function handleAbort() {
  if (!window.confirm('确认终止该流水线？将取消编译/适配/刷机等正在执行的 Agent 与外部任务。')) return
  await props.store.abortRun(props.timeline.run_id, '用户终止')
}

async function handleDiscardDraft() {
  if (!window.confirm('确认删除该草稿运行？删除后不可恢复。')) return
  const next = await props.store.discardDraftRun(props.timeline.run_id)
  emit('discarded', next)
}

watch(() => selectedNode.value?.key, (key) => {
  void loadLogsForNode(key ?? null)
}, { immediate: true })
</script>

<template>
  <div class="run-detail">
    <EaCard class="run-header">
      <div class="head-row">
        <div>
          <h2>
            {{ timeline.project_code }}
            <span v-if="osLabel" class="os">{{ osLabel }}</span>
          </h2>
          <p>
            第 {{ timeline.iteration }} 轮 / 共 {{ timeline.max_iterations }} 轮
            · 已运行 {{ formatDurationMs(timeline.duration_ms) }}
          </p>
        </div>
        <EaPill :variant="statusVariant(timeline.status)">{{ runStatusLabel(timeline.status) }}</EaPill>
      </div>
      <div class="head-actions">
        <button
          v-if="canDiscardDraft"
          type="button"
          class="btn-danger"
          :disabled="store.runActionBusy"
          @click="handleDiscardDraft"
        >
          删除草稿
        </button>
        <button
          v-if="canAbort"
          type="button"
          class="btn-danger"
          :disabled="store.runActionBusy"
          @click="handleAbort"
        >
          终止
        </button>
        <button
          v-if="humanDrawer && timeline.pending_human_count > 0"
          type="button"
          class="btn-warn"
          @click="emit('openHuman')"
        >
          ⚠ 人工介入 ({{ timeline.pending_human_count }})
        </button>
      </div>
    </EaCard>

    <EaCard class="stepper-card">
      <EaStageStepper
        :nodes="timeline.nodes"
        :active-key="selectedNode?.key ?? null"
        :iteration="timeline.iteration"
        @select="emit('selectNode', $event)"
      />
    </EaCard>

    <div class="cols" :class="{ drawer: humanDrawer }">
      <EaCard class="col-card">
        <h3>节点</h3>
        <PipelineNodeList
          :nodes="timeline.nodes"
          :selected-key="selectedNode?.key ?? null"
          @select="emit('selectNode', $event)"
        />
      </EaCard>

      <EaCard class="col-card">
        <PipelineNodePanel
          :node="selectedNode"
          :logs="selectedNodeLogs"
          :build-context="timeline.build_context"
        />
      </EaCard>

      <EaCard v-if="!humanDrawer" class="col-card human-col">
        <PipelineHumanPanel
          :run-id="timeline.run_id"
          :nodes="timeline.nodes"
          :store="store"
        />
      </EaCard>
    </div>

    <PipelineIterationBar
      :iterations="timeline.iterations"
      :current="timeline.iteration"
      :max-iterations="timeline.max_iterations"
    />
  </div>
</template>

<style scoped lang="scss">
.run-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
.run-header {
  padding: 14px 16px;
}
.head-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}
.head-row h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 800;
  .os {
    font-size: 13px;
    font-weight: 600;
    color: var(--muted);
    margin-left: 8px;
  }
}
.head-row p {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 12px;
}
.head-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
.btn-soft, .btn-danger, .btn-warn {
  padding: 7px 12px;
  border-radius: 10px;
  font-size: 13px;
  cursor: pointer;
  border: 1px solid var(--line);
  background: var(--surface);
}
.btn-danger {
  color: var(--err, #b03351);
  border-color: color-mix(in srgb, var(--err, #b03351) 30%, transparent);
}
.btn-warn {
  color: var(--warn);
  background: var(--warn-soft);
  border-color: color-mix(in srgb, var(--warn) 25%, transparent);
}
.stepper-card {
  padding: 12px 14px;
}
.cols {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr) minmax(260px, 320px);
  gap: 12px;
}
.col-card {
  padding: 12px;
  min-width: 0;
  overflow: hidden;
}
.human-col {
  overflow: auto;
}
.col-card h3 {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--faint);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
@media (max-width: 1400px) {
  .cols.drawer {
    grid-template-columns: 200px minmax(0, 1fr);
  }
  .cols:not(.drawer) {
    grid-template-columns: 200px minmax(0, 1fr);
  }
  .human-col {
    grid-column: 1 / -1;
  }
}
</style>
