<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { StageStatus, TimelineNode } from '@/api/tahp/adapt-pipeline'

const props = defineProps<{
  nodes: TimelineNode[]
  activeKey: string | null
  iteration: number
  /** 已完成运行可追加下游阶段时展示末尾入口 */
  showAppend?: boolean
}>()

const emit = defineEmits<{
  select: [key: string]
  append: []
}>()

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
          <span class="ea-step-body">
            <span class="ea-step-name">{{ node.label }}</span>
            <span class="ea-step-dur">{{ formatDuration(node.duration_ms) }}</span>
            <span v-if="node.summary_line" class="ea-step-sum">{{ node.summary_line }}</span>
          </span>
        </button>
        <span
          v-if="index < visibleNodes.length - 1"
          class="ea-step-conn"
          :class="connectorClass(index)"
          aria-hidden="true"
        />
      </template>
      <template v-if="showAppend">
        <span
          v-if="visibleNodes.length > 0"
          class="ea-step-conn conn-pending"
          aria-hidden="true"
        />
        <button
          type="button"
          class="ea-step ea-step-append"
          title="追加烧录 / 自检 / 提交 Gerrit"
          @click="emit('append')"
        >
          <span class="ea-step-ico">+</span>
          <span class="ea-step-body">
            <span class="ea-step-name">追加后续阶段</span>
            <span class="ea-step-sum">烧录 / 自检 / Gerrit</span>
          </span>
        </button>
      </template>
    </div>
    <div v-if="showLoopArc" class="ea-step-loop">
      第 {{ iteration }} 轮回环 → {{ visibleNodes.find(n => n.key === loopTargetKey)?.label ?? '编译' }}
    </div>
  </div>
</template>

<style scoped lang="scss">
.ea-stepper-wrap {
  padding: 0;
}

.ea-stepper {
  display: flex;
  align-items: center;
  gap: 0;
  overflow-x: auto;
  padding: 2px 0 4px;
  scrollbar-width: thin;

  &::-webkit-scrollbar { height: 6px; }
  &::-webkit-scrollbar-thumb {
    background: var(--line-strong);
    border-radius: 999px;
  }
}

.ea-step {
  min-width: 128px;
  flex: 1;
  max-width: 168px;
  border-radius: 12px;
  padding: 8px 10px;
  border: 1px solid transparent;
  cursor: pointer;
  text-align: left;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: box-shadow 0.12s, border-color 0.12s;
  background: var(--surface-2);
  color: var(--faint);
  font-family: inherit;

  &:hover { border-color: var(--line-strong); }
  &.active-sel {
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 28%, transparent);
  }
}

.ea-step-ico {
  width: 24px;
  height: 24px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  background: var(--surface);
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.ea-step-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.ea-step-name {
  display: block;
  font-weight: 700;
  font-size: 12.5px;
  color: inherit;
}

.ea-step-dur {
  display: block;
  font-size: 11px;
  opacity: 0.8;
}

.ea-step-sum {
  display: block;
  font-size: 11px;
  font-weight: 600;
  opacity: 0.85;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ea-step.st-done {
  background: var(--success-soft);
  color: var(--success);
  border-color: color-mix(in srgb, var(--success) 14%, transparent);
}

.ea-step.st-running {
  background: var(--accent-soft);
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 18%, transparent);
  animation: softPulse 1.8s ease-in-out infinite;
}

.ea-step.st-waiting_human {
  background: var(--warn-soft);
  color: var(--warn);
  border-color: color-mix(in srgb, var(--warn) 18%, transparent);
}

.ea-step.st-failed {
  background: var(--error-soft);
  color: var(--error);
  border-color: color-mix(in srgb, var(--error) 16%, transparent);
}

.ea-step.st-skipped {
  background: transparent;
  color: var(--faint);
  border-style: dashed;
  border-color: var(--line-strong);
  max-width: 92px;
  min-width: 92px;
  flex: 0 0 92px;
}

.ea-step.st-pending {
  background: var(--surface-2);
  color: var(--faint);
}

.ea-step.ea-step-append {
  background: color-mix(in srgb, var(--accent) 8%, var(--surface));
  color: var(--accent);
  border: 1px dashed color-mix(in srgb, var(--accent) 40%, transparent);
  max-width: 160px;
  min-width: 132px;
  flex: 0 0 auto;

  .ea-step-ico {
    background: var(--accent);
    color: #fff;
    font-size: 14px;
    font-weight: 500;
  }

  &:hover {
    background: color-mix(in srgb, var(--accent) 12%, var(--surface));
    border-color: var(--accent);
  }
}

.ea-step-conn {
  width: 16px;
  flex-shrink: 0;
  height: 2px;
  margin: 0 2px;
  border-radius: 1px;
  align-self: center;

  &.conn-done { background: var(--success); }
  &.conn-active {
    background: linear-gradient(90deg, var(--success), var(--accent));
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
  color: var(--warn);
  background: var(--warn-soft);
  border-radius: 999px;
  padding: 5px 12px;
}

@keyframes softPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(82, 86, 212, 0.12); }
  50% { box-shadow: 0 0 0 4px rgba(82, 86, 212, 0.04); }
}
</style>
