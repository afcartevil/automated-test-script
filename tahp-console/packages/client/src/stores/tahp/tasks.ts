/**
 * TAHP 任务状态 store — 维护任务列表 + 实时事件流.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { executeTask, getTaskStatus, listTasks, correctTask, type TaskInfo, type ExecuteTaskRequest } from '@/api/tahp/tasks'
import { getTahpSocket, type TahpEvent } from '@/api/tahp/socket'

interface TaskStreamEntry {
  type: string
  payload: Record<string, unknown>
  ts: number
}

export const useTahpTasksStore = defineStore('tahp-tasks', () => {
  const tasks = ref<TaskInfo[]>([])
  const loading = ref(false)
  const activeTaskId = ref<string | null>(null)
  const taskStreams = ref<Record<string, TaskStreamEntry[]>>({})
  const lastError = ref<string | null>(null)

  let socketBound = false

  function ensureSocket() {
    if (socketBound) return
    const s = getTahpSocket()
    const handler = (ev: TahpEvent) => {
      const tid = ev.task_id
      if (!tid) return

      // ── 更新事件流 ────────────────────────────────────────────────────
      const arr = taskStreams.value[tid] ? [...taskStreams.value[tid]] : []
      arr.push({ type: ev.type, payload: ev.payload, ts: ev.ts })
      if (arr.length > 500) arr.splice(0, arr.length - 500)
      taskStreams.value = { ...taskStreams.value, [tid]: arr }

      // ── 同步更新任务列表中的任务状态 ───────────────────────────────────
      const idx = tasks.value.findIndex(t => (t.task_id || t.taskId) === tid)
      if (idx === -1) return
      const task = { ...tasks.value[idx] }

      switch (ev.type) {
        case 'task.started':
          task.status = 'running'
          task.started_at = new Date(ev.ts).toISOString()
          break
        case 'task.phase':
          task.phase = ev.payload?.phase as string
          if (typeof ev.payload?.progress === 'number') {
            task.progress = ev.payload.progress as number
          }
          break
        case 'task.step':
          // 步骤完成时轻微推进进度感知（不改变 phase progress）
          break
        case 'task.completed':
          task.status = 'completed'
          task.phase = 'COMPLETED'
          task.progress = 100
          task.completed_at = new Date(ev.ts).toISOString()
          if (ev.payload?.response)      task.llm_response    = ev.payload.response as string
          if (ev.payload?.filesModified) task.files_modified  = ev.payload.filesModified as string[]
          break
        case 'task.failed':
          task.status = 'failed'
          task.phase = 'FAILED'
          task.completed_at = new Date(ev.ts).toISOString()
          task.error = ev.payload?.error as string
          break
      }

      tasks.value = tasks.value.map((t, i) => i === idx ? task : t)
    }

    const events = [
      'task.started', 'task.phase', 'task.step', 'task.message',
      'task.completed', 'task.failed', 'task.correction', 'task.progress',
      // Agent 自动适配扩展事件
      'task.skill_use', 'task.file_change', 'task.plan', 'task.tool_completed',
    ]
    events.forEach(e => s.on(e, handler))
    socketBound = true
  }

  function getStream(taskId: string): TaskStreamEntry[] {
    return taskStreams.value[taskId] || []
  }

  async function refresh(includeCompleted = true) {
    loading.value = true
    lastError.value = null
    try {
      const resp = await listTasks(includeCompleted)
      tasks.value = Array.isArray(resp) ? resp : (resp.tasks || [])
    } catch (err) {
      lastError.value = (err as Error).message
    } finally {
      loading.value = false
    }
  }

  async function start(req: ExecuteTaskRequest): Promise<TaskInfo> {
    ensureSocket()
    lastError.value = null
    try {
      const info = await executeTask(req)
      const tid = (info.task_id || info.taskId) as string | undefined
      if (tid) {
        activeTaskId.value = tid
        if (!taskStreams.value[tid]) taskStreams.value[tid] = []
      }
      tasks.value = [info, ...tasks.value]
      return info
    } catch (err) {
      lastError.value = (err as Error).message
      throw err
    }
  }

  async function fetchStatus(taskId: string): Promise<TaskInfo> {
    return getTaskStatus(taskId)
  }

  async function correct(taskId: string, feedback: string): Promise<TaskInfo | null> {
    ensureSocket()
    // tahpPost already unwraps the { success, data } envelope — result is data directly
    const info = await correctTask(taskId, feedback) as TaskInfo | null
    if (info) {
      const tid = (info.task_id || info.taskId) as string | undefined
      if (tid) {
        activeTaskId.value = tid
        if (!taskStreams.value[tid]) taskStreams.value[tid] = []
      }
      tasks.value = [info, ...tasks.value]
    }
    return info ?? null
  }

  const recent = computed(() => tasks.value.slice(0, 5))

  return {
    tasks, recent, loading, lastError, activeTaskId, taskStreams,
    ensureSocket, getStream, refresh, start, fetchStatus, correct,
  }
})
