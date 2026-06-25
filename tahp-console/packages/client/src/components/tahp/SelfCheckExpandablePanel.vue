<script setup lang="ts">
import EaFeatureHeroCard, { type FeatureHeroIcon } from '@/components/layout/EaFeatureHeroCard.vue'

const props = defineProps<{
  title: string
  summary: string
  tone: string
  icon?: FeatureHeroIcon
  expanded: boolean
}>()

const emit = defineEmits<{
  'update:expanded': [value: boolean]
}>()

function expand() {
  emit('update:expanded', true)
}

function collapse() {
  emit('update:expanded', false)
}
</script>

<template>
  <div class="expandable-panel">
    <EaFeatureHeroCard
      v-if="!props.expanded"
      :title="title"
      :summary="summary"
      :tone="tone"
      :icon="icon"
      @click="expand"
    />
    <template v-else>
      <div class="expandable-panel-toolbar">
        <button type="button" class="ea-btn-ghost ea-btn-sm" @click="collapse">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="15 18 9 12 15 6" />
          </svg>
          收起
        </button>
      </div>
      <slot />
    </template>
  </div>
</template>

<style scoped lang="scss">
.expandable-panel {
  margin-top: 16px;
}

.expandable-panel-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}
</style>
