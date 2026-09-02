import { computed, onMounted, ref } from 'vue'
import { fetchSkillConfigList, type SkillConfigListItem } from '@/api/tahp/skill-config'
import { summarizeSkillSetup } from '@/utils/config-navigation'

export function useSkillConfigReadiness() {
  const loading = ref(true)
  const skills = ref<SkillConfigListItem[]>([])
  const batchRunning = ref(false)
  const lastCheckOk = ref<boolean | null>(null)

  const unconfiguredSkills = computed(() =>
    skills.value.filter(s => s.status === 'not_configured'),
  )
  const hasUnconfigured = computed(() => unconfiguredSkills.value.length > 0)
  const unconfiguredCount = computed(() => unconfiguredSkills.value.length)
  const summary = computed(() => summarizeSkillSetup({
    skills: skills.value,
    batchRunning: batchRunning.value,
    lastCheckOk: lastCheckOk.value,
  }))

  async function refresh() {
    loading.value = true
    try {
      const data = await fetchSkillConfigList()
      skills.value = data.skills
      batchRunning.value = !!data.batch_task
      lastCheckOk.value = typeof data.last_check?.ok === 'boolean' ? data.last_check.ok : null
    } catch {
      skills.value = []
      batchRunning.value = false
      lastCheckOk.value = null
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    void refresh()
  })

  return {
    loading,
    skills,
    unconfiguredSkills,
    hasUnconfigured,
    unconfiguredCount,
    summary,
    refresh,
  }
}
