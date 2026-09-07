/**
 * 验测任务（中心 BFF 指派）轮询数据源。
 * 真相在中心 verify/mine?view=open：中心侧完成/取消后，本 composable
 * 下一次轮询（15s，与 EaShell 收件箱同节奏）或切回总览页（onActivated 立即刷新）即移除。
 * 轮询随 keep-alive 停启，组件卸载即清理。
 */
import { onActivated, onDeactivated, onMounted, onUnmounted, ref } from 'vue'
import { fetchMyVerifyTasks, type VerifyTaskItem } from '@/api/tahp/verify-tasks'

const POLL_INTERVAL_MS = 15_000

export function useVerifyTasks() {
  const tasks = ref<VerifyTaskItem[]>([])
  const loading = ref(false)
  let timer: number | null = null

  async function refresh() {
    loading.value = true
    try {
      tasks.value = await fetchMyVerifyTasks()
    } catch {
      // 拉取失败保留旧数据，下一轮再试
    } finally {
      loading.value = false
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

  return { tasks, loading, refresh }
}
