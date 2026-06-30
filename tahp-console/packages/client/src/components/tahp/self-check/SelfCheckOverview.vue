<script setup lang="ts">
import { computed } from 'vue'
import type { DeviceInfo, SelfCheckReportSummary } from '@/api/tahp/device-self-check'
import type { NextNodeItem, ScheduleItem } from '@/api/tahp/test-planning'
import type { PipelineStage } from './self-check-utils'
import SelfCheckOverviewCard from './SelfCheckOverviewCard.vue'
import SelfCheckFlowStatus from './SelfCheckFlowStatus.vue'
import {
  getDisplayStatus,
  getStatusColor,
  getTestTypeLabel,
  isActiveAuxiliaryDevice,
} from './self-check-utils'

const props = defineProps<{
  devices: DeviceInfo[]
  nextNodes: NextNodeItem[]
  scheduleItems: ScheduleItem[]
  overviewReports: SelfCheckReportSummary[]
  stats: {
    pendingProjects: number
    runningTests: number
    pendingManual: number
    pendingReports: number
  }
  pipelineStages: PipelineStage[]
  loading?: boolean
  gerritTaskStatus?: string
  reportsLoading?: boolean
}>()

const emit = defineEmits<{
  goDevices: []
  goPlanning: []
  goReports: []
  goGerrit: []
  goTab: [tab: string]
  selectDevice: [deviceId: string]
}>()

function isRunning(device: DeviceInfo): boolean {
  return device.status.includes('测试') || device.status.includes('等待') || device.status === '初始化中'
}

const runningDevices = computed(() => props.devices.filter(isRunning))

const deviceCounts = computed(() => ({
  idle: props.devices.filter(d => d.status === '空闲').length,
  activeAux: props.devices.filter(isActiveAuxiliaryDevice).length,
  error: props.devices.filter(d => d.status === '错误').length,
}))

const activeSchedules = computed(() =>
  props.scheduleItems.filter(
    i => i.runtimeStatus === 'running' || i.runtimeStatus === 'no_device',
  ),
)

const reportPreview = computed(() => props.overviewReports.slice(0, 3))

const gerritStatusLabel = computed(() => {
  const s = props.gerritTaskStatus || ''
  if (s === 'running') return '评审进行中'
  if (s === 'completed') return '最近评审已完成'
  if (s === 'failed') return '最近评审失败'
  return '暂无进行中的评审'
})

function formatReportTime(report: SelfCheckReportSummary): string {
  const t = report.completedAt || report.endTime || report.startTime
  try {
    return new Date(t).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return t
  }
}

function onFlowStage(tab: string) {
  emit('goTab', tab)
}
</script>

<template>
  <div class="overview-root">
    <SelfCheckOverviewCard
      compact
      hide-enter
      title="流程状态"
      tone="tone-violet"
      :metric="stats.pendingManual"
      metric-label="待人工确认"
    >
      <SelfCheckFlowStatus
        layout="horizontal"
        :stages="pipelineStages"
        @stage-click="onFlowStage"
      />
    </SelfCheckOverviewCard>

    <div class="module-grid">
      <SelfCheckOverviewCard
        title="项目规划"
        tone="tone-indigo"
        :metric="stats.pendingProjects"
        metric-label="待执行排期"
        @enter="emit('goPlanning')"
      >
        <div v-if="!nextNodes.length" class="panel-empty ea-muted">
          尚未同步项目节点，请进入
          <button type="button" class="link-btn" @click="emit('goPlanning')">项目规划</button>
          同步
        </div>
        <ul v-else class="item-list">
          <li v-for="node in nextNodes.slice(0, 3)" :key="`${node.project}-${node.node}`" class="item-row">
            <span class="item-main">
              <strong>{{ node.project }}</strong>
              <small>{{ node.node }} · {{ node.nodeDate }}</small>
            </span>
          </li>
          <li v-if="nextNodes.length > 3" class="item-more ea-muted">还有 {{ nextNodes.length - 3 }} 个节点</li>
        </ul>
        <ul v-if="activeSchedules.length" class="item-list item-list--secondary">
          <li v-for="item in activeSchedules.slice(0, 2)" :key="item.scheduleKey" class="item-row">
            <span class="item-main">
              <strong>{{ item.testTypeLabel }}</strong>
              <small>{{ item.displayLabel }}{{ item.tags.length ? ` · ${item.tags.join(' · ')}` : '' }}</small>
            </span>
          </li>
        </ul>
      </SelfCheckOverviewCard>

      <SelfCheckOverviewCard
        title="设备执行"
        tone="tone-sky"
        :metric="stats.runningTests"
        metric-label="运行中"
        :secondary-metric="`空闲 ${deviceCounts.idle} · 辅测 ${deviceCounts.activeAux} · 错误 ${deviceCounts.error}`"
        @enter="emit('goDevices')"
      >
        <div v-if="loading" class="panel-empty ea-muted">加载中…</div>
        <div v-else-if="!runningDevices.length" class="panel-empty ea-muted">
          暂无运行中测试，请进入
          <button type="button" class="link-btn" @click="emit('goDevices')">设备执行</button>
        </div>
        <ul v-else class="item-list">
          <li
            v-for="device in runningDevices.slice(0, 3)"
            :key="device.deviceId"
            class="item-row clickable"
            @click="emit('selectDevice', device.deviceId)"
          >
            <span class="status-dot" :style="{ background: getStatusColor(device.status) }" />
            <span class="item-main">
              <strong>{{ device.deviceName }}</strong>
              <small>{{ getDisplayStatus(device) }}</small>
            </span>
            <span class="item-meta">{{ getTestTypeLabel(device.testType) }}</span>
          </li>
        </ul>
      </SelfCheckOverviewCard>

      <SelfCheckOverviewCard
        title="测试报告"
        tone="tone-emerald"
        :metric="stats.pendingReports"
        metric-label="待审阅"
        @enter="emit('goReports')"
      >
        <div v-if="reportsLoading" class="panel-empty ea-muted">加载报告…</div>
        <div v-else-if="!reportPreview.length" class="panel-empty ea-muted">
          近 72 小时暂无测试报告
        </div>
        <ul v-else class="item-list">
          <li v-for="report in reportPreview" :key="report.reportId" class="item-row">
            <span class="item-main">
              <strong>{{ report.deviceName }}</strong>
              <small>{{ formatReportTime(report) }} · {{ report.passedCases }}/{{ report.totalCases }} 通过</small>
            </span>
          </li>
        </ul>
      </SelfCheckOverviewCard>

      <SelfCheckOverviewCard
        title="AI Review"
        tone="tone-amber"
        :metric="gerritStatusLabel"
        metric-label="状态"
        @enter="emit('goGerrit')"
      >
        <p class="panel-desc ea-muted">
          基于 Gerrit 变更进行 Code Review，并推荐关联测试用例。
        </p>
      </SelfCheckOverviewCard>
    </div>
  </div>
</template>

<style scoped lang="scss">
.overview-root {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.module-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}

.panel-empty {
  font-size: 13px;
  line-height: 1.5;
}

.panel-desc {
  font-size: 13px;
  line-height: 1.55;
  margin: 0;
}

.link-btn {
  border: none;
  background: none;
  padding: 0;
  color: var(--accent);
  cursor: pointer;
  font: inherit;
  text-decoration: underline;
}

.item-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;

  &--secondary {
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid var(--line);
  }
}

.item-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;

  &.clickable {
    cursor: pointer;
    padding: 6px 8px;
    margin: -6px -8px;
    border-radius: 8px;

    &:hover {
      background: var(--bg);
    }
  }
}

.item-more {
  font-size: 12px;
  padding-left: 2px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.item-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;

  strong {
    font-weight: 600;
  }

  small {
    color: var(--muted);
    font-size: 12px;
  }
}

.item-meta {
  font-size: 12px;
  color: var(--muted);
  flex-shrink: 0;
}

@media (max-width: 1100px) {
  .module-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 640px) {
  .module-grid {
    grid-template-columns: 1fr;
  }
}
</style>
