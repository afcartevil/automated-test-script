<script setup lang="ts">
import { computed } from 'vue'
import { NButton } from 'naive-ui'
import type { ModemBaselineRunMeta } from '@/api/tahp/modem-baseline'
import type { StageItem } from '@/composables/useModemBaseline'

const props = defineProps<{
  run: ModemBaselineRunMeta
  items: StageItem[]
  summary: string
  refreshing?: boolean
  continuing?: boolean
}>()

defineEmits<{
  'refresh-conflicts': []
  'continue-run': []
}>()

const unresolvedCount = computed(() => props.run.conflictFiles?.length ?? 0)
</script>

<template>
  <div class="ea-card ea-stack">
    <div class="stage-top">
      <div>
        <div class="ea-section-title">执行流程</div>
        <h3>基线升级工作台</h3>
        <p>{{ summary }}</p>
      </div>

      <div class="stage-actions">
        <NButton secondary :loading="refreshing" @click="$emit('refresh-conflicts')">刷新冲突</NButton>
        <NButton
          type="primary"
          :loading="continuing"
          :disabled="run.status !== 'conflict'"
          @click="$emit('continue-run')"
        >
          继续执行
        </NButton>
      </div>
    </div>

    <div class="ea-stage-track">
      <template v-for="(item, index) in items" :key="item.key">
        <div class="ea-stage" :class="item.state">
          <span class="ea-stage-node">{{ index + 1 }}</span>
          <div class="ea-stage-meta">
            <strong>{{ item.label }}</strong>
            <span>
              {{ item.state === 'done' ? '已完成' : item.state === 'active' ? '当前阶段' : '待执行' }}
            </span>
          </div>
        </div>
        <span v-if="index < items.length - 1" class="ea-stage-link" />
      </template>
    </div>

    <div class="stage-note">
      <span class="ea-pill-muted">{{ run.runId }}</span>
      <span :class="unresolvedCount ? 'ea-pill-warn' : 'ea-pill-ok'">
        {{ unresolvedCount ? `${unresolvedCount} 个冲突待处理` : '无待处理冲突' }}
      </span>
      <span class="ea-pill-info">创建于 {{ run.createdAt }}</span>
    </div>
  </div>
</template>

<style scoped lang="scss">
.stage-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;

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

.stage-actions {
  display: flex;
  gap: 10px;
  flex-shrink: 0;
}

.stage-note {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

:deep(.ea-stage-track) {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px 24px;
  align-items: start;
}

:deep(.ea-stage) {
  min-width: 0;
}

:deep(.ea-stage-link) {
  display: none;
}

:deep(.ea-stage-meta) {
  min-width: 0;
}

:deep(.ea-stage-meta strong),
:deep(.ea-stage-meta span) {
  display: block;
}

@media (max-width: 720px) {
  :deep(.ea-stage-track) {
    grid-template-columns: 1fr;
    gap: 14px;
  }

  .stage-top,
  .stage-actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
