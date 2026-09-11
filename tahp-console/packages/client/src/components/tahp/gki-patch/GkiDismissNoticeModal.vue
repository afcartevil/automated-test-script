<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NInput, NModal } from 'naive-ui'
import type { GkiExternalNotice } from '@/api/tahp/gki-upgrade-notices'

const props = defineProps<{
  show: boolean
  notice?: GkiExternalNotice | null
  reason: string
  submitting?: boolean
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  'update:reason': [value: string]
  confirm: []
  cancel: []
}>()

const canConfirm = computed(() => Boolean(props.reason.trim()) && !props.submitting)

function close() {
  emit('update:show', false)
  emit('cancel')
}

function confirm() {
  if (!canConfirm.value) return
  emit('confirm')
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    title="忽略通知"
    class="dismiss-notice-modal"
    style="width: 480px; max-width: calc(100vw - 32px)"
    @update:show="emit('update:show', $event)"
  >
    <div class="modal-body">
      <p class="lead">忽略后通知会移到「已处理」。请填写原因，便于后续核对。</p>
      <p v-if="notice?.title" class="notice-title">{{ notice.title }}</p>
      <label class="field">
        <span>忽略原因</span>
        <NInput
          type="textarea"
          :value="reason"
          :autosize="{ minRows: 3, maxRows: 6 }"
          placeholder="例如：该项目本迭代不升级 / 已人工评估无需处理"
          @update:value="emit('update:reason', $event)"
        />
      </label>
    </div>
    <template #footer>
      <div class="footer">
        <NButton secondary :disabled="submitting" @click="close">取消</NButton>
        <NButton type="primary" :loading="submitting" :disabled="!canConfirm" @click="confirm">
          确认忽略
        </NButton>
      </div>
    </template>
  </NModal>
</template>

<style scoped lang="scss">
.modal-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.lead {
  margin: 0;
  font-size: 13px;
  color: var(--muted);
  line-height: 1.45;
}

.notice-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--head);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
}

.footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
