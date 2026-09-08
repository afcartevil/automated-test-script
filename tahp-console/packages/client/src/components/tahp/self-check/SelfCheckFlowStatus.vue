<script setup lang="ts">
import { pipelineStatusLabel, type PipelineStage } from './self-check-utils'

const props = defineProps<{
  stages: PipelineStage[]
  layout?: 'vertical' | 'horizontal'
}>()

const emit = defineEmits<{
  stageClick: [key: string]
}>()

const stageTabMap: Record<string, string> = {
  test: 'devices',
  review: 'review',
}

function handleStageClick(stage: PipelineStage) {
  const tab = stageTabMap[stage.key]
  if (tab) emit('stageClick', tab)
}

function shouldShowStatus(stage: PipelineStage): boolean {
  return !(stage.key === 'test' && stage.status === 'done')
}
</script>

<template>
  <ul class="flow-list" :class="{ 'flow-list--horizontal': layout === 'horizontal' }">
    <li
      v-for="stage in props.stages"
      :key="stage.key"
      class="flow-item"
      :class="`status-${stage.status}`"
      @click="handleStageClick(stage)"
    >
      <span class="flow-dot" />
      <div class="flow-body">
        <div class="flow-label">{{ stage.label }}</div>
        <div v-if="shouldShowStatus(stage)" class="flow-status">
          {{ pipelineStatusLabel(stage.status) }}
        </div>
        <div v-if="stage.hint" class="flow-hint ea-muted">{{ stage.hint }}</div>
      </div>
    </li>
  </ul>
</template>

<style scoped lang="scss">
.flow-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;

  &--horizontal {
    flex-direction: row;
    flex-wrap: wrap;
    gap: 10px;

    .flow-item {
      flex: 1 1 140px;
      min-width: 0;
    }
  }
}

.flow-item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 6px 8px;
  margin: -6px -8px;
  border-radius: 8px;
  cursor: pointer;

  &:hover {
    background: var(--bg);
  }
}

.flow-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 5px;
  flex-shrink: 0;
  background: var(--muted);
}

.status-idle .flow-dot { background: var(--line-strong, #ccc); }
.status-queued .flow-dot { background: var(--muted); }
.status-running .flow-dot { background: var(--accent); }
.status-done .flow-dot { background: var(--success); }
.status-attention .flow-dot { background: var(--warning, #f59e0b); }

.flow-label {
  font-size: 13px;
  font-weight: 600;
}

.flow-status {
  font-size: 12px;
  color: var(--muted);
}

.flow-hint {
  font-size: 11px;
  margin-top: 2px;
}
</style>
