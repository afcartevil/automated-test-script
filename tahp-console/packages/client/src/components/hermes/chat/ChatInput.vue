<script setup lang="ts">
import type { Attachment } from '@/stores/hermes/chat'
import { useChatStore } from '@/stores/hermes/chat'
import { useAppStore } from '@/stores/hermes/app'
import { useProfilesStore } from '@/stores/hermes/profiles'
import { fetchContextLength } from '@/api/hermes/sessions'
import { setModelContext } from '@/api/hermes/model-context'
import { NButton, NTooltip, NSwitch, NModal, NInputNumber, NInput, NForm, NFormItem, NTag, useMessage } from 'naive-ui'
import { computed, ref, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToolTraceVisibility } from '@/composables/useToolTraceVisibility'
import { saveKnowledgeFromChat } from '@/api/tahp/knowledge'

const chatStore = useChatStore()
const { t } = useI18n()
const message = useMessage()
const { toolTraceVisible, toggleToolTraceVisible } = useToolTraceVisibility()
const inputText = ref('')
const textareaRef = ref<HTMLTextAreaElement>()
const commandDropdownRef = ref<HTMLDivElement>()
const fileInputRef = ref<HTMLInputElement>()
const attachments = ref<Attachment[]>([])
const isDragging = ref(false)
const dragCounter = ref(0)
const isComposing = ref(false)

const bridgeCommands = computed(() => [
  { name: 'usage', args: '', description: t('chat.slashCommands.usage') },
  { name: 'status', args: '', description: t('chat.slashCommands.status') },
  { name: 'abort', args: '', description: t('chat.slashCommands.abort') },
  { name: 'queue', args: t('chat.slashCommandArgs.message'), description: t('chat.slashCommands.queue') },
  { name: 'clear', args: '', description: t('chat.slashCommands.clear') },
  { name: 'clear', args: '--history', insertText: 'clear --history', description: t('chat.slashCommands.clearHistory') },
  { name: 'title', args: t('chat.slashCommandArgs.title'), description: t('chat.slashCommands.title') },
  { name: 'compress', args: '', description: t('chat.slashCommands.compress') },
  { name: 'steer', args: t('chat.slashCommandArgs.text'), description: t('chat.slashCommands.steer') },
  { name: 'destroy', args: '', description: t('chat.slashCommands.destroy') },
])

const slashActive = ref(false)
const slashQuery = ref('')
const slashActiveIndex = ref(0)
const isBridgeSession = computed(() => chatStore.activeSession?.source === 'cli')
const filteredBridgeCommands = computed(() => {
  const query = slashQuery.value.toLowerCase()
  return bridgeCommands.value.filter(command =>
    command.name.includes(query) || command.insertText?.includes(query),
  )
})

// 自定义高度拖拽
const textareaHeight = ref<number | null>(null) // null = auto

function startResize(e: MouseEvent) {
  e.preventDefault()
  const el = textareaRef.value
  if (!el) return
  // 如果当前是 auto，用实际 clientHeight 作为起始值
  const startHeight = el.clientHeight
  const startY = e.clientY

  function onMouseMove(e: MouseEvent) {
    const deltaY = e.clientY - startY
    // 往上拖 (deltaY < 0) → 高度增加
    const newHeight = startHeight - deltaY
    textareaHeight.value = Math.max(20, Math.min(400, Math.round(newHeight)))
  }

  function onMouseUp() {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }

  document.body.style.cursor = 'row-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

// 自动播放语音开关
const autoPlaySpeech = ref(false)

// 从 localStorage 读取设置
onMounted(() => {
  const saved = localStorage.getItem('autoPlaySpeech')
  if (saved !== null) {
    autoPlaySpeech.value = saved === 'true'
    // 同步到 chat store
    chatStore.setAutoPlaySpeech(autoPlaySpeech.value)
  }

  // 读取来自 TAHP 适配调试页面的预填内容
  const tahpDraft = sessionStorage.getItem('tahp_chat_draft')
  if (tahpDraft) {
    inputText.value = tahpDraft
    sessionStorage.removeItem('tahp_chat_draft')
    nextTick(() => textareaRef.value?.focus())
  }

  // 读取 TAHP 适配调试模式元数据（用于 TAHP 横幅 + 知识库沉淀）
  const ctxRaw = sessionStorage.getItem('tahp_chat_context')
  if (ctxRaw) {
    try { tahpCtx.value = JSON.parse(ctxRaw) } catch { /* ignore */ }
    // 保留在 sessionStorage，直到用户手动保存或关闭横幅
  }
})

// 监听变化并保存
watch(autoPlaySpeech, (value) => {
  localStorage.setItem('autoPlaySpeech', String(value))
  // 通知 chat store
  chatStore.setAutoPlaySpeech(value)
})

const canSend = computed(() => inputText.value.trim() || attachments.value.length > 0)

function scrollCommandIntoView() {
  nextTick(() => {
    if (!commandDropdownRef.value) return
    const active = commandDropdownRef.value.querySelector('.active') as HTMLElement | null
    active?.scrollIntoView({ block: 'nearest', behavior: 'instant' })
  })
}

function updateSlashState() {
  if (!isBridgeSession.value) {
    slashActive.value = false
    return
  }
  const el = textareaRef.value
  if (!el) return
  const cursorPos = el.selectionStart
  const beforeCursor = inputText.value.slice(0, cursorPos)
  if (!beforeCursor.startsWith('/') || beforeCursor.includes(' ') || beforeCursor.includes('\n')) {
    slashActive.value = false
    return
  }
  slashQuery.value = beforeCursor.slice(1)
  slashActiveIndex.value = 0
  slashActive.value = filteredBridgeCommands.value.length > 0
}

function selectBridgeCommand(command: { name: string; args: string; insertText?: string }) {
  inputText.value = `/${command.insertText || command.name} `
  slashActive.value = false
  nextTick(() => {
    const el = textareaRef.value
    if (!el) return
    const pos = inputText.value.length
    el.setSelectionRange(pos, pos)
    el.focus()
  })
}

// --- Context info ---

const contextLength = ref(200000)
const FALLBACK_CONTEXT = 200000

// Context length editing
const showContextEditModal = ref(false)
const editingContextLimit = ref(200000)
const isSavingContextLimit = ref(false)

async function handleEditContextLimit() {
  editingContextLimit.value = contextLength.value
  showContextEditModal.value = true
}

async function saveContextLimit() {
  if (!editingContextLimit.value || editingContextLimit.value <= 0) {
    message.error(t('chat.contextEditInvalid'))
    return
  }

  isSavingContextLimit.value = true
  try {
    const provider = chatStore.activeSession?.provider || useAppStore().selectedProvider || ''
    const model = chatStore.activeSession?.model || useAppStore().selectedModel || ''

    if (!provider || !model) {
      message.error(t('chat.contextEditFailed'))
      return
    }

    await setModelContext(provider, model, editingContextLimit.value)
    contextLength.value = editingContextLimit.value
    showContextEditModal.value = false
    message.success(t('chat.contextEditSuccess'))
  } catch (err: any) {
    message.error(`${t('chat.contextEditFailed')}: ${err.message || ''}`)
  } finally {
    isSavingContextLimit.value = false
  }
}

async function loadContextLength() {
  try {
    const activeSession = chatStore.activeSession
    const profile = activeSession?.profile || useProfilesStore().activeProfileName || undefined
    contextLength.value = await fetchContextLength(
      profile,
      activeSession?.provider || undefined,
      activeSession?.model || undefined,
    )
  } catch {
    contextLength.value = FALLBACK_CONTEXT
  }
}

onMounted(loadContextLength)
watch(() => useProfilesStore().activeProfileName, loadContextLength)
watch(() => useAppStore().selectedProvider, loadContextLength)
watch(() => useAppStore().selectedModel, loadContextLength)
watch(() => chatStore.activeSession?.id, loadContextLength)
watch(() => chatStore.activeSession?.profile, loadContextLength)
watch(() => chatStore.activeSession?.provider, loadContextLength)
watch(() => chatStore.activeSession?.model, loadContextLength)

const totalTokens = computed(() => {
  const input = chatStore.activeSession?.inputTokens ?? 0
  const output = chatStore.activeSession?.outputTokens ?? 0
  return input + output
})

const remainingTokens = computed(() => Math.max(0, contextLength.value - totalTokens.value))

const usagePercent = computed(() =>
  Math.min((totalTokens.value / contextLength.value) * 100, 100),
)

function formatTokens(n: number): string {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}

// --- File attachment helpers ---

function addFile(file: File) {
  if (attachments.value.find(a => a.name === file.name)) return
  const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
  const url = URL.createObjectURL(file)
  attachments.value.push({
    id,
    name: file.name,
    type: file.type,
    size: file.size,
    url,
    file,
  })
}

function handleAttachClick() {
  fileInputRef.value?.click()
}

function handleFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files) return
  for (const file of input.files) addFile(file)
  input.value = ''
}

// --- Paste image ---

function handlePaste(e: ClipboardEvent) {
  const items = Array.from(e.clipboardData?.items || [])
  const imageItems = items.filter(i => i.type.startsWith('image/'))
  if (!imageItems.length) return
  e.preventDefault()
  for (const item of imageItems) {
    const blob = item.getAsFile()
    if (!blob) continue
    const ext = item.type.split('/')[1] || 'png'
    const file = new File([blob], `pasted-${Date.now()}.${ext}`, { type: item.type })
    addFile(file)
  }
}

// --- Drag and drop ---

function handleDragOver(e: DragEvent) {
  e.preventDefault()
}

function handleDragEnter(e: DragEvent) {
  e.preventDefault()
  if (e.dataTransfer?.types.includes('Files')) {
    dragCounter.value++
    isDragging.value = true
  }
}

function handleDragLeave() {
  dragCounter.value--
  if (dragCounter.value <= 0) {
    dragCounter.value = 0
    isDragging.value = false
  }
}

function handleDrop(e: DragEvent) {
  e.preventDefault()
  dragCounter.value = 0
  isDragging.value = false
  const files = Array.from(e.dataTransfer?.files || [])
  if (!files.length) return
  for (const file of files) addFile(file)
  textareaRef.value?.focus()
}

// --- Send ---

function handleSend() {
  const text = inputText.value.trim()
  if (!text && attachments.value.length === 0) return

  const tahpInstructions = tahpCtx.value ? buildTahpHandoffInstructions(tahpCtx.value) : undefined
  chatStore.sendMessage(
    text,
    attachments.value.length > 0 ? attachments.value : undefined,
    tahpInstructions ? { instructions: tahpInstructions } : undefined,
  )
  inputText.value = ''
  attachments.value = []
  slashActive.value = false

  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
  }
}

function handleCompositionStart() {
  isComposing.value = true
}

function handleCompositionEnd() {
  requestAnimationFrame(() => {
    isComposing.value = false
    updateSlashState()
  })
}

function isImeEnter(e: KeyboardEvent): boolean {
  return isComposing.value || e.isComposing || e.keyCode === 229
}

function handleKeydown(e: KeyboardEvent) {
  if (slashActive.value && filteredBridgeCommands.value.length > 0) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      slashActiveIndex.value = (slashActiveIndex.value + 1) % filteredBridgeCommands.value.length
      scrollCommandIntoView()
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      slashActiveIndex.value = (slashActiveIndex.value - 1 + filteredBridgeCommands.value.length) % filteredBridgeCommands.value.length
      scrollCommandIntoView()
      return
    }
    if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault()
      selectBridgeCommand(filteredBridgeCommands.value[slashActiveIndex.value])
      return
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      slashActive.value = false
      return
    }
  }

  if (e.key !== 'Enter' || e.shiftKey) return
  if (isImeEnter(e)) return

  e.preventDefault()
  handleSend()
}

function handleInput(e: Event) {
  const el = e.target as HTMLTextAreaElement
  if (!isComposing.value) updateSlashState()
  // 用户手动拖拽自定义高度时，不覆盖
  if (textareaHeight.value !== null) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 100) + 'px'
}

function handleCommandHover(index: number) {
  slashActiveIndex.value = index
}

function onDocumentMousedown(e: MouseEvent) {
  if (!slashActive.value) return
  const target = e.target as HTMLElement
  if (!target.closest('.slash-command-dropdown') && !target.closest('.input-wrapper')) {
    slashActive.value = false
  }
}

onMounted(() => {
  document.addEventListener('mousedown', onDocumentMousedown)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', onDocumentMousedown)
})

function removeAttachment(id: string) {
  const idx = attachments.value.findIndex(a => a.id === id)
  if (idx !== -1) {
    URL.revokeObjectURL(attachments.value[idx].url)
    attachments.value.splice(idx, 1)
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function isImage(type: string): boolean {
  return type.startsWith('image/')
}

// ─── TAHP 适配调试模式 ─────────────────────────────────────────────────────────
interface TahpChatContext {
  domain: string
  domainLabel: string
  module: string
  relatedSkills: string[]
  project: { projectCode: string; soc: string; kernelVersion: string; preVendor: string; postVendor: string }
  taskId: string | null
}

const tahpCtx        = ref<TahpChatContext | null>(null)

/** 首条消息附带：让 BFF 在 system prompt 中注入优先 Skill 路径 */
function buildTahpHandoffInstructions(ctx: TahpChatContext): string {
  const skills = ctx.relatedSkills.filter(Boolean)
  const lines = [
    `TAHP handoff: scenario=adapt_debug domain=${ctx.domain} module=${ctx.module}.`,
    `项目: ${ctx.project.projectCode} / ${ctx.project.soc} / ${ctx.project.kernelVersion}.`,
  ]
  if (skills.length) {
    lines.push(`**关联 Skills**: ${skills.join(', ')}`)
  }
  return lines.join('\n')
}
const showKbModal    = ref(false)
const kbSaving       = ref(false)
const kbTitle        = ref('')
const kbContent      = ref('')
const kbTags         = ref('')

// 是否有 AI 回复（用于启用"提炼"按钮）
const hasAssistantReply = computed(() =>
  chatStore.messages.some(m => m.role === 'assistant' && !m.isStreaming)
)

function openKbSaveDialog() {
  if (!tahpCtx.value) return
  const ctx = tahpCtx.value
  // 自动生成标题和内容模板
  kbTitle.value   = `${ctx.domainLabel} BSP 适配调试经验 — ${ctx.project.soc}`
  // 从当前对话中提取内容摘要
  const turns = chatStore.messages
    .filter(m => m.role === 'user' || m.role === 'assistant')
    .slice(-10)  // 最近10条
    .map(m => `**[${m.role === 'user' ? '问' : '答'}]** ${m.content?.slice(0, 300) ?? ''}`)
    .join('\n\n')
  kbContent.value = `## 适配上下文\n\n- 项目: ${ctx.project.projectCode}\n- SoC: ${ctx.project.soc}\n- Kernel: ${ctx.project.kernelVersion}\n- 升级路径: ${ctx.project.preVendor} → ${ctx.project.postVendor}\n\n## 关键对话摘要\n\n${turns}\n`
  kbTags.value    = [ctx.module, ctx.domain, 'adapt-debug', ...ctx.relatedSkills.slice(0, 3)].join(', ')
  showKbModal.value = true
}

async function submitKbSave() {
  if (!tahpCtx.value || !kbTitle.value.trim() || !kbContent.value.trim()) return
  kbSaving.value = true
  try {
    const result = await saveKnowledgeFromChat({
      title:   kbTitle.value.trim(),
      content: kbContent.value.trim(),
      module:  tahpCtx.value.module,
      domain:  tahpCtx.value.domain,
      tags:    kbTags.value.split(',').map(t => t.trim()).filter(Boolean),
      category: 'practice_note',
      author: 'user',
    })
    message.success(`已沉淀至知识库: ${result.file}`)
    showKbModal.value = false
    // 标记已保存，避免重复提示
    tahpCtx.value = null
    sessionStorage.removeItem('tahp_chat_context')
  } catch (err) {
    message.error(`保存失败: ${(err as Error).message}`)
  } finally {
    kbSaving.value = false
  }
}
</script>

<template>
  <div class="chat-input-area">

    <!-- TAHP 适配调试模式横幅 -->
    <div v-if="tahpCtx" class="tahp-ctx-banner">
      <div class="tahp-banner-left">
        <span class="tahp-badge">EasyAdapter</span>
        <span class="tahp-banner-text">
          <strong>{{ tahpCtx.domainLabel }}</strong> 适配调试 ·
          {{ tahpCtx.project.soc }} / {{ tahpCtx.project.kernelVersion }} ·
          {{ tahpCtx.project.preVendor }} → {{ tahpCtx.project.postVendor }}
        </span>
        <NTag
          v-for="sk in tahpCtx.relatedSkills.slice(0, 3)"
          :key="sk"
          size="tiny"
          class="tahp-skill-tag"
        >{{ sk }}</NTag>
      </div>
      <div class="tahp-banner-right">
        <NButton
          size="tiny"
          type="primary"
          :disabled="!hasAssistantReply"
          @click="openKbSaveDialog"
          class="tahp-kb-btn"
        >
          <template #icon>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
          </template>
          提炼至知识库
        </NButton>
        <button class="tahp-banner-close" @click="tahpCtx = null; sessionStorage.removeItem('tahp_chat_context')">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
    </div>

    <!-- Top bar: attach + auto play speech + context info -->
    <div class="input-top-bar">
      <NTooltip trigger="hover">
        <template #trigger>
          <NButton quaternary size="tiny" @click="handleAttachClick" circle>
            <template #icon>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
            </template>
          </NButton>
        </template>
        {{ t('chat.attachFiles') }}
      </NTooltip>

      <div class="auto-play-speech-switch">
        <NTooltip trigger="hover">
          <template #trigger>
            <div class="switch-label">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="5 3 19 12 5 21 5 3"/>
              </svg>
            </div>
          </template>
          {{ t('chat.autoPlaySpeech') }}
        </NTooltip>
        <NSwitch
          size="small"
          v-model:value="autoPlaySpeech"
          :round="false"
        />
      </div>

      <NTooltip trigger="hover">
        <template #trigger>
          <NButton
            quaternary
            size="tiny"
            class="tool-trace-toggle"
            :class="{ active: toolTraceVisible }"
            :aria-label="toolTraceVisible ? t('chat.hideToolCalls') : t('chat.showToolCalls')"
            @click="toggleToolTraceVisible"
          >
            <svg class="tool-trace-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14.7 6.3a4.5 4.5 0 0 0-5.8 5.8L3.5 17.5a2.1 2.1 0 0 0 3 3l5.4-5.4a4.5 4.5 0 0 0 5.8-5.8l-3 3-3-3 3-3z"/>
            </svg>
          </NButton>
        </template>
        {{ toolTraceVisible ? t('chat.hideToolCalls') : t('chat.showToolCalls') }}
      </NTooltip>

      <span v-if="totalTokens > 0" class="context-info" :class="{ 'context-warning': usagePercent > 80 }">
        {{ formatTokens(totalTokens) }} /
        <NTooltip trigger="hover">
          <template #trigger>
            <span class="context-limit-editable" @click="handleEditContextLimit">
              {{ formatTokens(contextLength) }}
            </span>
          </template>
          <span>{{ t('chat.contextClickToEdit') }}</span>
        </NTooltip>
        · {{ t('chat.contextRemaining') }} {{ formatTokens(remainingTokens) }}
      </span>
      <div v-if="totalTokens > 0" class="context-bar">
        <div
          class="context-bar-fill"
          :class="{
            'context-bar-warn': usagePercent > 60 && usagePercent <= 80,
            'context-bar-danger': usagePercent > 80,
          }"
          :style="{ width: `${usagePercent}%` }"
        />
      </div>
    </div>

    <!-- Attachment previews -->
    <div v-if="attachments.length > 0" class="attachment-previews">
      <div
        v-for="att in attachments"
        :key="att.id"
        class="attachment-preview"
        :class="{ image: isImage(att.type) }"
      >
        <template v-if="isImage(att.type)">
          <img :src="att.url" :alt="att.name" class="attachment-thumb" />
        </template>
        <template v-else>
          <div class="attachment-file">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            <span class="file-name">{{ att.name }}</span>
            <span class="file-size">{{ formatSize(att.size) }}</span>
          </div>
        </template>
        <button class="attachment-remove" @click="removeAttachment(att.id)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
    </div>

    <div
      class="input-wrapper"
      :class="{ 'drag-over': isDragging }"
      @dragover="handleDragOver"
      @dragenter="handleDragEnter"
      @dragleave="handleDragLeave"
      @drop="handleDrop"
    >
      <input
        ref="fileInputRef"
        type="file"
        multiple
        class="file-input-hidden"
        @change="handleFileChange"
      />
      <div class="resize-handle" @mousedown="startResize"></div>
      <textarea
        ref="textareaRef"
        v-model="inputText"
        class="input-textarea"
        :style="textareaHeight ? { height: textareaHeight + 'px' } : {}"
        :placeholder="t('chat.inputPlaceholder')"
        rows="1"
        @keydown="handleKeydown"
        @compositionstart="handleCompositionStart"
        @compositionend="handleCompositionEnd"
        @input="handleInput"
        @paste="handlePaste"
      ></textarea>
      <Transition name="dropdown-fade">
        <div
          v-if="slashActive && filteredBridgeCommands.length > 0"
          ref="commandDropdownRef"
          class="slash-command-dropdown"
        >
          <div
            v-for="(command, i) in filteredBridgeCommands"
            :key="command.name"
            class="slash-command-item"
            :class="{ active: i === slashActiveIndex }"
            @mousedown.prevent="selectBridgeCommand(command)"
            @mouseenter="handleCommandHover(i)"
          >
            <span class="slash-command-name">/{{ command.name }}</span>
            <span v-if="command.args" class="slash-command-args">{{ command.args }}</span>
            <span class="slash-command-desc">{{ command.description }}</span>
          </div>
        </div>
      </Transition>
      <div class="input-actions">
        <NButton
          v-if="chatStore.isStreaming"
          size="small"
          type="error"
          :disabled="chatStore.isAborting"
          @click="chatStore.stopStreaming()"
        >
          {{ t('chat.stop') }}
        </NButton>
        <NButton
          size="small"
          type="primary"
          :disabled="!canSend"
          @click="handleSend"
        >
          <template #icon>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
          </template>
          {{ t('chat.send') }}
        </NButton>
      </div>
    </div>

    <!-- Context Length Edit Modal -->
    <NModal
      v-model:show="showContextEditModal"
      :title="t('chat.contextEditTitle')"
      :mask-closable="true"
      preset="card"
      style="width: 400px"
    >
      <div class="context-edit-content">
        <p style="margin-bottom: 16px; color: #666;">
          {{ t('chat.contextEditDesc') }}
        </p>
        <NInputNumber
          v-model:value="editingContextLimit"
          :min="1000"
          :max="10000000"
          :step="1000"
          :show-button="false"
          :placeholder="t('chat.contextEditPlaceholder')"
          style="width: 100%"
        >
          <template #suffix>
            <span style="color: #999;">tokens</span>
          </template>
        </NInputNumber>
        <div style="margin-top: 12px; font-size: 12px; color: #999;">
          {{ t('chat.contextEditHint') }}
        </div>
      </div>
      <template #footer>
        <div style="display: flex; justify-content: flex-end; gap: 8px;">
          <NButton @click="showContextEditModal = false" :disabled="isSavingContextLimit">
            {{ t('chat.contextEditCancel') }}
          </NButton>
          <NButton type="primary" @click="saveContextLimit" :loading="isSavingContextLimit">
            {{ t('chat.contextEditSave') }}
          </NButton>
        </div>
      </template>
    </NModal>

    <!-- TAHP 知识库沉淀对话框 -->
    <NModal
      v-model:show="showKbModal"
      preset="card"
      title="提炼至 EasyAdapter 知识库"
      style="width: 600px"
      :mask-closable="true"
    >
      <NForm label-placement="left" label-width="70" size="small">
        <NFormItem label="标题">
          <NInput v-model:value="kbTitle" placeholder="知识点标题" clearable />
        </NFormItem>
        <NFormItem label="标签">
          <NInput v-model:value="kbTags" placeholder="逗号分隔，如 telephony, audio, adapt-debug" />
        </NFormItem>
        <NFormItem label="内容">
          <NInput
            v-model:value="kbContent"
            type="textarea"
            placeholder="描述本次调试的关键发现、解决方案和复现步骤..."
            :autosize="{ minRows: 8, maxRows: 20 }"
            style="font-family: monospace; font-size: 12px;"
          />
        </NFormItem>
      </NForm>
      <div class="kb-modal-hint">
        内容将以 Markdown 格式写入 <code>knowledge-base/{{ tahpCtx?.module }}/docs/</code>，
        并自动更新模块索引，下次 AI 查询时可直接召回。
      </div>
      <template #footer>
        <div style="display: flex; justify-content: flex-end; gap: 8px;">
          <NButton @click="showKbModal = false" :disabled="kbSaving">取消</NButton>
          <NButton
            type="primary"
            :loading="kbSaving"
            :disabled="!kbTitle.trim() || !kbContent.trim()"
            @click="submitKbSave"
          >保存至知识库</NButton>
        </div>
      </template>
    </NModal>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.chat-input-area {
  padding: 12px 20px 16px;
  border-top: 1px solid $border-color;
  flex-shrink: 0;
}

.input-top-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 0 6px;
}

.auto-play-speech-switch {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 0 0 8px;
  border-left: 1px solid $border-light;
  margin-left: 4px;

  .switch-label {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    color: #999999;
    font-size: 12px;

    svg {
      opacity: 1;
    }
  }

  :deep(.n-switch),
  :deep(.n-switch__rail) {
    margin-right: 0;
  }
}

.tool-trace-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #999999;
  width: 24px;
  min-width: 24px;
  height: 22px;
  margin-left: -4px;
  padding: 0;
  background: transparent !important;
  opacity: 1;

  :deep(.n-button__state-border),
  :deep(.n-button__border),
  :deep(.n-button__ripple) {
    display: none;
  }

  .tool-trace-icon {
    display: block;
    flex: 0 0 16px;
    width: 16px;
    height: 16px;
  }

  &.active {
    color: #999999;
    opacity: 1;
  }

  &:hover {
    color: #999999;
    opacity: 1;
  }
}

.context-info {
  font-size: 11px;
  color: $text-muted;

  &.context-warning {
    color: #e8a735;
  }
}

.context-limit-editable {
  cursor: pointer;
  border-bottom: 1px dashed transparent;
  transition: all 0.2s ease;
  padding: 0 2px;

  &:hover {
    border-bottom-color: $text-muted;
    background: rgba(128, 128, 128, 0.1);
    border-radius: 2px;
  }
}

.context-bar {
  width: 60px;
  height: 4px;
  background: rgba(128, 128, 128, 0.2);
  border-radius: 2px;
  overflow: hidden;
}

.context-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, rgba(128, 128, 128, 0.3), rgba(128, 128, 128, 0.6));
  border-radius: 2px;
  transition: width 0.3s ease;

  &.context-bar-warn {
    background: linear-gradient(90deg, #c98a1a, #e8a735);
  }

  &.context-bar-danger {
    background: linear-gradient(90deg, #c43a2a, #e85d4a);
  }
}

.attachment-previews {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 0 10px;
}

.attachment-preview {
  position: relative;
  border-radius: $radius-sm;
  overflow: hidden;
  background-color: $bg-secondary;
  border: 1px solid $border-color;

  &.image {
    width: 64px;
    height: 64px;
  }
}

.attachment-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.attachment-file {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  padding: 8px 12px;
  min-width: 80px;
  max-width: 140px;
  color: $text-secondary;

  .file-name {
    font-size: 11px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }

  .file-size {
    font-size: 10px;
    color: $text-muted;
  }
}

.attachment-remove {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.5);
  color: var(--text-on-overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0;
  transition: opacity $transition-fast;

  .attachment-preview:hover & {
    opacity: 1;
  }
}

.file-input-hidden {
  display: none;
}

.input-wrapper {
  display: flex;
  align-items: center;
  gap: 10px;
  background-color: $bg-input;
  border: 1px solid $border-color;
  border-radius: $radius-md;
  padding: 10px 12px;
  position: relative;
  transition: border-color $transition-fast, background-color $transition-fast;

  &:focus-within {
    border-color: $accent-primary;
  }

  .dark & {
    background-color: #333333;
  }
}

.resize-handle {
  position: absolute;
  top: -4px;
  left: 0;
  right: 0;
  height: 8px;
  cursor: row-resize;
  z-index: 2;

  &:hover {
    background: rgba($accent-primary, 0.15);
    border-radius: 4px;
  }
}

.input-textarea {
  flex: 1;
  background: none;
  border: none;
  outline: none;
  color: $text-primary;
  font-family: $font-ui;
  font-size: 14px;
  line-height: 1.5;
  resize: none;
  max-height: 400px;
  min-height: 20px;
  overflow-y: auto;

  &::placeholder {
    color: $text-muted;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

.input-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
  align-items: center;
}

.slash-command-dropdown {
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: calc(100% + 8px);
  max-height: 240px;
  overflow-y: auto;
  background: $bg-primary;
  border: 1px solid $border-color;
  border-radius: $radius-sm;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.16);
  z-index: 20;
  padding: 4px;

  .dark & {
    background: #2a2a2a;
  }
}

.slash-command-item {
  display: grid;
  grid-template-columns: auto auto 1fr;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: $radius-sm;
  cursor: pointer;
  min-height: 36px;

  &.active,
  &:hover {
    background: rgba(var(--accent-primary-rgb), 0.1);
  }
}

.slash-command-name {
  font-family: $font-code;
  font-size: 13px;
  color: $accent-primary;
  white-space: nowrap;
}

.slash-command-args {
  font-family: $font-code;
  font-size: 12px;
  color: $text-muted;
  white-space: nowrap;
}

.slash-command-desc {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: $text-secondary;
  font-size: 12px;
}

.dropdown-fade-enter-active,
.dropdown-fade-leave-active {
  transition: opacity 0.12s ease, transform 0.12s ease;
}

.dropdown-fade-enter-from,
.dropdown-fade-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

// Drag-over state
.input-wrapper.drag-over {
  border-color: var(--accent-info);
  border-style: dashed;
  background-color: rgba(var(--accent-info-rgb), 0.04);
}

// ─── TAHP 适配调试模式横幅 ─────────────────────────────────────────────────────
.tahp-ctx-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 6px 14px;
  background: linear-gradient(90deg, rgba(56, 139, 253, 0.08) 0%, rgba(56, 139, 253, 0.04) 100%);
  border-bottom: 1px solid rgba(56, 139, 253, 0.2);
  border-top: 1px solid rgba(56, 139, 253, 0.12);
  font-size: 12px;
}

.tahp-banner-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}

.tahp-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #388bfd;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.5px;
  padding: 1px 5px;
  border-radius: 3px;
  flex-shrink: 0;
}

.tahp-banner-text {
  color: $text-secondary;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  strong { color: $text-primary; }
}

.tahp-skill-tag {
  opacity: 0.75;
}

.tahp-banner-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.tahp-kb-btn {
  font-size: 11px;
}

.tahp-banner-close {
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px;
  color: $text-muted;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 3px;
  transition: background 0.15s;
  &:hover { background: rgba(0,0,0,.06); color: $text-primary; }
}

// ─── 知识库沉淀弹窗提示 ────────────────────────────────────────────────────────
.kb-modal-hint {
  margin-top: 12px;
  padding: 8px 12px;
  background: rgba(56, 139, 253, 0.06);
  border: 1px solid rgba(56, 139, 253, 0.2);
  border-radius: 6px;
  font-size: 11px;
  color: $text-muted;
  line-height: 1.6;
  code {
    font-family: monospace;
    background: rgba(56, 139, 253, 0.1);
    padding: 1px 4px;
    border-radius: 3px;
    color: #388bfd;
  }
}
</style>
