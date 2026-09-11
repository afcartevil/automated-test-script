<template>
  <div class="tag-select" ref="rootRef">
    <input
      class="input mono"
      :class="inputClass"
      :value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      autocomplete="off"
      spellcheck="false"
      @focus="openPanel"
      @input="onInput"
      @keydown="onKeydown"
    />
    <div v-if="open" class="tag-select-panel">
      <div v-if="loading" class="tag-select-empty">正在读取仓库 tag…</div>
      <div v-else-if="!options.length" class="tag-select-empty">{{ emptyHint }}</div>
      <div v-else-if="!filtered.length" class="tag-select-empty">无匹配 tag，可继续输入自定义值</div>
      <ul v-else class="tag-select-list">
        <li
          v-for="(tag, idx) in visible"
          :key="tag"
          :class="{ active: idx === highlight, selected: tag === modelValue }"
          @mousedown.prevent="choose(tag)"
        >{{ tag }}</li>
      </ul>
      <div v-if="filtered.length > visibleLimit" class="tag-select-more">
        已显示 {{ visibleLimit }} / {{ filtered.length }}，继续输入可缩小范围
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: string
  options?: string[]
  placeholder?: string
  emptyHint?: string
  loading?: boolean
  disabled?: boolean
  visibleLimit?: number
  inputClass?: string
}>(), {
  options: () => [],
  placeholder: '输入检索并选择 tag',
  emptyHint: '未读取到 tag，请先在设置中配置本地 kernel 仓',
  loading: false,
  disabled: false,
  visibleLimit: 80,
  inputClass: '',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const rootRef = ref<HTMLElement | null>(null)
const open = ref(false)
const highlight = ref(0)
const query = ref('')

const filtered = computed(() => {
  const source = props.options || []
  const q = (query.value || '').trim().toLowerCase()
  if (!q) return source
  const parts = q.split(/\s+/).filter(Boolean)
  return source.filter((tag) => {
    const lower = tag.toLowerCase()
    return parts.every((part) => lower.includes(part))
  })
})

const visible = computed(() => filtered.value.slice(0, props.visibleLimit))

function openPanel() {
  query.value = String(props.modelValue || '')
  highlight.value = Math.max(0, visible.value.findIndex((tag) => tag === props.modelValue))
  open.value = true
}

function onInput(event: Event) {
  const value = (event.target as HTMLInputElement).value
  query.value = value
  highlight.value = 0
  open.value = true
  emit('update:modelValue', value)
}

function choose(tag: string) {
  emit('update:modelValue', tag)
  query.value = tag
  open.value = false
}

function onKeydown(event: KeyboardEvent) {
  if (!open.value && (event.key === 'ArrowDown' || event.key === 'Enter')) {
    openPanel()
    return
  }
  if (!open.value) return
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    highlight.value = Math.min(visible.value.length - 1, highlight.value + 1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    highlight.value = Math.max(0, highlight.value - 1)
  } else if (event.key === 'Enter') {
    const tag = visible.value[highlight.value]
    if (tag) {
      event.preventDefault()
      choose(tag)
    }
  } else if (event.key === 'Escape') {
    open.value = false
  }
}

function onDocClick(event: MouseEvent) {
  if (!rootRef.value?.contains(event.target as Node)) {
    open.value = false
  }
}

watch(() => props.modelValue, (value) => {
  if (!open.value) query.value = String(value || '')
})

onMounted(() => document.addEventListener('mousedown', onDocClick))
onBeforeUnmount(() => document.removeEventListener('mousedown', onDocClick))
</script>

<style scoped>
.tag-select {
  position: relative;
  width: 100%;
}
.tag-select-panel {
  position: absolute;
  z-index: 30;
  left: 0;
  right: 0;
  top: calc(100% + 4px);
  max-height: 280px;
  overflow: auto;
  background: #fff;
  border: 1px solid var(--border-strong);
  border-radius: 12px;
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.12);
}
.tag-select-list {
  margin: 0;
  padding: 6px;
  list-style: none;
}
.tag-select-list li {
  padding: 8px 10px;
  border-radius: 8px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  cursor: pointer;
  word-break: break-all;
}
.tag-select-list li:hover,
.tag-select-list li.active {
  background: rgba(37, 99, 235, 0.08);
}
.tag-select-list li.selected {
  color: #1d4ed8;
  font-weight: 700;
}
.tag-select-empty,
.tag-select-more {
  padding: 10px 12px;
  font-size: 12px;
  color: var(--muted);
}
</style>
