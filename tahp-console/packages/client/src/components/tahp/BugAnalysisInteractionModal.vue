<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { NModal, NButton, NSpace, NForm, NFormItem, NInput, NAlert, NProgress } from 'naive-ui'
import type { BugApprovalRequest, BugUserInputRequest } from '@/stores/tahp/bug-analysis'

const props = defineProps<{
  approval: BugApprovalRequest | null
  userInput: BugUserInputRequest | null
  submitting?: boolean
}>()

const emit = defineEmits<{
  approval: [choice: string]
  userInput: [values: Record<string, string>]
}>()

const show = computed(() => !!props.approval || !!props.userInput)
const mode = computed(() => (props.approval ? 'approval' : 'user_input') as 'approval' | 'user_input')

const countdownSec = ref(0)
let countdownTimer: ReturnType<typeof setInterval> | null = null

const formValues = ref<Record<string, string>>({})

function stopCountdown() {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
}

function startCountdown(deadlineAt: number) {
  stopCountdown()
  const tick = () => {
    const left = Math.max(0, Math.ceil((deadlineAt - Date.now()) / 1000))
    countdownSec.value = left
    if (left <= 0) stopCountdown()
  }
  tick()
  countdownTimer = setInterval(tick, 250)
}

watch(
  () => [props.approval, props.userInput] as const,
  ([ap, ui]) => {
    if (ap) {
      formValues.value = {}
      startCountdown(ap.deadline_at)
    } else if (ui) {
      const init: Record<string, string> = {}
      for (const f of ui.fields) {
        init[f.name] = f.default || ''
      }
      formValues.value = init
      startCountdown(ui.deadline_at)
    } else {
      stopCountdown()
    }
  },
  { immediate: true },
)

onBeforeUnmount(stopCountdown)

const countdownLabel = computed(() => {
  if (countdownSec.value <= 0) return '已超时'
  const m = Math.floor(countdownSec.value / 60)
  const s = countdownSec.value % 60
  return m > 0 ? `${m}:${String(s).padStart(2, '0')}` : `${s}s`
})

const countdownPercent = computed(() => {
  const ap = props.approval
  const ui = props.userInput
  const totalMs = ap
    ? (ap.timeout_ms || 60000)
    : ui
      ? (ui.timeout_sec || 300) * 1000
      : 1
  const leftMs = countdownSec.value * 1000
  return Math.max(0, Math.min(100, Math.round((leftMs / totalMs) * 100)))
})

function onApprovalClick(choice: string) {
  emit('approval', choice)
}

function onSubmitUserInput() {
  emit('userInput', { ...formValues.value })
}
</script>

<template>
  <NModal
    :show="show"
    :mask-closable="false"
    :close-on-esc="false"
    :auto-focus="false"
    transform-origin="center"
    class="bug-interaction-modal"
    style="width: min(640px, calc(100vw - 32px))"
  >
    <template #header>
      <div class="bim-header">
        <span v-if="mode === 'approval'">危险命令确认</span>
        <span v-else>{{ userInput?.title || '配置输入' }}</span>
        <span class="bim-countdown" :class="{ urgent: countdownSec > 0 && countdownSec <= 10 }">
          {{ countdownLabel }}
        </span>
      </div>
    </template>

    <div v-if="mode === 'approval' && approval" class="bim-body">
      <NAlert type="warning" :show-icon="true" style="margin-bottom: 12px">
        Agent 请求执行可能具有破坏性的命令。60 秒内未操作将<strong>自动同意一次</strong>。
      </NAlert>
      <div class="bim-desc">{{ approval.description }}</div>
      <code class="bim-command">{{ approval.command }}</code>
      <NProgress
        type="line"
        :percentage="countdownPercent"
        :show-indicator="false"
        status="warning"
        style="margin-top: 14px"
      />
      <NSpace justify="end" style="margin-top: 16px" wrap>
        <NButton type="primary" :loading="submitting" @click="onApprovalClick('once')">
          同意一次
        </NButton>
        <NButton v-if="approval.allow_permanent !== false" :loading="submitting" @click="onApprovalClick('session')">
          本次会话允许
        </NButton>
        <NButton v-if="approval.allow_permanent !== false" :loading="submitting" @click="onApprovalClick('always')">
          始终允许
        </NButton>
        <NButton type="error" ghost :loading="submitting" @click="onApprovalClick('deny')">
          拒绝
        </NButton>
      </NSpace>
    </div>

    <div v-else-if="mode === 'user_input' && userInput" class="bim-body">
      <NAlert type="info" :show-icon="true" style="margin-bottom: 12px">
        {{ userInput.message || '请按下方格式填写配置，提交后 Agent 将继续分析并持久化配置。' }}
      </NAlert>
      <NProgress
        type="line"
        :percentage="countdownPercent"
        :show-indicator="false"
        style="margin-bottom: 14px"
      />
      <NForm label-placement="top">
        <NFormItem
          v-for="field in userInput.fields"
          :key="field.name"
          :label="field.label"
          :required="field.required"
        >
          <NInput
            v-if="field.type !== 'textarea'"
            v-model:value="formValues[field.name]"
            :type="field.type === 'password' ? 'password' : field.type === 'number' ? 'text' : 'text'"
            :placeholder="field.placeholder"
            :show-password-on="field.type === 'password' ? 'click' : undefined"
          />
          <NInput
            v-else
            v-model:value="formValues[field.name]"
            type="textarea"
            :placeholder="field.placeholder"
            :autosize="{ minRows: 2, maxRows: 6 }"
          />
          <div v-if="field.hint" class="bim-hint">{{ field.hint }}</div>
        </NFormItem>
      </NForm>
      <NSpace justify="end" style="margin-top: 8px">
        <NButton type="primary" :loading="submitting" @click="onSubmitUserInput">
          提交并继续分析
        </NButton>
      </NSpace>
    </div>
  </NModal>
</template>

<style scoped>
.bug-interaction-modal :deep(.n-card-header) {
  padding-bottom: 8px;
}

.bim-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  font-weight: 600;
}

.bim-countdown {
  font-size: 13px;
  font-weight: 600;
  color: var(--n-text-color-3);
  font-variant-numeric: tabular-nums;
}

.bim-countdown.urgent {
  color: #d03050;
}

.bim-desc {
  font-size: 14px;
  line-height: 1.5;
  margin-bottom: 8px;
  color: var(--n-text-color-2);
}

.bim-command {
  display: block;
  padding: 10px 12px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.04);
  font-size: 12px;
  line-height: 1.45;
  word-break: break-all;
  white-space: pre-wrap;
}

.bim-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--n-text-color-3);
}
</style>

<!-- 固定于视口顶层，避免被分析区布局挤压 -->
<style>
.bug-interaction-modal.n-modal {
  z-index: 4000 !important;
}
</style>
