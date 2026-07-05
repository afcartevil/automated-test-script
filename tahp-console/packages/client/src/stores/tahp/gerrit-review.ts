/**
 * Gerrit Code Review 会话状态 — 跨页面导航保持评审进度与对话记录。
 */
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { sendGerritReviewMessage, fetchRecommendCases, cancelGerritReviewTask, type RecommendedCase, type RecommendSource } from '@/api/tahp/gerrit-review'
import { waitForTahpSocketReady } from '@/api/tahp/socket'
import { extractModules, extractP0TestSuggestions } from '@/utils/gerrit-review-report'
import { gerritReviewDebug, gerritRecommendTrace } from '@/utils/gerrit-review-debug'
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
  const stopping = ref(false)
  const finalizedTaskIds = ref<string[]>([])
  const serverP0Items = ref<string[]>([])
  const serverP0Raw = ref('')
  const serverModules = ref<string[]>([])
  const serverModulesDisplay = ref('未识别')
  const recommendedCases = ref<RecommendedCaseView[]>([])
  const loadingRecommendations = ref(false)
  const recommendSource = ref<RecommendSource | null>(null)

  let watcherInstalled = false
  let insightApplySeq = 0
  let recommendLoadSeq = 0
  let applyingReviewInsight = false
  let recommendRefreshPromise: Promise<boolean> | null = null
  let sendMessageInFlight = false
  /** 已完成测试建议/推荐写入的任务，避免 finalized 后 stream 重入重复 apply */
  const reviewInsightHandledTaskIds = new Set<string>()

  function isReviewInsightHandled(taskId: string): boolean {
    return reviewInsightHandledTaskIds.has(taskId)
  }

  function markReviewInsightHandled(taskId: string) {
    reviewInsightHandledTaskIds.add(taskId)
  }

  function resetInsightFieldsForNewTask() {
    insightApplySeq += 1
    serverP0Items.value = []
    serverP0Raw.value = ''
    serverModules.value = []
    serverModulesDisplay.value = '未识别'
    recommendedCases.value = []
    recommendSource.value = null
  }

  function isActiveRunTask(taskId: string): boolean {
    return activeTaskId.value === taskId || runningTaskId.value === taskId
  }

  /** 仅对当前会话关注的任务应用 P0 / 推荐用例，避免多轮评审时旧任务覆盖最新结果。 */
  function isInsightTargetTask(taskId?: string): boolean {
    if (!taskId) return true
    const active = activeTaskId.value
    if (!active) {
      // 新评审 API 尚未返回时忽略 SSE insight，避免写入后在 resetInsightFieldsForNewTask 中被清掉
      if (runningTaskId.value === 'pending') return false
      return true
    }
    return active === taskId
  }

  function shouldClearRunningForTask(taskId: string): boolean {
    return runningTaskId.value === taskId || activeTaskId.value === taskId
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

  function taskHasTerminal(taskId: string): boolean {
    return streamFor(taskId).some(
      e => e.type === 'task.completed' || e.type === 'task.failed' || e.type === 'task.cancelled',
    )
  }

  function hasActiveStreamingForTask(taskId: string): boolean {
    return chatMessages.value.some(
      m => m.streaming && (m.taskId === taskId || (!m.taskId && isActiveRunTask(taskId))),
    )
  }

  function logState(event: string, taskId?: string | null, detail?: Record<string, unknown>) {
    gerritReviewDebug(event, {
      taskId: taskId ?? activeTaskId.value,
      runningTaskId: runningTaskId.value,
      activeTaskId: activeTaskId.value,
      sending: sending.value,
      finalizedCount: finalizedTaskIds.value.length,
      streamingBubbles: chatMessages.value.filter(m => m.streaming).length,
      p0Count: serverP0Items.value.length,
      recommendedCount: recommendedCases.value.length,
      ...detail,
    })
  }

  function traceRecommend(event: string, taskId?: string | null, detail?: Record<string, unknown>) {
    gerritRecommendTrace(event, {
      taskId: taskId ?? activeTaskId.value,
      runningTaskId: runningTaskId.value,
      activeTaskId: activeTaskId.value,
      insightApplySeq,
      applyingReviewInsight,
      isRunning: isRunning.value,
      loadingRecommendations: loadingRecommendations.value,
      p0Count: serverP0Items.value.length,
      recommendedCount: recommendedCases.value.length,
      ...detail,
    })
  }

  const effectiveStreamTaskId = computed(() => {
    if (activeTaskId.value) return activeTaskId.value
    const rid = runningTaskId.value
    if (rid && rid !== 'pending') return rid
    return null
  })

  const stream = computed(() => streamFor(effectiveStreamTaskId.value))

  const streamingText = computed(() =>
    stream.value
      .filter(ev => ev.type === 'task.message' && ev.payload?.level !== 'reasoning')
      .map(ev => String(ev.payload?.text ?? ''))
      .join(''),
  )

  const isServerRecommending = computed(() => {
    const events = stream.value
    const recommending = events.some(
      e => e.type === 'task.phase' && e.payload?.phase === 'RECOMMENDING',
    )
    const terminal = events.some(
      e => e.type === 'task.completed' || e.type === 'task.failed' || e.type === 'task.cancelled',
    )
    return recommending && !terminal
  })

  const isRunning = computed(() => {
    if (sending.value) return true
    const rid = runningTaskId.value
    if (!rid) return false
    if (rid === 'pending') return true
    if (taskHasTerminal(rid)) {
      return hasActiveStreamingForTask(rid)
    }
    return true
  })

  function clearRunningState(terminalStatus: 'completed' | 'failed' = 'completed') {
    logState('clearRunningState', runningTaskId.value, { terminalStatus })
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
    if (idx < 0 && (activeTaskId.value === taskId || runningTaskId.value === taskId)) {
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
    } else {
      for (const msg of chatMessages.value) {
        if (msg.streaming && (msg.taskId === taskId || (!msg.taskId && isActiveRunTask(taskId)))) {
          msg.streaming = false
        }
      }
    }
    chatMessages.value = [...chatMessages.value]

    if (shouldClearRunningForTask(taskId)) {
      clearRunningState(terminalStatus)
    }
  }

  function resolveRecommendSource(
    payload: Record<string, unknown>,
    cases: RecommendedCase[],
  ): RecommendSource | null {
    const raw = payload?.recommend_source
    if (raw === 'llm' || raw === 'rule') return raw
    if (!cases.length) return null
    const ruleLike = cases.every(item =>
      item.reasons?.length && item.reasons.every(r => r.startsWith('必须测试:')),
    )
    return ruleLike ? 'rule' : 'llm'
  }

  function setRecommendSource(source: RecommendSource | null) {
    recommendSource.value = source
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
    modules?: string[],
    options?: { force?: boolean },
  ) {
    traceRecommend('loadRecommendedCasesForP0.start', sourceTaskId, {
      seq,
      force: options?.force === true,
      p0ItemCount: p0Items.length,
      moduleCount: modules?.length ?? 0,
    })
    if (!p0Items.length) {
      if (seq === insightApplySeq) recommendedCases.value = []
      traceRecommend('loadRecommendedCasesForP0.skip_empty_p0', sourceTaskId, { seq })
      return
    }

    const loadId = ++recommendLoadSeq
    loadingRecommendations.value = true
    try {
      const data = await fetchRecommendCases({ p0_items: p0Items, modules })
      logState('loadRecommendedCasesForP0.done', sourceTaskId, {
        seq,
        insightApplySeq,
        p0Items: p0Items.length,
        resultCount: data.recommended_cases?.length ?? 0,
        source: data.source,
        insightTarget: isInsightTargetTask(sourceTaskId),
        force: options?.force === true,
      })
      if (!options?.force && seq !== insightApplySeq) {
        traceRecommend('loadRecommendedCasesForP0.result_dropped', sourceTaskId, {
          reason: 'seq_mismatch',
          seq,
          insightApplySeq,
          resultCount: data.recommended_cases?.length ?? 0,
          source: data.source,
        })
        return
      }
      if (!options?.force && !isInsightTargetTask(sourceTaskId)) {
        traceRecommend('loadRecommendedCasesForP0.result_dropped', sourceTaskId, {
          reason: 'not_insight_target',
          seq,
          resultCount: data.recommended_cases?.length ?? 0,
          source: data.source,
        })
        return
      }
      recommendedCases.value = mapRecommendedCases(data.recommended_cases || [])
      setRecommendSource(data.source ?? resolveRecommendSource({}, data.recommended_cases || []))
      traceRecommend('loadRecommendedCasesForP0.applied', sourceTaskId, {
        seq,
        force: options?.force === true,
        resultCount: recommendedCases.value.length,
        source: data.source,
      })
    } catch (err) {
      logState('loadRecommendedCasesForP0.error', sourceTaskId, {
        seq,
        error: (err as Error).message,
      })
      traceRecommend('loadRecommendedCasesForP0.error', sourceTaskId, {
        seq,
        error: (err as Error).message,
      })
      if (seq === insightApplySeq && options?.force !== true) {
        recommendedCases.value = []
      }
    } finally {
      if (loadId === recommendLoadSeq) {
        loadingRecommendations.value = false
      }
    }
  }

  /** 同步写入 P0 / 模块 / 服务端推荐结果（不受 insightApplySeq 影响） */
  function applyInsightFieldsSync(
    payload: Record<string, unknown>,
    sourceTaskId?: string,
  ): { p0ForRecommend: string[]; serverRecommendApplied: boolean } {
    const payloadRecCount = Array.isArray(payload?.recommended_cases)
      ? (payload.recommended_cases as unknown[]).length
      : -1
    traceRecommend('applyInsightFieldsSync.enter', sourceTaskId, {
      insightTarget: isInsightTargetTask(sourceTaskId),
      payloadHasP0: Array.isArray(payload?.p0_items),
      payloadP0Count: Array.isArray(payload?.p0_items) ? payload.p0_items.length : 0,
      payloadRecCount,
      payloadRecommendSource: payload?.recommend_source ?? null,
    })
    if (!isInsightTargetTask(sourceTaskId)) {
      traceRecommend('applyInsightFieldsSync.skip', sourceTaskId, { reason: 'not_insight_target' })
      return { p0ForRecommend: [], serverRecommendApplied: false }
    }

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

    if (Array.isArray(payload?.recommended_cases)) {
      const cases = payload.recommended_cases as RecommendedCase[]
      const source = payload?.recommend_source
      if (source === 'llm' || source === 'rule') {
        recommendedCases.value = mapRecommendedCases(cases)
        setRecommendSource(source)
        logState('applyInsightFieldsSync.server_recommend', sourceTaskId, {
          recommendedCount: cases.length,
          source,
        })
        traceRecommend('applyInsightFieldsSync.server_recommend', sourceTaskId, {
          recommendedCount: cases.length,
          source,
          emptyCases: cases.length === 0,
        })
        return { p0ForRecommend, serverRecommendApplied: true }
      }
      if (cases.length > 0) {
        recommendedCases.value = mapRecommendedCases(cases)
        setRecommendSource(resolveRecommendSource(payload, cases))
        traceRecommend('applyInsightFieldsSync.server_recommend_inferred', sourceTaskId, {
          recommendedCount: cases.length,
        })
        return { p0ForRecommend, serverRecommendApplied: true }
      }
      traceRecommend('applyInsightFieldsSync.server_rec_empty_no_source', sourceTaskId, {
        payloadRecommendSource: source ?? null,
      })
    } else {
      traceRecommend('applyInsightFieldsSync.no_recommended_cases_field', sourceTaskId)
    }

    traceRecommend('applyInsightFieldsSync.done_no_server_rec', sourceTaskId, {
      p0ForRecommendCount: p0ForRecommend.length,
    })
    return { p0ForRecommend, serverRecommendApplied: false }
  }

  async function finalizeReviewInsight(
    payload: Record<string, unknown>,
    sourceTaskId?: string,
  ) {
    await applyReviewInsightFromPayload(payload, sourceTaskId)
    if (!isInsightTargetTask(sourceTaskId)) return
    if (recommendedCases.value.length) return
    if (!serverP0Items.value.length) return
    await ensureRecommendedCases()
  }

  async function applyReviewInsightFromPayload(
    payload: Record<string, unknown>,
    sourceTaskId?: string,
  ) {
    if (!isInsightTargetTask(sourceTaskId)) {
      logState('applyReviewInsight.skip', sourceTaskId, { reason: 'not_insight_target' })
      traceRecommend('applyReviewInsight.skip', sourceTaskId, { reason: 'not_insight_target' })
      return
    }

    logState('applyReviewInsight.start', sourceTaskId, { insightApplySeq })
    traceRecommend('applyReviewInsight.start', sourceTaskId, { insightApplySeq })
    const { p0ForRecommend, serverRecommendApplied } = applyInsightFieldsSync(payload, sourceTaskId)
    if (serverRecommendApplied) {
      logState('applyReviewInsight.done', sourceTaskId, {
        p0Count: serverP0Items.value.length,
        recommendedCount: recommendedCases.value.length,
        source: 'server',
      })
      traceRecommend('applyReviewInsight.done', sourceTaskId, {
        path: 'server_payload',
        p0Count: serverP0Items.value.length,
        recommendedCount: recommendedCases.value.length,
      })
      return
    }

    if (!p0ForRecommend.length) {
      logState('applyReviewInsight.done', sourceTaskId, {
        p0Count: 0,
        recommendedCount: recommendedCases.value.length,
        source: 'none',
      })
      traceRecommend('applyReviewInsight.done', sourceTaskId, { path: 'no_p0' })
      return
    }

    applyingReviewInsight = true
    const seq = ++insightApplySeq
    traceRecommend('applyReviewInsight.client_fetch', sourceTaskId, { seq, p0Count: p0ForRecommend.length })
    try {
      await loadRecommendedCasesForP0(
        p0ForRecommend,
        seq,
        sourceTaskId,
        serverModules.value.length ? serverModules.value : undefined,
      )
      logState('applyReviewInsight.done', sourceTaskId, {
        seq,
        p0Count: serverP0Items.value.length,
        recommendedCount: recommendedCases.value.length,
        source: 'client_fetch',
      })
      traceRecommend('applyReviewInsight.done', sourceTaskId, {
        path: 'client_fetch',
        seq,
        insightApplySeq,
        recommendedCount: recommendedCases.value.length,
      })
    } finally {
      applyingReviewInsight = false
    }
  }

  async function ensureRecommendedCases() {
    traceRecommend('ensureRecommendedCases.enter', activeTaskId.value, {
      hasRec: recommendedCases.value.length > 0,
    })
    if (recommendedCases.value.length) {
      traceRecommend('ensureRecommendedCases.skip', activeTaskId.value, { reason: 'already_has_rec' })
      return
    }
    if (applyingReviewInsight) {
      traceRecommend('ensureRecommendedCases.skip', activeTaskId.value, { reason: 'applying_review_insight' })
      return
    }
    if (recommendRefreshPromise) {
      traceRecommend('ensureRecommendedCases.wait_refresh', activeTaskId.value)
      await recommendRefreshPromise
      return
    }
    traceRecommend('ensureRecommendedCases.refresh', activeTaskId.value)
    await refreshRecommendedCases()
  }

  function isApplyingReviewInsight(): boolean {
    return applyingReviewInsight
  }

  function isRefreshingRecommendations(): boolean {
    return recommendRefreshPromise !== null
  }

  async function refreshRecommendedCases(): Promise<boolean> {
    if (recommendRefreshPromise) {
      return recommendRefreshPromise
    }

    recommendRefreshPromise = (async () => {
      const items = p0Result().items
      if (!items.length) return false

      logState('refreshRecommendedCases.start', activeTaskId.value, { p0Count: items.length })
      const previous = recommendedCases.value.map(item => ({ ...item }))
      const modules = serverModules.value.length ? serverModules.value : undefined

      await loadRecommendedCasesForP0(
        items,
        insightApplySeq,
        activeTaskId.value ?? undefined,
        modules,
        { force: true },
      )

      if (!recommendedCases.value.length && previous.length) {
        recommendedCases.value = previous
      }

      logState('refreshRecommendedCases.done', activeTaskId.value, {
        recommendedCount: recommendedCases.value.length,
      })
      return recommendedCases.value.length > 0
    })()

    try {
      return await recommendRefreshPromise
    } finally {
      recommendRefreshPromise = null
    }
  }

  function handleTerminalStreamEvent(
    taskId: string,
    completed: { payload: Record<string, unknown> } | undefined,
    failed: { payload: Record<string, unknown> } | undefined,
    cancelled?: { payload: Record<string, unknown> } | undefined,
    caller?: string,
  ) {
    traceRecommend('handleTerminalStreamEvent', taskId, {
      caller: caller ?? 'unknown',
      hasCompleted: !!completed,
      hasFailed: !!failed,
      hasCancelled: !!cancelled,
      stillStreaming: chatMessages.value.some(
        m => m.streaming && (m.taskId === taskId || (!m.taskId && isActiveRunTask(taskId))),
      ),
    })
    if (cancelled) {
      const partial = resolveTaskResponse(cancelled.payload, taskId) || responseFromStream(taskId)
      const stopMsg = String(cancelled.payload?.message ?? cancelled.payload?.error ?? '评审已被用户停止')
      const content = partial.trim()
        ? `${partial.trim()}\n\n---\n\n**${stopMsg}**`
        : `**${stopMsg}**`
      finalizeAssistantForTask(taskId, content, 'failed')
      return
    }
    if (completed) {
      const response = resolveTaskResponse(completed.payload, taskId)
      const payload = { ...completed.payload, llm_response: response, response }
      if (!isReviewInsightHandled(taskId) && isInsightTargetTask(taskId)) {
        applyInsightFieldsSync(payload, taskId)
        markReviewInsightHandled(taskId)
        finalizeAssistantForTask(taskId, response, 'completed')
        void finalizeReviewInsight(payload, taskId)
      } else {
        finalizeAssistantForTask(taskId, response, 'completed')
      }
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
    const completed = events.find(e => e.type === 'task.completed')
    const failed = events.find(e => e.type === 'task.failed')
    const cancelled = events.find(e => e.type === 'task.cancelled')
    if (!completed && !failed && !cancelled) return

    const stillStreaming = chatMessages.value.some(
      m => m.streaming && (m.taskId === taskId || (!m.taskId && isActiveRunTask(taskId))),
    )
    if (stillStreaming) {
      if (!isFinalized(taskId)) {
        markFinalized(taskId)
      }
      handleTerminalStreamEvent(taskId, completed, failed, cancelled)
      if (hasActiveStreamingForTask(taskId)) {
        recoverStreamingForTerminalTask(taskId)
      }
      return
    }

    if (shouldClearRunningForTask(taskId)) {
      clearRunningState(cancelled || completed ? 'completed' : 'failed')
    }
  }

  function finalizeStaleStreamingBubbles() {
    let changed = false
    for (const msg of chatMessages.value) {
      if (!msg.streaming) continue
      if (msg.taskId && isFinalized(msg.taskId)) {
        msg.streaming = false
        changed = true
      }
    }
    if (changed) {
      chatMessages.value = [...chatMessages.value]
    }
  }

  function recoverStreamingForTerminalTask(taskId: string) {
    if (!taskHasTerminal(taskId) || !hasActiveStreamingForTask(taskId)) return
    const events = streamFor(taskId)
    const completed = events.find(e => e.type === 'task.completed')
    const failed = events.find(e => e.type === 'task.failed')
    const cancelled = events.find(e => e.type === 'task.cancelled')
    handleTerminalStreamEvent(taskId, completed, failed, cancelled)
  }

  function sweepStaleRunningState() {
    const rid = runningTaskId.value
    if (!rid || rid === 'pending') {
      if (rid === 'pending' && !sending.value) {
        runningTaskId.value = null
      }
      return
    }

    if (!taskHasTerminal(rid)) return

    if (hasActiveStreamingForTask(rid)) {
      recoverStreamingForTerminalTask(rid)
    }

    if (!hasActiveStreamingForTask(rid)) {
      if (!isFinalized(rid)) {
        processStreamEvents(rid)
      }
      clearRunningState('completed')
    }
  }

  function processStreamEvents(taskId: string) {
    if (!taskId) return

    const events = streamFor(taskId)
    const completed = events.find(e => e.type === 'task.completed')
    const failed = events.find(e => e.type === 'task.failed')
    const cancelled = events.find(e => e.type === 'task.cancelled')
    if (!completed && !failed && !cancelled) return

    if (isFinalized(taskId)) {
      const needsRecovery = chatMessages.value.some(
        m => m.streaming && (m.taskId === taskId || (!m.taskId && isActiveRunTask(taskId))),
      )
      if (needsRecovery) {
        traceRecommend('processStreamEvents.finalized_recovery', taskId, { needsRecovery: true })
        handleTerminalStreamEvent(taskId, completed, failed, cancelled, 'processStreamEvents.finalized_recovery')
      } else if (completed && isInsightTargetTask(taskId) && !isReviewInsightHandled(taskId)) {
        traceRecommend('processStreamEvents.finalized_recovery_insight', taskId, {
          streamEventCount: events.length,
          payloadRecCount: Array.isArray(completed.payload?.recommended_cases)
            ? (completed.payload.recommended_cases as unknown[]).length
            : -1,
        })
        const response = resolveTaskResponse(completed.payload, taskId)
        const payload = { ...completed.payload, llm_response: response, response }
        applyInsightFieldsSync(payload, taskId)
        markReviewInsightHandled(taskId)
        void finalizeReviewInsight(payload, taskId)
      } else if (completed && isReviewInsightHandled(taskId)) {
        traceRecommend('processStreamEvents.finalized_replay_skip', taskId, {
          reason: 'insight_already_handled',
        })
      }
      clearRunningIfTaskTerminal(taskId)
      return
    }

    if (completed) {
      markFinalized(taskId)
      logState('processStreamEvents.completed', taskId)
      traceRecommend('processStreamEvents.first_complete', taskId, {
        streamEventCount: events.length,
        payloadRecCount: Array.isArray(completed.payload?.recommended_cases)
          ? (completed.payload.recommended_cases as unknown[]).length
          : -1,
      })
      handleTerminalStreamEvent(taskId, completed, failed, cancelled, 'processStreamEvents.first_complete')
      return
    }
    if (cancelled) {
      markFinalized(taskId)
      handleTerminalStreamEvent(taskId, undefined, undefined, cancelled)
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
    }
    finalizeStaleStreamingBubbles()
    for (const tid of taskIds) {
      processStreamEvents(tid)
      clearRunningIfTaskTerminal(tid)
    }
    sweepStaleRunningState()
  }

  function ensureTaskWatcher() {
    if (watcherInstalled) return
    watcherInstalled = true
    const tasksStore = useTahpTasksStore()
    tasksStore.$subscribe(() => {
      syncAllStreamingTasks()
    })
    watch(
      stream,
      () => {
        const tid = effectiveStreamTaskId.value
        if (!tid) return
        processStreamEvents(tid)
        clearRunningIfTaskTerminal(tid)
        sweepStaleRunningState()
      },
      { deep: true },
    )
  }

  function reconcileActiveTask() {
    traceRecommend('reconcileActiveTask.enter', activeTaskId.value, {
      runningTaskId: runningTaskId.value,
      finalized: activeTaskId.value ? isFinalized(activeTaskId.value) : null,
    })
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
    const hasTerminal = events.some(
      e => e.type === 'task.completed' || e.type === 'task.failed' || e.type === 'task.cancelled',
    )
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
    if (sendMessageInFlight) {
      logState('sendMessage.skip', activeTaskId.value, { reason: 'in_flight' })
      return
    }

    prepareForNextSend()
    if (isRunning.value) return

    if (activeTaskId.value && isFinalized(activeTaskId.value)) {
      activeTaskId.value = null
    }

    sendMessageInFlight = true
    chatMessages.value.push({
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed,
    })

    sending.value = true
    runningTaskId.value = 'pending'
    taskStatus.value = 'running'

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
      await waitForTahpSocketReady()

      const res = await sendGerritReviewMessage({
        session_id: sessionId.value ?? undefined,
        message: trimmed,
      })

      resetInsightFieldsForNewTask()

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
      logState('sendMessage.task_started', res.task_id)
    } catch (err) {
      cancelPendingAssistant()
      clearRunningState('failed')
      throw err
    } finally {
      sendMessageInFlight = false
    }
  }

  function displayLlmResponse(): string {
    const assistants = chatMessages.value.filter(m => m.role === 'assistant' && !m.streaming)
    const last = assistants[assistants.length - 1]
    if (isRunning.value && streamingText.value) return streamingText.value
    if (last?.content) return last.content

    const streamingAssistant = [...chatMessages.value].reverse().find(
      m => m.role === 'assistant' && m.streaming,
    )
    if (streamingAssistant) {
      const tid = streamingAssistant.taskId ?? activeTaskId.value
      if (tid && taskHasTerminal(tid)) {
        return responseFromStream(tid) || streamingText.value
      }
    }
    return ''
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

  async function stopReview(): Promise<void> {
    if (sending.value && runningTaskId.value === 'pending') {
      cancelPendingAssistant()
      return
    }

    const taskId = runningTaskId.value && runningTaskId.value !== 'pending'
      ? runningTaskId.value
      : activeTaskId.value
    if (!taskId) {
      clearRunningState('failed')
      return
    }

    const stopMsg = '**评审已被用户停止**'
    stopping.value = true
    try {
      const res = await cancelGerritReviewTask(taskId)
      if (!res.ok) {
        finalizeAssistantForTask(
          taskId,
          `${stopMsg}\n\n${res.error ?? '停止请求被拒绝'}`,
          'failed',
        )
        if (!isFinalized(taskId)) markFinalized(taskId)
        return
      }

      if (!isFinalized(taskId)) {
        markFinalized(taskId)
      }
      finalizeAssistantForTask(taskId, stopMsg, 'failed')
      processStreamEvents(taskId)
    } catch {
      finalizeAssistantForTask(taskId, `${stopMsg}\n\n停止请求失败，已重置界面状态`, 'failed')
      if (!isFinalized(taskId)) markFinalized(taskId)
      clearRunningState('failed')
    } finally {
      stopping.value = false
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
    void waitForTahpSocketReady()
  }

  return {
    sessionId,
    chatMessages,
    activeTaskId,
    runningTaskId,
    taskStatus,
    sending,
    stopping,
    finalizedTaskIds,
    serverP0Items,
    serverP0Raw,
    serverModules,
    serverModulesDisplay,
    recommendedCases,
    loadingRecommendations,
    recommendSource,
    checkedRecommendedCases,
    stream,
    effectiveStreamTaskId,
    streamingText,
    isServerRecommending,
    isRunning,
    init,
    reconcileActiveTask,
    sendMessage,
    stopReview,
    cancelPendingAssistant,
    processStreamEvents,
    displayLlmResponse,
    p0Result,
    modulesResult,
    reviewInsight,
    ensureRecommendedCases,
    refreshRecommendedCases,
    isRefreshingRecommendations,
    isApplyingReviewInsight,
    toggleRecommendedCase: setRecommendedCaseChecked,
    setRecommendedCaseChecked,
    isFinalized,
    taskHasTerminal,
  }
})
