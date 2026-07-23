<script setup lang="ts">
import EaCard from '@/components/layout/EaCard.vue'

const props = defineProps<{
  pendingProjects: number
  runningTests: number
  pendingManual: number
  pendingReports: number
  refreshing?: boolean
  syncing?: boolean
}>()

const emit = defineEmits<{
  syncNodes: []
  newTask: []
  refreshDevices: []
}>()

const statCards = [
  { key: 'pendingProjects' as const, label: '待执行项目', tone: 'stat-indigo' },
  { key: 'runningTests' as const, label: '运行中测试', tone: 'stat-sky' },
  { key: 'pendingManual' as const, label: '待人工确认', tone: 'stat-amber' },
  { key: 'pendingReports' as const, label: '待 Review 报告', tone: 'stat-emerald' },
]
</script>

<template>
  <div class="self-check-hero">
    <div class="hero-head">
      <div>
        <h1>质量验测</h1>
        <p class="hero-sub ea-muted">
          项目节点驱动，自动烧录、自动测试、AI Review，第二天人工复核报告
        </p>
      </div>
      <div class="hero-actions">
        <button
          type="button"
          class="ea-btn-ghost ea-btn-sm"
          :disabled="syncing"
          @click="emit('syncNodes')"
        >
          {{ syncing ? '同步中…' : '同步项目节点' }}
        </button>
        <button type="button" class="ea-btn-ghost ea-btn-sm" @click="emit('newTask')">
          新建自检任务
        </button>
        <button
          type="button"
          class="ea-btn-primary ea-btn-sm"
          :disabled="refreshing"
          @click="emit('refreshDevices')"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="23 4 23 10 17 10" />
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
          </svg>
          {{ refreshing ? '刷新中…' : '刷新设备' }}
        </button>
      </div>
    </div>

    <div class="stat-grid">
      <EaCard v-for="card in statCards" :key="card.key" class="stat-card" :class="card.tone">
        <div class="stat-value">{{ props[card.key] }}</div>
        <div class="stat-label">{{ card.label }}</div>
      </EaCard>
    </div>
  </div>
</template>

<style scoped lang="scss">
.self-check-hero {
  margin-bottom: 16px;
}

.hero-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;

  h1 {
    margin: 0 0 6px;
    font-size: 22px;
    font-weight: 800;
    letter-spacing: -0.02em;
  }
}

.hero-sub {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  max-width: 640px;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.stat-card {
  padding: 14px 16px;
  border-left: 3px solid var(--line);

  &.stat-indigo { border-left-color: #6366f1; }
  &.stat-sky { border-left-color: #0ea5e9; }
  &.stat-amber { border-left-color: #f59e0b; }
  &.stat-emerald { border-left-color: #10b981; }
}

.stat-value {
  font-size: 24px;
  font-weight: 800;
  line-height: 1.1;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 12px;
  color: var(--muted);
  font-weight: 600;
}

@media (max-width: 900px) {
  .hero-head {
    flex-direction: column;
  }

  .stat-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 520px) {
  .stat-grid {
    grid-template-columns: 1fr;
  }
}
</style>
