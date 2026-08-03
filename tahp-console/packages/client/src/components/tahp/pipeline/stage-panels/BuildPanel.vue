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
    case 'agent': return '启动 Agent'
    case 'tool': return '执行工具'
    case 'repo': return 'repo sync'
    case 'build': return '编译'
    case 'package': return '打包'
    case 'done': return '完成'
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
      <div v-if="buildContext?.build_skill_id || buildContext?.build_kind" class="meta-row">
        <span class="k">Skill</span>
        <span class="v">{{ buildContext?.build_skill_id || '—' }}（{{ buildContext?.build_kind === 'native_module' ? '模块' : '整机' }}）</span>
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

    <div v-if="buildContext?.components?.length && buildContext.build_kind !== 'native_module'" class="components-box">
      <span class="k">本轮编译组件</span>
      <div class="chips">
        <span v-for="c in buildContext.components" :key="c" class="chip">{{ c }}</span>
      </div>
    </div>
    <div v-else-if="buildContext?.native_target" class="components-box">
      <span class="k">Native 目标</span>
      <div class="chips">
        <span class="chip">{{ buildContext.native_component || 'sys' }}</span>
        <span class="chip">{{ buildContext.native_target }}</span>
        <span v-if="buildContext.lunch" class="chip">{{ buildContext.lunch }}</span>
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
.components-box {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid var(--line);
  background: var(--bg);
  .k { display: block; margin-bottom: 8px; color: var(--muted); font-weight: 700; font-size: 12px; }
}
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
}
.error-box {
  background: var(--error-soft); color: var(--error); border-radius: 12px; padding: 10px; margin-bottom: 12px;
  font-size: 13px; line-height: 1.5;
}
h4 { margin: 0 0 8px; font-size: 12px; color: var(--faint); letter-spacing: 0.04em; text-transform: uppercase; }
</style>
