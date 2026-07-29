<script setup lang="ts">
import type { TimelineNode } from '@/api/tahp/adapt-pipeline'
import EaLogViewer from '@/components/common/EaLogViewer.vue'

const props = defineProps<{
  node: TimelineNode
  logs: string[]
}>()

interface TriageProgress {
  state?: string
  conclusion?: string
  evidence?: string[]
}

function tp(): TriageProgress {
  return (props.node.progress ?? {}) as TriageProgress
}
</script>

<template>
  <div class="panel">
    <h3>{{ node.label }}</h3>

    <div v-if="tp().conclusion" class="conclusion">
      <h4>分析结论</h4>
      <div class="md-block">{{ tp().conclusion }}</div>
    </div>

    <div v-if="tp().evidence?.length" class="evidence">
      <h4>关键证据</h4>
      <ul>
        <li v-for="(e, i) in tp().evidence" :key="i">{{ e }}</li>
      </ul>
    </div>

    <p v-if="!tp().conclusion && node.summary_line" class="summary">{{ node.summary_line }}</p>
    <p v-if="!tp().conclusion && !node.summary_line" class="empty">暂无分析结论</p>

    <h4>日志</h4>
    <EaLogViewer :lines="logs" :height="240" />
  </div>
</template>

<style scoped lang="scss">
.panel h3 { margin: 0 0 8px; font-size: 16px; font-weight: 800; }
.conclusion { margin-bottom: 12px; }
.md-block {
  background: var(--bg); border: 1px solid var(--line); border-radius: 12px;
  padding: 12px; font-size: 13px; line-height: 1.6; white-space: pre-wrap;
}
.evidence { margin-bottom: 12px; }
.evidence ul { padding-left: 18px; margin: 0; font-size: 13px; color: var(--text); }
.evidence li { margin-bottom: 4px; }
.summary { font-weight: 600; margin: 0 0 12px; }
.empty { color: var(--faint); margin: 0 0 12px; }
h4 { margin: 0 0 8px; font-size: 12px; color: var(--faint); letter-spacing: 0.04em; text-transform: uppercase; }
</style>
