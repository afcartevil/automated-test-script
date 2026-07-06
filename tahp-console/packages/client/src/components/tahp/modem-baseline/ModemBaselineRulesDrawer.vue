<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { NButton, NDrawer, NForm, NFormItem, NInput, NSelect, NSwitch } from 'naive-ui'
import type { BranchRule, ModemPatchOperationType } from '@/api/tahp/modem-baseline'

const props = defineProps<{
  show: boolean
  rules: BranchRule[]
  saving?: boolean
  deleting?: boolean
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  'create': [input: Partial<BranchRule>]
  'update': [ruleId: string, input: Partial<BranchRule>]
  'remove': [ruleId: string]
}>()

type Draft = {
  ruleId: string
  enabled: boolean
  label: string
  operationType: ModemPatchOperationType
  platform: string
  vendor: string
  nodePattern: string
  trunkPattern: string
  mpPattern: string
  defaultTarget: 'trunk' | 'mp'
}

const draft = reactive<Draft>({
  ruleId: '',
  enabled: true,
  label: '',
  operationType: 'baseline_upgrade',
  platform: '',
  vendor: '',
  nodePattern: '{NODE_BRANCH}',
  trunkPattern: '{target_BRANCH}',
  mpPattern: '',
  defaultTarget: 'trunk',
})

const isEditing = computed(() => !!draft.ruleId)

const operationOptions = [
  { label: 'baseline_upgrade', value: 'baseline_upgrade' },
  { label: 'patch', value: 'patch' },
  { label: 'unknown', value: 'unknown' },
]

const targetOptions = [
  { label: 'trunk', value: 'trunk' },
  { label: 'mp', value: 'mp' },
]

const selectableRules = computed(() => props.rules.filter(item => item.ruleId !== 'default-baseline-upgrade'))

function resetDraft() {
  draft.ruleId = ''
  draft.enabled = true
  draft.label = ''
  draft.operationType = 'baseline_upgrade'
  draft.platform = ''
  draft.vendor = ''
  draft.nodePattern = '{NODE_BRANCH}'
  draft.trunkPattern = '{target_BRANCH}'
  draft.mpPattern = ''
  draft.defaultTarget = 'trunk'
}

function loadDraft(rule: BranchRule) {
  draft.ruleId = rule.ruleId
  draft.enabled = rule.enabled
  draft.label = rule.label
  draft.operationType = rule.operationType || 'baseline_upgrade'
  draft.platform = rule.platform || ''
  draft.vendor = rule.vendor || ''
  draft.nodePattern = rule.nodePattern
  draft.trunkPattern = rule.trunkPattern
  draft.mpPattern = rule.mpPattern || ''
  draft.defaultTarget = rule.defaultTarget || 'trunk'
}

function submit() {
  const payload: Partial<BranchRule> = {
    enabled: draft.enabled,
    label: draft.label,
    operationType: draft.operationType,
    platform: draft.platform || undefined,
    vendor: draft.vendor || undefined,
    nodePattern: draft.nodePattern,
    trunkPattern: draft.trunkPattern,
    mpPattern: draft.mpPattern || undefined,
    defaultTarget: draft.defaultTarget,
  }
  if (draft.ruleId) {
    emit('update', draft.ruleId, payload)
    return
  }
  emit('create', payload)
}

watch(
  () => props.show,
  (value) => {
    if (!value) resetDraft()
  },
)
</script>

<template>
  <NDrawer
    :show="show"
    :width="680"
    placement="right"
    @update:show="$emit('update:show', $event)"
  >
    <div class="drawer-body">
      <div class="drawer-head">
        <div>
          <div class="ea-section-title">规则管理</div>
          <h3>Branch rules</h3>
          <p>按用户维护推荐规则，支持 operationType/platform/vendor 精确匹配。</p>
        </div>
        <div class="drawer-actions">
          <NButton secondary @click="resetDraft">新建规则</NButton>
          <NButton secondary @click="$emit('update:show', false)">关闭</NButton>
        </div>
      </div>

      <div class="rule-list">
        <div v-for="rule in selectableRules" :key="rule.ruleId" class="rule-item">
          <div class="rule-main">
            <strong>{{ rule.label }}</strong>
            <p>
              {{ rule.operationType || 'baseline_upgrade' }}
              <span v-if="rule.platform"> · {{ rule.platform }}</span>
              <span v-if="rule.vendor"> · {{ rule.vendor }}</span>
              <span> · {{ rule.enabled ? 'enabled' : 'disabled' }}</span>
            </p>
          </div>
          <div class="rule-actions">
            <NButton secondary size="small" @click="loadDraft(rule)">编辑</NButton>
            <NButton secondary size="small" :loading="deleting" @click="$emit('remove', rule.ruleId)">删除</NButton>
          </div>
        </div>
        <div v-if="!selectableRules.length" class="empty-note">暂无自定义规则，可先创建一条通用规则。</div>
      </div>

      <div class="ea-divider" />

      <div class="ea-section-title">{{ isEditing ? '编辑规则' : '新增规则' }}</div>
      <NForm label-placement="top">
        <div class="ea-form-grid2">
          <NFormItem label="Enabled">
            <NSwitch :value="draft.enabled" @update:value="v => draft.enabled = v" />
          </NFormItem>
          <NFormItem label="Label">
            <NInput v-model:value="draft.label" placeholder="例如 GEN95 baseline upgrade" />
          </NFormItem>
        </div>

        <div class="ea-form-grid2">
          <NFormItem label="Operation type">
            <NSelect v-model:value="draft.operationType" :options="operationOptions" />
          </NFormItem>
          <NFormItem label="Default target">
            <NSelect v-model:value="draft.defaultTarget" :options="targetOptions" />
          </NFormItem>
        </div>

        <div class="ea-form-grid2">
          <NFormItem label="Platform (optional)">
            <NInput v-model:value="draft.platform" placeholder="例如 GEN95" />
          </NFormItem>
          <NFormItem label="Vendor (optional)">
            <NInput v-model:value="draft.vendor" placeholder="例如 TECNO" />
          </NFormItem>
        </div>

        <NFormItem label="NODE_BRANCH pattern">
          <NInput v-model:value="draft.nodePattern" placeholder="{NODE_BRANCH} / {platform} / {version}" />
        </NFormItem>

        <NFormItem label="Trunk target pattern">
          <NInput v-model:value="draft.trunkPattern" placeholder="{target_BRANCH} / {platform} / {version}" />
        </NFormItem>

        <NFormItem label="MP target pattern (optional)">
          <NInput v-model:value="draft.mpPattern" placeholder="{target_BRANCH} / {platform} / {version}" />
        </NFormItem>

        <div class="drawer-actions">
          <NButton type="primary" :loading="saving" @click="submit">{{ isEditing ? '保存修改' : '新增规则' }}</NButton>
        </div>
      </NForm>
    </div>
  </NDrawer>
</template>

<style scoped lang="scss">
.drawer-body {
  padding: 18px 18px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.drawer-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;

  h3 {
    font-size: 18px;
    font-weight: 700;
    color: var(--head);
  }

  p {
    font-size: 13px;
    color: var(--muted);
    margin-top: 4px;
  }
}

.drawer-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.rule-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.rule-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
  padding: 12px 14px;
  border-radius: 14px;
  background: var(--bg);
  border: 1px solid var(--line);
}

.rule-main strong {
  display: block;
  font-size: 13px;
  color: var(--text);
}

.rule-main p {
  margin-top: 4px;
  font-size: 12px;
  color: var(--muted);
}

.rule-actions {
  display: flex;
  gap: 8px;
  flex: 0 0 auto;
}

.empty-note {
  padding: 18px;
  border-radius: 14px;
  border: 1px dashed var(--line-strong);
  background: var(--bg);
  color: var(--muted);
  font-size: 13px;
}

.ea-divider {
  height: 1px;
  background: var(--line);
  margin: 4px 0;
}
</style>
