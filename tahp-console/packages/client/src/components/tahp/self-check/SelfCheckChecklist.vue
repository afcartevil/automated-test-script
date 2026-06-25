<script setup lang="ts">
import { computed } from 'vue'
import EaCard from '@/components/layout/EaCard.vue'

const props = withDefaults(
  defineProps<{
    compact?: boolean
    tpowerConnected?: boolean
    tpowerMessage?: string
  }>(),
  {
    compact: false,
    tpowerConnected: false,
    tpowerMessage: '',
  },
)

const emit = defineEmits<{
  startStr4: [domain: 'driver' | 'comm']
  startPower: []
  startStress: [type: 'gms' | 'stability' | 'custom']
  openCatalog: [testType: string]
}>()

const cards = computed(() => [
  {
    key: 'driver',
    title: '驱动 STR4 / 转测 Checklist',
    scope: '驱动摸底、转测 checklist 自检',
    automation: '脚本自动化 + 半自动化',
    prereq: 'ADB 连接测试机',
    lastResult: '—',
    action: '启动驱动自检',
    tone: 'ea-t-indigo',
    handler: () => emit('startStr4', 'driver'),
  },
  {
    key: 'comm',
    title: '通信 STR4 / 转测 Checklist',
    scope: '通信框架摸底、转测 checklist',
    automation: '脚本自动化 + 半自动化',
    prereq: '双卡 SIM + 辅测机',
    lastResult: '—',
    action: '启动通信自检',
    tone: 'ea-t-sky',
    handler: () => emit('startStr4', 'comm'),
  },
  {
    key: 'power',
    title: '功耗 T-Power 自动化测试',
    scope: 'USB 连接 T-Power 硬件，ADB 下发功耗测试命令',
    automation: '全自动（需硬件）',
    prereq: props.tpowerConnected ? 'T-Power 已连接' : (props.tpowerMessage || 'T-Power 未连接'),
    lastResult: props.tpowerConnected ? '硬件就绪' : '未就绪',
    action: '配置功耗测试',
    tone: 'ea-t-emerald',
    handler: () => emit('startPower'),
  },
  {
    key: 'stress',
    title: 'GMS / 稳定性 / 特定项压测',
    scope: '按项目节点提前自动排期执行',
    automation: '全自动（可设提前天数）',
    prereq: '项目节点已同步',
    lastResult: '—',
    action: '查看压测计划',
    tone: 'ea-t-amber',
    handler: () => emit('startStress', 'gms'),
  },
] as const)
</script>

<template>
  <div class="checklist-root" :class="{ compact }">
    <div v-if="!compact" class="checklist-head">
      <h3>Checklist 自检能力</h3>
      <p class="ea-muted">驱动、通信 STR4 摸底与转测 checklist；功耗接 T-Power；压测按项目节点自动跑</p>
    </div>
    <div class="checklist-grid">
      <EaCard
        v-for="card in cards"
        :key="card.key"
        class="checklist-card"
        :class="card.tone"
      >
        <h4>{{ card.title }}</h4>
        <dl class="checklist-meta">
          <div><dt>覆盖</dt><dd>{{ card.scope }}</dd></div>
          <div><dt>自动化</dt><dd>{{ card.automation }}</dd></div>
          <div><dt>前置</dt><dd>{{ card.prereq }}</dd></div>
          <div><dt>最近</dt><dd>{{ card.lastResult }}</dd></div>
        </dl>
        <button type="button" class="ea-btn-primary ea-btn-sm" @click="card.handler()">
          {{ card.action }}
        </button>
      </EaCard>
    </div>
  </div>
</template>

<style scoped lang="scss">
.checklist-root {
  margin-bottom: 16px;

  &.compact .checklist-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}

.checklist-head {
  margin-bottom: 12px;

  h3 {
    margin: 0 0 4px;
    font-size: 15px;
    font-weight: 700;
  }

  p {
    margin: 0;
    font-size: 13px;
  }
}

.checklist-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.checklist-card {
  padding: 14px 16px;
  border-top: 3px solid var(--line);

  &.ea-t-indigo { border-top-color: #6366f1; }
  &.ea-t-sky { border-top-color: #0ea5e9; }
  &.ea-t-emerald { border-top-color: #10b981; }
  &.ea-t-amber { border-top-color: #f59e0b; }

  h4 {
    margin: 0 0 10px;
    font-size: 14px;
    font-weight: 700;
    line-height: 1.35;
  }
}

.checklist-meta {
  margin: 0 0 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;

  div {
    display: grid;
    grid-template-columns: 48px 1fr;
    gap: 8px;
    font-size: 12px;
  }

  dt {
    color: var(--muted);
    font-weight: 600;
  }

  dd {
    margin: 0;
    line-height: 1.4;
  }
}

@media (max-width: 1100px) {
  .checklist-root.compact .checklist-grid,
  .checklist-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 640px) {
  .checklist-root.compact .checklist-grid,
  .checklist-grid {
    grid-template-columns: 1fr;
  }
}
</style>
