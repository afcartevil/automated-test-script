import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ModuleInfo } from '@/constants/tahp-modules'
import { TAHP_MODULES } from '@/constants/tahp-modules'

export const useTahpModulesStore = defineStore('tahp-modules', () => {
  const modules = ref<ModuleInfo[]>([...TAHP_MODULES])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function refresh() {
    loading.value = true
    error.value = null
    try {
      modules.value = [...TAHP_MODULES]
    } finally {
      loading.value = false
    }
  }

  return { modules, loading, error, refresh }
})
