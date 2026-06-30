<script setup lang="ts">
import { computed } from 'vue'
import type { CaseCatalogGroup } from '@/api/tahp/device-self-check'
import EaCard from '@/components/layout/EaCard.vue'
import {
  formatCatalogAutomation,
  formatCatalogModuleScope,
  formatCatalogPrereq,
} from './self-check-utils'

const props = withDefaults(
  defineProps<{
    compact?: boolean
    groups?: CaseCatalogGroup[]
    activeTestType?: string | null
  }>(),
  {
    compact: false,
    groups: () => [],
    activeTestType: null,
  },
)

const emit = defineEmits<{
  openCatalog: [testType: string]
}>()

const CASE_TYPES = ['str4', 'week', 'monkey', 'smoke'] as const

const catalogCards = computed(() => {
  const byType = new Map(props.groups.map(g => [g.testType, g]))
  return CASE_TYPES.map(testType => byType.get(testType)).filter(Boolean) as CaseCatalogGroup[]
})

const toneByType: Record<string, string> = {
  str4: 'ea-t-indigo',
  week: 'ea-t-sky',
  monkey: 'ea-t-amber',
  smoke: 'ea-t-emerald',
}

function openCatalog(testType: string) {
  emit('openCatalog', testType)
}
</script>

<template>
  <div class="checklist-root" :class="{ compact }">
    <div class="checklist-grid">
      <EaCard
        v-for="group in catalogCards"
        :key="group.testType"
        class="checklist-card checklist-card-clickable"
        :class="[
          toneByType[group.testType] || '',
          { 'is-active': activeTestType === group.testType },
        ]"
        role="button"
        tabindex="0"
        @click="openCatalog(group.testType)"
        @keydown.enter="openCatalog(group.testType)"
      >
        <h4>{{ group.label }}</h4>
        <dl class="checklist-meta">
          <div><dt>覆盖</dt><dd>{{ formatCatalogModuleScope(group) }}</dd></div>
          <div><dt>自动化</dt><dd>{{ formatCatalogAutomation(group) }}</dd></div>
          <div><dt>前置</dt><dd>{{ formatCatalogPrereq(group) }}</dd></div>
        </dl>
      </EaCard>
    </div>
  </div>
</template>

<style scoped lang="scss">
.checklist-root {
  margin-bottom: 16px;

  &.compact .checklist-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

.checklist-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.checklist-card {
  padding: 14px 16px;
  border-top: 3px solid var(--line);

  &.ea-t-indigo { border-top-color: #6366f1; }
  &.ea-t-sky { border-top-color: #0ea5e9; }
  &.ea-t-amber { border-top-color: #f59e0b; }

  h4 {
    margin: 0 0 10px;
    font-size: 14px;
    font-weight: 700;
    line-height: 1.35;
  }
}

.checklist-card-clickable {
  cursor: pointer;
  transition: box-shadow 0.15s ease, transform 0.15s ease;

  &:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  }

  &.is-active {
    box-shadow: 0 0 0 2px var(--accent);
  }

  &:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
}

.checklist-meta {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;

  div {
    display: grid;
    grid-template-columns: 48px 1fr;
    gap: 8px;
    font-size: 12px;
  }

  dt {
    color: var(--muted);
    font-weight: 600;
  }

  dd {
    margin: 0;
    line-height: 1.4;
  }
}

@media (max-width: 640px) {
  .checklist-root.compact .checklist-grid,
  .checklist-grid {
    grid-template-columns: 1fr;
  }
}
</style>
