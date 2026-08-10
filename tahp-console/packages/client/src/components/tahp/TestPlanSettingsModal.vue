<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  NButton,
  NInputNumber,
  NModal,
  NSelect,
  NSpace,
  useMessage,
} from 'naive-ui'
import type { PlanTestType, ProjectNodeKey, TestPlanRule } from '@/api/tahp/test-planning'
import { saveTestPlanRules } from '@/api/tahp/test-planning'
import { getTestTypeLabel } from '@/components/tahp/self-check/self-check-utils'

const NODE_OPTIONS: { label: string; value: ProjectNodeKey }[] = [
  { label: 'STR4', value: 'STR4' },
  { label: 'STR4A', value: 'STR4A' },
  { label: 'STR5', value: 'STR5' },
  { label: 'STR6', value: 'STR6' },
]

const TEST_TYPE_OPTIONS: { label: string; value: PlanTestType }[] = [
  { label: getTestTypeLabel('str4'), value: 'str4' },
  { label: getTestTypeLabel('week'), value: 'week' },
  { label: getTestTypeLabel('smoke'), value: 'smoke' },
  { label: getTestTypeLabel('monkey'), value: 'monkey' },
  { label: getTestTypeLabel('gms'), value: 'gms' },
  { label: getTestTypeLabel('power'), value: 'power' },
  { label: getTestTypeLabel('power_feature'), value: 'power_feature' },
  { label: getTestTypeLabel('thermal'), value: 'thermal' },
]

const EXAMPLE_RULES: TestPlanRule[] = [
  { node: 'STR4A', offsetDays: -10, testType: 'week' },
  { node: 'STR4A', offsetDays: -7, testType: 'monkey' },
]

const props = defineProps<{
  show: boolean
  rules: TestPlanRule[]
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  saved: []
}>()

const message = useMessage()
const saving = ref(false)
const draftRules = ref<TestPlanRule[]>([])

watch(
  () => props.show,
  (visible) => {
    if (visible) {
      draftRules.value = props.rules.length
        ? props.rules.map((rule) => ({ ...rule }))
        : []
    }
  },
)

const groupedNodes = computed(() => NODE_OPTIONS.map((opt) => opt.value))

function rulesForNode(node: ProjectNodeKey): TestPlanRule[] {
  return draftRules.value.filter((rule) => rule.node === node)
}

function addRule(node: ProjectNodeKey) {
  draftRules.value.push({ node, offsetDays: -7, testType: 'week' })
}

function removeRule(node: ProjectNodeKey, indexInNode: number) {
  const nodeRules = rulesForNode(node)
  const target = nodeRules[indexInNode]
  if (!target) return
  const globalIndex = draftRules.value.indexOf(target)
  if (globalIndex >= 0) draftRules.value.splice(globalIndex, 1)
}

function fillExample() {
  draftRules.value = EXAMPLE_RULES.map((rule) => ({ ...rule }))
}

function offsetLabel(offsetDays: number): string {
  if (offsetDays === 0) return '节点当天'
  if (offsetDays < 0) return `节点前 ${Math.abs(offsetDays)} 天`
  return `节点后 ${offsetDays} 天`
}

async function handleSave() {
  saving.value = true
  try {
    await saveTestPlanRules(draftRules.value)
    message.success('测试规划配置已保存')
    emit('saved')
    emit('update:show', false)
  } catch (err) {
    message.error((err as Error).message || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    title="测试规划设置"
    style="width: min(720px, 92vw)"
    @update:show="emit('update:show', $event)"
  >
    <p class="modal-desc ea-muted">
      为各项目节点配置前后 14 天内的测试项。偏移为负数表示节点前，正数表示节点后。测试项须从质量验测已有测试大类中选择。
    </p>

    <div class="toolbar">
      <NButton size="small" tertiary @click="fillExample">填充示例</NButton>
    </div>

    <div v-for="node in groupedNodes" :key="node" class="node-section">
      <div class="node-section-head">
        <h4>{{ node }}</h4>
        <NButton size="tiny" tertiary @click="addRule(node)">添加测试项</NButton>
      </div>

      <div v-if="!rulesForNode(node).length" class="node-empty ea-muted">暂无规则</div>

      <div
        v-for="(rule, idx) in rulesForNode(node)"
        :key="`${node}-${idx}`"
        class="rule-row"
      >
        <NSelect
          :value="rule.node"
          :options="NODE_OPTIONS"
          size="small"
          style="width: 110px"
          @update:value="(v) => { rule.node = v as ProjectNodeKey }"
        />
        <NInputNumber
          v-model:value="rule.offsetDays"
          size="small"
          :min="-14"
          :max="14"
          style="width: 120px"
        />
        <span class="offset-hint ea-muted">{{ offsetLabel(rule.offsetDays) }}</span>
        <NSelect
          v-model:value="rule.testType"
          :options="TEST_TYPE_OPTIONS"
          size="small"
          placeholder="测试大类"
          style="flex: 1; min-width: 160px"
        />
        <NButton size="tiny" quaternary type="error" @click="removeRule(node, idx)">删除</NButton>
      </div>
    </div>

    <template #footer>
      <NSpace justify="end">
        <NButton @click="emit('update:show', false)">取消</NButton>
        <NButton type="primary" :loading="saving" @click="handleSave">保存</NButton>
      </NSpace>
    </template>
  </NModal>
</template>

<style scoped lang="scss">
.modal-desc {
  margin: 0 0 12px;
  font-size: 13px;
  line-height: 1.5;
}

.toolbar {
  margin-bottom: 12px;
}

.node-section {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px dashed var(--line);

  &:last-child {
    border-bottom: none;
    margin-bottom: 0;
    padding-bottom: 0;
  }
}

.node-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;

  h4 {
    margin: 0;
    font-size: 13px;
    font-weight: 700;
  }
}

.node-empty {
  font-size: 12px;
  padding: 4px 0 8px;
}

.rule-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.offset-hint {
  font-size: 12px;
  min-width: 96px;
}
</style>
