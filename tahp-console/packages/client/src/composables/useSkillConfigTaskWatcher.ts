import { ref, watch, nextTick, computed, type Ref, type ComputedRef } from 'vue'
import { useMessage } from 'naive-ui'
import { useTahpTasksStore } from '@/stores/tahp/tasks'
import type { BugApprovalRequest } from '@/stores/tahp/bug-analysis'

export function useSkillConfigTaskWatcher(options: {
  activeTaskId: Ref<string | null>
  onSkillComplete?: () => void | Promise<void>
  onTaskEnd?: (result: 'completed' | 'failed') => void | Promise<void>
}) {
  const message = useMessage()
  const tasksStore = useTahpTasksStore()
  const pendingApproval = ref<BugApprovalRequest | null>(null)
  const handledEventTs = ref<Record<string, number>>({})
  const scroller = ref<HTMLElement | null>(null)

  function streamText(taskId: string): string {
    const parts: string[] = []
    for (const ev of tasksStore.getStream(taskId)) {
      if (ev.type === 'task.message') {
        const level = (ev.payload as { level?: string })?.level
        if (level === 'stream' || level === 'user') {
          parts.push(String((ev.payload as { text?: string })?.text ?? ''))
        }
      }
    }
    return parts.join('')
  }

  /** 最新阶段提示（Agent 思考中、等待用户输入等） */
  function latestPhaseMessage(taskId: string): string {
    let latest = ''
    for (const ev of tasksStore.getStream(taskId)) {
      if (ev.type === 'task.phase') {
        const msg = String((ev.payload as { message?: string }).message || '')
        if (msg) latest = msg
      }
      if (ev.type === 'task.started') {
        const msg = String((ev.payload as { message?: string }).message || '')
        if (msg) latest = msg
      }
    }
    return latest
  }

  const taskRunning = computed(() => {
    const tid = options.activeTaskId.value
    if (!tid) return false
    const stream = tasksStore.getStream(tid)
    const terminal = stream.some(e =>
      e.type === 'task.completed' || e.type === 'task.failed' || e.type === 'task.cancelled',
    )
    return !terminal
  })

  function watchTaskEvents() {
    tasksStore.ensureSocket()
    return setInterval(() => {
      const tid = options.activeTaskId.value
      if (!tid) return
      const stream = tasksStore.getStream(tid)
      for (const ev of stream) {
        const key = `${ev.type}:${ev.ts}`
        if (handledEventTs.value[key]) continue
        handledEventTs.value[key] = 1

        if (ev.type === 'task.approval_requested' && !pendingApproval.value) {
          const p = ev.payload
          pendingApproval.value = {
            approval_id: String(p.approval_id || ''),
            command: String(p.command || ''),
            description: String(p.description || ''),
            choices: Array.isArray(p.choices) ? p.choices as string[] : ['once', 'deny'],
            timeout_ms: Number(p.timeout_ms) || 60000,
            deadline_at: Number(p.deadline_at) || Date.now() + 60000,
          }
        }
        if (ev.type === 'task.approval_resolved') {
          pendingApproval.value = null
        }
        if (ev.type === 'task.skill_config_complete') {
          message.success(String((ev.payload as { message?: string }).message || '配置完成'))
          void options.onSkillComplete?.()
        }
        if (ev.type === 'task.completed' || ev.type === 'task.failed') {
          const isBatch = (ev.payload as { batch?: boolean }).batch === true
          if (ev.type === 'task.completed') {
            message.success(String((ev.payload as { message?: string }).message || '配置流程结束'))
          } else {
            message.error(String((ev.payload as { message?: string }).message || '配置流程失败'))
          }
          if (!isBatch) options.activeTaskId.value = null
          void options.onTaskEnd?.(ev.type === 'task.completed' ? 'completed' : 'failed')
        }
      }
    }, 400)
  }

  function scrollChatToBottom(markdown: Ref<string> | ComputedRef<string>) {
    watch(markdown, async () => {
      await nextTick()
      if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
    })
  }

  return {
    tasksStore,
    pendingApproval,
    scroller,
    streamText,
    latestPhaseMessage,
    taskRunning,
    watchTaskEvents,
    scrollChatToBottom,
  }
}
