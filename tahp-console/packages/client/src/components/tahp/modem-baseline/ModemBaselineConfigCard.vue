<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NInput } from 'naive-ui'

const props = defineProps<{
  loading?: boolean
  noticeText: string
  parsing?: boolean
  recommending?: boolean
  configActive?: boolean
}>()

const emit = defineEmits<{
  'update:noticeText': [value: string]
  'parse-and-apply': []
  'toggle-config': []
  'start': []
}>()

const processing = computed(() => Boolean(props.parsing || props.recommending))
</script>

<template>
  <div class="ea-card ea-stack create-card">
    <div class="cfg-head">
      <div>
        <div class="ea-section-title">新建升级任务</div>
        <h3>通知解析</h3>
      </div>
      <div class="cfg-actions">
        <NButton
          secondary
          size="small"
          :type="configActive ? 'primary' : 'default'"
          @click="$emit('toggle-config')"
        >
          基础配置
        </NButton>
        <NButton type="primary" secondary size="small" :loading="processing" @click="$emit('parse-and-apply')">
          解析并应用
        </NButton>
      </div>
    </div>

    <div class="ea-field">
      <label>通知内容</label>
      <NInput
        :value="noticeText"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 5 }"
        placeholder="例如：7月基线升级 GEN99-V V11.35"
        @update:value="$emit('update:noticeText', $event)"
      />
    </div>

    <NButton type="primary" class="start-btn" :loading="loading" @click="$emit('start')">
      启动基线升级
    </NButton>
  </div>
</template>

<style scoped lang="scss">
.create-card {
  padding: 14px 16px;
}

.cfg-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;

  h3 {
    font-size: 16px;
    font-weight: 700;
    color: var(--head);
  }
}

.cfg-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.start-btn {
  width: 100%;
}

@media (max-width: 720px) {
  .cfg-head,
  .cfg-actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
