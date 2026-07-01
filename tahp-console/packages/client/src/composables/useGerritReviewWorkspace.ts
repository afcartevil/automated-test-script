import { ref, computed, watch, nextTick } from 'vue'
import type { NScrollbar } from 'naive-ui'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import { useModelProviderReadiness } from '@/composables/useModelProviderReadiness'
import { useGerritReviewStore } from '@/stores/tahp/gerrit-review'
import { useDeviceSelfCheckLaunchStore } from '@/stores/tahp/device-self-check-launch'
import { fetchGerritConfig } from '@/api/tahp/gerrit-config'

export const GERRIT_NOT_CONFIGURED_MSG =
  'gerrit账号未设置，无法进行code review，请在设置中完善gerrit账号'

export function useGerritReviewWorkspace() {
  const message = useMessage()
  const gerritStore = useGerritReviewStore()
  const { isReady: modelProviderReady } = useModelProviderReadiness()

  const {
    chatMessages,
    stream,
    streamingText,
    isRunning,
    sending,
    stopping,
    loadingRecommendations,
    isServerRecommending,
    recommendSource,
  } = storeToRefs(gerritStore)

  const showRecommendLoading = computed(
    () => loadingRecommendations.value || isServerRecommending.value,
  )

  const recommendSourceLabel = computed(() => {
    if (recommendSource.value === 'llm') return 'LLM 语义匹配'
    if (recommendSource.value === 'rule') return '关键词规则（LLM 未命中或不可用）'
    return ''
  })

  const inputText = ref('')
  const gerritConfigured = ref(true)
  const thinkingLines = ref<string[]>([])
  const thinkingScrollRef = ref<HTMLElement | null>(null)
  const scrollRef = ref<InstanceType<typeof NScrollbar> | null>(null)
  const textareaRef = ref<HTMLTextAreaElement | null>(null)
  const isComposing = ref(false)

  const latestPhase = computed(() => {
    const phases = stream.value.filter(ev => ev.type === 'task.phase')
    const last = phases[phases.length - 1]
    return last ? String(last.payload?.message ?? '') : ''
  })

  const latestSkillUse = computed(() => {
    const uses = stream.value.filter(ev => ev.type === 'task.skill_use')
    const last = uses[uses.length - 1]
    return last ? String(last.payload?.message ?? last.payload?.skill_id ?? '') : ''
  })

  const p0Result = computed(() => gerritStore.p0Result())
  const modulesResult = computed(() => gerritStore.modulesResult())
  const recommendedCases = computed(() => gerritStore.recommendedCases)
  const checkedRecommendedCount = computed(() => gerritStore.checkedRecommendedCases.length)
  const p0Count = computed(() => p0Result.value.items.length)
  const recommendedCount = computed(() => recommendedCases.value.length)

  const modulesUnrecognized = computed(() =>
    !modulesResult.value.modules.length && modulesResult.value.display === '未识别',
  )

  function rebuildThinkingLines(events: typeof stream.value) {
    const lines: string[] = []
    let reasoningBuf = ''

    for (const ev of events) {
      switch (ev.type) {
        case 'task.started':
          lines.push('▶ Gerrit Code Review 已启动')
          break
        case 'task.phase': {
          const msg = String(ev.payload?.message ?? ev.payload?.phase ?? '').trim()
          if (msg) lines.push(`◆ ${msg}`)
          break
        }
        case 'task.plan': {
          const msg = String(ev.payload?.message ?? '').trim()
          if (msg) lines.push(`◎ ${msg}`)
          break
        }
        case 'task.skill_use': {
          const msg = String(ev.payload?.message ?? ev.payload?.skill_id ?? '').trim()
          if (msg) lines.push(`🛠 ${msg}`)
          break
        }
        case 'task.tool_completed': {
          const msg = String(ev.payload?.message ?? '').trim()
          if (msg) lines.push(`${ev.payload?.error ? '✗' : '✓'} ${msg}`)
          break
        }
        case 'task.message':
          if (ev.payload?.level === 'reasoning') {
            reasoningBuf += String(ev.payload?.text ?? '')
          }
          break
      }
    }

    if (reasoningBuf.trim()) {
      const normalized = reasoningBuf.replace(/\r\n/g, '\n')
      const chunks = normalized.split(/\n+/).map(s => s.trim()).filter(Boolean)
      if (chunks.length) {
        for (const chunk of chunks.slice(-6)) {
          lines.push(`💭 ${chunk.length > 160 ? `${chunk.slice(0, 160)}…` : chunk}`)
        }
      } else {
        const tail = normalized.trim()
        lines.push(`💭 ${tail.length > 160 ? `…${tail.slice(-160)}` : tail}`)
      }
    }

    if (!lines.length && isRunning.value) {
      lines.push('◆ 正在连接 Agent Bridge…')
    }

    thinkingLines.value = lines.slice(-8)
  }

  function bindThinkingScrollRef(el: unknown) {
    thinkingScrollRef.value = (el as HTMLElement | null) ?? null
  }

  function scrollThinkingToBottom() {
    nextTick(() => {
      const el = thinkingScrollRef.value
      if (el) el.scrollTop = el.scrollHeight
    })
  }

  function scrollToBottom() {
    nextTick(() => {
      const el = scrollRef.value?.$el?.querySelector('.n-scrollbar-container')
      if (el) el.scrollTop = el.scrollHeight
    })
  }

  function handleTextareaInput(e: Event) {
    const el = e.target as HTMLTextAreaElement
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 100)}px`
  }

  function ensureModelProviderOrWarn(): boolean {
    if (modelProviderReady.value) return true
    message.warning('请先在「模型管理」中配置模型 Provider 和 API Key')
    return false
  }

  async function loadGerritConfigStatus() {
    try {
      const data = await fetchGerritConfig()
      gerritConfigured.value = data.configured
    } catch {
      gerritConfigured.value = false
    }
  }

  async function handleStop() {
    try {
      await gerritStore.stopReview()
    } catch (err) {
      message.error((err as Error).message || '停止失败')
    }
  }

  async function handleSend() {
    const text = inputText.value.trim()
    if (!text || isRunning.value) return
    if (!gerritConfigured.value) return
    if (!ensureModelProviderOrWarn()) return

    inputText.value = ''
    if (textareaRef.value) textareaRef.value.style.height = 'auto'
    thinkingLines.value = ['◆ 正在提交评审任务…']
    scrollToBottom()

    try {
      await gerritStore.sendMessage(text)
    } catch (err) {
      gerritStore.cancelPendingAssistant()
      gerritStore.taskStatus = 'failed'
      message.error((err as Error).message || '发送失败')
    }
  }

  function handleCompositionStart() {
    isComposing.value = true
  }

  function handleCompositionEnd() {
    requestAnimationFrame(() => {
      isComposing.value = false
    })
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key !== 'Enter' || e.shiftKey) return
    if (isComposing.value || e.isComposing || e.keyCode === 229) return
    e.preventDefault()
    void handleSend()
  }

  watch(streamingText, () => {
    if (isRunning.value) scrollToBottom()
  })

  watch(thinkingLines, () => {
    if (isRunning.value) {
      scrollThinkingToBottom()
      scrollToBottom()
    }
  }, { deep: true })

  watch(stream, (events) => {
    rebuildThinkingLines(events)
    scrollThinkingToBottom()
  }, { deep: true })

  watch(
    () => [p0Result.value.items.length, isRunning.value, recommendedCases.value.length] as const,
    ([p0Count, running, recCount]) => {
      if (recCount > 0 || p0Count === 0) return
      if (running) return
      if (loadingRecommendations.value || gerritStore.isRefreshingRecommendations()) return
      if (gerritStore.isApplyingReviewInsight()) return
      void gerritStore.ensureRecommendedCases()
    },
  )

  function setRecommendedCaseChecked(caseKey: string, checked: boolean) {
    gerritStore.setRecommendedCaseChecked(caseKey, checked)
  }

  function handleStartRecommendedTest() {
    const caseKeys = gerritStore.checkedRecommendedCases.map(item => item.caseKey)
    if (!caseKeys.length) {
      message.warning('请至少选择一个推荐测试用例')
      return
    }
    useDeviceSelfCheckLaunchStore().launchCustomTestFromGerrit(caseKeys)
    message.info('已跳转自定义测试，请选择测试机后执行')
  }

  async function handleRefreshRecommend() {
    if (!p0Count.value) {
      message.warning('暂无必须测试项，无法推荐用例')
      return
    }
    try {
      const hasCases = await gerritStore.refreshRecommendedCases()
      if (!hasCases) {
        message.info('未匹配到推荐用例，请检查必须测试描述或稍后重试')
      }
    } catch (err) {
      message.error((err as Error).message || '重新推荐失败')
    }
  }

  function restoreWorkspace() {
    gerritStore.init()
    void loadGerritConfigStatus()
    rebuildThinkingLines(stream.value)
    scrollToBottom()
  }

  return {
    GERRIT_NOT_CONFIGURED_MSG,
    chatMessages,
    streamingText,
    isRunning,
    sending,
    stopping,
    inputText,
    gerritConfigured,
    thinkingLines,
    thinkingScrollRef,
    scrollRef,
    textareaRef,
    latestPhase,
    latestSkillUse,
    p0Result,
    modulesResult,
    recommendedCases,
    checkedRecommendedCount,
    p0Count,
    recommendedCount,
    loadingRecommendations,
    showRecommendLoading,
    recommendSourceLabel,
    modulesUnrecognized,
    bindThinkingScrollRef,
    toggleRecommendedCase: setRecommendedCaseChecked,
    setRecommendedCaseChecked,
    handleStartRecommendedTest,
    handleRefreshRecommend,
    handleTextareaInput,
    handleSend,
    handleStop,
    handleCompositionStart,
    handleCompositionEnd,
    handleKeydown,
    restoreWorkspace,
  }
}
