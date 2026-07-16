<template>
  <div class="execution-progress-section">
    <div class="execution-progress-summary">
      <div class="execution-progress-head split">
        <strong>{{ phaseMeta.icon }} {{ phaseMeta.label }}</strong>
        <span class="muted">{{ progressPercent }}%</span>
      </div>
      <div class="progress execution-progress-bar">
        <span :style="{ width: `${progressPercent}%` }"></span>
      </div>
      <div class="execution-progress-stats muted">
        <span>整体 <strong>{{ overallTotal }}</strong></span>
        <span>已完成 <strong>{{ overallCurrent }}</strong></span>
        <span>本阶段 <strong>{{ phaseCurrent }}/{{ phaseTotal || '—' }}</strong></span>
        <span v-if="failedCount">失败 <strong>{{ failedCount }}</strong></span>
        <span v-if="showTokenStats">
          🪙 prompt <strong>{{ promptTokens }}</strong>
        </span>
        <span v-if="showTokenStats">
          ↗ completion <strong>{{ completionTokens }}</strong>
        </span>
      </div>
      <div v-if="progress.message" class="execution-progress-message muted">
        {{ progress.message }}
      </div>
      <div
        v-if="squashValidation"
        class="squash-validation-panel"
        :class="squashValidation.ok ? 'ok' : 'fail'"
      >
        <div class="squash-validation-head">
          <span>{{ squashValidation.ok ? '✓' : '✗' }} Squash Patch 校验</span>
          <span class="pill" :class="squashValidation.ok ? 'success' : 'danger'">
            {{ squashValidation.ok ? '通过' : '未通过' }}
          </span>
        </div>
        <div v-if="squashValidation.summary" class="squash-validation-summary muted">
          {{ squashValidation.summary }}
        </div>
        <div class="squash-validation-checks">
          <div
            v-for="check in squashValidation.checks"
            :key="check.name"
            class="squash-validation-check"
            :class="check.passed ? 'ok' : 'fail'"
          >
            <span class="squash-validation-mark">{{ check.passed ? '✓' : '✗' }}</span>
            <span class="squash-validation-name">{{ squashCheckLabel(check.name) }}</span>
            <span v-if="check.detail" class="squash-validation-detail muted">{{ check.detail }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="execution-progress-body">
      <div class="execution-progress-col">
        <div class="execution-column-title">阶段进度</div>
        <div v-if="phaseSteps.length" class="execution-steps">
          <div
            v-for="step in phaseSteps"
            :key="step.key"
            class="execution-step-row"
            :class="step.status"
          >
            <span class="execution-step-icon">{{ step.icon }}</span>
            <div class="execution-step-body">
              <div class="execution-step-title split">
                <span>{{ step.label }}</span>
                <span class="execution-step-count">{{ step.current }}/{{ step.total }} ({{ step.percent }}%)</span>
              </div>
              <div class="execution-step-bar">
                <span :style="{ width: `${step.percent}%` }"></span>
              </div>
            </div>
            <span class="pill" :class="stepStatusTone(step.status)">{{ stepStatusText(step.status) }}</span>
          </div>
        </div>
        <div v-else class="execution-steps-empty muted">等待阶段信息…</div>
      </div>

      <div class="execution-progress-col execution-log-section">
        <div class="execution-column-title">执行日志（最近）</div>
        <div ref="logBoxRef" class="execution-log-box">
          <div v-if="!logLines.length" class="execution-log-empty">等待日志输出…</div>
          <div v-for="(line, index) in logLines" :key="`${line.time}-${index}`" class="execution-log-line">
            <span v-if="line.time" class="execution-log-time">[{{ line.time }}]</span>
            <span v-if="line.phase" class="execution-log-phase">{{ line.phase }}</span>
            <span>{{ analysisLogText(line) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  analysisLogText,
  analysisProgressLogs,
  buildAnalysisPhaseSteps,
  currentPhaseMeta,
  squashCheckLabel,
  squashValidationFromProgress,
} from '../../utils/analysisProgress'

const props = defineProps<{
  progress: any
  failedCount?: number
}>()

const logBoxRef = ref<HTMLElement | null>(null)
const followLog = ref(true)
let removeScrollListener: (() => void) | null = null

const phaseMeta = computed(() => currentPhaseMeta(props.progress?.status))
const phaseSteps = computed(() => buildAnalysisPhaseSteps(props.progress))
const logLines = computed(() => analysisProgressLogs(props.progress))
const squashValidation = computed(() => squashValidationFromProgress(props.progress))

const progressPercent = computed(() => {
  const status = String(props.progress?.status || '').toLowerCase()
  if (status === 'completed') return 100
  if (status === 'failed' || status === 'cancelled') return 0

  const overallTotal = Number(props.progress?.overall_total ?? 0)
  const overallCurrent = Number(props.progress?.overall_current ?? 0)
  if (overallTotal > 0) {
    return Math.min(99, Math.round((overallCurrent / overallTotal) * 100))
  }

  const total = Number(props.progress?.total ?? 0)
  const current = Number(props.progress?.current ?? 0)
  if (total > 0) {
    return Math.min(99, Math.round((current / total) * 100))
  }
  return 0
})

const overallTotal = computed(() => {
  const v = Number(props.progress?.overall_total ?? 0)
  return v > 0 ? v : Number(props.progress?.total ?? 0) || 0
})

const overallCurrent = computed(() => {
  const overallTotalVal = Number(props.progress?.overall_total ?? 0)
  if (overallTotalVal > 0) return Number(props.progress?.overall_current ?? 0)
  return Number(props.progress?.current ?? 0)
})

const phaseTotal = computed(() => Number(props.progress?.total ?? 0))
const phaseCurrent = computed(() => Number(props.progress?.current ?? 0))
const failedCount = computed(() => Number(props.failedCount ?? 0))

const showTokenStats = computed(() => String(props.progress?.status || '') === 'llm_analyzing')
const promptTokens = computed(() => Number(props.progress?.prompt_tokens ?? 0))
const completionTokens = computed(() => Number(props.progress?.completion_tokens ?? 0))

function stepStatusText(status: string) {
  if (status === 'done') return '完成'
  if (status === 'running') return '进行中'
  return '等待'
}

function stepStatusTone(status: string) {
  if (status === 'done') return 'success'
  if (status === 'running') return 'info'
  return 'muted'
}

watch(
  () => logLines.value.length,
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
  removeScrollListener = null
})
</script>
