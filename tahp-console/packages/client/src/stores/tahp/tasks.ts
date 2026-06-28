/**
 * TAHP 任务 Socket 事件流 store（Agent 任务实时进度）.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getTahpSocket, type TahpEvent } from '@/api/tahp/socket'

interface TaskStreamEntry {
  type: string
  payload: Record<string, unknown>
  ts: number
}

export const useTahpTasksStore = defineStore('tahp-tasks', () => {
  const activeTaskId = ref<string | null>(null)
  const taskStreams = ref<Record<string, TaskStreamEntry[]>>({})

  let socketBound = false

  function ensureSocket() {
    if (socketBound) return
    const s = getTahpSocket()
    const handler = (ev: TahpEvent) => {
      const tid = ev.task_id
      if (!tid) return
      const arr = taskStreams.value[tid] ? [...taskStreams.value[tid]] : []
      arr.push({ type: ev.type, payload: ev.payload, ts: ev.ts })
      if (arr.length > 500) arr.splice(0, arr.length - 500)
      taskStreams.value = { ...taskStreams.value, [tid]: arr }
    }

    const events = [
      'task.started', 'task.phase', 'task.step', 'task.message',
      'task.completed', 'task.failed', 'task.cancelled', 'task.correction', 'task.progress',
      'task.skill_use', 'task.file_change', 'task.plan', 'task.tool_completed',
      'task.audit_completed', 'task.skill_config_complete',
      'task.approval_requested', 'task.approval_resolved',
      'task.user_input_requested', 'task.user_input_submitted',
    ]
    events.forEach(e => s.on(e, handler))
    socketBound = true
  }

  function getStream(taskId: string): TaskStreamEntry[] {
    return taskStreams.value[taskId] || []
  }

  function trackTask(taskId: string) {
    activeTaskId.value = taskId
    if (!taskStreams.value[taskId]) {
      taskStreams.value = { ...taskStreams.value, [taskId]: [] }
    }
  }

  return {
    activeTaskId,
    taskStreams,
    ensureSocket,
    getStream,
    trackTask,
  }
})
