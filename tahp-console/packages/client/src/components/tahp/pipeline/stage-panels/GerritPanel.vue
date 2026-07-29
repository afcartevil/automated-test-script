<script setup lang="ts">
import type { TimelineNode } from '@/api/tahp/adapt-pipeline'
import EaLogViewer from '@/components/common/EaLogViewer.vue'
import EaPill from '@/components/layout/EaPill.vue'

const props = defineProps<{
  node: TimelineNode
  logs: string[]
}>()

interface GerritChange {
  domain_id: string
  repo?: string
  change_url?: string
  change_number?: string
  status: string
  files?: string[]
  error?: string
}

function getChanges(): GerritChange[] {
  const progress = props.node.progress as Record<string, unknown> | undefined
  const raw = progress?.changes
  if (!Array.isArray(raw)) return []
  return raw as GerritChange[]
}

function crVariant(status: string): 'ok' | 'info' | 'warn' | 'err' | 'muted' {
  switch (status) {
    case 'submitted': return 'ok'
    case 'pending': return 'info'
    case 'blocked_conflict': return 'err'
    case 'failed': return 'err'
    default: return 'muted'
  }
}

function crLabel(status: string): string {
  switch (status) {
    case 'submitted': return '已提交'
    case 'pending': return '待提交'
    case 'blocked_conflict': return '冲突'
    case 'failed': return '失败'
    default: return status
  }
}
</script>

<template>
  <div class="panel">
    <h3>{{ node.label }}</h3>
    <p v-if="node.summary_line" class="summary">{{ node.summary_line }}</p>

    <table v-if="getChanges().length" class="cr-table">
      <thead>
        <tr>
          <th>域</th>
          <th>仓</th>
          <th>文件数</th>
          <th>状态</th>
          <th>CR</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in getChanges()" :key="c.domain_id" :class="{ conflict: c.status === 'blocked_conflict' }">
          <td class="td-name">{{ c.domain_id }}</td>
          <td>{{ c.repo ?? '—' }}</td>
          <td>{{ c.files?.length ?? '—' }}</td>
          <td><EaPill :variant="crVariant(c.status)">{{ crLabel(c.status) }}</EaPill></td>
          <td>
            <a v-if="c.change_url" :href="c.change_url" target="_blank" rel="noopener noreferrer" class="cr-link">
              {{ c.change_number ?? 'Gerrit' }}
            </a>
            <span v-else>—</span>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="empty">暂无 CR 信息</p>

    <h4>日志</h4>
    <EaLogViewer :lines="logs" :height="240" />
  </div>
</template>

<style scoped lang="scss">
.panel h3 { margin: 0 0 8px; font-size: 16px; font-weight: 800; }
.summary { margin: 0 0 12px; font-weight: 600; }
.cr-table {
  width: 100%; border-collapse: collapse; margin-bottom: 14px; font-size: 13px;
  th { text-align: left; font-size: 11px; color: var(--faint); font-weight: 700; padding: 4px 6px; border-bottom: 1px solid var(--line); }
  td { padding: 8px 6px; border-bottom: 1px solid var(--line); }
  .td-name { font-weight: 700; }
  tr.conflict { background: var(--error-soft); }
}
.cr-link { color: var(--accent); text-decoration: none; font-weight: 600; &:hover { text-decoration: underline; } }
.empty { color: var(--faint); margin: 0 0 14px; }
h4 { margin: 0 0 8px; font-size: 12px; color: var(--faint); letter-spacing: 0.04em; text-transform: uppercase; }
</style>
