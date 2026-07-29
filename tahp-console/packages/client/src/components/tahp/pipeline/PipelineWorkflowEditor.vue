<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import EaCard from '@/components/layout/EaCard.vue'
import EaPill from '@/components/layout/EaPill.vue'
import type { OnUnavailablePolicy } from '@/api/tahp/adapt-pipeline'
import type { useAdaptPipelineStore } from '@/stores/tahp/adapt-pipeline'

const props = defineProps<{
  store: ReturnType<typeof useAdaptPipelineStore>
}>()

const message = useMessage()

const workflow = computed(() => props.store.workflowDraft)
const nodeViews = computed(() => props.store.workflowNodes)

const onUnavailableOptions: Array<{ value: OnUnavailablePolicy; label: string }> = [
  { value: 'fail', label: '失败' },
  { value: 'manual_gate', label: '转人工' },
  { value: 'skip', label: '跳过' },
]

function nodeLabel(key: string): string {
  return nodeViews.value.find(n => n.key === key)?.label ?? key
}

function availabilityVariant(key: string): 'ok' | 'warn' | 'muted' {
  const cap = props.store.capabilityForNode(key)
  if (!cap) return 'muted'
  return cap.availability.available ? 'ok' : 'warn'
}

function availabilityText(key: string): string {
  const cap = props.store.capabilityForNode(key)
  if (!cap) return '—'
  return cap.availability.available ? '可用' : (cap.availability.reason ?? '未接入')
}

async function handleSave() {
  const ok = await props.store.saveWorkflowDraft()
  if (ok) message.success('流程已保存')
}

function handleRestore() {
  props.store.restoreDefaultWorkflow()
  message.info('已恢复默认配置（尚未保存）')
}

onMounted(() => {
  void props.store.loadWorkflowEditor()
})
</script>

<template>
  <EaCard class="workflow-editor card">
    <div class="head">
      <div class="title-block">
        <h2>{{ workflow?.label ?? '标准适配流水线' }}</h2>
        <span class="version">v{{ workflow?.version ?? 1 }}</span>
      </div>
      <div class="actions">
        <button type="button" class="btn-soft" :disabled="store.workflowSaving" @click="handleRestore">
          恢复默认
        </button>
        <button
          type="button"
          class="ea-btn-primary"
          :disabled="store.workflowSaving || !workflow"
          @click="handleSave"
        >
          {{ store.workflowSaving ? '保存中…' : '保存' }}
        </button>
      </div>
    </div>

    <div v-if="store.workflowLoading" class="loading">加载流程配置…</div>
    <div v-else-if="workflow" class="node-list">
      <div
        v-for="(node, index) in workflow.nodes"
        :key="node.key"
        class="node-row"
      >
        <label class="enable">
          <input
            type="checkbox"
            :checked="node.enabled"
            @change="store.setWorkflowNodeEnabled(node.key, ($event.target as HTMLInputElement).checked)"
          >
          <span class="idx">{{ index + 1 }}</span>
        </label>

        <div class="node-main">
          <strong>{{ nodeLabel(node.key) }}</strong>
          <span class="key">{{ node.key }}</span>
        </div>

        <div class="policy">
          <template v-if="node.key === 'human_review'">
            <span class="muted">—</span>
          </template>
          <template v-else>
            <span class="policy-label">不可用时</span>
            <select
              :value="node.onUnavailable ?? 'fail'"
              @change="store.setWorkflowNodeOnUnavailable(node.key, ($event.target as HTMLSelectElement).value as OnUnavailablePolicy)"
            >
              <option v-for="opt in onUnavailableOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </template>
        </div>

        <div class="capability">
          <EaPill :variant="availabilityVariant(node.key)">
            {{ availabilityText(node.key) }}
          </EaPill>
        </div>
      </div>

      <div class="iterations">
        <label>
          最大迭代轮次
          <input
            type="number"
            min="1"
            max="99"
            :value="workflow.maxIterations"
            @change="store.setMaxIterations(Number(($event.target as HTMLInputElement).value))"
          >
        </label>
      </div>
    </div>
  </EaCard>
</template>

<style scoped lang="scss">
.workflow-editor {
  padding: 20px 22px;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.title-block {
  display: flex;
  align-items: baseline;
  gap: 10px;

  h2 {
    margin: 0;
    font-size: 18px;
  }
}

.version {
  color: var(--muted);
  font-size: 13px;
}

.actions {
  display: flex;
  gap: 8px;
}

.loading {
  color: var(--muted);
  padding: 24px 0;
}

.node-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.node-row {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr) 180px 140px;
  gap: 12px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: color-mix(in srgb, var(--surface) 92%, var(--bg));
}

.enable {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;

  .idx {
    color: var(--muted);
    font-size: 12px;
    font-weight: 700;
  }
}

.node-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;

  strong { font-size: 14px; }
  .key {
    font-size: 12px;
    color: var(--faint);
    font-family: var(--mono, monospace);
  }
}

.policy {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;

  select {
    flex: 1;
    min-width: 0;
    padding: 6px 8px;
    border-radius: 8px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: inherit;
  }
}

.policy-label, .muted {
  color: var(--muted);
  white-space: nowrap;
}

.capability {
  justify-self: end;
}

.iterations {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--line);

  label {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    font-size: 14px;
    color: var(--muted);
  }

  input {
    width: 72px;
    padding: 6px 8px;
    border-radius: 8px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: inherit;
  }
}

.btn-soft {
  padding: 8px 14px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: var(--surface);
  cursor: pointer;
  font-size: 13px;

  &:disabled { opacity: 0.6; cursor: not-allowed; }
}

@media (max-width: 900px) {
  .node-row {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .capability { justify-self: start; }
}
</style>
