<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NInput, NSelect, NTooltip } from 'naive-ui'
import type { ModemBaselineConfig } from '@/api/tahp/modem-baseline'

export type ConfigFieldErrors = {
  NODE_BRANCH?: string
  target_BRANCH?: string
  work_dir?: string
}

const props = defineProps<{
  modelValue: ModemBaselineConfig
  buildProjects?: string[]
  buildProjectsWarning?: string
  loadingBuildProjects?: boolean
  loading?: boolean
  starting?: boolean
  fieldErrors?: ConfigFieldErrors
  startDisabled?: boolean
  startDisabledReason?: string
  showClose?: boolean
  closeLabel?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: ModemBaselineConfig]
  'refresh-projects': []
  close: []
  start: []
}>()

function updateField<K extends keyof ModemBaselineConfig>(key: K, value: ModemBaselineConfig[K]) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}

const projectOptions = computed(() =>
  (props.buildProjects ?? []).map(name => ({ label: name, value: name })),
)

const workDirEmpty = computed(() => !String(props.modelValue.work_dir ?? '').trim())
const refreshDisabled = computed(() => Boolean(props.loading || props.loadingBuildProjects || workDirEmpty.value))
const refreshTip = computed(() =>
  workDirEmpty.value ? '请先填写工作区目录后再刷新项目' : '从 work_dir/projects 重新扫描编译项目',
)

function pathTitle(value?: string) {
  return String(value ?? '').trim() || undefined
}
</script>

<template>
  <div class="basic-config-card">
    <div class="basic-head">
      <div>
        <div class="ea-section-title">基础配置</div>
        <h3>分支、路径与编译</h3>
      </div>
      <NButton v-if="showClose" secondary size="small" @click="$emit('close')">
        {{ closeLabel || '查看运行详情' }}
      </NButton>
    </div>

    <div class="form-body">
      <div class="form-block">
        <div class="branch-row">
          <div class="ea-field" :class="{ 'has-error': fieldErrors?.NODE_BRANCH }">
            <label>源分支 <span class="required">*</span></label>
            <NInput
              size="small"
              :value="modelValue.NODE_BRANCH"
              :status="fieldErrors?.NODE_BRANCH ? 'error' : undefined"
              placeholder="例如 master"
              @update:value="updateField('NODE_BRANCH', $event)"
            />
            <p v-if="fieldErrors?.NODE_BRANCH" class="field-error">{{ fieldErrors.NODE_BRANCH }}</p>
          </div>
          <span class="branch-arrow" aria-hidden="true">→</span>
          <div class="ea-field" :class="{ 'has-error': fieldErrors?.target_BRANCH }">
            <label>目标分支 <span class="required">*</span></label>
            <NInput
              size="small"
              :value="modelValue.target_BRANCH"
              :status="fieldErrors?.target_BRANCH ? 'error' : undefined"
              placeholder="例如 PRODUCT_V_v0mp1rc_NR15_common"
              @update:value="updateField('target_BRANCH', $event)"
            />
            <p v-if="fieldErrors?.target_BRANCH" class="field-error">{{ fieldErrors.target_BRANCH }}</p>
          </div>
        </div>
      </div>

      <div class="form-block">
        <div class="fields-grid">
          <div class="ea-field">
            <label>描述</label>
            <NInput
              size="small"
              :value="modelValue.DESCRIPTION"
              placeholder="例如 BASELINE_UPGRADE"
              @update:value="updateField('DESCRIPTION', $event)"
            />
          </div>

          <div class="ea-field">
            <label>编译项目</label>
            <div class="project-row">
              <NSelect
                size="small"
                :value="modelValue.build_project || null"
                :options="projectOptions"
                :loading="loadingBuildProjects"
                clearable
                filterable
                placeholder="从 work_dir/projects 自动识别"
                @update:value="updateField('build_project', $event ? String($event) : undefined)"
              />
              <NTooltip>
                <template #trigger>
                  <span class="tip-wrap">
                    <NButton
                      secondary
                      size="small"
                      :disabled="refreshDisabled"
                      @click="$emit('refresh-projects')"
                    >
                      刷新
                    </NButton>
                  </span>
                </template>
                {{ refreshTip }}
              </NTooltip>
            </div>
            <p v-if="buildProjectsWarning" class="field-warn">{{ buildProjectsWarning }}</p>
          </div>

          <div class="ea-field">
            <label>AP 标签</label>
            <NInput
              size="small"
              :value="modelValue.AP_lable"
              placeholder="例如 V13.29"
              @update:value="updateField('AP_lable', $event)"
            />
          </div>

          <div class="ea-field">
            <label>JIRA ID</label>
            <NInput
              size="small"
              :value="modelValue.JIRAID"
              placeholder="例如 AR-UIF-0001-001-010"
              @update:value="updateField('JIRAID', $event)"
            />
          </div>
        </div>
      </div>

      <div class="form-block">
        <div class="ea-field work-dir-field" :class="{ 'has-error': fieldErrors?.work_dir }">
          <label>
            工作区目录 <span class="required">*</span>
            <span class="label-hint">仓库与映射前缀可在「配置中心」维护</span>
          </label>
          <NInput
            size="small"
            :value="modelValue.work_dir"
            :status="fieldErrors?.work_dir ? 'error' : undefined"
            :title="pathTitle(modelValue.work_dir)"
            class="path-input"
            placeholder="例如 Z:\modem\workspace"
            @update:value="updateField('work_dir', $event)"
          />
          <p v-if="fieldErrors?.work_dir" class="field-error">{{ fieldErrors.work_dir }}</p>
        </div>
      </div>
    </div>

    <div class="start-row">
      <p v-if="startDisabledReason" class="start-hint">{{ startDisabledReason }}</p>
      <NTooltip :disabled="!startDisabled || !startDisabledReason">
        <template #trigger>
          <span class="tip-wrap start-wrap">
            <NButton
              type="primary"
              class="start-btn"
              :loading="starting || loading"
              :disabled="startDisabled"
              @click="$emit('start')"
            >
              启动升级
            </NButton>
          </span>
        </template>
        {{ startDisabledReason }}
      </NTooltip>
    </div>
  </div>
</template>

<style scoped lang="scss">
.basic-config-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
}

.basic-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex: 0 0 auto;

  h3 {
    margin: 0;
    font-size: 16px;
    font-weight: 700;
    color: var(--head);
  }
}

.form-body {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  /* 分支 / 四字段 / 工作区 —— 纵向均分填满 */
  grid-template-rows: 1fr 1.4fr 1fr;
  gap: 0;
  overflow: hidden;
}

.form-block {
  min-height: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: clamp(6px, 1.4vh, 18px) 0;
}

.branch-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 12px;
  align-items: end;
  width: 100%;
}

.branch-arrow {
  color: var(--muted);
  font-size: 15px;
  line-height: 1;
  user-select: none;
  padding-bottom: 10px;
}

.fields-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-template-rows: 1fr 1fr;
  gap: clamp(12px, 2vh, 24px) 20px;
  width: 100%;
  height: 100%;
  align-items: center;
}

.project-row {
  display: flex;
  gap: 8px;
  align-items: center;

  :deep(.n-select) {
    flex: 1;
    min-width: 0;
  }
}

.work-dir-field {
  width: 100%;
}

.label-hint {
  margin-left: 8px;
  font-size: 11px;
  font-weight: 400;
  color: var(--muted);
}

.field-warn {
  margin: 4px 0 0;
  font-size: 11px;
  color: #b45309;
  word-break: break-all;
  max-height: 2.4em;
  overflow: hidden;
}

.field-error {
  margin: 4px 0 0;
  font-size: 11px;
  color: #dc2626;
}

.required {
  color: #dc2626;
}

.path-input {
  :deep(input) {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px;
  }
}

.start-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 0 0 auto;
  padding-top: 4px;
}

.start-hint {
  margin: 0;
  font-size: 12px;
  color: var(--amber-fg, #b45309);
  line-height: 1.35;
}

.start-btn {
  width: 100%;
}

.tip-wrap {
  display: inline-flex;
}

.start-wrap {
  width: 100%;

  .start-btn {
    width: 100%;
  }
}

:deep(.ea-field) {
  margin: 0;
  min-width: 0;

  label {
    margin-bottom: 6px;
    font-size: 12px;
  }
}

@media (max-width: 900px) {
  .form-body {
    grid-template-rows: none;
    gap: 12px;
    overflow: auto;
  }

  .form-block {
    padding: 0;
  }

  .fields-grid {
    grid-template-columns: 1fr;
    grid-template-rows: none;
    height: auto;
  }

  .branch-row {
    grid-template-columns: 1fr;
  }

  .branch-arrow {
    display: none;
  }

  .label-hint {
    display: none;
  }
}
</style>
