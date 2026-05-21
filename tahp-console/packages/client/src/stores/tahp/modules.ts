import { defineStore } from 'pinia'
import { ref } from 'vue'
import { listModules, type ModuleInfo } from '@/api/tahp/modules'

export const useTahpModulesStore = defineStore('tahp-modules', () => {
  const modules = ref<ModuleInfo[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function refresh() {
    loading.value = true
    error.value = null
    try {
      modules.value = await listModules()
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      loading.value = false
    }
  }

  return { modules, loading, error, refresh }
})
