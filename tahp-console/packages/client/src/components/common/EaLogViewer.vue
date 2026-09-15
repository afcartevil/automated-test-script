<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  lines: string[]
  height?: number
}>(), {
  height: 320,
})

type LogLevel = 'all' | 'error' | 'warn' | 'info'

const rowHeight = 20
const overscan = 12
const scrollTop = ref(0)
const query = ref('')
const level = ref<LogLevel>('all')
const viewportEl = ref<HTMLElement | null>(null)
const viewportPx = ref(props.height)

function detectLevel(line: string): LogLevel {
  const lower = line.toLowerCase()
  if (/\b(error|failed|exception|fatal)\b/.test(lower) || line.includes('失败') || line.includes('错误')) return 'error'
  if (/\b(warn|warning)\b/.test(lower) || line.includes('警告')) return 'warn'
  return 'info'
}

const filteredLines = computed(() => {
  const q = query.value.trim().toLowerCase()
  return props.lines.filter((line) => {
    const lv = detectLevel(line)
    if (level.value !== 'all' && lv !== level.value) return false
    if (q && !line.toLowerCase().includes(q)) return false
    return true
  })
})

const viewportCount = computed(() =>
  Math.max(1, Math.ceil(viewportPx.value / rowHeight)),
)

const startIndex = computed(() =>
  Math.max(0, Math.floor(scrollTop.value / rowHeight) - overscan),
)

const endIndex = computed(() =>
  Math.min(filteredLines.value.length, startIndex.value + viewportCount.value + overscan * 2),
)

const visibleLines = computed(() => filteredLines.value.slice(startIndex.value, endIndex.value))
const padTop = computed(() => startIndex.value * rowHeight)
const padBottom = computed(() => Math.max(0, (filteredLines.value.length - endIndex.value) * rowHeight))

function syncViewportHeight() {
  const measured = viewportEl.value?.clientHeight
  viewportPx.value = measured && measured > 0 ? measured : props.height
}

function onScroll(ev: Event) {
  const target = ev.target as HTMLElement
  scrollTop.value = target.scrollTop
}

let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  syncViewportHeight()
  if (typeof ResizeObserver === 'undefined' || !viewportEl.value) return
  resizeObserver = new ResizeObserver(() => syncViewportHeight())
  resizeObserver.observe(viewportEl.value)
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
})

watch(() => props.height, () => syncViewportHeight())
</script>

<template>
  <div class="ea-log-viewer-wrap">
    <div class="toolbar">
      <input v-model="query" type="search" class="search" placeholder="搜索日志…">
      <select v-model="level" class="level">
        <option value="all">全部</option>
        <option value="error">错误</option>
        <option value="warn">警告</option>
        <option value="info">信息</option>
      </select>
      <span class="count">{{ filteredLines.length }} / {{ lines.length }} 行</span>
    </div>
    <div
      ref="viewportEl"
      class="ea-log-viewer"
      :style="{ height: `var(--ea-log-height, ${height}px)` }"
      @scroll="onScroll"
    >
      <div class="pad" :style="{ height: `${padTop}px` }" />
      <pre
        v-for="(line, idx) in visibleLines"
        :key="startIndex + idx"
        class="line"
        :class="detectLevel(line)"
      >{{ line }}</pre>
      <div v-if="!filteredLines.length" class="empty">无匹配日志</div>
      <div class="pad" :style="{ height: `${padBottom}px` }" />
    </div>
  </div>
</template>

<style scoped lang="scss">
.ea-log-viewer-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.search, .level {
  height: 32px;
  padding: 0 10px;
  border-radius: 8px;
  border: 1px solid var(--line);
  background: var(--surface);
  font-size: 12px;
  color: inherit;
}
.search { flex: 1; min-width: 120px; }
.count {
  font-size: 11px;
  color: var(--faint);
  margin-left: auto;
}
.ea-log-viewer {
  overflow: auto;
  border-radius: 12px;
  background: #16192a;
  color: #c8ccd8;
  border: 1px solid rgba(255, 255, 255, 0.08);
  padding: 8px 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 20px;
}
.line {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  &.error { color: #ff8a9a; }
  &.warn { color: #f5c26b; }
}
.empty {
  color: #8b90a0;
  padding: 24px 0;
  text-align: center;
}
.pad {
  width: 100%;
}
</style>
