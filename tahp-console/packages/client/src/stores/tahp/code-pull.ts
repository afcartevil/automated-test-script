/**
 * 代码拉取页面 store：REST + /tahp-run Socket 实时日志
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { waitForTahpSocketReady } from '@/api/tahp/socket'
import { useTahpTasksStore } from '@/stores/tahp/tasks'
import {
  cancelCodePull,
  getCodePullRun,
  listCodePullRuns,
  probeCodePull,
  startCodePull,
  type CodePullRunDetail,
  type CodePullRunSummary,
} from '@/api/tahp/code-pull'

export const useCodePullStore = defineStore('tahp-code-pull', () => {
  const tasks = useTahpTasksStore()
  const systemRepoInit = ref('')
  const vendorRepoInit = ref('')
  const currentRunId = ref<string | null>(null)
  const currentRun = ref<CodePullRunDetail | null>(null)
  const history = ref<CodePullRunSummary[]>([])
  const probe = ref<{ available: boolean; reason?: string } | null>(null)
  const submitting = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)

  let pollTimer: ReturnType<typeof setInterval> | null = null

  const isRunning = computed(() => {
    const s = currentRun.value?.status
    return s === 'running' || s === 'pending'
  })

  const canStart = computed(() =>
    Boolean(systemRepoInit.value.trim() && vendorRepoInit.value.trim()),
  )

  const liveLines = computed(() => {
    const id = currentRunId.value
    if (!id) return currentRun.value?.log_tail || []
    const stream = tasks.getStream(id)
    if (!stream.length) return currentRun.value?.log_tail || []
    const fromSocket = stream
      .filter(e => e.type === 'task.message')
      .map(e => String(e.payload.text || e.payload.message || ''))
      .filter(Boolean)
    const base = currentRun.value?.log_tail || []
    const merged = [...base]
    for (const line of fromSocket) {
      if (merged[merged.length - 1] !== line) merged.push(line)
    }
    return merged.slice(-500)
  })

  async function refreshProbe() {
    try {
      probe.value = await probeCodePull()
    } catch (err) {
      probe.value = { available: false, reason: (err as Error).message }
    }
  }

  async function refreshHistory() {
    try {
      history.value = await listCodePullRuns(30)
    } catch {
      history.value = []
    }
  }

  async function refreshCurrent() {
    if (!currentRunId.value) return
    try {
      currentRun.value = await getCodePullRun(currentRunId.value)
      if (!isRunning.value) stopPoll()
    } catch (err) {
      error.value = (err as Error).message
    }
  }

  function startPoll() {
    stopPoll()
    pollTimer = setInterval(() => {
      void refreshCurrent()
    }, 8000)
  }

  function stopPoll() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function start() {
    error.value = null
    if (!canStart.value) {
      error.value = '请填写 system 与 vendor 的 repo init 命令'
      return
    }
    submitting.value = true
    try {
      await waitForTahpSocketReady()
      tasks.ensureSocket()
      const { run_id } = await startCodePull({
        system_repo_init: systemRepoInit.value.trim(),
        vendor_repo_init: vendorRepoInit.value.trim(),
      })
      currentRunId.value = run_id
      tasks.trackTask(run_id)
      await refreshCurrent()
      startPoll()
      await refreshHistory()
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      submitting.value = false
    }
  }

  async function cancel() {
    if (!currentRunId.value) return
    try {
      await cancelCodePull(currentRunId.value)
      await refreshCurrent()
      await refreshHistory()
    } catch (err) {
      error.value = (err as Error).message
    }
  }

  async function openRun(runId: string) {
    loading.value = true
    error.value = null
    try {
      await waitForTahpSocketReady()
      tasks.ensureSocket()
      currentRunId.value = runId
      tasks.trackTask(runId)
      currentRun.value = await getCodePullRun(runId)
      if (currentRun.value.system_repo_init) {
        systemRepoInit.value = currentRun.value.system_repo_init
      }
      if (currentRun.value.vendor_repo_init) {
        vendorRepoInit.value = currentRun.value.vendor_repo_init
      }
      if (isRunning.value) startPoll()
      else stopPoll()
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      loading.value = false
    }
  }

  function dispose() {
    stopPoll()
  }

  return {
    systemRepoInit,
    vendorRepoInit,
    currentRunId,
    currentRun,
    history,
    probe,
    submitting,
    loading,
    error,
    isRunning,
    canStart,
    liveLines,
    refreshProbe,
    refreshHistory,
    refreshCurrent,
    start,
    cancel,
    openRun,
    dispose,
  }
})
