<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  NButton,
  NInput,
  NInputNumber,
  NModal,
  NSelect,
  NSpace,
  useMessage,
} from 'naive-ui'
import type { ProjectNodeKey, TestPlanRule } from '@/api/tahp/test-planning'
import { saveTestPlanRules } from '@/api/tahp/test-planning'

const NODE_OPTIONS: { label: string; value: ProjectNodeKey }[] = [
  { label: 'STR4', value: 'STR4' },
  { label: 'STR4A', value: 'STR4A' },
  { label: 'STR5', value: 'STR5' },
  { label: 'STR6', value: 'STR6' },
]

const EXAMPLE_RULES: TestPlanRule[] = [
  { node: 'STR4A', offsetDays: -10, testName: 'GMS测试' },
  { node: 'STR4A', offsetDays: -7, testName: '内核稳定性测试' },
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
  draftRules.value.push({ node, offsetDays: -7, testName: '' })
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
      为各项目节点配置前后 14 天内的测试项。偏移为负数表示节点前，正数表示节点后。
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
        <NInput
          v-model:value="rule.testName"
          size="small"
          placeholder="测试项名称，如 GMS测试"
          style="flex: 1"
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
