<script setup lang="ts">
import { computed } from 'vue'
import { NButton } from 'naive-ui'
import type { PrecheckResult } from '@/api/tahp/modem-baseline'

const props = defineProps<{
  result: PrecheckResult | null
  loading?: boolean
}>()

defineEmits<{
  run: []
}>()

const blockingCount = computed(() => props.result?.items.filter(item => item.level === 'error').length ?? 0)
</script>

<template>
  <div class="ea-card ea-stack">
    <div class="cfg-head">
      <div>
        <div class="ea-section-title">执行前检查</div>
        <h3>Precheck</h3>
        <p>启动任务前先确认路径、仓库和 Harness bridge 状态，避免整流程白跑。</p>
      </div>
      <NButton type="primary" :loading="loading" @click="$emit('run')">执行前检查</NButton>
    </div>

    <div v-if="result" class="check-list">
      <div
        v-for="item in result.items"
        :key="item.key"
        class="check-item"
        :class="item.level"
      >
        <div>
          <strong>{{ item.title }}</strong>
          <p>{{ item.detail }}</p>
        </div>
        <span class="check-badge">{{ item.level }}</span>
      </div>
    </div>

    <div v-else class="empty-note">
      尚未执行 precheck。
    </div>

    <div v-if="result" class="summary-row">
      <span :class="blockingCount ? 'ea-pill-err' : 'ea-pill-ok'">
        {{ blockingCount ? `${blockingCount} 个阻断项` : '可执行' }}
      </span>
      <span class="ea-pill-muted">
        {{ result.canStart ? '当前配置允许启动任务' : '当前配置需先处理阻断项' }}
      </span>
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

.check-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.check-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid var(--line);
  background: var(--bg);

  strong {
    display: block;
    color: var(--text);
    font-size: 13px;
  }

  p {
    margin-top: 4px;
    color: var(--muted);
    font-size: 12px;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
}

.check-item.ok {
  border-color: color-mix(in srgb, var(--ok) 25%, var(--line));
}

.check-item.warn {
  border-color: color-mix(in srgb, var(--amber-ic) 35%, var(--line));
}

.check-item.error {
  border-color: color-mix(in srgb, var(--err) 35%, var(--line));
}

.check-badge {
  text-transform: uppercase;
  font-size: 11px;
  font-weight: 700;
  color: var(--muted);
}

.summary-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.empty-note {
  padding: 18px;
  border-radius: 14px;
  border: 1px dashed var(--line-strong);
  background: var(--bg);
  color: var(--muted);
  font-size: 13px;
}

@media (max-width: 720px) {
  .cfg-head,
  .check-item {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
