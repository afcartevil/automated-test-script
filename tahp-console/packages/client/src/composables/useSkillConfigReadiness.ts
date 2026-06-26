import { computed, onMounted, ref } from 'vue'
import { fetchSkillConfigList, type SkillConfigListItem } from '@/api/tahp/skill-config'

export function useSkillConfigReadiness() {
  const loading = ref(true)
  const skills = ref<SkillConfigListItem[]>([])

  const unconfiguredSkills = computed(() =>
    skills.value.filter(s => s.status === 'not_configured'),
  )
  const hasUnconfigured = computed(() => unconfiguredSkills.value.length > 0)
  const unconfiguredCount = computed(() => unconfiguredSkills.value.length)

  async function refresh() {
    loading.value = true
    try {
      const data = await fetchSkillConfigList()
      skills.value = data.skills
    } catch {
      skills.value = []
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
    refresh,
  }
}
