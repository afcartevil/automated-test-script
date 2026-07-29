<script setup lang="ts">
import type { TimelineNode } from '@/api/tahp/adapt-pipeline'

const props = defineProps<{
  nodes: TimelineNode[]
  selectedKey: string | null
}>()

const emit = defineEmits<{ select: [nodeKey: string] }>()

function icon(status: TimelineNode['status']): string {
  switch (status) {
    case 'done': return '✓'
    case 'running': return '◐'
    case 'waiting_human': return '⚠'
    case 'failed': return '✗'
    case 'skipped': return '−'
    default: return '○'
  }
}
</script>

<template>
  <div class="node-list">
    <button
      v-for="node in nodes"
      :key="node.key"
      type="button"
      class="node-item"
      :class="[{ selected: selectedKey === node.key }, `st-${node.status}`]"
      @click="emit('select', node.key)"
    >
      <span class="node-ico">{{ icon(node.status) }}</span>
      <span class="node-label">{{ node.label }}</span>
    </button>
  </div>
</template>

<style scoped lang="scss">
.node-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.node-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid transparent;
  background: var(--bg);
  cursor: pointer;
  font-family: inherit;
  text-align: left;
  color: var(--text);
}

.node-item:hover { border-color: var(--line-strong); }
.node-item.selected {
  background: var(--accent-soft);
  border-color: color-mix(in srgb, var(--accent) 24%, transparent);
  color: var(--accent);
}

.node-ico {
  width: 22px;
  height: 22px;
  border-radius: 7px;
  display: grid;
  place-items: center;
  font-size: 11px;
  font-weight: 800;
  flex-shrink: 0;
  background: var(--surface-2);
}

.node-item.st-done .node-ico { background: var(--success-soft); color: var(--success); }
.node-item.st-running .node-ico { background: var(--accent-soft); color: var(--accent); }
.node-item.st-waiting_human .node-ico { background: var(--warn-soft); color: var(--warn); }
.node-item.st-failed .node-ico { background: var(--error-soft); color: var(--error); }

.node-label {
  font-size: 13px;
  font-weight: 650;
}
</style>
