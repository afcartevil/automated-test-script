import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useDeviceSelfCheckLaunchStore = defineStore('tahp-device-self-check-launch', () => {
  const pendingCustomCaseKeys = ref<string[]>([])
  const fromGerrit = ref(false)

  function launchCustomTestFromGerrit(caseKeys: string[]) {
    pendingCustomCaseKeys.value = [...caseKeys]
    fromGerrit.value = caseKeys.length > 0
  }

  function consumePendingCustomCases(): string[] {
    const keys = [...pendingCustomCaseKeys.value]
    pendingCustomCaseKeys.value = []
    fromGerrit.value = false
    return keys
  }

  return {
    pendingCustomCaseKeys,
    fromGerrit,
    launchCustomTestFromGerrit,
    consumePendingCustomCases,
  }
})
