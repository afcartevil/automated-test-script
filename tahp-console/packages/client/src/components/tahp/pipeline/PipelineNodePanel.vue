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
</style>
