<script setup lang="ts">
import EaCard from '@/components/layout/EaCard.vue'

defineProps<{
  title: string
  tone?: string
  metric?: string | number
  metricLabel?: string
  secondaryMetric?: string
  compact?: boolean
  hideEnter?: boolean
  fillBody?: boolean
  tall?: boolean
}>()

const emit = defineEmits<{
  enter: []
}>()
</script>

<template>
  <EaCard class="overview-feature-card" :class="[tone, { compact, tall }]">
    <div class="card-head">
      <h3>{{ title }}</h3>
      <button
        v-if="!hideEnter"
        type="button"
        class="ea-btn-ghost ea-btn-sm card-enter"
        @click="emit('enter')"
      >
        进入 →
      </button>
    </div>
    <div v-if="metric !== undefined && metricLabel" class="card-metrics">
      <div class="metric-primary">
        <span class="metric-value" :class="{ 'metric-value--text': typeof metric !== 'number' }">{{ metric }}</span>
        <span class="metric-label">{{ metricLabel }}</span>
      </div>
      <div v-if="secondaryMetric" class="metric-secondary ea-muted">{{ secondaryMetric }}</div>
    </div>
    <div class="card-body" :class="{ 'card-body--fill': fillBody }">
      <slot />
    </div>
  </EaCard>
</template>

<style scoped lang="scss">
.overview-feature-card {
  --card-action-col: 68px;
  padding: 14px 16px;
  min-height: 200px;
  display: flex;
  flex-direction: column;
  border-left: 3px solid var(--line);

  &.tone-indigo { border-left-color: #6366f1; --metric-color: #4f46e5; }
  &.tone-sky { border-left-color: #0ea5e9; --metric-color: #0284c7; }
  &.tone-amber { border-left-color: #f59e0b; --metric-color: #b45309; }
  &.tone-emerald { border-left-color: #10b981; --metric-color: #059669; }
  &.tone-violet { border-left-color: #8b5cf6; --metric-color: #7c3aed; }

  &.compact {
    min-height: 0;
  }

  &.tall {
    min-height: 360px;
  }
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;

  h3 {
    margin: 0;
    font-size: 14px;
    font-weight: 700;
  }
}

.card-enter {
  flex-shrink: 0;
  min-width: var(--card-action-col);
  justify-content: center;
}

.card-metrics {
  margin-bottom: 10px;
}

.metric-primary {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.metric-value {
  font-size: 22px;
  font-weight: 800;
  line-height: 1.1;
  color: var(--metric-color);

  &--text {
    font-size: 15px;
    font-weight: 600;
    line-height: 1.3;
    color: var(--metric-color);
  }
}

.metric-label {
  font-size: 12px;
  color: var(--muted);
  font-weight: 600;
}

.metric-secondary {
  font-size: 12px;
  margin-top: 4px;
}

.card-body {
  flex: 1;
  min-height: 0;
  font-size: 13px;

  &--fill {
    display: flex;
    flex-direction: column;
  }
}
</style>
