<script setup lang="ts">
import type { TimelineNode } from '@/api/tahp/adapt-pipeline'
import EaLogViewer from '@/components/common/EaLogViewer.vue'

const props = defineProps<{
  node: TimelineNode
  logs: string[]
}>()

function summaryPairs(node: TimelineNode): Array<{ key: string; value: string }> {
  const pairs: Array<{ key: string; value: string }> = []
  if (node.progress?.percent != null) pairs.push({ key: '进度', value: `${node.progress.percent}%` })
  if (node.progress?.text) pairs.push({ key: '进度描述', value: node.progress.text })
  if (node.summary_line) pairs.push({ key: '摘要', value: node.summary_line })
  if (node.unavailable_reason) pairs.push({ key: '不可用原因', value: node.unavailable_reason })
  if (node.human?.reason) pairs.push({ key: '人工原因', value: node.human.reason })
  return pairs
}
</script>

<template>
  <div class="panel">
    <h3>{{ node.label }}</h3>
    <div v-if="summaryPairs(node).length" class="summary">
      <div v-for="pair in summaryPairs(node)" :key="pair.key" class="row">
        <span class="k">{{ pair.key }}</span>
        <span class="v">{{ pair.value }}</span>
      </div>
    </div>
    <p v-else class="empty">暂无摘要信息</p>

    <h4>日志</h4>
    <EaLogViewer :lines="logs" :height="300" />
  </div>
</template>

<style scoped lang="scss">
.panel h3 {
  margin: 0 0 12px;
  font-size: 16px;
  font-weight: 800;
}
.summary {
  margin-bottom: 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 10px;
  background: var(--bg);
}
.row {
  display: grid;
  grid-template-columns: 84px 1fr;
  gap: 8px;
  padding: 4px 0;
}
.k { color: var(--muted); font-weight: 600; font-size: 12px; }
.v { color: var(--text); font-size: 13px; }
.empty {
  color: var(--faint);
  margin: 0 0 14px;
}
h4 {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--faint);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
</style>
