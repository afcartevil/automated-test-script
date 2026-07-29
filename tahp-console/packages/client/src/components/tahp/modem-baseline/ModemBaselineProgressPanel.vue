<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { ModemBaselineRunMeta } from '@/api/tahp/modem-baseline'
import { buildStageItems, getStatusMeta, type StageItem } from '@/composables/useModemBaseline'
import { MODEM_LOG_TAIL_LINES, takeModemLogTail } from '@/utils/modemBaselineLog'

const props = defineProps<{
  run: ModemBaselineRunMeta
  logContent?: string
}>()

const LOG_TAIL_LINES = MODEM_LOG_TAIL_LINES

const logBoxRef = ref<HTMLElement | null>(null)
const followLog = ref(true)
let removeScrollListener: (() => void) | null = null

const STAGE_META: Record<string, { icon: string; hint: string }> = {
  precheck: { icon: '🔧', hint: '检查工作区、映射路径与执行前置条件' },
  merge: { icon: '📦', hint: '合并源分支补丁到目标分支' },
  conflict: { icon: '⚠️', hint: '检测到冲突，等待人工处理' },
  resume: { icon: '▶️', hint: '冲突处理后继续 commit / post-merge / push' },
  build: { icon: '🔨', hint: '执行 ./tools/bld_modem.sh 自动编译' },
  archive: { icon: '💾', hint: '归档运行结果与报告' },
}

type ProgressStep = {
  key: string
  label: string
  icon: string
  hint: string
  status: 'done' | 'running' | 'pending' | 'failed' | 'conflicts'
}

const statusMeta = computed(() => getStatusMeta(props.run.status, props.run.error, props.run.phase))
const stageItems = computed(() => buildStageItems(props.run.status, props.run.error, props.run.phase))

const phaseSteps = computed<ProgressStep[]>(() =>
  stageItems.value.map((item: StageItem) => {
    const meta = STAGE_META[item.key] || { icon: '•', hint: '' }
    let status: ProgressStep['status'] = 'pending'
    if (item.state === 'done') status = 'done'
    else if (item.state === 'active') {
      if (props.run.status === 'failed') status = 'failed'
      else if (props.run.status === 'conflict' && item.key === 'conflict') status = 'conflicts'
      else if (props.run.status === 'success' && item.key === 'archive') status = 'done'
      else status = 'running'
    }
    return {
      key: item.key,
      label: item.label,
      icon: meta.icon,
      hint: meta.hint,
      status,
    }
  }),
)

const progressPercent = computed(() => {
  const steps = phaseSteps.value
  if (!steps.length) return 0
  if (props.run.status === 'success') return 100
  const activeIndex = steps.findIndex(step => step.status === 'running' || step.status === 'failed' || step.status === 'conflicts')
  if (activeIndex < 0) {
    const doneCount = steps.filter(step => step.status === 'done').length
    return Math.round((doneCount / steps.length) * 100)
  }
  return Math.min(99, Math.round((activeIndex / steps.length) * 100))
})

const headline = computed(() => {
  const active = phaseSteps.value.find(step => step.status === 'running' || step.status === 'failed' || step.status === 'conflicts')
  if (props.run.status === 'success') return '✅ 完成'
  if (active) return `${active.icon} ${active.label}`
  return statusMeta.value.label
})

const message = computed(() => statusMeta.value.summary)

/** 单块文本渲染，避免按行 v-for 产生大量 DOM；内容已在上下游截断 */
const displayLogText = computed(() => takeModemLogTail(String(props.logContent || ''), LOG_TAIL_LINES))

const hasLog = computed(() => Boolean(displayLogText.value.trim()))

function stepStatusText(status: ProgressStep['status']) {
  switch (status) {
    case 'done':
      return '√ 完成'
    case 'running':
      return '进行中'
    case 'failed':
      return '失败'
    case 'conflicts':
      return '冲突'
    default:
      return '待执行'
  }
}

function stepStatusTone(status: ProgressStep['status']) {
  if (status === 'done') return 'success'
  if (status === 'running') return 'info'
  if (status === 'conflicts' || status === 'failed') return 'danger'
  return 'muted'
}

watch(
  () => displayLogText.value,
  async () => {
    await nextTick()
    const box = logBoxRef.value
    if (!box || !followLog.value) return
    box.scrollTop = box.scrollHeight
  },
)

onMounted(() => {
  const box = logBoxRef.value
  if (!box) return
  const onScroll = () => {
    followLog.value = box.scrollHeight - box.scrollTop - box.clientHeight < 48
  }
  box.addEventListener('scroll', onScroll, { passive: true })
  removeScrollListener = () => box.removeEventListener('scroll', onScroll)
})

onBeforeUnmount(() => {
  removeScrollListener?.()
})
</script>

<template>
  <div class="execution-progress-section">
    <div class="execution-progress-summary">
      <div class="execution-progress-head">
        <strong>{{ headline }}</strong>
        <span class="muted">{{ progressPercent }}%</span>
      </div>
      <div class="progress-bar">
        <span :style="{ width: `${progressPercent}%` }" />
      </div>
      <div v-if="message" class="execution-progress-message muted">{{ message }}</div>
    </div>

    <div class="execution-progress-body">
      <div class="execution-progress-col">
        <div class="execution-column-title">执行阶段</div>
        <div class="execution-steps">
          <div
            v-for="step in phaseSteps"
            :key="step.key"
            class="execution-step-row"
            :class="step.status"
          >
            <span class="execution-step-icon">{{ step.icon }}</span>
            <div class="execution-step-body">
              <div class="execution-step-title">
                <span>{{ step.label }}</span>
                <span class="pill" :class="stepStatusTone(step.status)">{{ stepStatusText(step.status) }}</span>
              </div>
              <p v-if="step.hint" class="step-hint muted">{{ step.hint }}</p>
            </div>
          </div>
        </div>
      </div>

      <div class="execution-progress-col execution-log-section">
        <div class="execution-column-title log-title">
          <span>执行日志</span>
        </div>
        <pre ref="logBoxRef" class="execution-log-box">{{ hasLog ? displayLogText : '等待日志输出…' }}</pre>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.execution-progress-section {
  padding: 14px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
}

.execution-progress-summary {
  margin-bottom: 14px;
  padding-bottom: 14px;
  border-bottom: 1px solid #e2e8f0;
}

.execution-progress-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 14px;
}

.progress-bar {
  height: 8px;
  border-radius: 999px;
  background: #e5e7eb;
  overflow: hidden;

  span {
    display: block;
    height: 100%;
    background: linear-gradient(90deg, #2563eb, #60a5fa);
    transition: width 0.35s ease;
  }
}

.execution-progress-message {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
}

.execution-progress-body {
  display: grid;
  grid-template-columns: minmax(300px, 1.05fr) minmax(260px, 0.95fr);
  gap: 16px;
  align-items: start;
}

.execution-progress-col {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.execution-column-title {
  margin-bottom: 8px;
  color: #64748b;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.4;
  flex-shrink: 0;
}

.log-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.execution-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 360px;
  max-height: 360px;
  overflow: auto;
}

.execution-step-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 12px;

  &.running {
    border-color: #93c5fd;
    background: #eff6ff;
  }

  &.done {
    border-color: #bbf7d0;
    background: #f0fdf4;
  }

  &.failed,
  &.conflicts {
    border-color: #fecaca;
    background: #fff7f7;
  }
}

.execution-step-icon {
  flex-shrink: 0;
  width: 20px;
  text-align: center;
}

.execution-step-body {
  flex: 1;
  min-width: 0;
}

.execution-step-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
  color: #334155;
  font-weight: 600;
}

.step-hint {
  margin: 0;
  font-size: 11px;
  line-height: 1.4;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 700;
  border-radius: 999px;
  flex: 0 0 auto;

  &.info {
    color: #1d4ed8;
    background: #eaf2ff;
  }

  &.success {
    color: #15803d;
    background: #dcfce7;
  }

  &.danger {
    color: #b91c1c;
    background: #fee2e2;
  }

  &.muted {
    color: #667085;
    background: #f1f5f9;
  }
}

.execution-log-box {
  margin: 0;
  height: 360px;
  max-height: 360px;
  overflow: auto;
  padding: 10px 12px;
  border-radius: 8px;
  background: #0f172a;
  color: #e2e8f0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

.muted {
  color: #64748b;
}

@media (max-width: 900px) {
  .execution-progress-body {
    grid-template-columns: 1fr;
  }

  .execution-steps,
  .execution-log-box {
    height: 280px;
    max-height: 280px;
  }
}
</style>
