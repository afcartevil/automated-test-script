<script setup lang="ts">
import type { TimelineNode } from '@/api/tahp/adapt-pipeline'
import EaLogViewer from '@/components/common/EaLogViewer.vue'
import EaPill from '@/components/layout/EaPill.vue'

const props = defineProps<{
  node: TimelineNode
  logs: string[]
}>()

function fp() {
  return (props.node.progress ?? {}) as Record<string, unknown>
}
</script>

<template>
  <div class="panel">
    <h3>{{ node.label }}</h3>

    <div class="device-card">
      <div class="row">
        <span class="k">状态</span>
        <EaPill v-if="node.status === 'done'" variant="ok">完成</EaPill>
        <EaPill v-else-if="node.status === 'running'" variant="info">进行中</EaPill>
        <EaPill v-else-if="node.status === 'failed'" variant="err">失败</EaPill>
        <EaPill v-else-if="node.status === 'waiting_human'" variant="warn">待人工</EaPill>
        <EaPill v-else variant="muted">{{ node.status }}</EaPill>
      </div>
      <div class="row">
        <span class="k">阶段</span>
        <span class="v">{{ fp().phase || fp().state || '等待' }}</span>
      </div>
      <div v-if="fp().percent != null" class="row">
        <span class="k">进度</span>
        <span class="v">{{ fp().percent }}%</span>
      </div>
      <div v-if="fp().via" class="row">
        <span class="k">通道</span>
        <span class="v">{{ fp().via }}</span>
      </div>
      <div v-if="fp().img_path" class="row">
        <span class="k">单镜像</span>
        <span class="v mono">{{ fp().img_path }}{{ fp().partition ? ` → ${fp().partition}` : '' }}</span>
      </div>
      <div v-if="fp().pkg_path || fp().pkgPath" class="row">
        <span class="k">刷机包</span>
        <span class="v mono">{{ fp().pkg_path || fp().pkgPath }}</span>
      </div>
      <div v-if="fp().artifacts_dir" class="row">
        <span class="k">产物目录</span>
        <span class="v mono">{{ fp().artifacts_dir }}</span>
      </div>
      <div v-if="fp().message || fp().text" class="row">
        <span class="k">消息</span>
        <span class="v">{{ fp().message || fp().text }}</span>
      </div>
    </div>

    <div v-if="fp().error || node.error" class="error-box">{{ fp().error || node.error }}</div>

    <h4>日志</h4>
    <EaLogViewer :lines="logs" :height="280" />
  </div>
</template>

<style scoped lang="scss">
.panel h3 { margin: 0 0 8px; font-size: 16px; font-weight: 800; }
.device-card {
  border: 1px solid var(--line); border-radius: 12px; padding: 10px; background: var(--bg); margin-bottom: 12px;
}
.row { display: grid; grid-template-columns: 72px 1fr; gap: 8px; padding: 4px 0; align-items: start; }
.k { color: var(--muted); font-weight: 600; font-size: 12px; }
.v { font-size: 13px; word-break: break-all; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
.error-box {
  background: var(--error-soft); color: var(--error); border-radius: 12px; padding: 10px; margin-bottom: 12px;
  font-size: 13px; line-height: 1.5;
}
h4 { margin: 0 0 8px; font-size: 12px; color: var(--faint); letter-spacing: 0.04em; text-transform: uppercase; }
</style>
