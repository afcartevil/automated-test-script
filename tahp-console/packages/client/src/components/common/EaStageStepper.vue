<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { StageStatus, TimelineNode } from '@/api/tahp/adapt-pipeline'

const props = defineProps<{
  nodes: TimelineNode[]
  activeKey: string | null
  iteration: number
}>()

const emit = defineEmits<{ select: [key: string] }>()

const scrollerRef = ref<HTMLElement | null>(null)

const visibleNodes = computed(() => props.nodes.filter(n => n.enabled))

const showLoopArc = computed(() =>
  props.iteration > 1 && visibleNodes.value.some(n => n.is_loop_target),
)

const loopTargetKey = computed(() =>
  visibleNodes.value.find(n => n.is_loop_target)?.key ?? null,
)

function statusIcon(status: StageStatus): string {
  switch (status) {
    case 'done': return '✓'
    case 'running': return '◐'
    case 'waiting_human': return '⚠'
    case 'failed': return '✗'
    case 'skipped': return '−'
    default: return '○'
  }
}

function formatDuration(ms?: number): string {
  if (ms == null || ms < 0) return '—'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`
  const m = Math.floor(ms / 60_000)
  const s = Math.floor((ms % 60_000) / 1000)
  if (m < 60) return s > 0 ? `${m}m ${s}s` : `${m}m`
  const h = Math.floor(m / 60)
  const rm = m % 60
  return rm > 0 ? `${h}h ${rm}m` : `${h}h`
}

function connectorClass(index: number): string {
  const nodes = visibleNodes.value
  const left = nodes[index]
  const right = nodes[index + 1]
  if (!left || !right) return 'conn-pending'
  if (left.status === 'skipped' || right.status === 'skipped') return 'conn-skipped'
  if (left.status === 'done' && right.status === 'done') return 'conn-done'
  if (left.status === 'done' && right.status === 'running') return 'conn-active'
  return 'conn-pending'
}

function scrollActiveIntoView() {
  if (!props.activeKey || !scrollerRef.value) return
  const el = scrollerRef.value.querySelector(`[data-step-key="${props.activeKey}"]`)
  if (el instanceof HTMLElement) {
    el.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
  }
}

watch(() => props.activeKey, () => {
  nextTick(scrollActiveIntoView)
}, { immediate: true })
</script>

<template>
  <div class="ea-stepper-wrap">
    <div ref="scrollerRef" class="ea-stepper">
      <template v-for="(node, index) in visibleNodes" :key="node.key">
        <button
          type="button"
          class="ea-step"
          :class="[
            `st-${node.status}`,
            { 'active-sel': activeKey === node.key },
          ]"
          :data-step-key="node.key"
          :title="node.unavailable_reason || node.summary_line || node.label"
          @click="emit('select', node.key)"
        >
          <span class="ea-step-ico">{{ statusIcon(node.status) }}</span>
          <span class="ea-step-name">{{ node.label }}</span>
          <span class="ea-step-dur">{{ formatDuration(node.duration_ms) }}</span>
          <span v-if="node.summary_line" class="ea-step-sum">{{ node.summary_line }}</span>
        </button>
        <span
          v-if="index < visibleNodes.length - 1"
          class="ea-step-conn"
          :class="connectorClass(index)"
          aria-hidden="true"
        />
      </template>
    </div>
    <div v-if="showLoopArc" class="ea-step-loop">
      第 {{ iteration }} 轮回环 → {{ visibleNodes.find(n => n.key === loopTargetKey)?.label ?? '编译' }}
    </div>
  </div>
</template>

<style scoped lang="scss">
.ea-stepper-wrap {
  padding: 4px 0 0;
}

.ea-stepper {
  display: flex;
  align-items: stretch;
  gap: 0;
  overflow-x: auto;
  padding: 4px 2px 8px;
  scrollbar-width: thin;

  &::-webkit-scrollbar { height: 6px; }
  &::-webkit-scrollbar-thumb {
    background: var(--line-strong);
    border-radius: 999px;
  }
}

.ea-step {
  min-width: 104px;
  flex: 1;
  max-width: 130px;
  border-radius: 16px;
  padding: 12px 10px;
  border: 1px solid transparent;
  cursor: pointer;
  text-align: left;
  transition: transform 0.12s, box-shadow 0.12s;
  background: #f4f5f8;
  color: var(--faint, #9aa0b0);
  font-family: inherit;

  &:hover { transform: translateY(-1px); }
  &.active-sel {
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 35%, transparent);
  }
}

.ea-step-ico {
  width: 28px;
  height: 28px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  background: rgba(255, 255, 255, 0.72);
  font-size: 13px;
  margin-bottom: 8px;
  font-weight: 700;
}

.ea-step-name {
  display: block;
  font-weight: 800;
  font-size: 13px;
  margin-bottom: 2px;
  color: inherit;
}

.ea-step-dur {
  display: block;
  font-size: 11.5px;
  opacity: 0.85;
}

.ea-step-sum {
  display: block;
  font-size: 11px;
  margin-top: 4px;
  font-weight: 700;
  opacity: 0.9;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ea-step.st-done {
  background: var(--success-soft, #e8f4ee);
  color: var(--success, #0f7a5a);
  border-color: color-mix(in srgb, var(--success) 16%, transparent);
}

.ea-step.st-running {
  background: var(--accent-soft, #eef0fb);
  color: var(--accent, #5256d4);
  border-color: color-mix(in srgb, var(--accent) 22%, transparent);
  animation: softPulse 1.6s ease-in-out infinite;
}

.ea-step.st-waiting_human {
  background: var(--warn-soft, #fbf2e2);
  color: var(--warn, #b45309);
  border-color: color-mix(in srgb, var(--warn) 22%, transparent);
  animation: breathe 1.6s ease-in-out infinite;
}

.ea-step.st-failed {
  background: var(--error-soft, #fbecef);
  color: var(--error, #d33b3b);
  border-color: color-mix(in srgb, var(--error) 18%, transparent);
}

.ea-step.st-skipped {
  background: var(--surface-2, #f1f3f7);
  color: var(--faint, #9aa0b0);
  border-style: dashed;
  border-color: var(--line-strong);
  text-decoration: line-through;
  max-width: 78px;
  min-width: 78px;
  flex: 0 0 78px;
}

.ea-step.st-pending {
  background: #f4f5f8;
  color: var(--faint, #9aa0b0);
}

.ea-step-conn {
  width: 18px;
  flex-shrink: 0;
  align-self: center;
  height: 2px;
  margin: 0 2px;
  border-radius: 1px;

  &.conn-done { background: var(--success, #0f7a5a); }
  &.conn-active {
    background: linear-gradient(90deg, var(--success, #0f7a5a), var(--accent, #5256d4));
  }
  &.conn-pending {
    background: transparent;
    border-top: 1px dashed var(--line-strong);
    height: 0;
  }
  &.conn-skipped {
    border-top: 1px dashed var(--line-strong);
    height: 0;
    background: transparent;
  }
}

.ea-step-loop {
  margin-top: 8px;
  text-align: center;
  font-size: 12px;
  font-weight: 700;
  color: var(--warn, #b45309);
  background: var(--warn-soft, #fbf2e2);
  border-radius: 999px;
  padding: 6px 12px;
}

@keyframes softPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(82, 86, 212, 0.18); }
  50% { box-shadow: 0 0 0 5px rgba(82, 86, 212, 0.04); }
}

@keyframes breathe {
  50% { opacity: 0.78; }
}
</style>
