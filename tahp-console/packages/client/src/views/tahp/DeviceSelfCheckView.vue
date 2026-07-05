<script setup lang="ts">
import { onMounted, provide, watch } from 'vue'
import { storeToRefs } from 'pinia'
import GerritReviewWorkspace from '@/components/tahp/GerritReviewWorkspace.vue'
import TestPlanningWorkspace from '@/components/tahp/TestPlanningWorkspace.vue'
import SelfCheckPageHeader from '@/components/tahp/self-check/SelfCheckPageHeader.vue'
import SelfCheckOverview from '@/components/tahp/self-check/SelfCheckOverview.vue'
import SelfCheckChecklist from '@/components/tahp/self-check/SelfCheckChecklist.vue'
import SelfCheckDeviceRun from '@/components/tahp/self-check/SelfCheckDeviceRun.vue'
import SelfCheckReportReview from '@/components/tahp/self-check/SelfCheckReportReview.vue'
import SelfCheckDialogs from '@/components/tahp/self-check/SelfCheckDialogs.vue'
import { DEVICE_SELF_CHECK_KEY } from '@/components/tahp/self-check/self-check-context'
import { useDeviceSelfCheck, SELF_CHECK_TABS, type SelfCheckTab } from '@/composables/useDeviceSelfCheck'
import { useGerritReviewStore } from '@/stores/tahp/gerrit-review'

const ctx = useDeviceSelfCheck()
provide(DEVICE_SELF_CHECK_KEY, ctx)

const gerritStore = useGerritReviewStore()
const { taskStatus: gerritTaskStatus } = storeToRefs(gerritStore)

onMounted(() => {
  gerritStore.init()
})

const {
  activeTab,
  loading,
  devices,
  nextNodes,
  scheduleItems,
  stats,
  pipelineStages,
  overviewReports,
  reportsLoading,
  viewMode,
  caseCatalogGroups,
  openCaseCatalog,
  catalogPanelExpanded,
  selectedCatalogTestType,
  selectDevice,
} = ctx

watch(activeTab, (tab, prev) => {
  if (tab === 'gerrit' && prev !== 'gerrit') {
    gerritStore.reconcileActiveTask()
  }
})

function goDevicesAndSelect(deviceId: string) {
  activeTab.value = 'devices'
  viewMode.value = 'list'
  selectDevice(deviceId)
}

function goTab(tab: string) {
  activeTab.value = tab as SelfCheckTab
}
</script>

<template>
  <div class="page page-wide">
    <SelfCheckPageHeader v-model:active-tab="activeTab" :tabs="SELF_CHECK_TABS" />

    <div class="tab-panel">
      <keep-alive>
        <SelfCheckOverview
          v-if="activeTab === 'overview'"
          key="overview"
          :devices="devices"
          :next-nodes="nextNodes"
          :schedule-items="scheduleItems"
          :overview-reports="overviewReports"
          :stats="stats"
          :pipeline-stages="pipelineStages"
          :loading="loading"
          :reports-loading="reportsLoading"
          :gerrit-task-status="gerritTaskStatus"
          @go-devices="activeTab = 'devices'"
          @go-planning="activeTab = 'planning'"
          @go-reports="activeTab = 'review'"
          @go-gerrit="activeTab = 'gerrit'"
          @go-tab="goTab"
          @select-device="goDevicesAndSelect"
        />

        <TestPlanningWorkspace v-else-if="activeTab === 'planning'" key="planning" />

        <div v-else-if="activeTab === 'devices'" key="devices" class="devices-tab">
          <SelfCheckChecklist
            compact
            :groups="caseCatalogGroups"
            :active-test-type="catalogPanelExpanded ? selectedCatalogTestType : null"
            @open-catalog="openCaseCatalog"
          />
          <SelfCheckDeviceRun />
        </div>

        <GerritReviewWorkspace v-else-if="activeTab === 'gerrit'" key="gerrit" />

        <SelfCheckReportReview v-else-if="activeTab === 'review'" key="review" />
      </keep-alive>
    </div>

    <SelfCheckDialogs />
  </div>
</template>

<style scoped lang="scss">
.tab-panel {
  min-height: calc(400px + 1.45em);
}

.devices-tab {
  display: contents;
}
</style>
