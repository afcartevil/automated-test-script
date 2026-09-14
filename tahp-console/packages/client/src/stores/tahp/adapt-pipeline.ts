import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  abortPipelineRun,
  appendPipelineStages,
  createPipelineRun,
  discardPipelineDraftRun,
  DEFAULT_WORKFLOW,
  fetchAppendCandidates,
  fetchCapabilities,
  fetchPipelineLogs,
  fetchPipelineRuns,
  fetchPipelineTimeline,
  fetchResumePoints,
  fetchWorkflow,
  failCurrentPipelineStage,
  pausePipelineRun,
  resumePipelineRun,
  saveWorkflow,
  startPipelineRun,
  submitPipelineHumanAction,
  type AppendCandidatesResponse,
  type AppendStagesRequest,
  type CapabilityItem,
  type ResumePointsResponse,
  type RunSummary,
  type TimelineView,
  type WorkflowDefinition,
  type WorkflowNodeView,
} from '@/api/tahp/adapt-pipeline'
import { getTahpSocket, type TahpEvent } from '@/api/tahp/socket'

const PIPELINE_EVENTS = [
  'pipeline.run_started',
  'pipeline.node_changed',
  'pipeline.node_progress',
  'pipeline.node_log',
  'pipeline.waiting_human',
  'pipeline.human_resolved',
  'pipeline.resumed',
  'pipeline.stages_appended',
  'pipeline.iteration_started',
  'pipeline.run_completed',
  'pipeline.run_failed',
] as const

const POLL_MS = 5000
const REFRESH_DEBOUNCE_MS = 250
const LOG_BUFFER = 2000

function runIdFromEvent(ev: TahpEvent): string | null {
  const id = ev.payload?.run_id
  return typeof id === 'string' && id ? id : null
}

function trimLogLines(lines: string[]): string[] {
  if (lines.length <= LOG_BUFFER) return lines
  return lines.slice(lines.length - LOG_BUFFER)
}

/** Keep the current session order; prepend runs the server just added. */
export function mergePipelineRunItems(current: RunSummary[], incoming: RunSummary[]): RunSummary[] {
  const byId = new Map(incoming.map(item => [item.run_id, item]))
  const seen = new Set<string>()
  const kept: RunSummary[] = []
  for (const item of current) {
    const next = byId.get(item.run_id)
    if (!next) continue
    kept.push(next)
    seen.add(item.run_id)
  }
  const newcomers = incoming.filter(item => !seen.has(item.run_id))
  return [...newcomers, ...kept]
}

export const useAdaptPipelineStore = defineStore('adapt-pipeline', () => {
  const runItems = ref<RunSummary[]>([])
  const runTotal = ref(0)
  const timelines = ref<Record<string, TimelineView>>({})
  const selectedRunId = ref<string | null>(null)
  const listLoading = ref(false)
  const timelineLoading = ref(false)
  const error = ref<string | null>(null)
  const socketConnected = ref(false)
  const nodeLogs = ref<Record<string, string[]>>({})
  const nodeLogErrors = ref<Record<string, string>>({})
  const resumePoints = ref<ResumePointsResponse | null>(null)
  const appendCandidates = ref<AppendCandidatesResponse | null>(null)
  const actionBusy = ref(false)
  const workflowDraft = ref<WorkflowDefinition | null>(null)
  const workflowNodes = ref<WorkflowNodeView[]>([])
  const capabilities = ref<CapabilityItem[]>([])
  const workflowLoading = ref(false)
  const workflowSaving = ref(false)
  const bridgeRunning = ref(true)
  const centralConfigured = ref(true)
  const runActionBusy = ref(false)

  let socketBound = false
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let refreshTimer: ReturnType<typeof setTimeout> | null = null
  const pendingRefresh = new Set<string>()

  const selectedTimeline = computed(() =>
    selectedRunId.value ? timelines.value[selectedRunId.value] ?? null : null,
  )

  const pendingHumanTotal = computed(() =>
    Object.values(timelines.value).reduce((sum, tl) => sum + (tl.pending_human_count ?? 0), 0),
  )

  function logKey(runId: string, nodeKey: string): string {
    return `${runId}:${nodeKey}`
  }

  function appendLog(runId: string, nodeKey: string, line: string) {
    const key = logKey(runId, nodeKey)
    const next = [...(nodeLogs.value[key] ?? []), line]
    nodeLogs.value = { ...nodeLogs.value, [key]: trimLogLines(next) }
  }

  async function loadRuns() {
    listLoading.value = true
    error.value = null
    try {
      const data = await fetchPipelineRuns({ limit: 50 })
      runItems.value = mergePipelineRunItems(runItems.value, data.items)
      runTotal.value = data.total
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      listLoading.value = false
    }
  }

  async function loadTimeline(runId: string, opts?: { silent?: boolean }) {
    if (!opts?.silent) timelineLoading.value = true
    try {
      const tl = await fetchPipelineTimeline(runId)
      timelines.value = { ...timelines.value, [runId]: tl }
      const idx = runItems.value.findIndex(r => r.run_id === runId)
      if (idx >= 0) {
        const next = [...runItems.value]
        next[idx] = {
          ...next[idx],
          status: tl.status,
          iteration: tl.iteration,
          current_node: tl.current_node,
        }
        runItems.value = next
      }
    } catch (err) {
      if (!opts?.silent) error.value = (err as Error).message
    } finally {
      if (!opts?.silent) timelineLoading.value = false
    }
  }

  async function loadNodeLogs(runId: string, nodeKey: string, tail = 500) {
    const key = logKey(runId, nodeKey)
    if (runId === '__mock_preview__') return
    try {
      const data = await fetchPipelineLogs(runId, nodeKey, tail)
      nodeLogs.value = { ...nodeLogs.value, [key]: trimLogLines(data.lines ?? []) }
      if (nodeLogErrors.value[key]) {
        const nextErrors = { ...nodeLogErrors.value }
        delete nextErrors[key]
        nodeLogErrors.value = nextErrors
      }
    } catch (err) {
      nodeLogErrors.value = { ...nodeLogErrors.value, [key]: (err as Error).message || '日志加载失败' }
    }
  }

  function getNodeLogs(runId: string, nodeKey: string): string[] {
    return nodeLogs.value[logKey(runId, nodeKey)] ?? []
  }

  function getNodeLogError(runId: string, nodeKey: string): string | undefined {
    return nodeLogErrors.value[logKey(runId, nodeKey)]
  }

  async function loadAllNodeLogs(runId: string, nodeKeys: string[], tail = 2000) {
    await Promise.all(nodeKeys.map(nodeKey => loadNodeLogs(runId, nodeKey, tail)))
  }

  async function loadResumePoints(runId: string) {
    resumePoints.value = await fetchResumePoints(runId)
  }

  async function submitHumanAction(runId: string, node: string, actionId: string, payload?: Record<string, unknown>) {
    actionBusy.value = true
    try {
      await submitPipelineHumanAction(runId, { node, action_id: actionId, payload })
      await loadTimeline(runId)
      await loadRuns()
    } finally {
      actionBusy.value = false
    }
  }

  async function resumeRun(
    runId: string,
    node: string,
    scope: 'continue' | 'restart',
    force = false,
    deviceId?: string,
  ) {
    actionBusy.value = true
    try {
      await resumePipelineRun(runId, {
        node,
        scope,
        force,
        device_id: deviceId?.trim() || undefined,
      })
      await loadTimeline(runId)
      await loadRuns()
    } finally {
      actionBusy.value = false
    }
  }

  async function loadAppendCandidates(runId: string) {
    try {
      appendCandidates.value = await fetchAppendCandidates(runId)
    } catch (err) {
      appendCandidates.value = null
      error.value = (err as Error).message
    }
  }

  async function appendStages(runId: string, input: AppendStagesRequest) {
    actionBusy.value = true
    try {
      await appendPipelineStages(runId, input)
      await loadTimeline(runId)
      await loadRuns()
      await loadAppendCandidates(runId)
    } finally {
      actionBusy.value = false
    }
  }

  async function selectRun(runId: string | null) {
    selectedRunId.value = runId
    resumePoints.value = null
    appendCandidates.value = null
    if (!runId) return
    if (!timelines.value[runId]) await loadTimeline(runId)
    const tl = timelines.value[runId]
    if (tl?.status === 'passed') await loadAppendCandidates(runId)
  }

  function scheduleTimelineRefresh(runId: string) {
    pendingRefresh.add(runId)
    if (refreshTimer) return
    refreshTimer = setTimeout(async () => {
      refreshTimer = null
      const ids = [...pendingRefresh]
      pendingRefresh.clear()
      await Promise.all(ids.map(id => loadTimeline(id, { silent: true })))
      if (ids.some(id => !runItems.value.find(r => r.run_id === id))) {
        void loadRuns()
      }
    }, REFRESH_DEBOUNCE_MS)
  }

  function handlePipelineEvent(ev: TahpEvent) {
    const runId = runIdFromEvent(ev)
    if (!runId) return

    if (ev.type === 'pipeline.node_log') {
      const node = typeof ev.payload.node === 'string' ? ev.payload.node : ''
      const line = typeof ev.payload.line === 'string' ? ev.payload.line : ''
      if (node && line) appendLog(runId, node, line)
    }

    if (
      ev.type === 'pipeline.run_started'
      || ev.type === 'pipeline.run_completed'
      || ev.type === 'pipeline.run_failed'
    ) {
      void loadRuns()
    }
    if (timelines.value[runId] || selectedRunId.value === runId) {
      scheduleTimelineRefresh(runId)
    }
  }

  function bindSocket() {
    if (socketBound) return
    const s = getTahpSocket()
    for (const name of PIPELINE_EVENTS) {
      s.on(name, handlePipelineEvent)
    }
    const onConnect = () => { socketConnected.value = true }
    const onDisconnect = () => { socketConnected.value = false }
    s.on('connect', onConnect)
    s.on('disconnect', onDisconnect)
    socketConnected.value = s.connected
    socketBound = true
  }

  function startPolling() {
    if (pollTimer) return
    pollTimer = setInterval(() => {
      if (socketConnected.value) return
      if (selectedRunId.value) {
        void loadTimeline(selectedRunId.value, { silent: true })
      }
      void loadRuns()
    }, POLL_MS)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function injectMockData() {
    const MOCK_RUN_ID = '__mock_preview__'
    const now = new Date().toISOString()
    runItems.value = [{
      run_id: MOCK_RUN_ID,
      project_code: 'X6876_DEV',
      status: 'waiting_human',
      iteration: 1,
      current_node: 'build',
      created_at: now,
      updated_at: now,
    }]
    runTotal.value = 1
    timelines.value = {
      [MOCK_RUN_ID]: {
        run_id: MOCK_RUN_ID,
        project_code: 'X6876_DEV',
        status: 'waiting_human',
        iteration: 1,
        max_iterations: 3,
        current_node: 'build',
        started_at: now,
        duration_ms: 186_000,
        pending_human_count: 1,
        iterations: [{ index: 1, started_at: now, verdict: 'running' }],
        nodes: [
          { key: 'prereq', label: '前置检查', status: 'done', enabled: true, duration_ms: 4200, summary_line: '路径检查通过' },
          {
            key: 'adapt', label: 'AI 适配', status: 'done', enabled: true, duration_ms: 127_000,
            summary_line: '3 域完成，1 域跳过',
            progress: {
              domains: [
                { domain_id: 'telephony', domain_label: '通信', status: 'done', changed_files: ['Ims.java', 'RilProxy.java'], related_skills: ['telephony-adapt'] },
                { domain_id: 'kernel', domain_label: '内核驱动', status: 'done', changed_files: ['spi_driver.c'], related_skills: ['kernel-adapt'] },
                { domain_id: 'power', domain_label: '功耗', status: 'done', changed_files: ['WakeLockPolicy.java'] },
                { domain_id: 'audio', domain_label: '音频', status: 'skipped' },
              ],
            } as unknown as { percent?: number; text?: string },
          },
          {
            key: 'build', label: '编译', status: 'waiting_human', enabled: true,
            summary_line: '编译能力尚未接入',
            unavailable_reason: '编译能力尚未接入',
            human: {
              reason: '编译能力尚未接入',
              message: '请在构建机手工完成编译后继续。',
              actions: [
                { id: 'confirm_done', label: '已手工完成，继续' },
                { id: 'skip', label: '跳过', danger: true },
              ],
            },
            progress: { phase: 'build', state: 'blocked' } as unknown as { percent?: number; text?: string },
          },
          { key: 'flash', label: '烧录', status: 'pending', enabled: true },
          {
            key: 'selfcheck', label: '自检', status: 'pending', enabled: true,
            progress: { total: 12, passed: 0, failed: 0, running: 0 } as unknown as { percent?: number; text?: string },
          },
          {
            key: 'gerrit', label: '提交 Gerrit', status: 'pending', enabled: true,
            progress: {
              changes: [
                { domain_id: 'telephony', repo: 'vendor/mediatek/ims', status: 'pending', files: ['Ims.java', 'RilProxy.java'] },
                { domain_id: 'kernel', repo: 'kernel/drivers', status: 'pending', files: ['spi_driver.c'] },
              ],
            } as unknown as { percent?: number; text?: string },
          },
        ],
      },
    }
    const mockLogs = [
      '[14:22:01] prereq: 路径检查通过',
      '[14:22:05] adapt: 开始 telephony 域适配…',
      '[14:23:12] adapt: telephony 完成, 2 文件变更',
      '[14:23:15] adapt: 开始 kernel 域适配…',
      '[14:24:08] adapt: kernel 完成, 1 文件变更',
      '[14:24:10] adapt: power 完成, 1 文件变更',
      '[14:24:12] adapt: audio 跳过（无 skill）',
      '[14:24:13] build: 等待人工操作…',
    ]
    nodeLogs.value = {
      [`${MOCK_RUN_ID}:prereq`]: mockLogs.slice(0, 1),
      [`${MOCK_RUN_ID}:adapt`]: mockLogs.slice(1, 7),
      [`${MOCK_RUN_ID}:build`]: mockLogs.slice(7),
    }
  }

  async function loadWorkflowEditor() {
    workflowLoading.value = true
    error.value = null
    try {
      const [wfData, caps] = await Promise.all([fetchWorkflow(), fetchCapabilities()])
      workflowDraft.value = structuredClone(wfData.workflow)
      workflowNodes.value = wfData.nodes
      capabilities.value = caps
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      workflowLoading.value = false
    }
  }

  async function saveWorkflowDraft(): Promise<boolean> {
    if (!workflowDraft.value) return false
    workflowSaving.value = true
    error.value = null
    try {
      const result = await saveWorkflow(workflowDraft.value)
      workflowDraft.value = structuredClone(result.workflow)
      await loadWorkflowEditor()
      return true
    } catch (err) {
      error.value = (err as Error).message
      return false
    } finally {
      workflowSaving.value = false
    }
  }

  function restoreDefaultWorkflow() {
    workflowDraft.value = structuredClone(DEFAULT_WORKFLOW)
  }

  function capabilityForNode(key: string): CapabilityItem | undefined {
    return capabilities.value.find(c => c.key === key)
  }

  function setWorkflowNodeEnabled(key: string, enabled: boolean) {
    if (!workflowDraft.value) return
    const node = workflowDraft.value.nodes.find(n => n.key === key)
    if (node) node.enabled = enabled
  }

  function setWorkflowNodeOnUnavailable(key: string, policy: WorkflowDefinition['nodes'][number]['onUnavailable']) {
    if (!workflowDraft.value) return
    const node = workflowDraft.value.nodes.find(n => n.key === key)
    if (node) node.onUnavailable = policy
  }

  function setMaxIterations(value: number) {
    if (!workflowDraft.value) return
    workflowDraft.value.maxIterations = Math.max(1, Math.min(99, value))
  }

  async function pauseRun(runId: string) {
    runActionBusy.value = true
    try {
      await pausePipelineRun(runId)
      await loadTimeline(runId)
      await loadRuns()
    } finally {
      runActionBusy.value = false
    }
  }

  async function abortRun(runId: string, reason?: string) {
    runActionBusy.value = true
    try {
      await abortPipelineRun(runId, reason)
      await loadTimeline(runId)
      await loadRuns()
    } finally {
      runActionBusy.value = false
    }
  }

  async function failCurrentStage(runId: string) {
    actionBusy.value = false
    runActionBusy.value = true
    try {
      await failCurrentPipelineStage(runId)
      await loadTimeline(runId)
      await loadResumePoints(runId)
      await loadRuns()
    } finally {
      runActionBusy.value = false
    }
  }

  async function discardDraftRun(runId: string): Promise<string | null> {
    runActionBusy.value = true
    try {
      await discardPipelineDraftRun(runId)
      const nextTimelines = { ...timelines.value }
      delete nextTimelines[runId]
      timelines.value = nextTimelines
      const nextLogs: Record<string, string[]> = {}
      for (const [key, lines] of Object.entries(nodeLogs.value)) {
        if (!key.startsWith(`${runId}::`)) nextLogs[key] = lines
      }
      nodeLogs.value = nextLogs
      await loadRuns()
      if (selectedRunId.value === runId) {
        const next = runItems.value[0]?.run_id ?? null
        selectedRunId.value = next
        if (next) await loadTimeline(next)
        return next
      }
      return selectedRunId.value
    } finally {
      runActionBusy.value = false
    }
  }

  async function createAndStartRun(input: Parameters<typeof createPipelineRun>[0]) {
    let createdRunId: string | null = null
    try {
      const created = await createPipelineRun(input)
      createdRunId = created.run_id
      await startPipelineRun(created.run_id)
      await loadRuns()
      await selectRun(created.run_id)
      await loadTimeline(created.run_id)
      return created.run_id
    } catch (err) {
      if (createdRunId) {
        try {
          await discardPipelineDraftRun(createdRunId)
        } catch {
          // ignore cleanup errors
        }
        await loadRuns()
      }
      throw err
    }
  }

  async function checkRuntimeReadiness() {
    try {
      const { getRuntimeMode } = await import('@/api/tahp/knowledge')
      const { fetchProfileRuntimeStatuses } = await import('@/api/hermes/profiles')
      const [mode, statuses] = await Promise.all([
        getRuntimeMode(),
        fetchProfileRuntimeStatuses().catch(() => []),
      ])
      centralConfigured.value = mode.central_configured
      // bridge.running = 该 profile 的 worker 是否已拉起（懒启动，首次对话前常为 false）
      // bridge.reachable = broker 是否在线（与 adapt 阶段 probe 一致）
      bridgeRunning.value = statuses.some(s => s.bridge.reachable || s.bridge.running)
    } catch {
      centralConfigured.value = false
      bridgeRunning.value = false
    }
  }

  async function start() {
    bindSocket()
    startPolling()
    await Promise.all([loadRuns(), checkRuntimeReadiness()])
    const useMock = runItems.value.length === 0
      && (import.meta.env.DEV || new URLSearchParams(window.location.search).has('mock'))
    if (useMock) {
      injectMockData()
    }
  }

  function stop() {
    stopPolling()
    if (refreshTimer) {
      clearTimeout(refreshTimer)
      refreshTimer = null
    }
  }

  return {
    runItems,
    runTotal,
    timelines,
    selectedRunId,
    selectedTimeline,
    pendingHumanTotal,
    listLoading,
    timelineLoading,
    error,
    socketConnected,
    nodeLogs,
    resumePoints,
    appendCandidates,
    actionBusy,
    workflowDraft,
    workflowNodes,
    capabilities,
    workflowLoading,
    workflowSaving,
    bridgeRunning,
    centralConfigured,
    runActionBusy,
    loadRuns,
    loadTimeline,
    loadNodeLogs,
    getNodeLogs,
    getNodeLogError,
    loadAllNodeLogs,
    loadResumePoints,
    submitHumanAction,
    resumeRun,
    loadAppendCandidates,
    appendStages,
    selectRun,
    loadWorkflowEditor,
    saveWorkflowDraft,
    restoreDefaultWorkflow,
    capabilityForNode,
    setWorkflowNodeEnabled,
    setWorkflowNodeOnUnavailable,
    setMaxIterations,
    pauseRun,
    abortRun,
    failCurrentStage,
    discardDraftRun,
    createAndStartRun,
    checkRuntimeReadiness,
    start,
    stop,
  }
})
