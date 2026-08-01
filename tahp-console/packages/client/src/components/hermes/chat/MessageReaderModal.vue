<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import type { Message } from '@/stores/hermes/chat'
import { copyToClipboard } from '@/utils/clipboard'
import MarkdownRenderer from './MarkdownRenderer.vue'

type FontSize = 'sm' | 'md' | 'lg'
type ReaderWidth = 'narrow' | 'medium' | 'full'

interface ReaderPrefs {
  fontSize: FontSize
  width: ReaderWidth
}

const STORAGE_KEY = 'ea_chat_reader_prefs'

const props = defineProps<{
  show: boolean
  messageId: string | null
  messages: Message[]
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  'update:messageId': [value: string | null]
}>()

const { t } = useI18n()
const toast = useMessage()

const fontSize = ref<FontSize>('md')
const width = ref<ReaderWidth>('medium')

function readPrefs(): ReaderPrefs {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { fontSize: 'md', width: 'medium' }
    const parsed = JSON.parse(raw) as Partial<ReaderPrefs>
    const fs = parsed.fontSize
    const w = parsed.width
    return {
      fontSize: fs === 'sm' || fs === 'md' || fs === 'lg' ? fs : 'md',
      width: w === 'narrow' || w === 'medium' || w === 'full' ? w : 'medium',
    }
  } catch {
    return { fontSize: 'md', width: 'medium' }
  }
}

function savePrefs() {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ fontSize: fontSize.value, width: width.value } satisfies ReaderPrefs),
    )
  } catch {
    // Ignore storage failures; in-memory prefs still work for this tab.
  }
}

const prefs = readPrefs()
fontSize.value = prefs.fontSize
width.value = prefs.width

watch([fontSize, width], savePrefs)

const readableMessages = computed(() =>
  props.messages.filter(
    (m) => m.role === 'assistant' && !!m.content?.trim() && m.systemType !== 'error',
  ),
)

const currentIndex = computed(() => {
  if (!props.messageId) return -1
  return readableMessages.value.findIndex((m) => m.id === props.messageId)
})

const currentMessage = computed(() => {
  if (currentIndex.value < 0) return null
  return readableMessages.value[currentIndex.value] ?? null
})

const canPrev = computed(() => currentIndex.value > 0)
const canNext = computed(
  () => currentIndex.value >= 0 && currentIndex.value < readableMessages.value.length - 1,
)

function close() {
  emit('update:show', false)
  emit('update:messageId', null)
}

function goPrev() {
  if (!canPrev.value) return
  const prev = readableMessages.value[currentIndex.value - 1]
  if (prev) emit('update:messageId', prev.id)
}

function goNext() {
  if (!canNext.value) return
  const next = readableMessages.value[currentIndex.value + 1]
  if (next) emit('update:messageId', next.id)
}

async function copyContent() {
  const text = currentMessage.value?.content?.trim()
  if (!text) return
  const ok = await copyToClipboard(text)
  if (ok) toast.success(t('chat.copiedBubble'))
  else toast.error(t('chat.copyFailed'))
}

function onKeydown(e: KeyboardEvent) {
  if (!props.show) return
  if (e.key === 'Escape') {
    e.preventDefault()
    close()
    return
  }
  if (e.key === 'ArrowLeft') {
    e.preventDefault()
    goPrev()
    return
  }
  if (e.key === 'ArrowRight') {
    e.preventDefault()
    goNext()
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

watch(
  () => props.show,
  (visible) => {
    if (visible) document.body.style.overflow = 'hidden'
    else document.body.style.overflow = ''
  },
)

onUnmounted(() => {
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <Transition name="reader-fade">
      <div v-if="show && currentMessage" class="message-reader" role="dialog" aria-modal="true">
        <header class="reader-toolbar">
          <div class="reader-toolbar-left">
            <button type="button" class="reader-btn" :disabled="!canPrev" :title="t('chat.readerPrev')" @click="goPrev">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="15 18 9 12 15 6" />
              </svg>
            </button>
            <button type="button" class="reader-btn" :disabled="!canNext" :title="t('chat.readerNext')" @click="goNext">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </button>
            <span class="reader-counter">
              {{ currentIndex + 1 }} / {{ readableMessages.length }}
            </span>
          </div>

          <div class="reader-toolbar-center">
            <div class="reader-seg" :title="t('chat.readerFontSize')">
              <button
                type="button"
                class="reader-seg-btn"
                :class="{ active: fontSize === 'sm' }"
                @click="fontSize = 'sm'"
              >A-</button>
              <button
                type="button"
                class="reader-seg-btn"
                :class="{ active: fontSize === 'md' }"
                @click="fontSize = 'md'"
              >A</button>
              <button
                type="button"
                class="reader-seg-btn"
                :class="{ active: fontSize === 'lg' }"
                @click="fontSize = 'lg'"
              >A+</button>
            </div>
            <div class="reader-seg" :title="t('chat.readerWidth')">
              <button
                type="button"
                class="reader-seg-btn"
                :class="{ active: width === 'narrow' }"
                @click="width = 'narrow'"
              >{{ t('chat.readerWidthNarrow') }}</button>
              <button
                type="button"
                class="reader-seg-btn"
                :class="{ active: width === 'medium' }"
                @click="width = 'medium'"
              >{{ t('chat.readerWidthMedium') }}</button>
              <button
                type="button"
                class="reader-seg-btn"
                :class="{ active: width === 'full' }"
                @click="width = 'full'"
              >{{ t('chat.readerWidthFull') }}</button>
            </div>
          </div>

          <div class="reader-toolbar-right">
            <button type="button" class="reader-btn" :title="t('chat.copyBubble')" @click="copyContent">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
            </button>
            <button type="button" class="reader-btn reader-close" :title="t('chat.readerClose')" @click="close">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        </header>

        <div class="reader-scroll">
          <article
            class="reader-body"
            :class="[`font-${fontSize}`, `width-${width}`]"
          >
            <MarkdownRenderer :content="currentMessage.content || ''" />
          </article>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.message-reader {
  position: fixed;
  inset: 0;
  z-index: 2100;
  display: flex;
  flex-direction: column;
  background: var(--surface);
}

.reader-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
  background: var(--bg);
}

.reader-toolbar-left,
.reader-toolbar-right,
.reader-toolbar-center {
  display: flex;
  align-items: center;
  gap: 8px;
}

.reader-toolbar-center {
  flex-wrap: wrap;
  justify-content: center;
}

.reader-counter {
  font-size: 12px;
  color: var(--muted);
  margin-left: 4px;
  white-space: nowrap;
}

.reader-btn {
  width: 34px;
  height: 34px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: var(--surface);
  color: var(--muted);
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: all 0.18s;

  &:hover:not(:disabled) {
    border-color: var(--accent);
    color: var(--accent);
  }

  &:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }

  &.reader-close:hover:not(:disabled) {
    border-color: var(--error);
    color: var(--error);
  }
}

.reader-seg {
  display: inline-flex;
  border: 1px solid var(--line);
  border-radius: 9px;
  overflow: hidden;
  background: var(--surface);
}

.reader-seg-btn {
  border: none;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  font-weight: 600;
  padding: 7px 10px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;

  & + & {
    border-left: 1px solid var(--line);
  }

  &.active {
    background: var(--accent-soft);
    color: var(--accent);
  }

  &:hover:not(.active) {
    color: var(--text);
    background: var(--bg);
  }
}

.reader-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 24px 20px 48px;
}

.reader-body {
  margin: 0 auto;
  line-height: 1.7;
  color: var(--text);

  &.width-narrow { max-width: 720px; }
  &.width-medium { max-width: 960px; }
  &.width-full { max-width: min(1200px, 100%); }

  &.font-sm { font-size: 14px; }
  &.font-md { font-size: 16px; }
  &.font-lg { font-size: 18px; }

  :deep(.markdown-body) {
    font-size: inherit;
    line-height: inherit;
  }
}

.reader-fade-enter-active,
.reader-fade-leave-active {
  transition: opacity 0.18s ease;
}

.reader-fade-enter-from,
.reader-fade-leave-to {
  opacity: 0;
}

@media (max-width: $breakpoint-mobile) {
  .reader-toolbar {
    flex-wrap: wrap;
    padding: 10px 12px;
  }

  .reader-toolbar-center {
    order: 3;
    width: 100%;
    justify-content: flex-start;
  }

  .reader-scroll {
    padding: 16px 14px 32px;
  }
}
</style>
