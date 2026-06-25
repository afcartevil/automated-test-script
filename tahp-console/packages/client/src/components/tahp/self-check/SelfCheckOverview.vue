<script setup lang="ts">
import EaCard from '@/components/layout/EaCard.vue'
import type { DeviceInfo } from '@/api/tahp/device-self-check'
import type { NextNodeItem, ScheduleItem } from '@/api/tahp/test-planning'
import { getDisplayStatus, getStatusColor, getTestTypeLabel } from './self-check-utils'

defineProps<{
  devices: DeviceInfo[]
  nextNodes: NextNodeItem[]
  scheduleItems: ScheduleItem[]
  loading?: boolean
}>()

const emit = defineEmits<{
  goDevices: []
  goPlanning: []
  goReports: []
  selectDevice: [deviceId: string]
}>()

function isRunning(device: DeviceInfo): boolean {
  return device.status.includes('测试') || device.status.includes('等待') || device.status === '初始化中'
}
</script>

<template>
  <div class="overview-root">
    <div class="overview-grid">
      <EaCard class="overview-panel">
        <div class="panel-head">
          <h3>运行中设备</h3>
          <button type="button" class="ea-btn-ghost ea-btn-sm" @click="emit('goDevices')">查看全部</button>
        </div>
        <div v-if="loading" class="panel-empty ea-muted">加载中…</div>
        <div v-else-if="!devices.filter(isRunning).length" class="panel-empty ea-muted">
          暂无运行中测试，可在「设备执行」启动
        </div>
        <ul v-else class="item-list">
          <li
            v-for="device in devices.filter(isRunning).slice(0, 5)"
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
      </EaCard>

      <EaCard class="overview-panel">
        <div class="panel-head">
          <h3>即将到节点</h3>
          <button type="button" class="ea-btn-ghost ea-btn-sm" @click="emit('goPlanning')">项目规划</button>
        </div>
        <div v-if="!nextNodes.length" class="panel-empty ea-muted">
          尚未同步项目节点，点击顶部「同步项目节点」
        </div>
        <ul v-else class="item-list">
          <li v-for="node in nextNodes.slice(0, 5)" :key="`${node.project}-${node.node}`" class="item-row">
            <span class="item-main">
              <strong>{{ node.project }}</strong>
              <small>{{ node.node }} · {{ node.nodeDate }}</small>
            </span>
          </li>
        </ul>
      </EaCard>

      <EaCard class="overview-panel">
        <div class="panel-head">
          <h3>计划任务</h3>
          <button type="button" class="ea-btn-ghost ea-btn-sm" @click="emit('goPlanning')">查看规则</button>
        </div>
        <div v-if="!scheduleItems.length" class="panel-empty ea-muted">
          配置节点规则后，GMS / 稳定性 / 特定项压测将自动排期
        </div>
        <ul v-else class="item-list">
          <li
            v-for="item in scheduleItems.slice(0, 5)"
            :key="`${item.project}-${item.node}-${item.testName}`"
            class="item-row"
          >
            <span class="item-main">
              <strong>{{ item.testName }}</strong>
              <small>{{ item.display }}</small>
            </span>
          </li>
        </ul>
      </EaCard>

      <EaCard class="overview-panel">
        <div class="panel-head">
          <h3>待 Review 报告</h3>
          <button type="button" class="ea-btn-ghost ea-btn-sm" @click="emit('goReports')">报告 Review</button>
        </div>
        <div class="panel-empty ea-muted">
          昨晚完成的测试报告将在此汇总，支持 AI 摘要与人工结论
        </div>
      </EaCard>
    </div>
  </div>
</template>

<style scoped lang="scss">
.overview-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}

.overview-panel {
  padding: 14px 16px;
  min-height: 180px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;

  h3 {
    margin: 0;
    font-size: 14px;
    font-weight: 700;
  }
}

.panel-empty {
  font-size: 13px;
  line-height: 1.5;
  padding: 8px 0;
}

.item-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
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

@media (max-width: 900px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }
}
</style>
