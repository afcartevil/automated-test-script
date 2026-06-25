/**
 * Gerrit Code Review 会话状态 — 跨页面导航保持评审进度与对话记录。
 */
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { sendGerritReviewMessage, fetchRecommendCases, type RecommendedCase } from '@/api/tahp/gerrit-review'
import { extractModules, extractP0TestSuggestions } from '@/utils/gerrit-review-report'
import { useTahpTasksStore } from './tasks'

export interface GerritChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  taskId?: string
}

export interface RecommendedCaseView extends RecommendedCase {
  checked: boolean
}

export const useGerritReviewStore = defineStore('tahp-gerrit-review', () => {
  const sessionId = ref<string | null>(null)
  const chatMessages = ref<GerritChatMessage[]>([])
  const activeTaskId = ref<string | null>(null)
  const runningTaskId = ref<string | null>(null)
  const taskStatus = ref('')
  const sending = ref(false)
  const finalizedTaskIds = ref<string[]>([])
  const serverP0Items = ref<string[]>([])
  const serverP0Raw = ref('')
  const serverModules = ref<string[]>([])
  const serverModulesDisplay = ref('未识别')
  const recommendedCases = ref<RecommendedCaseView[]>([])

  let watcherInstalled = false
  let insightApplySeq = 0

  function isActiveRunTask(taskId: string): boolean {
    return activeTaskId.value === taskId
      || runningTaskId.value === taskId
      || runningTaskId.value === 'pending'
  }

  function shouldClearRunningForTask(taskId: string): boolean {
    return runningTaskId.value === taskId
      || runningTaskId.value === 'pending'
      || activeTaskId.value === taskId
  }

  function isFinalized(taskId: string): boolean {
    return finalizedTaskIds.value.includes(taskId)
  }

  function markFinalized(taskId: string) {
    if (!finalizedTaskIds.value.includes(taskId)) {
      finalizedTaskIds.value = [...finalizedTaskIds.value, taskId]
    }
  }

  function streamFor(taskId: string | null) {
    if (!taskId) return []
    return useTahpTasksStore().getStream(taskId)
  }

  const stream = computed(() => streamFor(activeTaskId.value))

  const streamingText = computed(() =>
    stream.value
      .filter(ev => ev.type === 'task.message' && ev.payload?.level !== 'reasoning')
      .map(ev => String(ev.payload?.text ?? ''))
      .join(''),
  )

  const isRunning = computed(() => sending.value || runningTaskId.value !== null)

  function clearRunningState(terminalStatus: 'completed' | 'failed' = 'completed') {
    runningTaskId.value = null
    sending.value = false
    taskStatus.value = terminalStatus
  }

  function responseFromStream(taskId: string): string {
    const events = streamFor(taskId)
    const streamText = events
      .filter(ev => ev.type === 'task.message' && ev.payload?.level !== 'reasoning')
      .map(ev => String(ev.payload?.text ?? ''))
      .join('')
    const completed = events.find(e => e.type === 'task.completed')
    if (completed) {
      const fromPayload = String(completed.payload?.llm_response ?? completed.payload?.response ?? '').trim()
      if (fromPayload) return fromPayload
      return streamText
    }
    return streamText
  }

  function finalizeAssistantForTask(
    taskId: string,
    content: string,
    terminalStatus: 'completed' | 'failed' = 'completed',
  ) {
    for (const msg of chatMessages.value) {
      if (msg.streaming && msg.taskId && msg.taskId !== taskId) {
        msg.streaming = false
      }
    }

    let idx = -1
    for (let i = chatMessages.value.length - 1; i >= 0; i--) {
      const m = chatMessages.value[i]
      if (m.streaming && m.taskId === taskId) {
        idx = i
        break
      }
    }
    if (idx < 0 && isActiveRunTask(taskId)) {
      for (let i = chatMessages.value.length - 1; i >= 0; i--) {
        if (chatMessages.value[i].streaming) {
          idx = i
          break
        }
      }
    }

    if (idx >= 0) {
      chatMessages.value[idx] = {
        ...chatMessages.value[idx],
        content,
        streaming: false,
        taskId,
      }
    } else if (content) {
      chatMessages.value.push({
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content,
        taskId,
      })
    }
    chatMessages.value = [...chatMessages.value]
    if (shouldClearRunningForTask(taskId)) {
      clearRunningState(terminalStatus)
    }
  }

  function mapRecommendedCases(items: RecommendedCase[]): RecommendedCaseView[] {
    return items.map(item => ({ ...item, checked: true }))
  }

  function resolveTaskResponse(
    payload: Record<string, unknown>,
    sourceTaskId?: string,
  ): string {
    const fromPayload = String(payload?.llm_response ?? payload?.response ?? '').trim()
    if (fromPayload) return fromPayload
    if (sourceTaskId) return responseFromStream(sourceTaskId)
    return ''
  }

  async function loadRecommendedCasesForP0(
    p0Items: string[],
    seq: number,
    sourceTaskId?: string,
  ) {
    if (!p0Items.length) {
      if (seq === insightApplySeq) recommendedCases.value = []
      return
    }

    try {
      const data = await fetchRecommendCases({ p0_items: p0Items })
      if (seq !== insightApplySeq) return
      if (sourceTaskId && activeTaskId.value && activeTaskId.value !== sourceTaskId) return
      recommendedCases.value = mapRecommendedCases(data.recommended_cases || [])
    } catch {
      if (seq === insightApplySeq) {
        recommendedCases.value = []
      }
    }
  }

  async function applyReviewInsightFromPayload(
    payload: Record<string, unknown>,
    sourceTaskId?: string,
  ) {
    if (sourceTaskId && activeTaskId.value && activeTaskId.value !== sourceTaskId) {
      return
    }

    const seq = ++insightApplySeq
    const response = resolveTaskResponse(payload, sourceTaskId)
    const p0Items = payload?.p0_items
    let p0ForRecommend: string[] = []
    if (Array.isArray(p0Items) && p0Items.length) {
      serverP0Items.value = p0Items.map(String).filter(Boolean)
      serverP0Raw.value = String(payload?.p0_raw_section ?? '')
      p0ForRecommend = serverP0Items.value
    } else if (response) {
      const extracted = extractP0TestSuggestions(response)
      serverP0Items.value = extracted.items
      serverP0Raw.value = extracted.rawSection
      p0ForRecommend = extracted.items
    }

    if (Array.isArray(payload?.modules)) {
      serverModules.value = payload.modules.map(String).filter(Boolean)
      serverModulesDisplay.value = String(payload?.modules_display ?? '') || (
        serverModules.value.length ? serverModules.value.join('/') : '未识别'
      )
    } else if (response) {
      const moduleInfo = extractModules(response)
      serverModules.value = moduleInfo.modules
      serverModulesDisplay.value = moduleInfo.display
    }

    if (Array.isArray(payload?.recommended_cases) && payload.recommended_cases.length) {
      if (seq === insightApplySeq) {
        recommendedCases.value = mapRecommendedCases(payload.recommended_cases as RecommendedCase[])
      }
      return
    }

    await loadRecommendedCasesForP0(p0ForRecommend, seq, sourceTaskId)
  }

  async function ensureRecommendedCases() {
    if (isRunning.value || recommendedCases.value.length) return
    const items = p0Result().items
    if (!items.length) return
    const seq = ++insightApplySeq
    await loadRecommendedCasesForP0(items, seq)
  }

  function handleTerminalStreamEvent(
    taskId: string,
    completed: { payload: Record<string, unknown> } | undefined,
    failed: { payload: Record<string, unknown> } | undefined,
  ) {
    if (completed) {
      const response = resolveTaskResponse(completed.payload, taskId)
      finalizeAssistantForTask(taskId, response, 'completed')
      void applyReviewInsightFromPayload(
        { ...completed.payload, llm_response: response, response },
        taskId,
      )
      return
    }
    if (failed) {
      finalizeAssistantForTask(
        taskId,
        `**评审失败**\n\n${failed.payload?.error ?? failed.payload?.message ?? '未知错误'}`,
        'failed',
      )
    }
  }

  function clearRunningIfTaskTerminal(taskId: string) {
    const events = streamFor(taskId)
    const hasTerminal = events.some(e => e.type === 'task.completed' || e.type === 'task.failed')
    if (!hasTerminal) return

    const stillStreaming = chatMessages.value.some(
      m => m.streaming && (m.taskId === taskId || (!m.taskId && isActiveRunTask(taskId))),
    )
    if (stillStreaming) return

    if (
      runningTaskId.value === taskId
      || runningTaskId.value === 'pending'
      || activeTaskId.value === taskId
    ) {
      clearRunningState('completed')
    }
  }

  function processStreamEvents(taskId: string) {
    if (!taskId) return

    const events = streamFor(taskId)
    const completed = events.find(e => e.type === 'task.completed')
    const failed = events.find(e => e.type === 'task.failed')
    if (!completed && !failed) return

    if (isFinalized(taskId)) {
      const stillStreaming = chatMessages.value.some(
        m => m.streaming && (m.taskId === taskId || (!m.taskId && isActiveRunTask(taskId))),
      )
      const stillRunning = runningTaskId.value === taskId
        || (runningTaskId.value === 'pending' && activeTaskId.value === taskId)
      if ((stillStreaming || stillRunning) && (completed || failed)) {
        handleTerminalStreamEvent(taskId, completed, failed)
      }
      return
    }

    if (completed) {
      markFinalized(taskId)
      handleTerminalStreamEvent(taskId, completed, failed)
      return
    }
    if (failed) {
      markFinalized(taskId)
      handleTerminalStreamEvent(taskId, undefined, failed)
    }
  }

  function syncAllStreamingTasks() {
    const taskIds = new Set<string>()
    if (activeTaskId.value) taskIds.add(activeTaskId.value)
    if (runningTaskId.value && runningTaskId.value !== 'pending') {
      taskIds.add(runningTaskId.value)
    }
    for (const msg of chatMessages.value) {
      if (msg.streaming && msg.taskId) taskIds.add(msg.taskId)
      if (msg.taskId) taskIds.add(msg.taskId)
    }
    for (const tid of taskIds) {
      processStreamEvents(tid)
      clearRunningIfTaskTerminal(tid)
    }
  }

  function ensureTaskWatcher() {
    if (watcherInstalled) return
    watcherInstalled = true
    const tasksStore = useTahpTasksStore()
    watch(
      () => tasksStore.taskStreams,
      () => {
        syncAllStreamingTasks()
      },
      { deep: true },
    )
  }

  function reconcileActiveTask() {
    syncAllStreamingTasks()

    const tid = activeTaskId.value
    if (!tid) {
      if (runningTaskId.value && runningTaskId.value !== 'pending') {
        clearRunningIfTaskTerminal(runningTaskId.value)
      }
      void ensureRecommendedCases()
      return
    }

    if (isFinalized(tid)) {
      clearRunningIfTaskTerminal(tid)
      void ensureRecommendedCases()
      return
    }

    const events = streamFor(tid)
    const hasTerminal = events.some(e => e.type === 'task.completed' || e.type === 'task.failed')
    if (hasTerminal) {
      processStreamEvents(tid)
      clearRunningIfTaskTerminal(tid)
      void ensureRecommendedCases()
      return
    }

    runningTaskId.value = tid
    taskStatus.value = 'running'
    sending.value = false
    const hasBubble = chatMessages.value.some(m => m.taskId === tid && m.streaming)
    if (!hasBubble) {
      chatMessages.value.push({
        id: `assistant-stream-${tid}`,
        role: 'assistant',
        content: '',
        streaming: true,
        taskId: tid,
      })
      chatMessages.value = [...chatMessages.value]
    }
  }

  function prepareForNextSend() {
    syncAllStreamingTasks()
    if (runningTaskId.value && isFinalized(runningTaskId.value)) {
      clearRunningState('completed')
    }
    if (activeTaskId.value && isFinalized(activeTaskId.value)) {
      if (runningTaskId.value === null || runningTaskId.value === activeTaskId.value) {
        clearRunningState('completed')
      }
    }
    if (!runningTaskId.value) {
      sending.value = false
    }
  }

  async function sendMessage(text: string): Promise<void> {
    const trimmed = text.trim()
    if (!trimmed) return

    prepareForNextSend()
    if (isRunning.value) return

    chatMessages.value.push({
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed,
    })

    sending.value = true
    runningTaskId.value = 'pending'
    taskStatus.value = 'running'
    serverP0Items.value = []
    serverP0Raw.value = ''
    serverModules.value = []
    serverModulesDisplay.value = '未识别'
    recommendedCases.value = []

    const pendingId = `assistant-pending-${Date.now()}`
    chatMessages.value.push({
      id: pendingId,
      role: 'assistant',
      content: '',
      streaming: true,
    })
    chatMessages.value = [...chatMessages.value]

    const tasksStore = useTahpTasksStore()
    tasksStore.ensureSocket()
    ensureTaskWatcher()

    try {
      const res = await sendGerritReviewMessage({
        session_id: sessionId.value ?? undefined,
        message: trimmed,
      })

      sessionId.value = res.session_id
      activeTaskId.value = res.task_id
      runningTaskId.value = res.task_id
      sending.value = false
      tasksStore.trackTask(res.task_id)

      const pendingIdx = chatMessages.value.findIndex(m => m.id === pendingId)
      if (pendingIdx >= 0) {
        chatMessages.value[pendingIdx] = {
          ...chatMessages.value[pendingIdx],
          taskId: res.task_id,
        }
        chatMessages.value = [...chatMessages.value]
      }

      processStreamEvents(res.task_id)
    } catch (err) {
      cancelPendingAssistant()
      clearRunningState('failed')
      throw err
    }
  }

  function displayLlmResponse(): string {
    const assistants = chatMessages.value.filter(m => m.role === 'assistant' && !m.streaming)
    const last = assistants[assistants.length - 1]
    if (isRunning.value && streamingText.value) return streamingText.value
    return last?.content ?? ''
  }

  function p0Result() {
    if (serverP0Items.value.length) {
      return { items: serverP0Items.value, rawSection: serverP0Raw.value }
    }
    return extractP0TestSuggestions(displayLlmResponse())
  }

  function modulesResult() {
    if (serverModules.value.length || serverModulesDisplay.value !== '未识别') {
      return { modules: serverModules.value, display: serverModulesDisplay.value }
    }
    return extractModules(displayLlmResponse())
  }

  function setRecommendedCaseChecked(caseKey: string, checked: boolean) {
    recommendedCases.value = recommendedCases.value.map(item =>
      item.caseKey === caseKey ? { ...item, checked } : item,
    )
  }

  const checkedRecommendedCases = computed(() =>
    recommendedCases.value.filter(item => item.checked),
  )

  function reviewInsight() {
    return {
      modules: modulesResult(),
      p0: p0Result(),
      recommendedCases: recommendedCases.value,
      checkedRecommendedCases: checkedRecommendedCases.value,
    }
  }

  function cancelPendingAssistant() {
    const next = chatMessages.value.filter(m => !m.streaming)
    if (next.length !== chatMessages.value.length) {
      chatMessages.value = next
    }
    clearRunningState('failed')
  }

  function init() {
    const tasksStore = useTahpTasksStore()
    tasksStore.ensureSocket()
    ensureTaskWatcher()
    reconcileActiveTask()
  }

  return {
    sessionId,
    chatMessages,
    activeTaskId,
    runningTaskId,
    taskStatus,
    sending,
    finalizedTaskIds,
    serverP0Items,
    serverP0Raw,
    serverModules,
    serverModulesDisplay,
    recommendedCases,
    checkedRecommendedCases,
    stream,
    streamingText,
    isRunning,
    init,
    reconcileActiveTask,
    sendMessage,
    cancelPendingAssistant,
    processStreamEvents,
    displayLlmResponse,
    p0Result,
    modulesResult,
    reviewInsight,
    ensureRecommendedCases,
    toggleRecommendedCase: setRecommendedCaseChecked,
    setRecommendedCaseChecked,
    isFinalized,
  }
})
