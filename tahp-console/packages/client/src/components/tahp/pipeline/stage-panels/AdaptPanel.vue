<script setup lang="ts">
import type { AdaptDomainProgress, TimelineNode } from '@/api/tahp/adapt-pipeline'
import EaLogViewer from '@/components/common/EaLogViewer.vue'
import EaPill from '@/components/layout/EaPill.vue'

const props = defineProps<{
  node: TimelineNode
  logs: string[]
}>()

function getDomains(): AdaptDomainProgress[] {
  return props.node.progress?.domains ?? []
}

function domainVariant(status: string): 'ok' | 'info' | 'warn' | 'err' | 'muted' {
  switch (status) {
    case 'done': return 'ok'
    case 'running': return 'info'
    case 'failed': return 'err'
    default: return 'muted'
  }
}

function domainLabel(status: string): string {
  switch (status) {
    case 'done': return '完成'
    case 'running': return '进行中'
    case 'failed': return '失败'
    case 'pending': return '等待'
    case 'skipped': return '跳过'
    default: return status
  }
}

function errorPreview(error?: string): string {
  if (!error) return '—'
  const line = error.split('\n').find(l => l.trim()) ?? error
  return line.length > 120 ? `${line.slice(0, 120)}…` : line
}
</script>

<template>
  <div class="panel">
    <h3>{{ node.label }}</h3>
    <p v-if="node.summary_line" class="summary-line">{{ node.summary_line }}</p>

    <div v-if="node.error" class="stage-error">
      <strong>阶段失败</strong>
      <pre>{{ node.error }}</pre>
    </div>

    <table v-if="getDomains().length" class="domain-table">
      <thead>
        <tr>
          <th>域</th>
          <th>状态</th>
          <th>变更文件</th>
          <th>Skill</th>
          <th>错误</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="d in getDomains()" :key="d.domain_id" :class="{ failed: d.status === 'failed' }">
          <td class="td-name">{{ d.domain_label || d.domain_id }}</td>
          <td>
            <EaPill :variant="domainVariant(d.status)">{{ domainLabel(d.status) }}</EaPill>
            <span v-if="d.retry_count" class="retry-hint">
              重试 {{ d.retry_count }}/{{ d.retry_max ?? 3 }}
            </span>
          </td>
          <td>{{ d.changed_files?.length ?? '—' }}</td>
          <td class="td-skill">{{ d.related_skills?.join(', ') || '—' }}</td>
          <td class="td-error" :title="d.error">{{ errorPreview(d.error) }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="empty">暂无域信息</p>

    <h4>日志</h4>
    <EaLogViewer :lines="logs" :height="420" />
  </div>
</template>

<style scoped lang="scss">
.panel h3 { margin: 0 0 8px; font-size: 16px; font-weight: 800; }
.summary-line { margin: 0 0 12px; font-weight: 600; color: var(--text); }
.stage-error {
  margin: 0 0 14px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--err) 35%, var(--line));
  background: color-mix(in srgb, var(--err) 8%, var(--bg));
  strong { display: block; margin-bottom: 6px; color: var(--err); font-size: 12px; }
  pre {
    margin: 0;
    white-space: pre-wrap;
    word-break: break-word;
    font: inherit;
    font-size: 12px;
    color: var(--text);
  }
}
.domain-table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 14px;
  font-size: 13px;
  th { text-align: left; font-size: 11px; color: var(--faint); font-weight: 700; padding: 4px 6px; border-bottom: 1px solid var(--line); }
  td { padding: 8px 6px; border-bottom: 1px solid var(--line); vertical-align: top; }
  tr.failed { background: color-mix(in srgb, var(--err) 6%, transparent); }
  .td-name { font-weight: 700; }
  .td-skill { color: var(--muted); font-size: 12px; }
  .td-error { color: var(--err); font-size: 12px; max-width: 220px; }
}
.retry-hint {
  display: inline-block;
  margin-left: 6px;
  font-size: 11px;
  color: var(--muted);
}
.empty { color: var(--faint); margin: 0 0 14px; }
h4 { margin: 0 0 8px; font-size: 12px; color: var(--faint); letter-spacing: 0.04em; text-transform: uppercase; }
</style>
