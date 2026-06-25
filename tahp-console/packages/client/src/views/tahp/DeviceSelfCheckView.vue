<script setup lang="ts">
import { provide } from 'vue'
import EaInnerTabs from '@/components/layout/EaInnerTabs.vue'
import GerritReviewWorkspace from '@/components/tahp/GerritReviewWorkspace.vue'
import TestPlanningWorkspace from '@/components/tahp/TestPlanningWorkspace.vue'
import SelfCheckHero from '@/components/tahp/self-check/SelfCheckHero.vue'
import SelfCheckPipeline from '@/components/tahp/self-check/SelfCheckPipeline.vue'
import SelfCheckOverview from '@/components/tahp/self-check/SelfCheckOverview.vue'
import SelfCheckChecklist from '@/components/tahp/self-check/SelfCheckChecklist.vue'
import SelfCheckDeviceRun from '@/components/tahp/self-check/SelfCheckDeviceRun.vue'
import SelfCheckReportReview from '@/components/tahp/self-check/SelfCheckReportReview.vue'
import SelfCheckDialogs from '@/components/tahp/self-check/SelfCheckDialogs.vue'
import { DEVICE_SELF_CHECK_KEY } from '@/components/tahp/self-check/self-check-context'
import { useDeviceSelfCheck, SELF_CHECK_TABS } from '@/composables/useDeviceSelfCheck'

const ctx = useDeviceSelfCheck()
provide(DEVICE_SELF_CHECK_KEY, ctx)

const {
  activeTab,
  syncing,
  loading,
  devices,
  nextNodes,
  scheduleItems,
  stats,
  pipelineStages,
  viewMode,
  handleSyncNodes,
  handleNewTask,
  doRefreshDevices,
  handleChecklistStr4,
  handleChecklistPower,
  handleChecklistStress,
  selectDevice,
  tpowerStatus,
} = ctx

function goDevicesAndSelect(deviceId: string) {
  activeTab.value = 'devices'
  viewMode.value = 'list'
  selectDevice(deviceId)
}
</script>

<template>
  <div class="page page-wide">
    <SelfCheckHero
      :pending-projects="stats.pendingProjects"
      :running-tests="stats.runningTests"
      :pending-manual="stats.pendingManual"
      :pending-reports="stats.pendingReports"
      :refreshing="loading"
      :syncing="syncing"
      @sync-nodes="handleSyncNodes"
      @new-task="handleNewTask"
      @refresh-devices="doRefreshDevices"
    />

    <SelfCheckPipeline :stages="pipelineStages" />

    <EaInnerTabs v-model="activeTab" :tabs="[...SELF_CHECK_TABS]" class="self-check-tabs" />

    <div class="tab-panel">
      <SelfCheckOverview
        v-if="activeTab === 'overview'"
        :devices="devices"
        :next-nodes="nextNodes"
        :schedule-items="scheduleItems"
        :loading="loading"
        @go-devices="activeTab = 'devices'"
        @go-planning="activeTab = 'planning'"
        @go-reports="activeTab = 'review'"
        @select-device="goDevicesAndSelect"
      />

      <TestPlanningWorkspace v-else-if="activeTab === 'planning'" />

      <template v-else-if="activeTab === 'devices'">
        <SelfCheckChecklist
          compact
          :tpower-connected="tpowerStatus?.connected ?? false"
          :tpower-message="tpowerStatus?.message"
          @start-str4="handleChecklistStr4"
          @start-power="handleChecklistPower"
          @start-stress="handleChecklistStress"
        />
        <SelfCheckDeviceRun />
      </template>

      <GerritReviewWorkspace v-else-if="activeTab === 'gerrit'" />

      <SelfCheckReportReview v-else-if="activeTab === 'review'" />
    </div>

    <SelfCheckDialogs />
  </div>
</template>

<style scoped lang="scss">
.self-check-tabs {
  margin-bottom: 16px;
}

.tab-panel {
  min-height: 400px;
}
</style>
