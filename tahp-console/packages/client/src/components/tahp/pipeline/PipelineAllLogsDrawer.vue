<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import EaLogViewer from '@/components/common/EaLogViewer.vue'
import type { TimelineView } from '@/api/tahp/adapt-pipeline'
import type { useAdaptPipelineStore } from '@/stores/tahp/adapt-pipeline'
import { formatOsRange, formatPipelineProjectTitle } from '@/utils/pipeline-os-label'

const props = defineProps<{
  open: boolean
  timeline: TimelineView
  store: ReturnType<typeof useAdaptPipelineStore>
}>()

const emit = defineEmits<{
  close: []
}>()

interface LogEntry {
  stageLabel: string
  tone: number
  time: string
  fullTime: string
  tag: string
  message: string
}

const TONE_COUNT = 6
const TIME_PREFIX = /^\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\]\s*/
const TAG_PREFIX = /^\[([^\][]{1,12})\]\s*/

const stageFilter = ref('all')
const loading = ref(false)
const errorsOpen = ref(true)

const enabledNodes = computed(() => props.timeline.nodes.filter(node => node.enabled))

const projectTitle = computed(() =>
  formatPipelineProjectTitle(props.timeline.project_code, props.timeline.to_os),
)

const osLabel = computed(() =>
  formatOsRange(props.timeline.from_os, props.timeline.to_os),
)

const isLive = computed(() => props.timeline.status === 'running')

const stageTabs = computed(() =>
  enabledNodes.value.map((node, idx) => ({
    key: node.key,
    label: node.label,
    tone: idx % TONE_COUNT,
    count: props.store.getNodeLogs(props.timeline.run_id, node.key).length,
  })),
)

const totalCount = computed(() => stageTabs.value.reduce((sum, tab) => sum + tab.count, 0))

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

function formatClock(iso: string): { time: string, fullTime: string } {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return { time: '', fullTime: '' }
  return {
    time: date.toLocaleTimeString('zh-CN', { hour12: false }),
    fullTime: date.toLocaleString('zh-CN', { hour12: false }),
  }
}

function parseLine(raw: string, stageLabel: string, tone: number): LogEntry {
  let rest = raw
  let clock = { time: '', fullTime: '' }
  const timeMatch = rest.match(TIME_PREFIX)
  if (timeMatch) {
    clock = formatClock(timeMatch[1])
    rest = rest.slice(timeMatch[0].length)
  }
  let tag = ''
  const tagMatch = rest.match(TAG_PREFIX)
  if (tagMatch) {
    tag = tagMatch[1]
    rest = rest.slice(tagMatch[0].length)
  }
  return { stageLabel, tone, ...clock, tag, message: rest }
}

const entries = computed(() => {
  const tabs = stageFilter.value === 'all'
    ? stageTabs.value
    : stageTabs.value.filter(tab => tab.key === stageFilter.value)
  const out: { search: string, entry: LogEntry }[] = []
  for (const tab of tabs) {
    for (const raw of props.store.getNodeLogs(props.timeline.run_id, tab.key)) {
      out.push({ search: `${tab.label} ${raw}`, entry: parseLine(raw, tab.label, tab.tone) })
    }
  }
  return out
})

const searchLines = computed(() => entries.value.map(item => item.search))
const showStage = computed(() => stageFilter.value === 'all')

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
        <div class="head-main">
          <h3>全部阶段日志</h3>
          <p class="meta">
            <span>{{ projectTitle }}</span>
            <span v-if="osLabel">{{ osLabel }}</span>
            <span v-if="isLive" class="live"><i />实时更新</span>
          </p>
        </div>
        <button type="button" class="icon-btn" aria-label="关闭" @click="emit('close')">×</button>
      </header>

      <nav class="stage-tabs" aria-label="按阶段筛选">
        <button
          type="button"
          class="tab"
          :class="{ active: stageFilter === 'all' }"
          @click="stageFilter = 'all'"
        >
          全部<em>{{ totalCount }}</em>
        </button>
        <button
          v-for="tab in stageTabs"
          :key="tab.key"
          type="button"
          class="tab"
          :class="{ active: stageFilter === tab.key, empty: tab.count === 0 }"
          :data-stage="tab.key"
          @click="stageFilter = tab.key"
        >
          <i class="dot" :class="`tone-${tab.tone}`" />{{ tab.label }}<em>{{ tab.count }}</em>
        </button>
        <span v-if="loading" class="loading">加载中…</span>
      </nav>

      <div class="body">
        <div v-if="visibleFailedStages.length" class="errors">
          <button type="button" class="errors-toggle" @click="errorsOpen = !errorsOpen">
            {{ visibleFailedStages.length }} 个阶段日志加载失败
            <span>{{ errorsOpen ? '收起' : '展开' }}</span>
          </button>
          <div v-if="errorsOpen">
            <p v-for="item in visibleFailedStages" :key="item.key">
              {{ item.label }}：{{ item.message }}
            </p>
          </div>
        </div>
        <EaLogViewer :lines="searchLines" :height="720">
          <template #line="{ index }">
            <div v-if="entries[index]" class="ln">
              <span class="ln-time" :title="entries[index].entry.fullTime">{{ entries[index].entry.time }}</span>
              <span
                v-if="showStage"
                class="ln-stage"
                :class="`tone-${entries[index].entry.tone}`"
              >{{ entries[index].entry.stageLabel }}</span>
              <span class="ln-msg"><b v-if="entries[index].entry.tag" class="ln-tag">{{ entries[index].entry.tag }}</b>{{ entries[index].entry.message }}</span>
            </div>
          </template>
        </EaLogViewer>
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
  grid-template-rows: auto auto 1fr;
  min-width: 0;
}
.head {
  padding: 16px 18px 10px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  h3 { margin: 0; font-size: 16px; font-weight: 800; }
}
.meta {
  margin: 6px 0 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
  span + span::before {
    content: '·';
    margin-right: 6px;
    color: var(--faint);
  }
}
.live {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--success);
  font-weight: 600;
  i {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    animation: pulse 1.6s ease-in-out infinite;
  }
}
@keyframes pulse {
  50% { opacity: 0.3; }
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
  flex-shrink: 0;
}
.stage-tabs {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 0 18px 12px;
  border-bottom: 1px solid var(--line);
}
.tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--text);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  em {
    font-style: normal;
    font-size: 11px;
    color: var(--faint);
  }
  &.empty { color: var(--faint); }
  &.active {
    border-color: var(--accent);
    background: var(--accent-soft);
    color: var(--accent);
    font-weight: 700;
    em { color: inherit; }
  }
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.loading {
  margin-left: auto;
  font-size: 12px;
  color: var(--muted);
}
.body {
  --ea-log-height: calc(100dvh - 178px);
  padding: 12px 18px 14px;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.errors {
  margin: 0;
  padding: 6px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--error) 8%, var(--surface));
  color: var(--error);
  font-size: 12px;
  p { margin: 6px 0 0; }
}
.errors-toggle {
  display: flex;
  justify-content: space-between;
  width: 100%;
  border: none;
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
  padding: 0;
  span { font-weight: 600; color: var(--muted); }
}
.ln {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.ln-time {
  flex: 0 0 60px;
  color: #6b7289;
  font-variant-numeric: tabular-nums;
}
.ln-stage {
  flex: 0 0 auto;
  min-width: 56px;
  font-size: 11px;
  font-weight: 700;
}
.ln-msg {
  flex: 1;
  min-width: 0;
  white-space: pre-wrap;
  word-break: break-word;
}
.ln-tag {
  margin-right: 6px;
  font-weight: 400;
  color: #8b90a0;
}
/* 阶段色板：页签色点与日志行阶段名共用，按启用顺序循环 */
.tone-0 { color: #7aa2f7; }
.tone-1 { color: #bb9af7; }
.tone-2 { color: #7dcfff; }
.tone-3 { color: #9ece6a; }
.tone-4 { color: #e0af68; }
.tone-5 { color: #73daca; }
.dot { background: currentColor; }
</style>
