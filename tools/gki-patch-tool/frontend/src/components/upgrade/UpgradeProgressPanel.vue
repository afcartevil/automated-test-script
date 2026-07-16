<template>
  <div class="execution-progress-section upgrade-progress-section" style="margin-top: 18px">
    <div class="execution-progress-summary">
      <div class="execution-progress-head split">
        <strong>{{ headline }}</strong>
        <span class="muted">{{ progressPercent }}%</span>
      </div>
      <div class="progress execution-progress-bar">
        <span :style="{ width: `${progressPercent}%` }"></span>
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
            class="execution-step-row upgrade-step-row"
            :class="step.status"
          >
            <span class="execution-step-icon">{{ step.icon }}</span>
            <div class="execution-step-body">
              <div class="execution-step-title split">
                <span>
                  {{ step.label }}
                  <span v-if="step.duration" class="muted" style="font-size: 11px; margin-left: 6px">{{ step.duration }}</span>
                </span>
                <span class="pill" :class="stepStatusTone(step.status)">{{ stepStatusText(step.status) }}</span>
              </div>
              <p v-if="step.hint" class="upgrade-step-hint muted">{{ step.hint }}</p>
            </div>
          </div>
        </div>
      </div>

      <div class="execution-progress-col execution-log-section">
        <div class="execution-column-title split">
          <span>执行日志</span>
          <a v-if="executionLogUrl" class="muted" :href="executionLogUrl" target="_blank" style="font-size: 11px">完整日志</a>
        </div>
        <div ref="logBoxRef" class="execution-log-box">
          <div v-if="!logLines.length" class="execution-log-empty">等待日志输出…</div>
          <div v-for="(line, index) in logLines" :key="`${line.time}-${index}`" class="execution-log-line">
            <span v-if="line.time" class="execution-log-time">[{{ line.time }}]</span>
            <span v-if="line.phase" class="execution-log-phase">{{ line.phase }}</span>
            <span>{{ line.msg }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  UPGRADE_STATE_LABEL,
  buildUpgradePhaseSteps,
  effectiveUpgradePhase,
  upgradeProgressLogs,
  upgradeProgressPercent,
} from '../../utils/upgradeProgress'

const props = defineProps<{
  job?: Record<string, any>
  progress?: Record<string, any>
  jobId?: string
}>()

const logBoxRef = ref<HTMLElement | null>(null)
const followLog = ref(true)
let removeScrollListener: (() => void) | null = null

const phaseSteps = computed(() => buildUpgradePhaseSteps(props.job, props.progress))
const logLines = computed(() => upgradeProgressLogs(props.progress, props.job))
const progressPercent = computed(() => upgradeProgressPercent(props.progress, props.job))
const message = computed(() => props.progress?.message || props.job?.error_msg || '')
const executionLogUrl = computed(() =>
  props.jobId ? `/api/upgrade/jobs/${props.jobId}/execution-log` : '',
)

const headline = computed(() => {
  const phase = effectiveUpgradePhase(props.job, props.progress)
  const step = phaseSteps.value.find((s) => s.key === phase)
  const rawPhase = String(props.progress?.phase || props.job?.phase || '').trim()
  if (step) {
    if (rawPhase === 'build_fix') return `${step.icon} ${step.label}（AI 修复编译错误）`
    return `${step.icon} ${step.label}`
  }
  return '升级执行中'
})

function stepStatusText(status: string) {
  return UPGRADE_STATE_LABEL[status] || status
}

function stepStatusTone(status: string) {
  if (status === 'done') return 'success'
  if (status === 'running') return 'info'
  if (status === 'conflicts' || status === 'failed') return 'danger'
  if (status === 'manual') return 'warning'
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
})
</script>

<style scoped>
.upgrade-step-hint {
  margin: 4px 0 0;
  font-size: 11px;
  line-height: 1.4;
}
.upgrade-step-row.conflicts {
  border-color: #fecaca;
  background: #fff7f7;
}
.upgrade-step-row.failed {
  border-color: #fecaca;
}
</style>
