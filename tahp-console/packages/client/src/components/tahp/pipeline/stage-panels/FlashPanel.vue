<script setup lang="ts">
import type { TimelineNode } from '@/api/tahp/adapt-pipeline'
import EaLogViewer from '@/components/common/EaLogViewer.vue'
import EaPill from '@/components/layout/EaPill.vue'

const props = defineProps<{
  node: TimelineNode
  logs: string[]
}>()

interface FlashProgress {
  state?: string
  progress?: number
  phase?: string
  message?: string
  error?: string
}

function fp(): FlashProgress {
  return (props.node.progress ?? {}) as FlashProgress
}
</script>

<template>
  <div class="panel">
    <h3>{{ node.label }}</h3>

    <div class="device-card">
      <div class="row">
        <span class="k">阶段</span>
        <span class="v">{{ fp().phase ?? '等待' }}</span>
      </div>
      <div v-if="fp().progress != null" class="row">
        <span class="k">进度</span>
        <span class="v">{{ fp().progress }}%</span>
      </div>
      <div v-if="fp().message" class="row">
        <span class="k">消息</span>
        <span class="v">{{ fp().message }}</span>
      </div>
      <div class="row">
        <span class="k">状态</span>
        <EaPill v-if="node.status === 'done'" variant="ok">完成</EaPill>
        <EaPill v-else-if="node.status === 'running'" variant="info">进行中</EaPill>
        <EaPill v-else-if="node.status === 'failed'" variant="err">失败</EaPill>
        <EaPill v-else variant="muted">{{ node.status }}</EaPill>
      </div>
    </div>

    <div v-if="fp().error" class="error-box">{{ fp().error }}</div>

    <h4>日志</h4>
    <EaLogViewer :lines="logs" :height="280" />
  </div>
</template>

<style scoped lang="scss">
.panel h3 { margin: 0 0 8px; font-size: 16px; font-weight: 800; }
.device-card {
  border: 1px solid var(--line); border-radius: 12px; padding: 10px; background: var(--bg); margin-bottom: 12px;
}
.row { display: grid; grid-template-columns: 64px 1fr; gap: 8px; padding: 4px 0; }
.k { color: var(--muted); font-weight: 600; font-size: 12px; }
.v { font-size: 13px; }
.error-box {
  background: var(--error-soft); color: var(--error); border-radius: 12px; padding: 10px; margin-bottom: 12px;
  font-size: 13px; line-height: 1.5;
}
h4 { margin: 0 0 8px; font-size: 12px; color: var(--faint); letter-spacing: 0.04em; text-transform: uppercase; }
</style>
