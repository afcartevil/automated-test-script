<template>
  <div class="retry-hint-form">
    <div class="retry-hint-form-title">{{ title }}</div>
    <p v-if="errorText" class="retry-hint-error">{{ errorText }}</p>
    <div v-if="analysisReason || analysisAdvice" class="retry-hint-analysis">
      <p class="retry-hint-analysis-title">{{ analysisHeadline }}</p>
      <p v-if="analysisReason"><strong>原因：</strong>{{ analysisReason }}</p>
      <p v-if="analysisAdvice" class="retry-hint-advice">{{ analysisAdvice }}</p>
    </div>
    <p class="retry-hint-desc">{{ description }}</p>
    <label class="retry-hint-label">补充说明（交给大模型按此重试）</label>
    <textarea
      v-model="hint"
      class="retry-hint-input"
      rows="5"
      spellcheck="false"
      :placeholder="placeholder"
    />
    <p v-if="savedPreview" class="retry-hint-saved">已保存经验会一并带上：{{ savedPreview }}</p>
    <div class="retry-hint-form-footer">
      <label class="retry-hint-check">
        <input v-model="saveToPrompt" type="checkbox" />
        写入后续 prompt（本机保留，下次同类任务自动带上）
      </label>
      <button class="btn primary btn-sm" type="button" :disabled="submitting" @click="onSubmit">
        {{ submitting ? '提交中…' : submitLabel }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '../../api'

const props = defineProps<{
  kind: 'conflict' | 'build_fix'
  errorText?: string
  submitLabel?: string
  submitting?: boolean
  analysisReason?: string
  analysisAdvice?: string
  analysisVerdict?: string
  initialHint?: string
}>()

const emit = defineEmits<{
  submit: [payload: { hint: string; saveToPrompt: boolean }]
}>()

const hint = ref('')
const saveToPrompt = ref(true)
const savedHints = ref({ conflict: '', build_fix: '' })

const analysisHeadline = computed(() =>
  props.analysisVerdict === 'retry' ? '模型建议再试一轮 AI' : '建议本机处理',
)

watch(
  () => props.initialHint,
  (value) => {
    if (value && !hint.value) hint.value = value
  },
  { immediate: true },
)

const title = computed(() =>
  props.kind === 'conflict' ? '补充说明后重试冲突合入' : '补充说明后重试编译修复',
)
const description = computed(() =>
  props.kind === 'conflict'
    ? '说明应如何合入（例如只改 +/-、保留 vendor 函数实现）。可勾选写入 prompt，方便以后同类冲突直接遵守。'
    : '说明应如何修编译错误（例如只删冲突宏、不要改内核头）。可勾选写入 prompt，方便以后同类错误直接遵守。',
)
const placeholder = computed(() =>
  props.kind === 'conflict'
    ? '例如：不要整段替换 mtk_i2c_transfer，只把 .rej 里的 +/- 合进现有函数。'
    : '例如：只删冲突的 #define，不要改 include/linux 内核头。',
)
const submitLabel = computed(() => props.submitLabel || '按此说明重试')
const savedPreview = computed(() => {
  const text = (savedHints.value[props.kind] || '').trim()
  if (!text) return ''
  return text.length > 80 ? `${text.slice(0, 80)}…` : text
})

watch(
  () => props.kind,
  async () => {
    try {
      const data = await api.get<{ hints?: Record<string, string> }>('/api/settings/retry-hints')
      savedHints.value = {
        conflict: data.hints?.conflict || '',
        build_fix: data.hints?.build_fix || '',
      }
    } catch {
      savedHints.value = { conflict: '', build_fix: '' }
    }
  },
  { immediate: true },
)

function onSubmit() {
  emit('submit', { hint: hint.value.trim(), saveToPrompt: saveToPrompt.value })
}

defineExpose({
  submit: onSubmit,
  getPayload: () => ({ hint: hint.value.trim(), saveToPrompt: saveToPrompt.value }),
})
</script>

<style scoped>
.retry-hint-form {
  margin: 10px 0 12px;
  padding: 12px 12px 10px;
  border: 1px solid #fecdd3;
  border-radius: 10px;
  background: #fff8f8;
}
.retry-hint-form-title {
  margin: 0 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: #991b1b;
}
.retry-hint-error {
  margin: 0 0 8px;
  padding: 8px 10px;
  font-size: 12px;
  color: var(--danger);
  background: var(--danger-soft);
  border-radius: 8px;
  white-space: pre-wrap;
  max-height: 72px;
  overflow: auto;
}
.retry-hint-analysis {
  margin: 0 0 10px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  font-size: 12px;
  line-height: 1.5;
  color: #334155;
}
.retry-hint-analysis-title {
  margin: 0 0 6px;
  font-weight: 600;
  color: #0f172a;
}
.retry-hint-advice {
  margin: 6px 0 0;
  white-space: pre-wrap;
}
.retry-hint-desc {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.5;
}
.retry-hint-label {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 600;
}
.retry-hint-input {
  width: 100%;
  resize: vertical;
  min-height: 88px;
  padding: 8px 10px;
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.45;
}
.retry-hint-saved {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--muted);
}
.retry-hint-form-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
  flex-wrap: wrap;
}
.retry-hint-check {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
</style>
