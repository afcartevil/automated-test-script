import { computed, ref } from 'vue'
import {
  continueModemBaselineRun,
  createModemBaselineRun,
  getModemBaselineDefaults,
  getModemBaselineLog,
  getModemBaselineRun,
  listModemBaselineRuns,
  openModemBaselineConflictFile,
  refreshModemBaselineConflicts,
  subscribeModemBaselineEvents,
  type ModemBaselineConfig,
  type ModemBaselineRunMeta,
  type ModemBaselineStatus,
} from '@/api/tahp/modem-baseline'

export type StageItem = {
  key: string
  label: string
  state: 'done' | 'active' | 'pending'
}

export function emptyModemBaselineConfig(): ModemBaselineConfig {
  return {
    NODE_BRANCH: '',
    target_BRANCH: '',
    AP_lable: '',
    DESCRIPTION: '',
    JIRAID: '',
    work_dir: '',
    mapped_prefix: 'Z:',
    remote_prefix: '/work/user/code',
  }
}

export function getStatusMeta(status?: ModemBaselineStatus, error?: string) {
  if (status === 'success') {
    return { label: '执行完成', tone: 'success', summary: '流程已完成，可查看日志、报告与冲突结果。' }
  }
  if (status === 'conflict') {
    return { label: '等待人工处理', tone: 'warn', summary: '检测到冲突，需研发手动处理后点击继续执行。' }
  }
  if (status === 'failed') {
    const summary = error === 'bridge_not_ready'
      ? 'Harness bridge 未就绪，请先确认 bridge-serve 与权限状态。'
      : '执行失败，请结合运行日志定位失败阶段。'
    return { label: '执行失败', tone: 'error', summary }
  }
  if (status === 'running') {
    return { label: '执行中', tone: 'info', summary: '正在执行预检、合并或后续处理，请关注实时日志。' }
  }
  return { label: '待启动', tone: 'muted', summary: '加载默认配置后即可启动 Modem 基线升级。' }
}

export function buildStageItems(status?: ModemBaselineStatus, error?: string): StageItem[] {
  if (status === 'success') {
    return [
      { key: 'precheck', label: '准备环境', state: 'done' },
      { key: 'merge', label: '合并补丁', state: 'done' },
      { key: 'conflict', label: '冲突停驻', state: 'done' },
      { key: 'resume', label: '继续执行', state: 'done' },
      { key: 'archive', label: '结果归档', state: 'active' },
    ]
  }

  if (status === 'conflict') {
    return [
      { key: 'precheck', label: '准备环境', state: 'done' },
      { key: 'merge', label: '合并补丁', state: 'done' },
      { key: 'conflict', label: '冲突停驻', state: 'active' },
      { key: 'resume', label: '继续执行', state: 'pending' },
      { key: 'archive', label: '结果归档', state: 'pending' },
    ]
  }

  if (status === 'failed') {
    return [
      { key: 'precheck', label: '准备环境', state: error === 'bridge_not_ready' ? 'active' : 'done' },
      { key: 'merge', label: '合并补丁', state: error === 'bridge_not_ready' ? 'pending' : 'active' },
      { key: 'conflict', label: '冲突停驻', state: 'pending' },
      { key: 'resume', label: '继续执行', state: 'pending' },
      { key: 'archive', label: '结果归档', state: 'pending' },
    ]
  }

  if (status === 'running') {
    return [
      { key: 'precheck', label: '准备环境', state: 'done' },
      { key: 'merge', label: '合并补丁', state: 'active' },
      { key: 'conflict', label: '冲突停驻', state: 'pending' },
      { key: 'resume', label: '继续执行', state: 'pending' },
      { key: 'archive', label: '结果归档', state: 'pending' },
    ]
  }

  return [
    { key: 'precheck', label: '准备环境', state: 'active' },
    { key: 'merge', label: '合并补丁', state: 'pending' },
    { key: 'conflict', label: '冲突停驻', state: 'pending' },
    { key: 'resume', label: '继续执行', state: 'pending' },
    { key: 'archive', label: '结果归档', state: 'pending' },
  ]
}

function withString(value?: string) {
  return value?.trim() || '—'
}

export function useModemBaseline() {
  const config = ref<ModemBaselineConfig>(emptyModemBaselineConfig())
  const toolRoot = ref('')
  const runs = ref<ModemBaselineRunMeta[]>([])
  const selectedRunId = ref('')
  const logContent = ref('')
  const loading = ref(false)
  const starting = ref(false)
  const continuing = ref(false)
  const refreshing = ref(false)
  const errorMessage = ref('')
  const eventSource = ref<EventSource | null>(null)

  const selectedRun = computed(() => runs.value.find(item => item.runId === selectedRunId.value) ?? runs.value[0] ?? null)
  const statusMeta = computed(() => getStatusMeta(selectedRun.value?.status, selectedRun.value?.error))
  const stageItems = computed(() => buildStageItems(selectedRun.value?.status, selectedRun.value?.error))
  const conflictFiles = computed(() => selectedRun.value?.conflictFiles ?? [])

  const metrics = computed(() => [
    { label: '当前任务', value: selectedRun.value?.runId ?? '—' },
    { label: '当前状态', value: statusMeta.value.label },
    { label: '冲突文件', value: `${conflictFiles.value.length}` },
    { label: '工作区', value: withString(selectedRun.value?.config.work_dir || config.value.work_dir) },
  ])

  function closeEventSource() {
    eventSource.value?.close()
    eventSource.value = null
  }

  function mergeRun(nextRun: ModemBaselineRunMeta) {
    const index = runs.value.findIndex(item => item.runId === nextRun.runId)
    if (index >= 0) {
      runs.value.splice(index, 1, nextRun)
      return
    }
    runs.value.unshift(nextRun)
  }

  async function reloadRun(runId: string) {
    const nextRun = await getModemBaselineRun(runId)
    mergeRun(nextRun)
  }

  async function reloadRuns() {
    const nextRuns = await listModemBaselineRuns()
    runs.value = nextRuns
    if (!selectedRunId.value && nextRuns.length) {
      selectedRunId.value = nextRuns[0].runId
    }
    if (selectedRunId.value && !nextRuns.find(item => item.runId === selectedRunId.value)) {
      selectedRunId.value = nextRuns[0]?.runId ?? ''
    }
  }

  async function loadDefaults() {
    const data = await getModemBaselineDefaults()
    config.value = { ...data.config }
    toolRoot.value = data.toolRoot
  }

  async function loadLog(runId: string) {
    const data = await getModemBaselineLog(runId)
    logContent.value = data.content || ''
  }

  function subscribe(runId: string) {
    closeEventSource()
    const source = subscribeModemBaselineEvents(runId)

    source.addEventListener('status', async (event) => {
      try {
        const payload = JSON.parse((event as MessageEvent).data) as { status?: ModemBaselineStatus; reportPath?: string; error?: string }
        const current = runs.value.find(item => item.runId === runId)
        if (current) {
          mergeRun({
            ...current,
            status: payload.status ?? current.status,
            reportPath: payload.reportPath ?? current.reportPath,
            error: payload.error ?? current.error,
          })
        }
        if (payload.status && payload.status !== 'running') {
          await reloadRun(runId)
        }
      } catch {}
    })

    source.addEventListener('log', (event) => {
      try {
        const payload = JSON.parse((event as MessageEvent).data) as { line?: string; full?: boolean }
        if (!payload.line) return
        if (payload.full || !logContent.value) {
          logContent.value = payload.line
        } else {
          logContent.value += payload.line
        }
      } catch {}
    })

    source.addEventListener('conflicts', (event) => {
      try {
        const payload = JSON.parse((event as MessageEvent).data) as { files?: string[] }
        const current = runs.value.find(item => item.runId === runId)
        if (!current) return
        mergeRun({
          ...current,
          conflictFiles: payload.files ?? [],
          status: (payload.files?.length ?? 0) > 0 ? 'conflict' : current.status,
        })
      } catch {}
    })

    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED) {
        closeEventSource()
      }
    }

    eventSource.value = source
  }

  async function selectRun(runId: string) {
    selectedRunId.value = runId
    await Promise.all([
      reloadRun(runId).catch(() => {}),
      loadLog(runId).catch(() => {
        logContent.value = ''
      }),
    ])
    subscribe(runId)
  }

  async function initialize() {
    loading.value = true
    errorMessage.value = ''
    try {
      await loadDefaults()
    } catch (error) {
      errorMessage.value = String((error as Error)?.message ?? error)
    }

    try {
      await reloadRuns()
      if (selectedRunId.value) {
        await selectRun(selectedRunId.value)
      }
    } finally {
      loading.value = false
    }
  }

  async function startRun() {
    starting.value = true
    try {
      const result = await createModemBaselineRun(config.value)
      await reloadRuns()
      await selectRun(result.runId)
    } finally {
      starting.value = false
    }
  }

  async function continueRun() {
    if (!selectedRun.value) return
    continuing.value = true
    try {
      await continueModemBaselineRun(selectedRun.value.runId)
      await reloadRun(selectedRun.value.runId)
      subscribe(selectedRun.value.runId)
    } finally {
      continuing.value = false
    }
  }

  async function refreshConflicts() {
    if (!selectedRun.value) return
    refreshing.value = true
    try {
      await refreshModemBaselineConflicts(selectedRun.value.runId)
      await reloadRun(selectedRun.value.runId)
    } finally {
      refreshing.value = false
    }
  }

  async function openConflictFile(file: string) {
    if (!selectedRun.value) return
    await openModemBaselineConflictFile(selectedRun.value.runId, file)
  }

  return {
    config,
    toolRoot,
    runs,
    selectedRun,
    selectedRunId,
    conflictFiles,
    logContent,
    loading,
    starting,
    continuing,
    refreshing,
    errorMessage,
    statusMeta,
    stageItems,
    metrics,
    initialize,
    loadDefaults,
    selectRun,
    startRun,
    continueRun,
    refreshConflicts,
    openConflictFile,
    closeEventSource,
  }
}
