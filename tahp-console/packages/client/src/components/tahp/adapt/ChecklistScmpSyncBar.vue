<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NButton, NInput, NProgress, useMessage } from 'naive-ui'
import EaPill from '@/components/layout/EaPill.vue'
import {
  CHECKLIST_SCMP_HINT,
  CHECKLIST_SCMP_PLACEHOLDER,
  useChecklistScmpSyncStore,
} from '@/stores/tahp/checklist-scmp-sync'

const message = useMessage()
const store = useChecklistScmpSyncStore()
const logBox = ref<HTMLElement | null>(null)

const statusVariant = computed(() => {
  const s = store.currentRun?.status
  if (s === 'completed') return 'ok' as const
  if (s === 'failed') return 'err' as const
  if (s === 'cancelled') return 'warn' as const
  if (s === 'running' || s === 'pending') return 'info' as const
  return 'muted' as const
})

const statusLabel = computed(() => {
  const s = store.currentRun?.status
  if (s === 'completed') return '已完成'
  if (s === 'failed') return '失败'
  if (s === 'cancelled') return '已取消'
  if (s === 'running') return '执行中'
  if (s === 'pending') return '启动中'
  return '未开始'
})

const showPanel = computed(() => Boolean(store.currentRun || store.liveLines.length || store.error))

const sheetLabel = computed(() => {
  const run = store.currentRun
  if (!run?.sheet_total) return ''
  const index = run.sheet_index || 0
  const name = run.current_sheet ? ` · ${run.current_sheet}` : ''
  return `${index}/${run.sheet_total}${name}`
})

async function scrollLog() {
  await nextTick()
  const el = logBox.value
  if (el) el.scrollTop = el.scrollHeight
}

watch(() => store.liveLines.length, () => { void scrollLog() })

onMounted(() => {
  void store.hydrate()
})

onBeforeUnmount(() => {
  store.stopPoll()
})

async function onStart() {
  await store.start()
  if (store.error) message.error(store.error)
  else message.success('已开始查询并回写飞书表格')
  await scrollLog()
}

async function onCancel() {
  await store.cancel()
  if (store.error) message.error(store.error)
  else message.warning('已请求取消')
}
</script>

<template>
  <div class="scmp-sync-bar">
    <div class="scmp-sync-row">
      <NInput
        v-model:value="store.url"
        size="small"
        :placeholder="CHECKLIST_SCMP_PLACEHOLDER"
        :disabled="store.isRunning || store.submitting"
        class="scmp-sync-input"
        @keyup.enter="onStart"
      />
      <NButton
        v-if="!store.isRunning"
        size="small"
        type="primary"
        :loading="store.submitting"
        :disabled="!store.url.trim()"
        @click="onStart"
      >
        开始
      </NButton>
      <NButton
        v-else
        size="small"
        type="warning"
        secondary
        @click="onCancel"
      >
        取消
      </NButton>
    </div>
    <p class="scmp-sync-hint">{{ CHECKLIST_SCMP_HINT }}</p>

    <div v-if="showPanel" class="scmp-sync-panel">
      <div class="scmp-sync-meta">
        <EaPill :variant="statusVariant">{{ statusLabel }}</EaPill>
        <span v-if="store.currentRun?.title" class="scmp-sync-title">{{ store.currentRun.title }}</span>
        <span v-if="store.currentRun?.project" class="scmp-sync-kv">
          {{ store.currentRun.project }} / tOS {{ store.currentRun.tos_version }}
        </span>
        <span v-if="sheetLabel" class="scmp-sync-kv">{{ sheetLabel }}</span>
      </div>
      <NProgress
        type="line"
        :percentage="store.progress"
        :status="store.currentRun?.status === 'failed' ? 'error' : store.currentRun?.status === 'completed' ? 'success' : 'info'"
        :show-indicator="true"
      />
      <p class="scmp-sync-message">{{ store.currentRun?.message || store.error || '' }}</p>
      <div v-if="store.currentRun?.summary" class="scmp-sync-summary">
        共 {{ store.currentRun.summary.sheet_count }} 张表 /
        {{ store.currentRun.summary.feature_count }} 条编码：
        支持 {{ store.currentRun.summary.supported }}，
        不支持 {{ store.currentRun.summary.unsupported }}，
        部分 {{ store.currentRun.summary.partial }}，
        编码不存在 {{ store.currentRun.summary.missing }}
        <template v-if="store.currentRun.summary.failed_sheets.length">
          ；失败 sheet：{{ store.currentRun.summary.failed_sheets.join('、') }}
        </template>
      </div>
      <div ref="logBox" class="scmp-sync-log">
        <div v-for="(line, idx) in store.liveLines" :key="idx" class="scmp-sync-log-line">{{ line }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.scmp-sync-bar {
  margin: -6px 0 16px;
  padding: 10px 12px 12px;
  border: 1px solid var(--line, rgba(255, 255, 255, 0.08));
  border-radius: 12px;
  background: var(--surface, rgba(255, 255, 255, 0.03));
}

.scmp-sync-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.scmp-sync-input {
  flex: 1;
  min-width: 0;
}

.scmp-sync-hint {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--muted);
}

.scmp-sync-panel {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.scmp-sync-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.scmp-sync-title,
.scmp-sync-kv {
  color: var(--text);
}

.scmp-sync-message {
  margin: 0;
  font-size: 13px;
  color: var(--text);
}

.scmp-sync-summary {
  font-size: 12px;
  color: var(--muted);
}

.scmp-sync-log {
  max-height: 180px;
  overflow: auto;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--surface-2, rgba(0, 0, 0, 0.18));
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.45;
}

.scmp-sync-log-line {
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
