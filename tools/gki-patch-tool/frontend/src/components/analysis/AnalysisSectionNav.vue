<template>
  <nav v-if="sections.length" class="analysis-section-nav" :aria-label="navLabel">
    <button
      v-for="section in sections"
      :key="section.id"
      type="button"
      class="analysis-section-nav-btn"
      :class="{ active: activeId === section.id }"
      @click="onNavigate(section.id)"
    >
      {{ section.label }}
    </button>
  </nav>
</template>

<script setup lang="ts">
import type { AnalysisNavSection } from '../../utils/analysisDisplay'

withDefaults(defineProps<{
  sections: AnalysisNavSection[]
  navLabel?: string
}>(), {
  navLabel: '分析结果导航',
})

const activeId = defineModel<string>('activeId', { default: '' })

const emit = defineEmits<{
  navigate: [sectionId: string]
}>()

function onNavigate(sectionId: string) {
  activeId.value = sectionId
  emit('navigate', sectionId)
}
</script>
