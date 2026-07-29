<script setup lang="ts">
import { computed, onMounted } from 'vue'
import type { TimelineNode } from '@/api/tahp/adapt-pipeline'
import PipelineResumePicker from './PipelineResumePicker.vue'
import type { useAdaptPipelineStore } from '@/stores/tahp/adapt-pipeline'

const props = defineProps<{
  runId: string
  nodes: TimelineNode[]
  store: ReturnType<typeof useAdaptPipelineStore>
}>()

const waitingNodes = computed(() =>
  props.nodes.filter(n => n.status === 'waiting_human' && n.human),
)

onMounted(async () => {
  if (waitingNodes.value.some(n => n.key === 'human_review')) {
    await props.store.loadResumePoints(props.runId)
  }
})

async function onAction(nodeKey: string, actionId: string) {
  if (actionId === 'abort') {
    await props.store.submitHumanAction(props.runId, nodeKey, actionId)
    return
  }
  if (actionId === 'confirm_done' && nodeKey === 'human_review') {
    return
  }
  await props.store.submitHumanAction(props.runId, nodeKey, actionId)
}

async function onResume(node: string, scope: 'continue' | 'restart', force: boolean) {
  await props.store.resumeRun(props.runId, node, scope, force)
}
</script>

<template>
  <div class="human-panel">
    <h3>人工介入</h3>
    <div v-if="waitingNodes.length === 0" class="empty">当前无需人工介入</div>
    <div v-for="node in waitingNodes" :key="node.key" class="card">
      <strong>⚠ {{ node.label }}</strong>
      <p>{{ node.human?.message }}</p>
      <div class="actions">
        <button
          v-for="action in node.human?.actions ?? []"
          :key="action.id"
          type="button"
          :class="action.danger ? 'btn-danger' : 'btn-soft'"
          :disabled="store.actionBusy"
          @click="onAction(node.key, action.id)"
        >
          {{ action.label }}
        </button>
      </div>
      <PipelineResumePicker
        v-if="node.key === 'human_review'"
        :data="store.resumePoints"
        :busy="store.actionBusy"
        @reload="store.loadResumePoints(runId)"
        @submit="onResume"
      />
    </div>
  </div>
</template>

<style scoped lang="scss">
.human-panel h3 {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--faint);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.card {
  border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--warn) 25%, transparent);
  background: var(--warn-soft);
  padding: 10px;
  margin-bottom: 10px;
}
.card p {
  margin: 6px 0 10px;
  color: var(--warn);
  line-height: 1.45;
}
.actions {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.empty { color: var(--faint); }
</style>
