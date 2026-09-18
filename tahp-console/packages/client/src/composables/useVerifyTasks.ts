/**
 * 验测任务（中心 BFF 指派）轮询数据源。
 * 真相在中心 verify/mine?view=open：中心侧完成/取消后，本 composable
 * 下一次轮询（15s，与 EaShell 收件箱同节奏）或切回总览页（onActivated 立即刷新）即移除。
 * 测试账号（test- 前缀）额外带回本机自动执行状态（标签/设备/暂停开关）。
 * 轮询随 keep-alive 停启，组件卸载即清理。
 */
import { onActivated, onDeactivated, onMounted, onUnmounted, ref } from 'vue'
import {
  cancelVerifyAutoRunTask,
  fetchMyVerifyTasks,
  setVerifyAutoRunEnabled,
  type VerifyAutoRunSummary,
  type VerifyTaskItem,
} from '@/api/tahp/verify-tasks'

const POLL_INTERVAL_MS = 15_000

export function useVerifyTasks() {
  const tasks = ref<VerifyTaskItem[]>([])
  const loading = ref(false)
  /** 中心不可达（代理层 degraded 或请求失败）：卡片红字提示 */
  const unreachable = ref(false)
  /** 本机自动执行状态（测试账号）；中心不可达时仍可用 */
  const autoRun = ref<VerifyAutoRunSummary | null>(null)
  const autoRunBusy = ref(false)
  let timer: number | null = null

  async function refresh() {
    loading.value = true
    try {
      const result = await fetchMyVerifyTasks()
      tasks.value = result.tasks || []
      unreachable.value = result.degraded === true
      if (result.auto_run) autoRun.value = result.auto_run
    } catch {
      // 拉取失败保留旧数据并提示不可达，下一轮再试
      unreachable.value = true
    } finally {
      loading.value = false
    }
  }

  async function toggleAutoRun(enabled: boolean) {
    autoRunBusy.value = true
    try {
      autoRun.value = await setVerifyAutoRunEnabled(enabled)
    } finally {
      autoRunBusy.value = false
      void refresh()
    }
  }

  async function cancelAutoRun(taskId: string) {
    autoRunBusy.value = true
    try {
      await cancelVerifyAutoRunTask(taskId)
    } finally {
      autoRunBusy.value = false
      void refresh()
    }
  }

  function start() {
    if (timer !== null) return
    timer = window.setInterval(() => void refresh(), POLL_INTERVAL_MS)
  }

  function stop() {
    if (timer !== null) {
      window.clearInterval(timer)
      timer = null
    }
  }

  onMounted(() => {
    void refresh()
    start()
  })
  onActivated(() => {
    void refresh()
    start()
  })
  onDeactivated(stop)
  onUnmounted(stop)

  return { tasks, loading, unreachable, autoRun, autoRunBusy, refresh, toggleAutoRun, cancelAutoRun }
}
