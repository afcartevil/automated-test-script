/**
 * 特性适配页：飞书 checklist × SCMP 回写
 */
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { waitForTahpSocketReady } from '@/api/tahp/socket'
import { useTahpTasksStore } from '@/stores/tahp/tasks'
import {
  cancelChecklistScmpSync,
  getChecklistScmpRun,
  listChecklistScmpRuns,
  startChecklistScmpSync,
  type ChecklistScmpRun,
} from '@/api/tahp/checklist-scmp-sync'

const URL_STORAGE_KEY = 'tahp-checklist-scmp-url'
const TITLE_EXAMPLE = 'X6879-tOS17 全功能特性checklist_V2.5'
const TERMINAL = new Set(['task.completed', 'task.failed', 'task.cancelled'])

function readStoredUrl() {
  try {
    return localStorage.getItem(URL_STORAGE_KEY) || ''
  } catch {
    return ''
  }
}

export const CHECKLIST_SCMP_PLACEHOLDER =
  `飞书 Wiki/表格链接。文档标题必须含项目编码与 tOS，例如：${TITLE_EXAMPLE}`

export const CHECKLIST_SCMP_HINT =
  `标题格式：{项目编码}-tOS{版本} 全功能特性checklist_…，例如 ${TITLE_EXAMPLE}。将按各 sheet 特性编码查询 SCMP 并回写「此特性是否支持」。`

export const useChecklistScmpSyncStore = defineStore('tahp-checklist-scmp-sync', () => {
  const tasks = useTahpTasksStore()
  const url = ref(readStoredUrl())
  const currentRunId = ref<string | null>(null)
  const currentRun = ref<ChecklistScmpRun | null>(null)
  const submitting = ref(false)
  const error = ref<string | null>(null)
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let lastTerminalAt = 0

  const isRunning = computed(() => {
    const s = currentRun.value?.status
    return s === 'running' || s === 'pending'
  })

  const liveLines = computed(() => {
    const id = currentRunId.value
    const base = currentRun.value?.log_tail || []
    if (!id) return base
    const fromSocket = tasks.getStream(id)
      .filter(e => e.type === 'task.message' || e.type === 'task.started' || TERMINAL.has(e.type))
      .map(e => String(e.payload.text || e.payload.message || ''))
      .filter(Boolean)
    if (!fromSocket.length) return base
    const merged = [...base]
    for (const line of fromSocket) {
      if (merged[merged.length - 1] !== line) merged.push(line)
    }
    return merged.slice(-200)
  })

  const progress = computed(() => currentRun.value?.progress || 0)

  watch(url, (value) => {
    try {
      localStorage.setItem(URL_STORAGE_KEY, value)
    } catch {
      /* ignore */
    }
  })

  watch(
    () => {
      const id = currentRunId.value
      if (!id) return null
      const stream = tasks.getStream(id)
      const terminal = [...stream].reverse().find(e => TERMINAL.has(e.type))
      return terminal ? { ts: terminal.ts, type: terminal.type } : null
    },
    (term) => {
      if (!term || term.ts === lastTerminalAt) return
      lastTerminalAt = term.ts
      void refreshCurrent()
    },
  )

  function stopPoll() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function startPoll() {
    stopPoll()
    pollTimer = setInterval(() => {
      void refreshCurrent()
    }, 2500)
  }

  async function refreshCurrent() {
    if (!currentRunId.value) return
    try {
      currentRun.value = await getChecklistScmpRun(currentRunId.value)
      if (!isRunning.value) stopPoll()
    } catch (err) {
      error.value = (err as Error).message
    }
  }

  async function hydrate() {
    tasks.ensureSocket()
    try {
      const data = await listChecklistScmpRuns(10)
      const active = data.active || data.items.find(item => item.status === 'running' || item.status === 'pending')
      const latest = active || data.items[0]
      if (!latest) return
      currentRunId.value = latest.run_id
      currentRun.value = latest
      if (latest.url && !url.value.trim()) url.value = latest.url
      tasks.trackTask(latest.run_id)
      if (latest.status === 'running' || latest.status === 'pending') startPoll()
    } catch {
      /* ignore */
    }
  }

  async function start() {
    error.value = null
    const trimmed = url.value.trim()
    if (!trimmed) {
      error.value = '请填写飞书文档链接'
      return
    }
    if (isRunning.value || submitting.value) {
      error.value = '已有任务在进行中，请等待完成或取消后再试'
      return
    }
    submitting.value = true
    try {
      await waitForTahpSocketReady()
      tasks.ensureSocket()
      const { run_id } = await startChecklistScmpSync(trimmed)
      currentRunId.value = run_id
      tasks.trackTask(run_id)
      currentRun.value = {
        run_id,
        url: trimmed,
        status: 'pending',
        progress: 0,
        phase: 'queued',
        message: '正在启动…',
        log_tail: ['正在启动…'],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }
      startPoll()
      await refreshCurrent()
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      submitting.value = false
    }
  }

  async function cancel() {
    if (!currentRunId.value) return
    error.value = null
    try {
      await cancelChecklistScmpSync(currentRunId.value)
      await refreshCurrent()
    } catch (err) {
      error.value = (err as Error).message
    }
  }

  return {
    url,
    currentRunId,
    currentRun,
    submitting,
    error,
    isRunning,
    liveLines,
    progress,
    hydrate,
    start,
    cancel,
    stopPoll,
  }
})
