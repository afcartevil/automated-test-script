<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import EaPageHead from '@/components/layout/EaPageHead.vue'
import ConfigModelsPanel from '@/components/tahp/config/ConfigModelsPanel.vue'
import ConfigSkillPanel from '@/components/tahp/config/ConfigSkillPanel.vue'
import ConfigUnifiedFormPanel from '@/components/tahp/config/ConfigUnifiedFormPanel.vue'
import ConfigBatchPanel from '@/components/tahp/config/ConfigBatchPanel.vue'
import {
  CONFIG_MAIN_TABS,
  CONFIG_TAB_LABELS,
  CONFIG_ROUTE_NAME,
  parseConfigTab,
  type ConfigTab,
} from '@/utils/config-navigation'

const route = useRoute()
const router = useRouter()

const activeTab = computed(() => parseConfigTab(route.query.tab))

/** 首次进入 batch 后保持组件挂载，返回表单时会话不丢失 */
const batchPanelMounted = ref(false)
/** 每次从表单点击「启动skill配置检查」递增，驱动 batch 面板启动或恢复 */
const batchStartToken = ref(0)

const pageSubtitle = computed(() => {
  if (activeTab.value === 'batch') {
    return '依据已保存的一键配置表单，由 Agent 依次检查并完成各 Skill 配置'
  }
  return '模型 Provider、常用 Skill 与一键配置表单统一管理'
})

function switchTab(tab: ConfigTab) {
  if (tab === activeTab.value) return
  router.replace({ name: CONFIG_ROUTE_NAME, query: { tab } })
}

function goBatch() {
  batchPanelMounted.value = true
  batchStartToken.value += 1
  router.push({ name: CONFIG_ROUTE_NAME, query: { tab: 'batch' } })
}

function backToForm() {
  router.push({ name: CONFIG_ROUTE_NAME, query: { tab: 'form' } })
}

/** 兼容旧 query：openForm=1 → 一键配置表单 */
watch(
  () => route.query,
  (q) => {
    if (q.openForm === '1' && activeTab.value !== 'form') {
      router.replace({ name: CONFIG_ROUTE_NAME, query: { tab: 'form' } })
    }
    if (activeTab.value === 'batch') {
      batchPanelMounted.value = true
    }
  },
  { immediate: true },
)

watch(activeTab, (tab) => {
  if (tab === 'batch') batchPanelMounted.value = true
})
</script>

<template>
  <div class="page config-view">
    <EaPageHead title="配置" :subtitle="pageSubtitle" />

    <nav v-if="activeTab !== 'batch'" class="config-tabs" role="tablist">
      <button
        v-for="tab in CONFIG_MAIN_TABS"
        :key="tab"
        type="button"
        role="tab"
        class="config-tab"
        :class="{ active: activeTab === tab }"
        :aria-selected="activeTab === tab"
        @click="switchTab(tab)"
      >
        {{ CONFIG_TAB_LABELS[tab] }}
      </button>
    </nav>

    <div class="config-panel">
      <ConfigModelsPanel v-if="activeTab === 'models'" />
      <ConfigSkillPanel v-else-if="activeTab === 'skills'" />
      <ConfigUnifiedFormPanel
        v-else-if="activeTab === 'form'"
        @start-batch="goBatch"
      />
      <ConfigBatchPanel
        v-if="batchPanelMounted"
        v-show="activeTab === 'batch'"
        :start-token="batchStartToken"
        @back="backToForm"
      />
    </div>
  </div>
</template>

<style scoped lang="scss">
.config-view {
  max-width: 1280px;
}

.config-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 18px;
  padding: 4px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 12px;
  width: fit-content;
  max-width: 100%;
  overflow-x: auto;
}

.config-tab {
  padding: 8px 16px;
  border: none;
  background: none;
  color: var(--muted);
  cursor: pointer;
  font-family: inherit;
  font-size: 13px;
  font-weight: 600;
  border-radius: 8px;
  white-space: nowrap;
  transition: color 0.18s, background 0.18s;

  &:hover {
    color: var(--text);
    background: var(--surface-2, var(--bg));
  }

  &.active {
    color: var(--accent);
    background: var(--accent-soft);
    font-weight: 700;
  }
}

.config-panel {
  min-height: 200px;
}
</style>
