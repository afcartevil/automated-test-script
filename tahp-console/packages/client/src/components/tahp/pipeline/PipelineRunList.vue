<script setup lang="ts">
import { computed } from 'vue'
import type { RunSummary } from '@/api/tahp/adapt-pipeline'
import EaPill from '@/components/layout/EaPill.vue'

const props = withDefaults(defineProps<{
  items: RunSummary[]
  selectedId: string | null
  loading?: boolean
  busy?: boolean
  collapsed?: boolean
}>(), {
  collapsed: false,
})

const emit = defineEmits<{
  select: [runId: string]
  create: []
  discard: [runId: string]
  clone: [runId: string]
  toggle: []
}>()

const selectedItem = computed(() =>
  props.items.find(item => item.run_id === props.selectedId) ?? null,
)

function statusVariant(status: RunSummary['status']): 'ok' | 'info' | 'warn' | 'err' | 'muted' {
  switch (status) {
    case 'passed': return 'ok'
    case 'running': return 'info'
    case 'waiting_human': return 'warn'
    case 'failed':
    case 'aborted': return 'err'
    default: return 'muted'
  }
}

function statusLabel(status: RunSummary['status']): string {
  switch (status) {
    case 'draft': return '草稿'
    case 'running': return '运行中'
    case 'waiting_human': return '待人工'
    case 'paused': return '已暂停'
    case 'passed': return '已完成'
    case 'failed': return '失败'
    case 'aborted': return '已终止'
    default: return status
  }
}

function fmtRelTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  return new Date(iso).toLocaleString()
}

function canDelete(status: RunSummary['status']): boolean {
  return status !== 'running' && status !== 'waiting_human'
}

function onDiscard(ev: Event, runId: string) {
  ev.stopPropagation()
  if (!window.confirm('确认删除该运行记录？将从列表移除，日志一并删除，不可恢复。')) return
  emit('discard', runId)
}

function onClone(ev: Event, runId: string) {
  ev.stopPropagation()
  emit('clone', runId)
}

function itemTitle(item: RunSummary): string {
  return `${item.project_code} · ${statusLabel(item.status)} · 第 ${item.iteration} 轮`
}
</script>

<template>
  <aside class="pipeline-run-list card" :class="{ collapsed }">
    <div class="list-head">
      <h3 v-if="!collapsed">运行列表</h3>
      <button
        type="button"
        class="collapse-btn"
        :title="collapsed ? '展开运行列表' : '折叠运行列表'"
        :aria-expanded="!collapsed"
        @click="emit('toggle')"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          :class="{ 'is-flipped': collapsed }"
        >
          <polyline points="15 18 9 12 15 6" />
        </svg>
      </button>
    </div>

    <div class="list-scroll">
      <div v-if="loading && !items.length" class="list-empty">{{ collapsed ? '…' : '加载中…' }}</div>
      <div v-else-if="!items.length" class="list-empty">{{ collapsed ? '空' : '还没有运行记录' }}</div>

      <div
        v-for="item in items"
        :key="item.run_id"
        class="run-item"
        :class="{ selected: selectedId === item.run_id, rail: collapsed }"
        role="button"
        tabindex="0"
        :title="itemTitle(item)"
        :aria-current="selectedId === item.run_id ? 'true' : undefined"
        @click="emit('select', item.run_id)"
        @keydown.enter="emit('select', item.run_id)"
      >
        <span class="status-dot" :data-status="item.status" aria-hidden="true" />
        <template v-if="!collapsed">
          <div class="run-main">
            <strong>{{ item.project_code }}</strong>
            <span class="run-meta">第 {{ item.iteration }} 轮 · {{ fmtRelTime(item.updated_at) }}</span>
          </div>
          <div class="run-side">
            <EaPill :variant="statusVariant(item.status)">{{ statusLabel(item.status) }}</EaPill>
            <div class="run-actions">
              <button
                type="button"
                class="btn-clone"
                title="复制配置到新建运行"
                :disabled="busy"
                @click="onClone($event, item.run_id)"
              >
                复制
              </button>
              <button
                v-if="canDelete(item.status)"
                type="button"
                class="btn-discard"
                title="删除运行记录"
                :disabled="busy"
                @click="onDiscard($event, item.run_id)"
              >
                删除
              </button>
            </div>
          </div>
        </template>
      </div>
    </div>

    <p v-if="collapsed && selectedItem" class="selected-hint" :title="itemTitle(selectedItem)">
      {{ selectedItem.project_code }}
    </p>

    <button
      type="button"
      class="btn-new"
      :title="collapsed ? '新建运行' : undefined"
      @click="emit('create')"
    >
      {{ collapsed ? '+' : '+ 新建运行' }}
    </button>
  </aside>
</template>

<style scoped lang="scss">
.pipeline-run-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px;
  min-height: 0;
  height: 100%;
  overflow: hidden;

  &.collapsed {
    padding: 10px 8px;
    align-items: center;
  }
}

.card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 20px;
  box-shadow: var(--shadow);
}

.list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-shrink: 0;
  width: 100%;

  .collapsed & {
    justify-content: center;
  }
}

h3 {
  margin: 0;
  font-size: 12px;
  font-weight: 800;
  color: var(--faint);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.collapse-btn {
  width: 32px;
  height: 32px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--bg);
  color: var(--muted);
  cursor: pointer;
  display: grid;
  place-items: center;
  flex-shrink: 0;

  &:hover {
    border-color: var(--accent);
    color: var(--accent);
  }

  svg {
    transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  }

  svg.is-flipped {
    transform: rotate(180deg);
  }
}

.list-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-right: 2px;
  width: 100%;

  .collapsed & {
    align-items: center;
    gap: 6px;
    padding-right: 0;
  }
}

.list-empty {
  padding: 24px 8px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;

  .collapsed & {
    padding: 8px 0;
    font-size: 11px;
  }
}

.run-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid transparent;
  cursor: pointer;
  background: var(--bg);
  text-align: left;
  width: 100%;
  color: inherit;
  font-family: inherit;

  &:hover { border-color: var(--line-strong); }
  &.selected {
    background: var(--accent-soft);
    border-color: color-mix(in srgb, var(--accent) 28%, transparent);
  }

  &.rail {
    width: 36px;
    height: 36px;
    padding: 0;
    justify-content: center;
    border-radius: 12px;
  }
}

.status-dot {
  display: none;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--faint);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--faint) 25%, transparent);

  &[data-status='passed'] {
    background: var(--ok, #2f9e6b);
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--ok, #2f9e6b) 28%, transparent);
  }
  &[data-status='running'] {
    background: var(--accent);
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 28%, transparent);
  }
  &[data-status='waiting_human'] {
    background: var(--warn);
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--warn) 28%, transparent);
  }
  &[data-status='failed'],
  &[data-status='aborted'] {
    background: var(--err, #c0392b);
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--err, #c0392b) 28%, transparent);
  }

  .rail & {
    display: block;
  }
}

.run-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;

  strong {
    font-size: 13px;
    font-weight: 700;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.run-meta {
  font-size: 11.5px;
  color: var(--muted);
}

.run-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  flex-shrink: 0;
}

.run-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-clone,
.btn-discard {
  border: none;
  background: transparent;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  padding: 0 2px;
  font-family: inherit;

  &:hover:not(:disabled) { text-decoration: underline; }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

.btn-clone {
  color: var(--accent);
}

.btn-discard {
  color: var(--err, #c0392b);
}

.selected-hint {
  margin: 0;
  max-width: 100%;
  font-size: 10px;
  font-weight: 700;
  color: var(--accent);
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.btn-new {
  margin-top: auto;
  flex-shrink: 0;
  border: 1px dashed var(--line-strong);
  background: transparent;
  padding: 12px;
  border-radius: 14px;
  color: var(--muted);
  font-weight: 700;
  cursor: pointer;
  font-family: inherit;
  width: 100%;

  .collapsed & {
    width: 36px;
    height: 36px;
    padding: 0;
    border-radius: 12px;
    font-size: 18px;
    line-height: 1;
  }

  &:hover {
    border-color: var(--accent);
    color: var(--accent);
    background: var(--accent-soft);
  }
}

@media (max-width: 960px) {
  .pipeline-run-list {
    height: auto;
    max-height: min(42vh, 360px);
  }
}
</style>
