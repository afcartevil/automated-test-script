<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NInput, NSelect } from 'naive-ui'
import type { ModemBaselineConfig } from '@/api/tahp/modem-baseline'

const props = defineProps<{
  modelValue: ModemBaselineConfig
  buildProjects?: string[]
  buildProjectsWarning?: string
  loadingBuildProjects?: boolean
  loading?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: ModemBaselineConfig]
  'refresh-projects': []
  close: []
}>()

function updateField<K extends keyof ModemBaselineConfig>(key: K, value: ModemBaselineConfig[K]) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}

const projectOptions = computed(() =>
  (props.buildProjects ?? []).map(name => ({ label: name, value: name })),
)
</script>

<template>
  <div class="ea-card ea-stack basic-config-card">
    <div class="basic-head">
      <div>
        <div class="ea-section-title">基础配置</div>
        <h3>分支、路径与编译</h3>
      </div>
      <NButton secondary size="small" @click="$emit('close')">返回</NButton>
    </div>

    <div class="branch-row">
      <div class="ea-field">
        <label>源分支 <span class="required">*</span></label>
        <NInput
          :value="modelValue.NODE_BRANCH"
          placeholder="例如 master"
          @update:value="updateField('NODE_BRANCH', $event)"
        />
      </div>
      <span class="branch-arrow" aria-hidden="true">→</span>
      <div class="ea-field">
        <label>目标分支 <span class="required">*</span></label>
        <NInput
          :value="modelValue.target_BRANCH"
          placeholder="例如 PRODUCT_V_v0mp1rc_NR15_common"
          @update:value="updateField('target_BRANCH', $event)"
        />
      </div>
    </div>

    <div class="ea-form-grid2">
      <div class="ea-field">
        <label>描述</label>
        <NInput
          :value="modelValue.DESCRIPTION"
          placeholder="例如 BASELINE_UPGRADE"
          @update:value="updateField('DESCRIPTION', $event)"
        />
      </div>

      <div class="ea-field">
        <label>编译项目</label>
        <div class="project-row">
          <NSelect
            :value="modelValue.build_project || null"
            :options="projectOptions"
            :loading="loadingBuildProjects"
            clearable
            filterable
            placeholder="从 work_dir/projects 自动识别"
            @update:value="updateField('build_project', $event ? String($event) : undefined)"
          />
          <NButton secondary :disabled="loading || loadingBuildProjects" @click="$emit('refresh-projects')">
            刷新项目
          </NButton>
        </div>
        <p class="field-hint">
          继续执行成功后自动运行 <code>./tools/bld_modem.sh &lt;项目名&gt;</code>
        </p>
        <p v-if="buildProjectsWarning" class="field-warn">{{ buildProjectsWarning }}</p>
      </div>
    </div>

    <div class="ea-form-grid2">
      <div class="ea-field">
        <label>AP 标签</label>
        <NInput
          :value="modelValue.AP_lable"
          placeholder="例如 V13.29"
          @update:value="updateField('AP_lable', $event)"
        />
      </div>

      <div class="ea-field">
        <label>JIRA ID</label>
        <NInput
          :value="modelValue.JIRAID"
          placeholder="例如 AR-UIF-0001-001-010"
          @update:value="updateField('JIRAID', $event)"
        />
      </div>
    </div>

    <div class="ea-field">
      <label>工作区目录 <span class="required">*</span></label>
      <NInput
        :value="modelValue.work_dir"
        placeholder="例如 Z:\modem\workspace"
        @update:value="updateField('work_dir', $event)"
      />
      <p class="field-hint">仓库与映射前缀可在「配置中心」维护；此处为当前任务工作区路径。</p>
    </div>
  </div>
</template>

<style scoped lang="scss">
.basic-config-card {
  height: 100%;
  min-height: 0;
  overflow: auto;
}

.basic-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;

  h3 {
    font-size: 18px;
    font-weight: 700;
    color: var(--head);
  }
}

.branch-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 8px;
  align-items: end;
}

.branch-arrow {
  padding-bottom: 10px;
  color: var(--muted);
  font-size: 15px;
  line-height: 1;
  user-select: none;
}

.project-row {
  display: flex;
  gap: 10px;
  align-items: center;

  :deep(.n-select) {
    flex: 1;
    min-width: 0;
  }
}

.field-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--muted);

  code {
    font-size: 12px;
  }
}

.field-warn {
  margin-top: 6px;
  font-size: 12px;
  color: #b45309;
  word-break: break-all;
}

.required {
  color: #dc2626;
}

@media (max-width: 720px) {
  .branch-row {
    grid-template-columns: 1fr;
  }

  .branch-arrow {
    display: none;
  }

  .project-row {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
