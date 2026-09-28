<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDialog } from 'naive-ui'
import EaCard from '@/components/layout/EaCard.vue'
import EaPill from '@/components/layout/EaPill.vue'
import EaStageStepper from '@/components/common/EaStageStepper.vue'
import PipelineNodePanel from './PipelineNodePanel.vue'
import PipelineHumanPanel from './PipelineHumanPanel.vue'
import PipelineIterationBar from './PipelineIterationBar.vue'
import PipelineAppendStagesDrawer from './PipelineAppendStagesDrawer.vue'
import PipelineAllLogsDrawer from './PipelineAllLogsDrawer.vue'
import {
  formatDurationMs,
  runStatusLabel,
  type AppendableStageKey,
  type TimelineView,
  type RunStatus,
} from '@/api/tahp/adapt-pipeline'
import type { useAdaptPipelineStore } from '@/stores/tahp/adapt-pipeline'
import { formatOsRange, formatPipelineProjectTitle } from '@/utils/pipeline-os-label'

const props = defineProps<{
  timeline: TimelineView
  selectedNodeKey: string | null
  store: ReturnType<typeof useAdaptPipelineStore>
  humanDrawer?: boolean
}>()

const emit = defineEmits<{
  selectNode: [nodeKey: string]
  openHuman: []
}>()

const appendOpen = ref(false)
const allLogsOpen = ref(false)
const humanColRef = ref<HTMLElement | null>(null)

const pendingHumanCount = computed(() => {
  if (props.timeline.pending_human_count > 0) return props.timeline.pending_human_count
  return props.timeline.nodes.filter(node => node.status === 'waiting_human' && Boolean(node.human)).length
})

const hasPendingHuman = computed(() =>
  props.timeline.status === 'waiting_human' && pendingHumanCount.value > 0,
)

const showHumanColumn = computed(() => !props.humanDrawer && hasPendingHuman.value)

const selectedNode = computed(() =>
  props.timeline.nodes.find(n => n.key === props.selectedNodeKey) ?? props.timeline.nodes[0] ?? null,
)

const selectedNodeLogs = computed(() => {
  if (!selectedNode.value) return []
  return props.store.getNodeLogs(props.timeline.run_id, selectedNode.value.key)
})

const canAbort = computed(() =>
  !['draft', 'passed', 'failed', 'aborted'].includes(props.timeline.status),
)

const canFailCurrentStage = computed(() => {
  if (props.timeline.can_fail_current_stage) return true
  if (props.timeline.status !== 'running') return false
  const key = props.timeline.current_node
  if (key !== 'adapt' && key !== 'build' && key !== 'flash') return false
  return props.timeline.nodes.find(n => n.key === key)?.status === 'running'
})

const canAppend = computed(() =>
  props.timeline.status === 'passed'
  && Boolean(props.store.appendCandidates?.eligible),
)

const projectTitle = computed(() =>
  formatPipelineProjectTitle(props.timeline.project_code, props.timeline.to_os),
)

const osLabel = computed(() =>
  formatOsRange(props.timeline.from_os, props.timeline.to_os),
)

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

const dialog = useDialog()

async function loadLogsForNode(nodeKey: string | null) {
  if (!nodeKey) return
  await props.store.loadNodeLogs(props.timeline.run_id, nodeKey, 2000)
}

async function handleAbort() {
  dialog.error({
    title: '确认终止该流水线？',
    content: '将立即取消编译/适配/刷机等正在执行的 Agent 与外部任务，本次运行标记为已终止且不可恢复。已产出的日志和结果保留。',
    positiveText: '终止流水线',
    negativeText: '取消',
    onPositiveClick: () => props.store.abortRun(props.timeline.run_id, '用户终止'),
  })
}

async function handleFailCurrentStage() {
  if (!window.confirm(
    '确认停止当前步骤？将取消本步 Agent，并停止堡垒机上的编译/刷机进程。本步按失败转人工，可从恢复点继续，不会终止整条流水线。',
  )) return
  await props.store.failCurrentStage(props.timeline.run_id)
}

async function openAppendDrawer() {
  await props.store.loadAppendCandidates(props.timeline.run_id)
  if (!props.store.appendCandidates?.eligible) {
    window.alert(props.store.appendCandidates?.reason || '当前运行不可追加后续阶段')
    return
  }
  appendOpen.value = true
}

function firstWaitingNodeKey(): string | null {
  const waiting = props.timeline.nodes.find(n => n.status === 'waiting_human' && n.human)
    ?? props.timeline.nodes.find(n => n.status === 'waiting_human')
  return waiting?.key ?? null
}

function handleHumanClick() {
  const nodeKey = firstWaitingNodeKey()
  if (nodeKey) emit('selectNode', nodeKey)
  if (props.humanDrawer) {
    emit('openHuman')
    return
  }
  humanColRef.value?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
}

async function handleAppendConfirm(payload: {
  stages: AppendableStageKey[]
  gerrit_skip_flash?: boolean
  device_id?: string
}) {
  await props.store.appendStages(props.timeline.run_id, payload)
  appendOpen.value = false
  const first = payload.stages[0]
  if (first) emit('selectNode', first)
}

watch(() => selectedNode.value?.key, (key) => {
  void loadLogsForNode(key ?? null)
}, { immediate: true })

watch(
  () => [props.timeline.run_id, props.timeline.status] as const,
  ([runId, status]) => {
    appendOpen.value = false
    allLogsOpen.value = false
    if (status === 'passed') void props.store.loadAppendCandidates(runId)
  },
  { immediate: true },
)
</script>

<template>
  <div class="run-detail">
    <EaCard class="run-header">
      <div class="head-row">
        <div class="head-title">
          <h2>
            {{ projectTitle }}
            <span v-if="osLabel" class="os">{{ osLabel }}</span>
            <EaPill :variant="statusVariant(timeline.status)">{{ runStatusLabel(timeline.status) }}</EaPill>
          </h2>
          <p>
            第 {{ timeline.iteration }} 轮 / 共 {{ timeline.max_iterations }} 轮
            · 已运行 {{ formatDurationMs(timeline.duration_ms) }}
          </p>
        </div>
        <div class="head-actions">
          <button
            type="button"
            class="btn-logs"
            title="按阶段汇总查看本次运行的全部日志"
            @click="allLogsOpen = true"
          >
            <svg class="ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true">
              <path d="M2.5 4.5h11M2.5 8h7.5M2.5 11.5h9.5" />
            </svg>
            查看全部日志
          </button>
          <button
            v-if="canFailCurrentStage"
            type="button"
            class="btn-warn"
            :disabled="store.runActionBusy"
            @click="handleFailCurrentStage"
          >
            停止本步并转人工
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
            v-if="hasPendingHuman"
            type="button"
            class="btn-warn btn-human"
            @click="handleHumanClick"
          >
            ⚠ 人工介入 ({{ pendingHumanCount }})
          </button>
        </div>
      </div>
      <div class="stepper-slot">
        <EaStageStepper
          :nodes="timeline.nodes"
          :active-key="selectedNode?.key ?? null"
          :iteration="timeline.iteration"
          :show-append="canAppend"
          @select="emit('selectNode', $event)"
          @append="openAppendDrawer"
        />
      </div>
      <PipelineIterationBar
        :iterations="timeline.iterations"
        :current="timeline.iteration"
        :max-iterations="timeline.max_iterations"
      />
    </EaCard>

    <div class="cols" :class="{ drawer: humanDrawer, 'has-human': showHumanColumn }">
      <EaCard class="col-card">
        <PipelineNodePanel
          :node="selectedNode"
          :logs="selectedNodeLogs"
          :build-context="timeline.build_context"
        />
      </EaCard>

      <div v-if="showHumanColumn" ref="humanColRef" class="human-col-wrap">
        <EaCard class="col-card human-col">
          <PipelineHumanPanel
            :run-id="timeline.run_id"
            :nodes="timeline.nodes"
            :store="store"
          />
        </EaCard>
      </div>
    </div>

    <PipelineAppendStagesDrawer
      :open="appendOpen"
      :candidates="store.appendCandidates"
      :busy="store.actionBusy"
      :current-device-id="timeline.device_id"
      @close="appendOpen = false"
      @confirm="handleAppendConfirm"
    />

    <PipelineAllLogsDrawer
      :open="allLogsOpen"
      :timeline="timeline"
      :store="store"
      @close="allLogsOpen = false"
    />
  </div>
</template>

<style scoped lang="scss">
.run-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  flex: 1;
  min-height: 0;
}
.run-header {
  padding: 14px 16px 12px;
  border-radius: 16px;
}
.head-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  flex-wrap: wrap;
}
.head-title h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 800;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  .os {
    font-size: 12px;
    font-weight: 600;
    color: var(--muted);
    background: var(--surface-2);
    border-radius: 999px;
    padding: 2px 8px;
  }
}
.head-title p {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 12px;
}
.head-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}
.btn-logs, .btn-danger, .btn-warn {
  display: inline-flex;
  align-items: center;
  height: 30px;
  padding: 0 12px;
  border-radius: 8px;
  font-size: 12.5px;
  cursor: pointer;
  border: 1px solid var(--line);
  background: var(--surface);
  font-family: inherit;
}
.btn-logs {
  gap: 7px;
  padding: 0 14px 0 11px;
  border-radius: 999px;
  border-color: var(--line-strong);
  color: var(--text);
  font-weight: 600;
  transition: border-color 0.15s, color 0.15s;
  .ico {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
    color: var(--muted);
    transition: color 0.15s;
  }
  &:hover {
    border-color: var(--accent);
    color: var(--accent);
    .ico { color: var(--accent); }
  }
  &:active { transform: translateY(1px); }
  &:focus-visible {
    outline: 2px solid color-mix(in srgb, var(--accent) 50%, transparent);
    outline-offset: 1px;
  }
}
.btn-danger {
  color: var(--error);
  background: transparent;
  border-color: transparent;
}
.btn-warn {
  color: var(--warn);
  background: var(--surface);
  border-color: color-mix(in srgb, var(--warn) 22%, var(--line));
}
.stepper-slot {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--line);
}
.cols {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 12px;
  flex: 1;
  min-height: 0;
  align-items: stretch;

  &.has-human {
    grid-template-columns: minmax(0, 1fr) minmax(320px, 380px);
  }
}
.col-card {
  padding: 12px 14px;
  min-width: 0;
  overflow: hidden;
  height: 100%;
  display: flex;
  flex-direction: column;
  border-radius: 16px;
}
.human-col-wrap,
.human-col {
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow: auto;
}
@media (max-width: 1400px) {
  .cols,
  .cols.has-human,
  .cols.drawer {
    grid-template-columns: minmax(0, 1fr);
  }
  .human-col-wrap {
    grid-column: 1 / -1;
  }
}
</style>
