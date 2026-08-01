<script setup lang="ts">
import type { Attachment } from '@/stores/hermes/chat'
import { useChatStore } from '@/stores/hermes/chat'
import { useAppStore } from '@/stores/hermes/app'
import { useProfilesStore } from '@/stores/hermes/profiles'
import { fetchContextLength } from '@/api/hermes/sessions'
import { setModelContext } from '@/api/hermes/model-context'
import { NButton, NTooltip, NSwitch, NModal, NInputNumber, NInput, NForm, NFormItem, NTag, NSelect, NPopover, useMessage } from 'naive-ui'
import { computed, ref, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToolTraceVisibility } from '@/composables/useToolTraceVisibility'
import { useModelProviderReadiness } from '@/composables/useModelProviderReadiness'
import { saveKnowledgeFromChat, fetchDifyOptions } from '@/api/tahp/knowledge'

const props = withDefaults(defineProps<{
  centered?: boolean
}>(), {
  centered: false,
})

const chatStore = useChatStore()
const { t } = useI18n()
const message = useMessage()
const { isReady: modelProviderReady } = useModelProviderReadiness()
const { toolTraceVisible, setToolTraceVisible } = useToolTraceVisibility()
const inputText = ref('')
const textareaRef = ref<HTMLTextAreaElement>()
const commandDropdownRef = ref<HTMLDivElement>()
const fileInputRef = ref<HTMLInputElement>()
const attachments = ref<Attachment[]>([])
const isDragging = ref(false)
const dragCounter = ref(0)
const isComposing = ref(false)
const plusMenuOpen = ref(false)

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

// 对话检索模式（分场景检索）
type RetrievalModeOption = 'auto' | 'historical' | 'concept' | 'sop' | 'adapt'
const retrievalMode = ref<RetrievalModeOption>('auto')
const searchLark = ref(false)
const searchDify = ref(true) // Mode A: default ON, user can turn off
const difyEnabled = ref(false)
const retrievalModeOptions = [
  { label: '自动', value: 'auto' },
  { label: '历史案例', value: 'historical' },
  { label: '概念文档', value: 'concept' },
  { label: '分析 SOP', value: 'sop' },
  { label: '适配指南', value: 'adapt' },
]

onMounted(() => {
  const savedMode = localStorage.getItem('tahp_retrieval_mode') as RetrievalModeOption | null
  if (savedMode && retrievalModeOptions.some(o => o.value === savedMode)) {
    retrievalMode.value = savedMode
  }
  const savedLark = localStorage.getItem('tahp_search_lark')
  if (savedLark !== null) searchLark.value = savedLark === 'true'
  const savedDify = localStorage.getItem('tahp_search_dify')
  // Default ON when no preference saved
  if (savedDify !== null) searchDify.value = savedDify === 'true'
  else searchDify.value = true

  void fetchDifyOptions().then((opts) => {
    difyEnabled.value = opts.enabled
    // Server explicitly disabled → force off locally
    if (!opts.enabled) searchDify.value = false
  }).catch(() => {
    // Options API transient failure: keep user preference / default-ON and show controls.
    // Server-side difyEnabled() still gates the actual supplement emit.
    difyEnabled.value = true
  })

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
watch(retrievalMode, (value) => {
  localStorage.setItem('tahp_retrieval_mode', value)
})

watch(searchLark, (value) => {
  localStorage.setItem('tahp_search_lark', String(value))
})

watch(searchDify, (value) => {
  localStorage.setItem('tahp_search_dify', String(value))
})

const canSend = computed(() =>
  modelProviderReady.value && (inputText.value.trim() || attachments.value.length > 0),
)

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
  if (!modelProviderReady.value) {
    message.warning('请先在「配置 → 模型管理」中配置模型 Provider 和 API Key')
    return
  }
  const text = inputText.value.trim()
  if (!text && attachments.value.length === 0) return

  const tahpInstructions = tahpCtx.value ? buildTahpHandoffInstructions(tahpCtx.value) : undefined
  chatStore.sendMessage(
    text,
    attachments.value.length > 0 ? attachments.value : undefined,
    {
      ...(tahpInstructions ? { instructions: tahpInstructions } : {}),
      retrieval_mode: retrievalMode.value,
      search_lark: searchLark.value,
      search_dify: difyEnabled.value ? searchDify.value : false,
      // kb_tag omitted: server resolveKbTag() defaults to 全局搜索
    },
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
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
}

function handleAttachFromMenu() {
  plusMenuOpen.value = false
  handleAttachClick()
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

function closeTahpContextBanner() {
  tahpCtx.value = null
  sessionStorage.removeItem('tahp_chat_context')
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
  <div class="chat-input-area" :class="{ centered: props.centered }">

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
        <button class="tahp-banner-close" @click="closeTahpContextBanner">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
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
        <button class="attachment-remove" type="button" @click="removeAttachment(att.id)">
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

      <NPopover
        v-model:show="plusMenuOpen"
        trigger="click"
        placement="top-start"
        :show-arrow="false"
        raw
        class="plus-menu-popover"
      >
        <template #trigger>
          <button
            type="button"
            class="pill-icon-btn plus-btn"
            :aria-label="t('chat.advancedOptions')"
            :aria-expanded="plusMenuOpen"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </button>
        </template>
        <div class="plus-menu">
          <button type="button" class="plus-menu-item" @click="handleAttachFromMenu">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
            </svg>
            <span>{{ t('chat.attachFiles') }}</span>
          </button>

          <div class="plus-menu-section">
            <div class="plus-menu-label">{{ t('chat.retrievalMode') }}</div>
            <NSelect
              v-model:value="retrievalMode"
              :options="retrievalModeOptions"
              size="small"
              class="plus-menu-select"
            />
          </div>

          <label class="plus-menu-toggle">
            <span>搜索飞书</span>
            <NSwitch v-model:value="searchLark" size="small" />
          </label>

          <label v-if="difyEnabled" class="plus-menu-toggle" title="开启后本地先答，底软通信知识库异步补充参考">
            <span>底软通信知识库</span>
            <NSwitch v-model:value="searchDify" size="small" />
          </label>

          <label class="plus-menu-toggle">
            <span>{{ toolTraceVisible ? t('chat.hideToolCalls') : t('chat.showToolCalls') }}</span>
            <NSwitch
              :value="toolTraceVisible"
              size="small"
              @update:value="setToolTraceVisible"
            />
          </label>

          <div v-if="totalTokens > 0" class="plus-menu-context">
            <button type="button" class="plus-menu-context-btn" @click="handleEditContextLimit">
              {{ formatTokens(totalTokens) }} / {{ formatTokens(contextLength) }}
              · {{ t('chat.contextRemaining') }} {{ formatTokens(remainingTokens) }}
            </button>
            <div class="context-bar">
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
        </div>
      </NPopover>

      <textarea
        ref="textareaRef"
        v-model="inputText"
        class="input-textarea"
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

      <NTooltip v-if="chatStore.isStreaming" trigger="hover">
        <template #trigger>
          <button
            type="button"
            class="pill-action-btn stop"
            :disabled="chatStore.isAborting"
            :aria-label="t('chat.stop')"
            @click="chatStore.stopStreaming()"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          </button>
        </template>
        {{ t('chat.stop') }}
      </NTooltip>
      <NTooltip v-else trigger="hover">
        <template #trigger>
          <button
            type="button"
            class="pill-action-btn send"
            :disabled="!canSend"
            :aria-label="t('chat.send')"
            @click="handleSend"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="19" x2="12" y2="5" />
              <polyline points="5 12 12 5 19 12" />
            </svg>
          </button>
        </template>
        {{ t('chat.send') }}
      </NTooltip>
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
  padding: 0;
  border-top: none;
  flex-shrink: 0;
  width: 100%;
  background: transparent;
}

.context-bar {
  width: 100%;
  height: 4px;
  background: rgba(128, 128, 128, 0.2);
  border-radius: 2px;
  overflow: hidden;
  margin-top: 8px;
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
  align-items: flex-end;
  gap: 8px;
  min-height: 56px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 28px;
  padding: 8px 10px 8px 8px;
  position: relative;
  box-shadow: 0 8px 28px rgba(20, 24, 40, 0.08);
  transition: border-color $transition-fast, box-shadow $transition-fast;

  &:focus-within {
    border-color: color-mix(in srgb, var(--accent) 45%, var(--line));
    box-shadow: 0 10px 32px rgba(20, 24, 40, 0.12);
  }

  .dark & {
    background: #2a2a2a;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.28);
  }
}

.pill-icon-btn {
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--muted);
  display: grid;
  place-items: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s ease, color 0.15s ease;

  &:hover {
    background: var(--bg);
    color: var(--text);
  }

  &:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
}

.input-textarea {
  flex: 1;
  min-width: 0;
  background: none;
  border: none;
  outline: none;
  color: $text-primary;
  font-family: $font-ui;
  font-size: 15px;
  line-height: 1.45;
  resize: none;
  max-height: 160px;
  min-height: 24px;
  padding: 8px 4px;
  overflow-y: auto;

  &::placeholder {
    color: $text-muted;
  }
}

.pill-action-btn {
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 50%;
  display: grid;
  place-items: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s ease, color 0.15s ease, opacity 0.15s ease;

  &.send {
    background: #e8eaed;
    color: #202124;

    &:hover:not(:disabled) {
      background: #dadce0;
    }

    &:disabled {
      opacity: 0.45;
      cursor: not-allowed;
    }
  }

  &.stop {
    background: var(--accent);
    color: #fff;

    &:hover:not(:disabled) {
      filter: brightness(0.95);
    }

    &:disabled {
      opacity: 0.55;
      cursor: not-allowed;
    }
  }

  &:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .dark &.send {
    background: #3c4043;
    color: #e8eaed;
  }
}

.plus-menu {
  width: min(280px, calc(100vw - 32px));
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: var(--surface);
  box-shadow: var(--shadow-lg, 0 16px 40px rgba(0, 0, 0, 0.14));
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.plus-menu-item,
.plus-menu-context-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  padding: 10px 10px;
  cursor: pointer;
  text-align: left;

  &:hover {
    background: var(--bg);
  }
}

.plus-menu-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 4px 4px 0;
}

.plus-menu-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--muted);
  letter-spacing: 0.02em;
}

.plus-menu-select {
  width: 100%;
}

.plus-menu-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 10px;
  border-radius: 10px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;

  &:hover {
    background: var(--bg);
  }
}

.plus-menu-context {
  padding: 4px 4px 2px;
  border-top: 1px solid var(--line);
}

.plus-menu-context-btn {
  color: var(--muted);
  font-weight: 500;
  font-size: 12px;
  padding: 8px 6px;
}

@media (max-width: $breakpoint-mobile) {
  .input-wrapper {
    min-height: 52px;
    border-radius: 24px;
    gap: 6px;
    padding: 6px 8px 6px 6px;
  }

  .pill-icon-btn,
  .pill-action-btn {
    width: 36px;
    height: 36px;
  }

  .input-textarea {
    font-size: 14px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .input-wrapper,
  .pill-icon-btn,
  .pill-action-btn {
    transition: none;
  }
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
