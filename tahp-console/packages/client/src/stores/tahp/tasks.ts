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
      const arr = taskStreams.value[tid] || []
      arr.push({ type: ev.type, payload: ev.payload, ts: ev.ts })
      // 保留最近 500 条
      if (arr.length > 500) arr.splice(0, arr.length - 500)
      taskStreams.value = { ...taskStreams.value, [tid]: arr }
    }
    const events = [
      'task.started', 'task.phase', 'task.step', 'task.message',
      'task.completed', 'task.failed', 'task.correction', 'task.progress',
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

  async function correct(taskId: string, feedback: string): Promise<void> {
    await correctTask(taskId, feedback)
  }

  const recent = computed(() => tasks.value.slice(0, 5))

  return {
    tasks, recent, loading, lastError, activeTaskId, taskStreams,
    ensureSocket, getStream, refresh, start, fetchStatus, correct,
  }
})
