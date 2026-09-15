<script setup lang="ts">
import type { IterationRecord } from '@/api/tahp/adapt-pipeline'

defineProps<{
  iterations: IterationRecord[]
  current: number
  maxIterations: number
}>()
</script>

<template>
  <div v-if="iterations.length > 1" class="iter-bar">
    <div class="title">迭代收敛（上限 {{ maxIterations }} 轮）</div>
    <div class="dots">
      <div
        v-for="it in iterations"
        :key="it.index"
        class="dot"
        :class="{
          running: it.verdict === 'running',
          passed: it.verdict === 'passed',
          failed: it.verdict === 'failed',
          current: current === it.index,
        }"
      >
        第{{ it.index }}轮
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.iter-bar {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--line);
}
.title {
  margin-bottom: 8px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}
.dots {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.dot {
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--surface);
  color: var(--muted);
  font-size: 12px;
  border: 1px solid var(--line);
}
.dot.running { background: var(--accent-soft); color: var(--accent); border-color: color-mix(in srgb, var(--accent) 25%, var(--line)); }
.dot.passed { background: var(--success-soft); color: var(--success); border-color: color-mix(in srgb, var(--success) 25%, var(--line)); }
.dot.failed { background: var(--error-soft); color: var(--error); border-color: color-mix(in srgb, var(--error) 25%, var(--line)); }
.dot.current {
  font-weight: 800;
  border-color: var(--accent);
}
</style>
