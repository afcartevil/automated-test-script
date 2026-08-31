<script setup lang="ts">
import type { BuildContext, TimelineNode } from '@/api/tahp/adapt-pipeline'
import EaLogViewer from '@/components/common/EaLogViewer.vue'

const props = defineProps<{
  node: TimelineNode
  logs: string[]
  buildContext?: BuildContext
}>()

function bp() {
  return (props.node.progress ?? {}) as Record<string, unknown>
}

function result(): Record<string, unknown> {
  return (bp().result ?? {}) as Record<string, unknown>
}

function phaseLabel(phase?: unknown): string {
  switch (String(phase ?? '')) {
    case 'init': return '初始化'
    case 'deploy': return '部署脚本'
    case 'build': return '编译'
    case 'done': return '完成'
    case 'agent': return '启动 Agent'
    case 'tool': return '执行工具'
    default: return String(phase || '—')
  }
}

function stateLabel(state?: unknown): string {
  switch (String(state ?? '')) {
    case 'success': return '成功'
    case 'failed': return '失败'
    case 'running': return '进行中'
    case 'pending': return '排队'
    case 'cancelled': return '已取消'
    default: return String(state || props.node.status)
  }
}

function targetsLine(): string {
  const bc = props.buildContext
  if (!bc) return ''
  const targets = [...(bc.build_targets ?? [])]
  if (bc.need_pack && !targets.includes('pack')) targets.push('pack')
  return targets.join(',') || (bc.components?.join(',') ?? '')
}
</script>

<template>
  <div class="panel">
    <h3>{{ node.label }}</h3>

    <div class="build-meta">
      <div class="meta-row">
        <span class="k">状态</span>
        <span class="v emph">{{ stateLabel(bp().state) }}</span>
      </div>
      <div class="meta-row">
        <span class="k">阶段</span>
        <span class="v">{{ phaseLabel(bp().phase) }}{{ bp().percent != null ? ` · ${bp().percent}%` : '' }}</span>
      </div>
      <div v-if="bp().message || bp().text" class="meta-row">
        <span class="k">消息</span>
        <span class="v">{{ bp().message || bp().text }}</span>
      </div>
      <div v-if="buildContext?.project" class="meta-row">
        <span class="k">project</span>
        <span class="v">{{ buildContext.project }} · {{ buildContext.variant }} / {{ buildContext.build_flag || '—' }}</span>
      </div>
      <div v-if="buildContext?.system_path" class="meta-row">
        <span class="k">system</span>
        <span class="v mono">{{ buildContext.system_path }}</span>
      </div>
      <div v-if="buildContext?.vendor_path" class="meta-row">
        <span class="k">vendor</span>
        <span class="v mono">{{ buildContext.vendor_path }}</span>
      </div>
      <div v-if="buildContext?.trsys_root_path" class="meta-row">
        <span class="k">trsys</span>
        <span class="v mono">{{ buildContext.trsys_root_path }}</span>
      </div>
      <div v-else-if="buildContext?.trsys_branch" class="meta-row">
        <span class="k">trsys 分支</span>
        <span class="v mono">{{ buildContext.trsys_branch }}</span>
      </div>
      <div v-if="buildContext?.sys_version" class="meta-row">
        <span class="k">sys_ver</span>
        <span class="v">{{ buildContext.sys_version }}</span>
      </div>
      <div v-if="targetsLine()" class="meta-row">
        <span class="k">targets</span>
        <span class="v">{{ targetsLine() }}</span>
      </div>
      <div v-if="node.summary_line" class="meta-row">
        <span class="k">摘要</span>
        <span class="v">{{ node.summary_line }}</span>
      </div>
      <div v-if="result().artifacts_dir || result().artifactsDir" class="meta-row">
        <span class="k">产物目录</span>
        <span class="v mono">{{ result().artifacts_dir || result().artifactsDir }}</span>
      </div>
      <div v-if="result().pkg_path || result().pkgPath" class="meta-row">
        <span class="k">刷机包</span>
        <span class="v mono">{{ result().pkg_path || result().pkgPath }}</span>
      </div>
    </div>

    <div v-if="bp().error || node.error" class="error-box">{{ bp().error || node.error }}</div>

    <h4>日志</h4>
    <EaLogViewer :lines="logs" :height="280" />
  </div>
</template>

<style scoped lang="scss">
.panel h3 { margin: 0 0 8px; font-size: 16px; font-weight: 800; }
.build-meta {
  margin-bottom: 12px;
  border: 1px solid var(--line); border-radius: 12px; padding: 10px; background: var(--bg);
}
.meta-row { display: grid; grid-template-columns: 72px 1fr; gap: 8px; padding: 4px 0; }
.k { color: var(--muted); font-weight: 600; font-size: 12px; }
.v { font-size: 13px; word-break: break-all; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
.emph {
  display: inline-block; background: var(--warn-soft); color: var(--warn);
  border-radius: 8px; padding: 2px 8px; font-weight: 700; font-size: 12.5px;
}
.error-box {
  background: var(--error-soft); color: var(--error); border-radius: 12px; padding: 10px; margin-bottom: 12px;
  font-size: 13px; line-height: 1.5;
}
h4 { margin: 0 0 8px; font-size: 12px; color: var(--faint); letter-spacing: 0.04em; text-transform: uppercase; }
</style>
