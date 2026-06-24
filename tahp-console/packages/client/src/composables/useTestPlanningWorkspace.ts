import { computed, ref } from 'vue'
import { useMessage } from 'naive-ui'
import {
  fetchProjectNodes,
  fetchTestPlanRules,
  fetchTestSchedule,
  syncProjectNodes,
  type NextNodeItem,
  type ScheduleItem,
  type TestPlanRule,
} from '@/api/tahp/test-planning'

export function useTestPlanningWorkspace() {
  const message = useMessage()

  const loading = ref(false)
  const syncing = ref(false)
  const settingsVisible = ref(false)

  const updatedAt = ref<string | null>(null)
  const sourcePath = ref<string | null>(null)
  const nextNodes = ref<NextNodeItem[]>([])
  const scheduleItems = ref<ScheduleItem[]>([])
  const rules = ref<TestPlanRule[]>([])

  const hasSyncedData = computed(() => Boolean(updatedAt.value))
  const hasRules = computed(() => rules.value.length > 0)

  const updatedAtLabel = computed(() => {
    if (!updatedAt.value) return ''
    try {
      return new Date(updatedAt.value).toLocaleString('zh-CN')
    } catch {
      return updatedAt.value
    }
  })

  async function loadAll() {
    loading.value = true
    try {
      const [nodesView, scheduleView, rulesView] = await Promise.all([
        fetchProjectNodes(),
        fetchTestSchedule(),
        fetchTestPlanRules(),
      ])
      updatedAt.value = nodesView.updatedAt
      sourcePath.value = nodesView.sourcePath
      nextNodes.value = nodesView.nextNodes
      scheduleItems.value = scheduleView.items
      rules.value = rulesView.rules
    } catch (err) {
      const msg = (err as Error).message || ''
      if (/failed to fetch|networkerror|load failed/i.test(msg)) {
        message.error('无法连接后端服务，请确认已执行 npm run dev 且 server:8650 已启动')
      } else {
        message.error(msg || '加载测试自规划数据失败')
      }
    } finally {
      loading.value = false
    }
  }

  async function handleSync() {
    syncing.value = true
    try {
      await syncProjectNodes()
      message.success('项目节点已更新')
      await loadAll()
    } catch (err) {
      message.error((err as Error).message || '更新项目节点失败')
    } finally {
      syncing.value = false
    }
  }

  async function handleRulesSaved() {
    await loadAll()
  }

  function restoreWorkspace() {
    void loadAll()
  }

  return {
    loading,
    syncing,
    settingsVisible,
    updatedAt,
    sourcePath,
    nextNodes,
    scheduleItems,
    rules,
    hasSyncedData,
    hasRules,
    updatedAtLabel,
    handleSync,
    handleRulesSaved,
    restoreWorkspace,
  }
}
