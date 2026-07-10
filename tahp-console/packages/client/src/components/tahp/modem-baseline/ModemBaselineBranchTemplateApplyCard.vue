<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NEmpty, NRadioButton, NRadioGroup, NSelect, NTag } from 'naive-ui'
import type { BranchTemplate, NoticeParseResult } from '@/api/tahp/modem-baseline'

const props = defineProps<{
  templates: BranchTemplate[]
  selectedTos?: string
  selectedTemplateId?: string
  selectedTarget: 'trunk' | 'mp'
  loading?: boolean
  parsed?: NoticeParseResult | null
}>()

const emit = defineEmits<{
  'update:selectedTos': [value: string]
  'update:selectedTemplateId': [value: string]
  'update:selectedTarget': [value: 'trunk' | 'mp']
  apply: []
}>()

const tosOptions = computed(() => {
  const items = Array.from(new Set(props.templates.map(item => item.tos)))
  return items.map(item => ({ label: item, value: item }))
})

const suggestedTos = computed(() => {
  const parsed = props.parsed?.tosVersion
  if (parsed && tosOptions.value.some(item => item.value === parsed)) return parsed
  return tosOptions.value[0]?.value || ''
})

const currentTos = computed(() => props.selectedTos || suggestedTos.value)

const filteredTemplates = computed(() => props.templates.filter(item => item.tos === currentTos.value))

const templateOptions = computed(() => filteredTemplates.value.map(item => ({
  label: item.platform,
  value: item.templateId,
})))

const selectedTemplate = computed(() => (
  filteredTemplates.value.find(item => item.templateId === props.selectedTemplateId)
  ?? filteredTemplates.value[0]
  ?? null
))

const previewNodeBranch = computed(() => {
  if (!selectedTemplate.value) return '—'
  return props.selectedTarget === 'mp' ? selectedTemplate.value.mpNodeBranch : selectedTemplate.value.nodeBranch
})

const previewTargetBranch = computed(() => {
  if (!selectedTemplate.value) return '—'
  return props.selectedTarget === 'mp' ? selectedTemplate.value.mpBranch : selectedTemplate.value.trunkBranch
})
</script>

<template>
  <div class="ea-card ea-stack">
    <div class="card-head">
      <div>
        <div class="ea-section-title">分支模板回填</div>
        <h3>按版本选择分支</h3>
        <p>优先用配置中心导入的模板回填 `NODE_BRANCH` / `target_BRANCH`，避免手工录入出错。</p>
      </div>
      <NTag v-if="parsed?.tosVersion" size="small" type="success" round>通知命中 {{ parsed.tosVersion }}</NTag>
    </div>

    <NEmpty v-if="!templates.length && !loading" description="当前还没有可用分支模板，请先到配置中心导入 Excel。" />

    <template v-else>
      <div class="ea-field">
        <label>当前版本</label>
        <NSelect
          :value="currentTos || ''"
          :options="tosOptions"
          placeholder="选择 tOS 版本"
          @update:value="$emit('update:selectedTos', String($event || ''))"
        />
      </div>

      <div class="ea-field">
        <label>平台模板</label>
        <NSelect
          :value="selectedTemplate?.templateId || ''"
          :options="templateOptions"
          placeholder="选择平台"
          @update:value="$emit('update:selectedTemplateId', String($event || ''))"
        />
      </div>

      <div class="ea-field">
        <label>目标类型</label>
        <NRadioGroup
          class="branch-target-group"
          :value="selectedTarget"
          @update:value="$emit('update:selectedTarget', $event as 'trunk' | 'mp')"
        >
          <NRadioButton value="trunk">主干</NRadioButton>
          <NRadioButton value="mp">MP</NRadioButton>
        </NRadioGroup>
      </div>

      <div class="preview-box">
        <div class="preview-item">
          <span class="ea-pill-muted">节点分支</span>
          <strong>{{ previewNodeBranch }}</strong>
        </div>
        <div class="preview-item">
          <span class="ea-pill-muted">目标分支</span>
          <strong>{{ previewTargetBranch }}</strong>
        </div>
      </div>

      <div class="apply-actions">
        <NButton
          type="primary"
          :disabled="!selectedTemplate"
          @click="$emit('apply')"
        >
          回填到执行参数
        </NButton>
      </div>
    </template>
  </div>
</template>

<style scoped lang="scss">
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;

  h3 {
    font-size: 18px;
    font-weight: 700;
    color: var(--head);
  }

  p {
    margin-top: 4px;
    font-size: 13px;
    color: var(--muted);
  }
}

.version-value,
.preview-box {
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid var(--line);
  background: var(--bg);
}

.preview-box {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.preview-item strong {
  display: block;
  margin-top: 8px;
  font-size: 14px;
  color: var(--text);
  word-break: break-word;
}

.branch-target-group {
  display: inline-flex;
  border-radius: 14px;
  overflow: hidden;
}

.apply-actions {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 720px) {
  .card-head {
    flex-direction: column;
    align-items: stretch;
  }

  .preview-box {
    grid-template-columns: 1fr;
  }
}
</style>
