<script setup lang="ts">
import { computed } from 'vue'
import type { DeviceInfo, SelfCheckReportSummary } from '@/api/tahp/device-self-check'
import type { PipelineStage } from './self-check-utils'
import SelfCheckOverviewCard from './SelfCheckOverviewCard.vue'
import SelfCheckFlowStatus from './SelfCheckFlowStatus.vue'
import { useVerifyTasks } from '@/composables/useVerifyTasks'
import {
  displayReportStatus,
  getDisplayRole,
  getDisplayStatus,
  getStatusColor,
  getTestTypeLabel,
  isActiveAuxiliaryDevice,
  reportTitle,
} from './self-check-utils'

const props = defineProps<{
  devices: DeviceInfo[]
  overviewReports: SelfCheckReportSummary[]
  stats: {
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
  goReports: []
  goGerrit: []
  goTab: [tab: string]
  selectDevice: [deviceId: string]
}>()

const { tasks: verifyTasks } = useVerifyTasks()

const deviceCounts = computed(() => ({
  idle: props.devices.filter(d => d.status === '空闲').length,
  activeAux: props.devices.filter(isActiveAuxiliaryDevice).length,
  error: props.devices.filter(d => d.status === '错误').length,
}))

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

function formatAssignTime(iso?: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
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
        title="验测任务"
        tone="tone-indigo"
        :metric="verifyTasks.length"
        metric-label="待完成"
        @enter="emit('goDevices')"
      >
        <div v-if="!verifyTasks.length" class="panel-empty ea-muted">
          暂无未完成的验测任务
        </div>
        <ul v-else class="item-list">
          <li v-for="t in verifyTasks.slice(0, 3)" :key="t.task_id" class="item-row">
            <span class="item-main">
              <strong>{{ t.project || '—' }}</strong>
              <small>{{ t.item_label }} · 指派于 {{ formatAssignTime(t.created_at) }} · {{ t.created_by }}</small>
            </span>
          </li>
          <li v-if="verifyTasks.length > 3" class="item-more ea-muted">还有 {{ verifyTasks.length - 3 }} 项</li>
        </ul>
      </SelfCheckOverviewCard>

      <SelfCheckOverviewCard
        title="测试执行"
        tone="tone-sky"
        fill-body
        tall
        :metric="stats.runningTests"
        metric-label="运行中"
        :secondary-metric="`空闲 ${deviceCounts.idle} · 辅测 ${deviceCounts.activeAux} · 错误 ${deviceCounts.error}`"
        @enter="emit('goDevices')"
      >
        <div v-if="loading" class="device-panel panel-empty ea-muted">加载中…</div>
        <div v-else-if="!devices.length" class="device-panel panel-empty ea-muted">
          暂无设备，请连接 ADB 后刷新
        </div>
        <div v-else class="device-panel">
          <ul class="item-list device-list">
            <li
              v-for="device in devices"
              :key="device.deviceId"
              class="device-row clickable"
              :title="`${device.deviceName} · ${device.deviceId}`"
              @click="emit('selectDevice', device.deviceId)"
            >
              <span class="status-dot" :style="{ background: getStatusColor(device.status) }" />
              <strong class="device-name">{{ device.deviceName }}</strong>
              <span class="device-role">{{ getDisplayRole(device) }}</span>
              <div class="device-info-meta">
                <span class="device-id">{{ device.deviceId }}</span>
                <span class="device-sep">·</span>
                <span class="device-status" :style="{ color: getStatusColor(device.status) }">
                  {{ getDisplayStatus(device) }}
                </span>
                <template v-if="device.testType">
                  <span class="device-sep">·</span>
                  <span class="device-test">{{ getTestTypeLabel(device.testType) }}</span>
                </template>
              </div>
            </li>
          </ul>
        </div>
      </SelfCheckOverviewCard>

      <SelfCheckOverviewCard
        title="评审补全"
        tone="tone-amber"
        :metric="gerritStatusLabel"
        metric-label="状态"
        @enter="emit('goGerrit')"
      >
        <p class="panel-desc ea-muted">
          Gerrit 链接 → 启动识别「必测项」 → 从用例库推荐测试用例（带覆盖度评分）→ 覆盖不足时 AI 生成用例
        </p>
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
          近 72 小时暂无新报告，进入查看历史
        </div>
        <ul v-else class="item-list">
          <li v-for="report in reportPreview" :key="report.reportId" class="item-row">
            <span class="item-main">
              <strong>{{ reportTitle(report) }}</strong>
              <small>{{ displayReportStatus(report) }} · {{ formatReportTime(report) }} · {{ report.passedCases }}/{{ report.totalCases }} 通过</small>
            </span>
          </li>
        </ul>
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
  align-items: stretch;

  > * {
    min-width: 0;
  }
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
  grid-column: 1;
  grid-row: 1;
  align-self: start;
  margin-top: 0.35em;
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

.device-panel {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.device-list {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  padding-right: 2px;
}

.device-row {
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr) var(--card-action-col, 68px);
  grid-template-rows: auto auto;
  column-gap: 10px;
  row-gap: 4px;
  align-items: center;
  font-size: 13px;
  line-height: 1.45;
  min-width: 0;

  &.clickable {
    cursor: pointer;
    padding: 8px 0 8px 8px;
    margin: -8px 0 -8px -8px;
    border-radius: 8px;

    &:hover {
      background: var(--bg);
    }
  }
}

.device-name {
  grid-column: 2;
  grid-row: 1;
  min-width: 0;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-role {
  grid-column: 3;
  grid-row: 1;
  justify-self: start;
  flex-shrink: 0;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--bg);
  color: var(--muted);
}

.device-info-meta {
  grid-column: 2;
  grid-row: 2;
  font-size: 12px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-id {
  font-size: 11px;
  font-family: var(--font-mono, ui-monospace, monospace);
}

.device-sep {
  margin: 0 4px;
}

.device-test {
  color: var(--muted);
}

.device-status {
  font-weight: 500;
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
