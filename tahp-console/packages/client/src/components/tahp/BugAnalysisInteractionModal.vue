<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { NModal, NButton, NSpace, NForm, NFormItem, NInput, NAlert, NProgress } from 'naive-ui'
import type { BugApprovalRequest, BugUserInputRequest } from '@/stores/tahp/bug-analysis'

export interface ContinueChatPrompt {
  title: string
  message?: string
  placeholder?: string
}

const props = defineProps<{
  approval: BugApprovalRequest | null
  userInput: BugUserInputRequest | null
  continueChat?: ContinueChatPrompt | null
  /** 仅 continue_chat 模式：由父组件控制是否显示（不自动弹出） */
  showContinueChat?: boolean
  submitting?: boolean
}>()

const emit = defineEmits<{
  approval: [choice: string]
  userInput: [values: Record<string, string>]
  continueChat: [message: string]
  continueChatDismiss: []
}>()

const show = computed(() =>
  !!props.approval
  || !!props.userInput
  || (!!props.continueChat && props.showContinueChat === true),
)
const mode = computed(() => {
  if (props.approval) return 'approval' as const
  if (props.userInput) return 'user_input' as const
  return 'continue_chat' as const
})

const countdownSec = ref(0)
let countdownTimer: ReturnType<typeof setInterval> | null = null

const formValues = ref<Record<string, string>>({})
const continueMessage = ref('')

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
  () => [props.approval, props.userInput, props.continueChat] as const,
  ([ap, ui, cc]) => {
    if (ap) {
      formValues.value = {}
      continueMessage.value = ''
      startCountdown(ap.deadline_at)
    } else if (ui) {
      const init: Record<string, string> = {}
      for (const f of ui.fields) {
        init[f.name] = f.default || ''
      }
      formValues.value = init
      continueMessage.value = ''
      startCountdown(ui.deadline_at)
    } else if (cc) {
      formValues.value = {}
      continueMessage.value = ''
      stopCountdown()
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

function onSubmitContinue() {
  const text = continueMessage.value.trim()
  if (!text) return
  emit('continueChat', text)
}

function onModalShowUpdate(visible: boolean) {
  if (!visible && mode.value === 'continue_chat') {
    emit('continueChatDismiss')
  }
}
</script>

<template>
  <NModal
    preset="card"
    :show="show"
    :mask-closable="mode === 'continue_chat'"
    :close-on-esc="mode === 'continue_chat'"
    :closable="mode === 'continue_chat'"
    :auto-focus="false"
    transform-origin="center"
    class="bug-interaction-modal"
    :style="{ width: 'min(640px, calc(100vw - 32px))' }"
    :content-style="{ padding: '0 20px 20px' }"
    :segmented="{ content: true, footer: false }"
    @update:show="onModalShowUpdate"
  >
    <template #header>
      <div class="bim-header">
        <span v-if="mode === 'approval'">危险命令确认</span>
        <span v-else-if="mode === 'user_input'">{{ userInput?.title || '配置输入' }}</span>
        <span v-else>{{ continueChat?.title || '补充信息' }}</span>
        <span
          v-if="mode !== 'continue_chat'"
          class="bim-countdown"
          :class="{ urgent: countdownSec > 0 && countdownSec <= 10 }"
        >
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
      <div v-if="userInput.message" class="bim-message">{{ userInput.message }}</div>
      <NAlert v-else type="info" :show-icon="true" style="margin-bottom: 12px">
        请按下方格式填写，提交后 Agent 将继续执行。
      </NAlert>
      <NProgress
        type="line"
        :percentage="countdownPercent"
        :show-indicator="false"
        style="margin-bottom: 14px"
      />
      <NForm label-placement="top" class="bim-form">
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

    <div v-else-if="mode === 'continue_chat' && continueChat" class="bim-body">
      <div v-if="continueChat.message" class="bim-message">{{ continueChat.message }}</div>
      <NAlert v-else type="info" :show-icon="true" style="margin-bottom: 12px">
        请输入补充说明，Agent 将根据您的输入继续执行。
      </NAlert>
      <NForm label-placement="top" class="bim-form">
        <NFormItem label="补充信息">
          <NInput
            v-model:value="continueMessage"
            type="textarea"
            :placeholder="continueChat.placeholder || '确认结果、补充路径、变更说明等'"
            :autosize="{ minRows: 3, maxRows: 8 }"
          />
        </NFormItem>
      </NForm>
      <NSpace justify="end" style="margin-top: 8px">
        <NButton type="primary" :loading="submitting" :disabled="!continueMessage.trim()" @click="onSubmitContinue">
          发送并继续对话
        </NButton>
      </NSpace>
    </div>
  </NModal>
</template>

<style scoped>
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

.bim-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: min(68vh, 640px);
  overflow-y: auto;
}

.bim-message {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--n-text-color-2);
  background: var(--n-color-modal);
  border: 1px solid var(--n-border-color);
}

.bim-form {
  width: 100%;
}

.bim-form :deep(.n-form-item) {
  margin-bottom: 14px;
}

.bim-form :deep(.n-form-item-label) {
  font-weight: 600;
  padding-bottom: 4px;
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

<!-- 固定于视口顶层，不透明卡片背景，避免背后 Agent 输出穿透 -->
<style>
.bug-interaction-modal.n-modal {
  z-index: 4000 !important;
}

.bug-interaction-modal.n-modal .n-card {
  background: var(--n-color-modal) !important;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.45);
}

.bug-interaction-modal.n-modal .n-card__content {
  background: var(--n-color-modal) !important;
}

.bug-interaction-modal.n-modal .n-modal-mask {
  background-color: rgba(0, 0, 0, 0.55) !important;
}
</style>
