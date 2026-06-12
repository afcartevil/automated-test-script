import { computed, onMounted, ref } from 'vue'
import { useAppStore } from '@/stores/hermes/app'
import { isModelProviderConfigured } from '@/utils/model-provider-readiness'

export function useModelProviderReadiness() {
  const appStore = useAppStore()
  const checking = ref(false)

  const isReady = computed(() => isModelProviderConfigured(appStore.modelGroups))
  const loading = computed(() => checking.value)

  async function refresh() {
    checking.value = true
    try {
      await appStore.loadModels(true)
    } finally {
      checking.value = false
    }
  }

  onMounted(() => {
    if (appStore.modelGroups.length === 0) {
      void refresh()
    }
  })

  return { isReady, loading, refresh }
}
