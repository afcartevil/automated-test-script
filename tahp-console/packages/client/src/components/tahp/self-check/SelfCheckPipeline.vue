<script setup lang="ts">
import EaCard from '@/components/layout/EaCard.vue'
import { pipelineStatusLabel, type PipelineStage } from './self-check-utils'

defineProps<{
  stages: PipelineStage[]
}>()
</script>

<template>
  <EaCard class="pipeline-card">
    <div class="pipeline-title">今日自动化流程</div>
    <div class="pipeline-track">
      <template v-for="(stage, index) in stages" :key="stage.key">
        <div class="pipeline-step" :class="`status-${stage.status}`">
          <div class="step-dot" />
          <div class="step-body">
            <div class="step-label">{{ stage.label }}</div>
            <div class="step-status">{{ pipelineStatusLabel(stage.status) }}</div>
            <div v-if="stage.hint" class="step-hint ea-muted">{{ stage.hint }}</div>
          </div>
        </div>
        <div v-if="index < stages.length - 1" class="pipeline-connector" />
      </template>
    </div>
  </EaCard>
</template>

<style scoped lang="scss">
.pipeline-card {
  margin-bottom: 16px;
  padding: 16px 18px;
}

.pipeline-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 14px;
}

.pipeline-track {
  display: flex;
  align-items: flex-start;
  gap: 0;
  overflow-x: auto;
  padding-bottom: 4px;
}

.pipeline-step {
  flex: 1;
  min-width: 120px;
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.step-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-top: 4px;
  flex-shrink: 0;
  background: var(--muted);
}

.status-idle .step-dot { background: var(--line-strong, #ccc); }
.status-queued .step-dot { background: var(--muted); }
.status-running .step-dot { background: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.status-done .step-dot { background: var(--success); }
.status-attention .step-dot { background: var(--warning, #f59e0b); }

.step-label {
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 2px;
}

.step-status {
  font-size: 12px;
  color: var(--muted);
}

.step-hint {
  font-size: 11px;
  margin-top: 2px;
}

.pipeline-connector {
  flex: 0 0 24px;
  height: 2px;
  background: var(--line);
  margin-top: 8px;
  align-self: flex-start;
}

@media (max-width: 720px) {
  .pipeline-track {
    flex-direction: column;
    gap: 12px;
  }

  .pipeline-connector {
    width: 2px;
    height: 16px;
    flex: none;
    margin: 0 0 0 4px;
  }
}
</style>
