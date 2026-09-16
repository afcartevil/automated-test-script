/**
 * AI 适配调试 — 当前任务状态。
 * 放 Pinia + sessionStorage，避免离开页面后丢失仍在跑的任务。
 */
import { defineStore } from 'pinia'
import { reactive, watch } from 'vue'
import { getAdaptAgentRun, listActiveAdaptAgentRuns, type AdaptAgentRunSummary } from '@/api/tahp/adapt'
import {
  ADAPT_WORKSPACE_IDS,
  isAdaptWorkspaceId,
  type AdaptWorkspaceId,
} from '@/constants/adapt-domains'

export interface WorkspaceRunState {
  agentLaunching: boolean
  launchedTaskId: string | null
  taskStatus: string
  showMonitor: boolean
  monitorMode: 'agent' | null
  startTime: number
}

export interface DomainActiveRun {
  taskId: string
  domainId: string
  workspaceId: AdaptWorkspaceId
}

export const ADAPT_DEBUG_RUN_STORAGE_KEY = 'tahp-adapt-debug-run'

export function defaultRunState(): WorkspaceRunState {
  return {
    agentLaunching: false,
    launchedTaskId: null,
    taskStatus: '',
    showMonitor: false,
    monitorMode: null,
    startTime: 0,
  }
}

function emptyRunStateByWorkspace(): Record<AdaptWorkspaceId, WorkspaceRunState> {
  return {
    'adapt-debug': defaultRunState(),
    'feature-adapt': defaultRunState(),
    'carrier-config': defaultRunState(),
  }
}

export function domainRunKey(workspaceId: AdaptWorkspaceId, domainId: string): string {
  return `${workspaceId}:${domainId}`
}

function liveUiStatus(task: AdaptAgentRunSummary): string {
  if (task.phase) return String(task.phase)
  const s = String(task.status || '').toLowerCase()
  if (s === 'waiting_user_input') return 'WAITING_USER_INPUT'
  if (s === 'waiting_user') return 'WAITING_USER'
  if (s === 'completed') return 'COMPLETED'
  if (s === 'failed') return 'FAILED'
  if (s === 'pending') return 'starting'
  return 'running'
}

interface PersistedAdaptDebugRun {
  runStateByWorkspace?: Partial<Record<string, Partial<WorkspaceRunState>>>
  activeRunsByKey?: Record<string, DomainActiveRun>
}

function readPersisted(): PersistedAdaptDebugRun | null {
  try {
    const raw = sessionStorage.getItem(ADAPT_DEBUG_RUN_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as PersistedAdaptDebugRun
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch {
    return null
  }
}

export const useAdaptDebugRunStore = defineStore('adapt-debug-run', () => {
  const runStateByWorkspace = reactive<Record<AdaptWorkspaceId, WorkspaceRunState>>(emptyRunStateByWorkspace())
  const activeRunsByKey = reactive<Record<string, DomainActiveRun>>({})

  function persist() {
    try {
      const runState: Record<string, WorkspaceRunState> = {}
      for (const id of ADAPT_WORKSPACE_IDS) {
        runState[id] = { ...runStateByWorkspace[id], agentLaunching: false }
      }
      sessionStorage.setItem(ADAPT_DEBUG_RUN_STORAGE_KEY, JSON.stringify({
        runStateByWorkspace: runState,
        activeRunsByKey: { ...activeRunsByKey },
      }))
    } catch {
      // private mode / quota
    }
  }

  function hydrate() {
    const saved = readPersisted()
    if (!saved) return
    for (const id of ADAPT_WORKSPACE_IDS) {
      const row = saved.runStateByWorkspace?.[id]
      if (!row) continue
      Object.assign(runStateByWorkspace[id], {
        agentLaunching: false,
        launchedTaskId: typeof row.launchedTaskId === 'string' ? row.launchedTaskId : row.launchedTaskId === null ? null : runStateByWorkspace[id].launchedTaskId,
        taskStatus: typeof row.taskStatus === 'string' ? row.taskStatus : '',
        showMonitor: row.showMonitor === true,
        monitorMode: row.monitorMode === 'agent' ? 'agent' : null,
        startTime: typeof row.startTime === 'number' ? row.startTime : 0,
      })
    }
    if (saved.activeRunsByKey && typeof saved.activeRunsByKey === 'object') {
      for (const [key, run] of Object.entries(saved.activeRunsByKey)) {
        if (!run || !isAdaptWorkspaceId(run.workspaceId) || !run.taskId || !run.domainId) continue
        activeRunsByKey[key] = {
          taskId: run.taskId,
          domainId: run.domainId,
          workspaceId: run.workspaceId,
        }
      }
    }
  }

  hydrate()

  watch([runStateByWorkspace, activeRunsByKey], persist, { deep: true })

  function registerActiveRun(taskId: string, domainId: string, workspaceId: AdaptWorkspaceId) {
    activeRunsByKey[domainRunKey(workspaceId, domainId)] = { taskId, domainId, workspaceId }
  }

  function unregisterActiveRun(taskId: string) {
    for (const [key, run] of Object.entries(activeRunsByKey)) {
      if (run.taskId === taskId) delete activeRunsByKey[key]
    }
  }

  function applyLiveTask(task: AdaptAgentRunSummary) {
    if (!isAdaptWorkspaceId(task.workspace_id)) return
    const ws = task.workspace_id
    registerActiveRun(task.task_id, task.domain_id, ws)
    const st = runStateByWorkspace[ws]
    const status = liveUiStatus(task)
    if (!st.launchedTaskId) {
      st.launchedTaskId = task.task_id
      st.taskStatus = status
      st.monitorMode = 'agent'
      return
    }
    if (st.launchedTaskId === task.task_id) {
      st.taskStatus = status
    }
  }

  async function reattachLiveTasks(opts: {
    ensureSocket: () => void
    trackTask: (taskId: string) => void
  }) {
    opts.ensureSocket()
    for (const st of Object.values(runStateByWorkspace)) {
      if (st.launchedTaskId) opts.trackTask(st.launchedTaskId)
    }
    for (const run of Object.values(activeRunsByKey)) {
      opts.trackTask(run.taskId)
    }

    let live: AdaptAgentRunSummary[] = []
    try {
      live = await listActiveAdaptAgentRuns()
    } catch {
      return
    }
    if (!Array.isArray(live)) return

    const liveIds = new Set(live.map(t => t.task_id))
    for (const [key, run] of Object.entries(activeRunsByKey)) {
      if (!liveIds.has(run.taskId)) delete activeRunsByKey[key]
    }

    for (const task of live) {
      applyLiveTask(task)
      opts.trackTask(task.task_id)
    }

    for (const id of ADAPT_WORKSPACE_IDS) {
      const st = runStateByWorkspace[id]
      const liveForWs = live.filter(t => t.workspace_id === id)
      if (st.launchedTaskId && liveIds.has(st.launchedTaskId)) continue
      if (liveForWs.length) {
        const latest = liveForWs[0]
        st.launchedTaskId = latest.task_id
        st.taskStatus = liveUiStatus(latest)
        st.monitorMode = 'agent'
        opts.trackTask(latest.task_id)
      } else if (st.launchedTaskId) {
        await refreshStoredTaskStatus(st.launchedTaskId, st)
      }
    }
  }

  async function refreshStoredTaskStatus(taskId: string, st: WorkspaceRunState) {
    try {
      const data = await getAdaptAgentRun(taskId)
      const live = data?.live as { status?: string; phase?: string } | null | undefined
      if (live?.status) {
        st.taskStatus = liveUiStatus({
          task_id: taskId,
          workspace_id: '',
          domain_id: '',
          domain_label: '',
          status: live.status,
          phase: live.phase,
          started_at: '',
        })
        if (live.status === 'completed' || live.status === 'failed') {
          unregisterActiveRun(taskId)
        }
        return
      }
      if (data?.report) {
        st.taskStatus = 'COMPLETED'
        unregisterActiveRun(taskId)
      }
    } catch {
      // 保持本地状态
    }
  }

  return {
    runStateByWorkspace,
    activeRunsByKey,
    persist,
    domainRunKey,
    registerActiveRun,
    unregisterActiveRun,
    reattachLiveTasks,
  }
})
