/**
 * Gerrit Code Review 会话状态 — 跨页面导航保持评审进度与对话记录。
 */
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { sendGerritReviewMessage } from '@/api/tahp/gerrit-review'
import { extractP0TestSuggestions } from '@/utils/gerrit-review-report'
import { useTahpTasksStore } from './tasks'

export interface GerritChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  taskId?: string
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

  let watcherInstalled = false

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
    const completed = events.find(e => e.type === 'task.completed')
    if (completed) {
      return String(completed.payload?.llm_response ?? completed.payload?.response ?? '')
    }
    return events
      .filter(ev => ev.type === 'task.message' && ev.payload?.level !== 'reasoning')
      .map(ev => String(ev.payload?.text ?? ''))
      .join('')
  }

  function finalizeAssistantForTask(
    taskId: string,
    content: string,
    terminalStatus: 'completed' | 'failed' = 'completed',
  ) {
    const idx = chatMessages.value.findIndex(m => m.taskId === taskId && m.streaming)
    if (idx >= 0) {
      chatMessages.value[idx] = {
        ...chatMessages.value[idx],
        content,
        streaming: false,
      }
    } else {
      const lastStreaming = chatMessages.value.findIndex(m => m.streaming)
      if (lastStreaming >= 0) {
        chatMessages.value[lastStreaming] = {
          ...chatMessages.value[lastStreaming],
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
    }
    chatMessages.value = [...chatMessages.value]
    if (runningTaskId.value === taskId || runningTaskId.value === 'pending') {
      clearRunningState(terminalStatus)
    }
  }

  function applyP0FromPayload(payload: Record<string, unknown>) {
    const p0Items = payload?.p0_items
    if (Array.isArray(p0Items)) {
      serverP0Items.value = p0Items.map(String).filter(Boolean)
      serverP0Raw.value = String(payload?.p0_raw_section ?? '')
    }
  }

  function processStreamEvents(taskId: string) {
    if (!taskId) return

    const events = streamFor(taskId)
    const completed = events.find(e => e.type === 'task.completed')
    const failed = events.find(e => e.type === 'task.failed')

    if (isFinalized(taskId)) {
      if (activeTaskId.value === taskId) {
        if (completed) clearRunningState('completed')
        else if (failed) clearRunningState('failed')
      }
      const streaming = chatMessages.value.find(m => m.taskId === taskId && m.streaming)
      if (streaming && completed) {
        finalizeAssistantForTask(
          taskId,
          String(completed.payload?.llm_response ?? completed.payload?.response ?? responseFromStream(taskId)),
          'completed',
        )
      } else if (streaming && failed) {
        finalizeAssistantForTask(
          taskId,
          `**评审失败**\n\n${failed.payload?.error ?? failed.payload?.message ?? '未知错误'}`,
          'failed',
        )
      }
      return
    }

    for (const ev of events) {
      if (ev.type === 'task.completed') {
        markFinalized(taskId)
        applyP0FromPayload(ev.payload)
        const response = String(
          ev.payload?.llm_response ?? ev.payload?.response ?? responseFromStream(taskId),
        )
        finalizeAssistantForTask(taskId, response, 'completed')
        return
      }
      if (ev.type === 'task.failed') {
        markFinalized(taskId)
        finalizeAssistantForTask(
          taskId,
          `**评审失败**\n\n${ev.payload?.error ?? ev.payload?.message ?? '未知错误'}`,
          'failed',
        )
        return
      }
    }
  }

  function syncAllStreamingTasks() {
    const taskIds = new Set<string>()
    if (activeTaskId.value) taskIds.add(activeTaskId.value)
    for (const msg of chatMessages.value) {
      if (msg.streaming && msg.taskId) taskIds.add(msg.taskId)
    }
    for (const tid of taskIds) processStreamEvents(tid)
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
    if (!tid || isFinalized(tid)) return

    const events = streamFor(tid)
    const hasTerminal = events.some(e => e.type === 'task.completed' || e.type === 'task.failed')
    if (!hasTerminal) {
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
  }

  function prepareForNextSend() {
    syncAllStreamingTasks()
    if (runningTaskId.value && isFinalized(runningTaskId.value)) {
      clearRunningState('completed')
    }
    if (activeTaskId.value && isFinalized(activeTaskId.value) && runningTaskId.value === null) {
      taskStatus.value = 'completed'
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
    isFinalized,
  }
})
