/**
 * 同步中心状态缓存 — Tab 切换不丢数据，再次进入先秒开快照。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchSyncStatus, type SkillSyncStatus } from '@/api/hermes/skills'

export const useSkillSyncStore = defineStore('skill-sync', () => {
  const status = ref<SkillSyncStatus | null>(null)
  const loading = ref(false)
  const refreshing = ref(false)
  const lastError = ref<string | null>(null)
  const selectedGroupId = ref<string | null>(null)

  async function load(opts?: { force?: boolean }): Promise<SkillSyncStatus | null> {
    lastError.value = null
    const force = !!opts?.force

    // 1) 无数据时先尝试服务端磁盘/内存快照（几乎瞬间；cached=1 绝不扫盘）
    if (!status.value && !force) {
      try {
        const cached = await fetchSyncStatus({ cachedOnly: true })
        if (cached && Array.isArray(cached.skills)) {
          status.value = cached
        }
      } catch {
        /* 无快照时忽略 */
      }
    }

    // 2) 有旧数据 → 后台刷新；无数据 → 阻塞加载
    const hasUi = !!status.value
    if (hasUi) refreshing.value = true
    else loading.value = true

    try {
      const data = await fetchSyncStatus({ force })
      if (!data) {
        throw new Error('同步状态为空')
      }
      status.value = data
      if (
        selectedGroupId.value
        && !data.groups.some(g => g.id === selectedGroupId.value)
      ) {
        selectedGroupId.value = null
      }
      return data
    } catch (e) {
      lastError.value = (e as Error).message
      throw e
    } finally {
      loading.value = false
      refreshing.value = false
    }
  }

  function setStatus(s: SkillSyncStatus | null) {
    status.value = s
  }

  return {
    status,
    loading,
    refreshing,
    lastError,
    selectedGroupId,
    load,
    setStatus,
  }
})
