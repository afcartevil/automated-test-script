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

interface RepoGroup {
  repo: string
  repo_label: string
  files: string[]
  domain_ids: string[]
}

function gp() {
  return (props.node.progress ?? {}) as Record<string, unknown>
}

function getChanges(): GerritChange[] {
  const raw = gp().changes
  if (!Array.isArray(raw)) return []
  return raw as GerritChange[]
}

function getRepos(): RepoGroup[] {
  const raw = gp().repos
  if (!Array.isArray(raw)) return []
  return raw as RepoGroup[]
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

function stateLabel(state?: unknown): string {
  switch (String(state ?? '')) {
    case 'awaiting_repo_selection': return '选择入库仓库'
    case 'awaiting_confirm_no_changes': return '未检测到变更'
    case 'submitting': return '提交中'
    case 'done': return '完成'
    case 'blocked_conflict': return '跨域冲突'
    case 'no_changes': return '无变更'
    case 'submit_failed': return '提交失败'
    default: return String(state || props.node.status)
  }
}
</script>

<template>
  <div class="panel">
    <h3>{{ node.label }}</h3>
    <p v-if="node.summary_line || gp().text" class="summary">{{ node.summary_line || gp().text }}</p>

    <div class="meta">
      <div class="row">
        <span class="k">状态</span>
        <span class="v">{{ stateLabel(gp().state) }}</span>
      </div>
      <div v-if="gp().queue" class="row">
        <span class="k">进度</span>
        <span class="v">
          {{ Number(gp().current_index ?? 0) }} / {{ (gp().queue as string[]).length }}
          <template v-if="gp().current_domain_id"> · 当前 {{ gp().current_domain_id }}</template>
        </span>
      </div>
      <div v-if="gp().percent != null" class="row">
        <span class="k">百分比</span>
        <span class="v">{{ gp().percent }}%</span>
      </div>
    </div>

    <div v-if="getRepos().length && String(gp().state) === 'awaiting_repo_selection'" class="repos">
      <h4>待选仓库</h4>
      <ul>
        <li v-for="r in getRepos()" :key="r.repo">
          <strong class="repo-label">{{ r.repo_label }}</strong>
          <span class="repo-path" :title="r.repo">{{ r.repo }}</span>
          <span>{{ r.files.length }} 文件 · {{ r.domain_ids.join(', ') }}</span>
        </li>
      </ul>
    </div>

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
            <span v-else-if="c.error" class="err" :title="c.error">失败</span>
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
.meta {
  border: 1px solid var(--line); border-radius: 12px; padding: 10px; background: var(--bg); margin-bottom: 12px;
}
.row { display: grid; grid-template-columns: 64px 1fr; gap: 8px; padding: 4px 0; }
.k { color: var(--muted); font-weight: 600; font-size: 12px; }
.v { font-size: 13px; }
.repos {
  margin-bottom: 12px;
  min-width: 0;
  ul { margin: 0; padding-left: 18px; }
  li {
    margin: 6px 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    .repo-label {
      overflow-wrap: anywhere;
      word-break: break-word;
    }
    .repo-path {
      font-size: 11.5px;
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      overflow-wrap: anywhere;
      word-break: break-all;
      line-height: 1.35;
    }
    span { color: var(--muted); font-size: 12px; }
  }
}
.cr-table {
  width: 100%; border-collapse: collapse; margin-bottom: 14px; font-size: 13px;
  th { text-align: left; font-size: 11px; color: var(--faint); font-weight: 700; padding: 4px 6px; border-bottom: 1px solid var(--line); }
  td { padding: 8px 6px; border-bottom: 1px solid var(--line); }
  .td-name { font-weight: 700; }
  tr.conflict { background: var(--error-soft); }
}
.cr-link { color: var(--accent); text-decoration: none; font-weight: 600; &:hover { text-decoration: underline; } }
.err { color: var(--err); }
.empty { color: var(--faint); margin: 0 0 14px; }
h4 { margin: 0 0 8px; font-size: 12px; color: var(--faint); letter-spacing: 0.04em; text-transform: uppercase; }
</style>
