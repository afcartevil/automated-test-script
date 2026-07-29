<script setup lang="ts">
import type { TimelineNode } from '@/api/tahp/adapt-pipeline'
import EaLogViewer from '@/components/common/EaLogViewer.vue'
const props = defineProps<{
  node: TimelineNode
  logs: string[]
}>()

interface SelfCheckProgress {
  state?: string
  total?: number
  passed?: number
  failed?: number
  running?: number
  failed_cases?: Array<{ name: string; message?: string }>
}

function sp(): SelfCheckProgress {
  return (props.node.progress ?? {}) as SelfCheckProgress
}
</script>

<template>
  <div class="panel">
    <h3>{{ node.label }}</h3>

    <div v-if="sp().total != null" class="stats">
      <div class="stat ok"><strong>{{ sp().passed ?? 0 }}</strong><small>通过</small></div>
      <div class="stat err"><strong>{{ sp().failed ?? 0 }}</strong><small>失败</small></div>
      <div class="stat info"><strong>{{ sp().running ?? 0 }}</strong><small>进行中</small></div>
      <div class="stat muted"><strong>{{ sp().total }}</strong><small>总计</small></div>
    </div>

    <div v-if="node.summary_line" class="summary">{{ node.summary_line }}</div>

    <div v-if="sp().failed_cases?.length" class="fail-list">
      <h4>失败用例</h4>
      <div v-for="c in sp().failed_cases" :key="c.name" class="fail-item">
        <strong>{{ c.name }}</strong>
        <p v-if="c.message">{{ c.message }}</p>
      </div>
    </div>

    <h4>日志</h4>
    <EaLogViewer :lines="logs" :height="240" />
  </div>
</template>

<style scoped lang="scss">
.panel h3 { margin: 0 0 8px; font-size: 16px; font-weight: 800; }
.stats {
  display: flex; gap: 10px; margin-bottom: 12px;
}
.stat {
  flex: 1; text-align: center; padding: 10px 8px; border-radius: 12px;
  strong { display: block; font-size: 20px; }
  small { font-size: 11px; }
}
.stat.ok { background: var(--success-soft); color: var(--success); }
.stat.err { background: var(--error-soft); color: var(--error); }
.stat.info { background: var(--accent-soft); color: var(--accent); }
.stat.muted { background: var(--surface-2); color: var(--muted); }
.summary { margin: 0 0 12px; font-weight: 600; }
.fail-list { margin-bottom: 12px; }
.fail-item {
  padding: 8px 10px; border-radius: 10px; background: var(--error-soft); margin-bottom: 6px;
  strong { font-size: 13px; color: var(--error); }
  p { margin: 4px 0 0; font-size: 12px; color: var(--muted); }
}
h4 { margin: 0 0 8px; font-size: 12px; color: var(--faint); letter-spacing: 0.04em; text-transform: uppercase; }
</style>
