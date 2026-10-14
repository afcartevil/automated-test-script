<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { CaseCatalogGroup } from '@/api/tahp/device-self-check'
import EaCard from '@/components/layout/EaCard.vue'
import {
  TEST_TYPE_CATEGORIES,
  formatCatalogAutomation,
  formatCatalogModuleScope,
  formatCatalogPrereq,
  getTestTypeCategory,
  getTestTypeLabel,
  type TestTypeCategoryKey,
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

/** 当前展开的分类；null 时仅展示「通用测试 / 领域测试」两张大类卡 */
const activeCategory = ref<TestTypeCategoryKey | null>(null)

// 用例目录展开（含外部重开）时，卡片自动落在对应分类并保持二级视图；
// 目录收起（activeTestType 变 null）后停留在当前二级视图，上下文不丢
watch(
  () => props.activeTestType,
  (testType) => {
    if (!testType) return
    const category = getTestTypeCategory(testType)
    if (category) activeCategory.value = category.key
  },
  { immediate: true },
)

const CATEGORY_TONES: Record<TestTypeCategoryKey, string> = {
  general: 'ea-t-sky',
  domain: 'ea-t-violet',
}

const categoryCards = computed(() =>
  TEST_TYPE_CATEGORIES.map(category => ({
    ...category,
    tone: CATEGORY_TONES[category.key],
    summary: category.testTypes.map(testType => getTestTypeLabel(testType)).join('、'),
  })),
)

const catalogCards = computed(() => {
  if (!activeCategory.value) return []
  const category = TEST_TYPE_CATEGORIES.find(c => c.key === activeCategory.value)
  if (!category) return []
  const byType = new Map(props.groups.map(g => [g.testType, g]))
  return category.testTypes.map(testType => {
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
  ota_upgrade: 'ea-t-teal',
  monkey: 'ea-t-amber',
  monkey_check: 'ea-t-teal',
  power: 'ea-t-rose',
  power_feature: 'ea-t-violet',
  thermal: 'ea-t-orange',
  ai_generated: 'ea-t-cyan',
  bitflip: 'ea-t-indigo',
}

function openCategory(key: TestTypeCategoryKey) {
  activeCategory.value = key
}

function backToCategories() {
  activeCategory.value = null
}

function openCatalog(testType: string) {
  emit('openCatalog', testType)
}
</script>

<template>
  <div class="checklist-root" :class="{ compact }">
    <div v-if="!activeCategory" class="checklist-grid checklist-grid--categories">
      <EaCard
        v-for="category in categoryCards"
        :key="category.key"
        class="checklist-card checklist-card-clickable"
        :class="category.tone"
        role="button"
        tabindex="0"
        @click="openCategory(category.key)"
        @keydown.enter="openCategory(category.key)"
      >
        <h4>{{ category.label }}</h4>
        <p class="category-summary">{{ category.summary }}</p>
        <p class="category-count ea-muted">{{ category.testTypes.length }} 个测试项</p>
      </EaCard>
    </div>

    <template v-else>
      <div class="checklist-toolbar">
        <button type="button" class="checklist-back" @click="backToCategories">← 返回分类</button>
        <div class="category-switch">
          <button
            v-for="category in categoryCards"
            :key="category.key"
            type="button"
            class="category-switch-btn"
            :class="{ active: activeCategory === category.key }"
            @click="openCategory(category.key)"
          >{{ category.label }}</button>
        </div>
      </div>
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
    </template>
  </div>
</template>

<style scoped lang="scss">
.checklist-root {
  margin-bottom: 16px;

  &.compact .checklist-grid {
    grid-template-columns: repeat(5, minmax(0, 1fr));
  }

  &.compact .checklist-grid--categories {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.checklist-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.checklist-grid--categories {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.checklist-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.checklist-back {
  border: none;
  background: none;
  padding: 0;
  color: var(--accent);
  cursor: pointer;
  font-size: 13px;
  white-space: nowrap;
}

.category-switch {
  display: flex;
  gap: 8px;
}

.category-switch-btn {
  border: 1px solid var(--line);
  background: var(--bg);
  color: var(--muted);
  border-radius: 999px;
  padding: 4px 14px;
  font-size: 13px;
  cursor: pointer;

  &.active {
    color: var(--accent);
    border-color: var(--accent);
    background: var(--accent-soft, color-mix(in srgb, var(--accent) 10%, transparent));
    font-weight: 600;
  }
}

.category-summary {
  margin: 0 0 8px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--muted);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.category-count {
  margin: 0;
  font-size: 12px;
}

.checklist-card {
  padding: 14px 16px;
  border-top: 3px solid var(--line);

  &.ea-t-indigo { border-top-color: #6366f1; }
  &.ea-t-sky { border-top-color: #0ea5e9; }
  &.ea-t-emerald { border-top-color: #129b71; }
  &.ea-t-teal { border-top-color: #0d9488; }
  &.ea-t-amber { border-top-color: #f59e0b; }
  &.ea-t-teal { border-top-color: #14b8a6; }
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
