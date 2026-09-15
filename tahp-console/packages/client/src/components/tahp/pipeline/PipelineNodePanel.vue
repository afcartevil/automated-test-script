<script setup lang="ts">
import { computed, type Component } from 'vue'
import type { BuildContext, TimelineNode } from '@/api/tahp/adapt-pipeline'
import DefaultPanel from './stage-panels/DefaultPanel.vue'
import AdaptPanel from './stage-panels/AdaptPanel.vue'
import BuildPanel from './stage-panels/BuildPanel.vue'
import FlashPanel from './stage-panels/FlashPanel.vue'
import SelfCheckPanel from './stage-panels/SelfCheckPanel.vue'
import TriagePanel from './stage-panels/TriagePanel.vue'
import GerritPanel from './stage-panels/GerritPanel.vue'

const RENDERERS: Record<string, Component> = {
  adapt: AdaptPanel,
  build: BuildPanel,
  flash: FlashPanel,
  selfcheck: SelfCheckPanel,
  triage: TriagePanel,
  gerrit: GerritPanel,
}

const props = defineProps<{
  node: TimelineNode | null
  logs: string[]
  buildContext?: BuildContext
}>()

const panel = computed(() => (props.node ? RENDERERS[props.node.key] ?? DefaultPanel : DefaultPanel))
</script>

<template>
  <div class="node-panel">
    <component
      :is="panel"
      v-if="node"
      :node="node"
      :logs="logs"
      :build-context="buildContext"
    />
    <p v-else class="empty">请点击上方阶段条查看详情。</p>
  </div>
</template>

<style scoped lang="scss">
.node-panel {
  --ea-log-height: clamp(420px, 52vh, 680px);
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.empty {
  color: var(--faint);
}
:deep(.panel) {
  h3 {
    margin: 0 0 10px;
    font-size: 15px;
    font-weight: 800;
  }
  h4 {
    margin: 0 0 8px;
    font-size: 12px;
    color: var(--faint);
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .build-meta,
  .summary,
  .meta,
  .device-card {
    margin-bottom: 12px;
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 10px 12px;
    background: var(--bg);
  }
  .summary:not(:has(.row)) {
    border: none;
    background: transparent;
    padding: 0;
  }
  .meta-row,
  .row {
    display: grid;
    grid-template-columns: 84px 1fr;
    gap: 8px;
    padding: 6px 0;
  }
  .k { color: var(--muted); font-weight: 600; font-size: 12px; }
  .v { font-size: 13px; word-break: break-word; }
  .mono {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px;
  }
  .error-box,
  .stage-error {
    background: var(--error-soft);
    color: var(--error);
    border-radius: 12px;
    padding: 10px 12px;
    margin-bottom: 12px;
    font-size: 13px;
    line-height: 1.5;
  }
}
</style>
