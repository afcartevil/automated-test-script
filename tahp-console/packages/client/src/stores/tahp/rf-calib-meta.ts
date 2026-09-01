/**
 * 射频校准 MetaCLI 页面 store
 */
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { waitForTahpSocketReady } from '@/api/tahp/socket'
import { useTahpTasksStore } from '@/stores/tahp/tasks'
import {
  cancelRfCalibMeta,
  getRfCalibMetaRun,
  listRfCalibMetaRuns,
  probeRfCalibMeta,
  startRfCalibMeta,
  type RfCalibMetaConnectionStrategy,
  type RfCalibMetaMode,
  type RfCalibMetaProbeResult,
  type RfCalibMetaRunDetail,
  type RfCalibMetaRunSummary,
} from '@/api/tahp/rf-calib-meta'

const TERMINAL = new Set(['task.completed', 'task.failed', 'task.cancelled'])

export const useRfCalibMetaStore = defineStore('tahp-rf-calib-meta', () => {
  const tasks = useTahpTasksStore()
  const mode = ref<RfCalibMetaMode>('backup')
  const connectionStrategy = ref<RfCalibMetaConnectionStrategy>('preloader_boot')
  const calFilePath = ref('')
  const outputCalPath = ref('')
  const comPort = ref('Auto Connection')
  const currentRunId = ref<string | null>(null)
  const currentRun = ref<RfCalibMetaRunDetail | null>(null)
  const history = ref<RfCalibMetaRunSummary[]>([])
  const probe = ref<RfCalibMetaProbeResult | null>(null)
  const submitting = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)

  let pollTimer: ReturnType<typeof setInterval> | null = null
  let lastTerminalAt = 0

  const isRunning = computed(() => {
    const s = currentRun.value?.status
    return s === 'running' || s === 'pending'
  })

  const canStart = computed(() => {
    if (!probe.value?.available) return false
    if (mode.value === 'restore' && !calFilePath.value.trim()) return false
    return true
  })

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
      void refreshHistory()
    },
  )

  async function refreshProbe() {
    try {
      probe.value = await probeRfCalibMeta()
      if (probe.value?.suggested_com_port && (!comPort.value.trim() || comPort.value === 'Auto Connection')) {
        comPort.value = probe.value.suggested_com_port
      }
    } catch (err) {
      const msg = (err as Error).message
      if (/404/.test(msg)) {
        probe.value = {
          available: false,
          reason: 'BFF 未加载射频校准 API（404）。请重启 Console 后端（停止后重新 npm run dev，或 npm run build && npm run start）',
        }
      } else {
        probe.value = { available: false, reason: msg }
      }
    }
  }

  async function refreshHistory() {
    try {
      history.value = await listRfCalibMetaRuns(30)
    } catch {
      history.value = []
    }
  }

  async function refreshCurrent() {
    if (!currentRunId.value) return
    try {
      currentRun.value = await getRfCalibMetaRun(currentRunId.value)
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
    if (isRunning.value || submitting.value) {
      error.value = '已有任务在进行中，请等待完成或取消后再试'
      return
    }
    if (!probe.value?.available) {
      error.value = probe.value?.reason
        || '未配置 Modem Meta。请前往「配置 → 一键配置表单 → Modem 工具」填写安装目录'
      return
    }
    if (!canStart.value) {
      error.value = mode.value === 'restore'
        ? '请填写校准数据文件路径'
        : '请检查表单参数'
      return
    }
    submitting.value = true
    try {
      await waitForTahpSocketReady()
      tasks.ensureSocket()
      const { run_id } = await startRfCalibMeta({
        mode: mode.value,
        items_ini_path: '',
        cal_file_path: mode.value === 'restore' ? calFilePath.value.trim() : undefined,
        output_cal_path: mode.value === 'backup' && outputCalPath.value.trim()
          ? outputCalPath.value.trim()
          : undefined,
        com_port: comPort.value.trim() || 'Auto Connection',
        connection_strategy: connectionStrategy.value,
        label: mode.value === 'backup' ? '备份校准数据' : '恢复校准数据',
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
      await cancelRfCalibMeta(currentRunId.value)
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
      currentRun.value = await getRfCalibMetaRun(runId)
      if (currentRun.value.mode) mode.value = currentRun.value.mode
      if (currentRun.value.cal_file_path) calFilePath.value = currentRun.value.cal_file_path
      if (currentRun.value.output_cal_path) outputCalPath.value = currentRun.value.output_cal_path
      if (currentRun.value.com_port) comPort.value = currentRun.value.com_port
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
    mode,
    connectionStrategy,
    calFilePath,
    outputCalPath,
    comPort,
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
