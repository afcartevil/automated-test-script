<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NInput, NModal, NSelect } from 'naive-ui'
import type { GkiExternalNotice } from '@/api/tahp/gki-upgrade-notices'

const props = defineProps<{
  show: boolean
  notice?: GkiExternalNotice | null
  fromTag: string
  toTag: string
  latestTag?: string
  latestMonth?: string
  recommendedTag?: string
  recommendedMonth?: string
  tagOptions: string[]
  tagsLoading?: boolean
  tagsHint?: string
  warning?: string
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  'update:toTag': [value: string]
  confirm: []
  cancel: []
}>()

const canConfirm = computed(() => Boolean(props.fromTag.trim() && props.toTag.trim()))

const selectOptions = computed(() =>
  props.tagOptions.map(tag => ({ label: tag, value: tag })),
)

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
    title="选择升级 To Tag"
    class="apply-notice-modal"
    style="width: 560px; max-width: calc(100vw - 32px)"
    @update:show="emit('update:show', $event)"
  >
    <div class="modal-body">
      <p class="lead">
        通知只带当前 GKI 版本。To Tag 默认按次新月推荐，可改选。
      </p>

      <div v-if="notice" class="meta">
        <span v-if="notice.platform">平台 {{ notice.platform }}</span>
        <span v-if="notice.projects">项目 {{ notice.projects }}</span>
      </div>

      <label class="field">
        <span>当前 GKI（From Tag）</span>
        <code class="readonly">{{ fromTag || '-' }}</code>
      </label>

      <div class="month-row">
        <div class="month-card">
          <span class="month-label">仓库最新月</span>
          <code>{{ latestTag || '-' }}</code>
          <span v-if="latestMonth" class="month-sub">{{ latestMonth }}</span>
        </div>
        <div class="month-card recommend">
          <span class="month-label">推荐次新月</span>
          <code>{{ recommendedTag || '-' }}</code>
          <span v-if="recommendedMonth" class="month-sub">{{ recommendedMonth }}</span>
        </div>
      </div>

      <label class="field">
        <span>To Tag</span>
        <NSelect
          v-if="tagOptions.length"
          :value="toTag"
          filterable
          :options="selectOptions"
          :loading="tagsLoading"
          placeholder="选择或输入检索目标 tag"
          @update:value="emit('update:toTag', String($event || ''))"
        />
        <NInput
          v-else
          :value="toTag"
          placeholder="仓库 tag 未就绪时请手动输入"
          @update:value="emit('update:toTag', $event)"
        />
      </label>

      <p v-if="tagsHint" class="hint">{{ tagsHint }}</p>
      <p v-if="warning" class="hint warn">{{ warning }}</p>
    </div>

    <template #footer>
      <div class="footer">
        <NButton secondary @click="close">取消</NButton>
        <NButton type="primary" :disabled="!canConfirm" @click="confirm">填入并采用</NButton>
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

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  font-size: 12px;
  color: var(--muted);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
}

.readonly,
.month-card code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
  font-weight: 600;
  color: var(--head);
  overflow-wrap: anywhere;
}

.readonly {
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--line) 35%, transparent);
}

.month-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.month-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface);

  &.recommend {
    border-color: color-mix(in srgb, var(--accent, #5b6cff) 35%, var(--line));
    background: color-mix(in srgb, var(--accent, #5b6cff) 8%, var(--surface));
  }
}

.month-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
}

.month-sub {
  font-size: 11px;
  color: var(--muted);
}

.hint {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.4;
}

.hint.warn {
  color: var(--error, #d14343);
}

.footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 640px) {
  .month-row {
    grid-template-columns: 1fr;
  }
}
</style>
