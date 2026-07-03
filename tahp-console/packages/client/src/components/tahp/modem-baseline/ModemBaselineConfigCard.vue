<script setup lang="ts">
import { NButton, NInput } from 'naive-ui'
import type { ModemBaselineConfig } from '@/api/tahp/modem-baseline'

const props = defineProps<{
  modelValue: ModemBaselineConfig
  loading?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: ModemBaselineConfig]
  'load-defaults': []
  'start': []
}>()

function updateField<K extends keyof ModemBaselineConfig>(key: K, value: ModemBaselineConfig[K]) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}
</script>

<template>
  <div class="ea-card ea-stack">
    <div>
      <div class="ea-section-title">基线配置</div>
      <div class="cfg-head">
        <div>
          <h3>执行参数</h3>
          <p>字段与外部 Modem 基线工具保持一致，直接用于真实任务启动。</p>
        </div>
        <span class="ea-pill-info">
          Stop After Merge
        </span>
      </div>
    </div>

    <div class="ea-form-grid2">
      <div class="ea-field">
        <label>源分支</label>
        <NInput
          :value="modelValue.NODE_BRANCH"
          placeholder="例如 master"
          @update:value="updateField('NODE_BRANCH', $event)"
        />
      </div>

      <div class="ea-field">
        <label>目标分支</label>
        <NInput
          :value="modelValue.target_BRANCH"
          placeholder="例如 PRODUCT_V_v0mp1rc_NR15_common"
          @update:value="updateField('target_BRANCH', $event)"
        />
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
      <label>工作区目录</label>
      <NInput
        :value="modelValue.work_dir"
        placeholder="例如 Z:\modem\workspace"
        @update:value="updateField('work_dir', $event)"
      />
    </div>

    <div class="ea-field">
      <label>描述</label>
      <NInput
        :value="modelValue.DESCRIPTION"
        placeholder="例如 BASELINE_UPGRADE"
        @update:value="updateField('DESCRIPTION', $event)"
      />
    </div>

    <div class="ea-form-grid2">
      <div class="ea-field">
        <label>映射盘前缀</label>
        <NInput
          :value="modelValue.mapped_prefix"
          placeholder="默认 Z:"
          @update:value="updateField('mapped_prefix', $event)"
        />
      </div>

      <div class="ea-field">
        <label>远端前缀</label>
        <NInput
          :value="modelValue.remote_prefix"
          placeholder="默认 /work/user/code"
          @update:value="updateField('remote_prefix', $event)"
        />
      </div>
    </div>

    <div class="cfg-actions">
      <NButton secondary :disabled="loading" @click="$emit('load-defaults')">重新加载默认配置</NButton>
      <NButton type="primary" :loading="loading" @click="$emit('start')">启动基线升级</NButton>
    </div>
  </div>
</template>

<style scoped lang="scss">
.cfg-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;

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

.cfg-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

@media (max-width: 720px) {
  .cfg-head,
  .cfg-actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
