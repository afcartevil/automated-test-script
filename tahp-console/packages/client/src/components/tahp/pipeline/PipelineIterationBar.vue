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
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 10px;
  background: var(--bg);
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
  padding: 4px 8px;
  border-radius: 999px;
  background: var(--surface-2);
  color: var(--muted);
  font-size: 12px;
}
.dot.running { background: var(--accent-soft); color: var(--accent); }
.dot.passed { background: var(--success-soft); color: var(--success); }
.dot.failed { background: var(--error-soft); color: var(--error); }
.dot.current { font-weight: 800; }
</style>
