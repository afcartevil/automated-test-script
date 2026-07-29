<script setup lang="ts">
import type { BuildContext, TimelineNode } from '@/api/tahp/adapt-pipeline'
import EaLogViewer from '@/components/common/EaLogViewer.vue'
import EaPill from '@/components/layout/EaPill.vue'

const props = defineProps<{
  node: TimelineNode
  logs: string[]
  buildContext?: BuildContext
}>()

interface BuildProgress {
  state?: string
  phase?: string
  progress?: number
  message?: string
  error?: string
  result?: { artifactsDir?: string; artifacts?: Array<{ name: string; path: string }> }
}

function bp(): BuildProgress {
  return (props.node.progress ?? {}) as BuildProgress
}

function phaseLabel(phase?: string): string {
  switch (phase) {
    case 'repo': return 'repo sync'
    case 'build': return '编译'
    case 'package': return '打包'
    default: return phase ?? '—'
  }
}
</script>

<template>
  <div class="panel">
    <h3>{{ node.label }}</h3>

    <div class="build-meta">
      <div class="meta-row">
        <span class="k">模式</span>
        <span class="v emph">{{ bp().state === 'success' ? '完成' : (bp().phase ?? '等待') }}</span>
      </div>
      <div v-if="node.summary_line" class="meta-row">
        <span class="k">摘要</span>
        <span class="v">{{ node.summary_line }}</span>
      </div>
    </div>

    <div v-if="buildContext?.components?.length" class="components-box">
      <span class="k">本轮编译组件</span>
      <div class="chips">
        <span v-for="c in buildContext.components" :key="c" class="chip">{{ c }}</span>
      </div>
    </div>

    <div v-if="bp().phase" class="phases">
      <div
        v-for="p in ['repo', 'build', 'package']"
        :key="p"
        class="phase"
        :class="{ running: bp().phase === p && bp().state !== 'success' }"
      >
        <span>{{ phaseLabel(p) }}</span>
        <EaPill v-if="bp().phase === p && bp().state === 'success'" variant="ok">完成</EaPill>
        <EaPill v-else-if="bp().phase === p" variant="info">{{ bp().progress != null ? `${bp().progress}%` : '进行中' }}</EaPill>
        <EaPill v-else variant="muted">等待</EaPill>
      </div>
    </div>

    <div v-if="bp().error" class="error-box">{{ bp().error }}</div>

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
.meta-row { display: grid; grid-template-columns: 64px 1fr; gap: 8px; padding: 4px 0; }
.k { color: var(--muted); font-weight: 600; font-size: 12px; }
.v { font-size: 13px; }
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
.phases { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.phase {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 12px; border-radius: 12px; background: var(--bg); border: 1px solid var(--line);
}
.phase.running { background: var(--accent-soft); border-color: color-mix(in srgb, var(--accent) 18%, transparent); }
.error-box {
  background: var(--error-soft); color: var(--error); border-radius: 12px; padding: 10px; margin-bottom: 12px;
  font-size: 13px; line-height: 1.5;
}
h4 { margin: 0 0 8px; font-size: 12px; color: var(--faint); letter-spacing: 0.04em; text-transform: uppercase; }
</style>
