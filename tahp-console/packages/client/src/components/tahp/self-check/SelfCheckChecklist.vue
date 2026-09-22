<script setup lang="ts">
import { computed } from 'vue'
import type { CaseCatalogGroup } from '@/api/tahp/device-self-check'
import EaCard from '@/components/layout/EaCard.vue'
import {
  formatCatalogAutomation,
  formatCatalogModuleScope,
  formatCatalogPrereq,
  getTestTypeLabel,
  STANDARD_TEST_TYPE_ORDER,
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

const EMPTY_AI_GENERATED_GROUP: CaseCatalogGroup = {
  testType: 'ai_generated',
  label: getTestTypeLabel('ai_generated'),
  modules: [{
    key: 'ai_generated/generated',
    testType: 'ai_generated',
    module: 'generated',
    moduleLabel: 'AI生成用例',
    conditions: { dutSimCount: 0, auxRequired: 0, auxSimCount: 0 },
    cases: [],
  }],
}

const catalogCards = computed(() => {
  const byType = new Map(props.groups.map(g => [g.testType, g]))
  return STANDARD_TEST_TYPE_ORDER.map(testType => {
    const group = byType.get(testType)
    if (group) return group
    if (testType === 'ai_generated') return EMPTY_AI_GENERATED_GROUP
    return null
  }).filter(Boolean) as CaseCatalogGroup[]
})

const toneByType: Record<string, string> = {
  str4: 'ea-t-indigo',
  week: 'ea-t-sky',
  smoke: 'ea-t-emerald',
  monkey: 'ea-t-amber',
  power: 'ea-t-rose',
  power_feature: 'ea-t-violet',
  thermal: 'ea-t-orange',
  ai_generated: 'ea-t-cyan',
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
          {
            'is-active': activeTestType === group.testType,
            'is-unavailable': Boolean(group.unavailableReason),
          },
        ]"
        role="button"
        tabindex="0"
        @click="openCatalog(group.testType)"
        @keydown.enter="openCatalog(group.testType)"
      >
        <h4>{{ group.label }}</h4>
        <p v-if="group.unavailableReason" class="checklist-unavailable">{{ group.unavailableReason }}</p>
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
    grid-template-columns: repeat(5, minmax(0, 1fr));
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
  &.ea-t-emerald { border-top-color: #129b71; }
  &.ea-t-amber { border-top-color: #f59e0b; }
  &.ea-t-violet { border-top-color: #8b5cf6; }
  &.ea-t-rose { border-top-color: #f43f5e; }
  &.ea-t-orange { border-top-color: #f97316; }
  &.ea-t-cyan { border-top-color: #06b6d4; }

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

  &.is-unavailable {
    opacity: 0.82;
  }

  &:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
}

.checklist-unavailable {
  margin: 0 0 8px;
  font-size: 12px;
  line-height: 1.4;
  color: #b42318;
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
