<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import EaPageHead from '@/components/layout/EaPageHead.vue'
import EaPill from '@/components/layout/EaPill.vue'
import ConfigModelsPanel from '@/components/tahp/config/ConfigModelsPanel.vue'
import ConfigUnifiedFormPanel from '@/components/tahp/config/ConfigUnifiedFormPanel.vue'
import ConfigBatchPanel from '@/components/tahp/config/ConfigBatchPanel.vue'
import { useSkillConfigReadiness } from '@/composables/useSkillConfigReadiness'
import {
  CONFIG_MAIN_TABS,
  CONFIG_TAB_LABELS,
  CONFIG_ROUTE_NAME,
  isConfigSetupTab,
  parseConfigTab,
  type ConfigTab,
} from '@/utils/config-navigation'

const route = useRoute()
const router = useRouter()
const { loading: skillStatusLoading, summary: skillSummary, refresh: refreshSkillStatus } = useSkillConfigReadiness()

const activeTab = computed(() => parseConfigTab(route.query.tab))

/** 首次进入检查步后保持组件挂载，返回表单时会话不丢失 */
const batchPanelMounted = ref(false)
/** 每次从表单保存并启动检查时递增，驱动 batch 面板启动或恢复 */
const batchStartToken = ref(0)

const pageSubtitle = computed(() => {
  if (activeTab.value === 'batch') {
    return '依据已保存的配置，由 Agent 依次检查并完成各 Skill 配置'
  }
  return '模型 Provider 与一键配置（填表后保存并启动 Skill 检查）'
})

function isMainTabActive(tab: Exclude<ConfigTab, 'batch'>): boolean {
  if (tab === 'form') return isConfigSetupTab(activeTab.value)
  return activeTab.value === tab
}

function switchTab(tab: Exclude<ConfigTab, 'batch'>) {
  if (tab === 'form') {
    if (activeTab.value === 'form') return
    router.replace({ name: CONFIG_ROUTE_NAME, query: { tab: 'form' } })
    return
  }
  if (activeTab.value === 'models') return
  router.replace({ name: CONFIG_ROUTE_NAME, query: { tab } })
}

function goBatch() {
  batchPanelMounted.value = true
  batchStartToken.value += 1
  router.push({ name: CONFIG_ROUTE_NAME, query: { tab: 'batch' } })
}

function backToForm() {
  void refreshSkillStatus()
  router.push({ name: CONFIG_ROUTE_NAME, query: { tab: 'form' } })
}

function showBatch() {
  batchPanelMounted.value = true
  router.push({ name: CONFIG_ROUTE_NAME, query: { tab: 'batch' } })
}

/** 兼容旧 query：openForm=1 / tab=skills → 一键配置 */
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
  if (tab === 'form') void refreshSkillStatus()
})
</script>

<template>
  <div class="page config-view">
    <EaPageHead title="配置" :subtitle="pageSubtitle" />

    <nav class="config-tabs" role="tablist">
      <button
        v-for="tab in CONFIG_MAIN_TABS"
        :key="tab"
        type="button"
        role="tab"
        class="config-tab"
        :class="{ active: isMainTabActive(tab) }"
        :aria-selected="isMainTabActive(tab)"
        @click="switchTab(tab)"
      >
        {{ CONFIG_TAB_LABELS[tab] }}
      </button>
    </nav>

    <div class="config-panel">
      <ConfigModelsPanel v-if="activeTab === 'models'" />
      <template v-else-if="activeTab === 'form'">
        <div class="setup-status" :class="`setup-status--${skillSummary.tone}`">
          <EaPill v-if="!skillStatusLoading" :variant="skillSummary.tone">{{ skillSummary.label }}</EaPill>
          <span v-else class="setup-status__loading">正在读取 Skill 配置状态…</span>
          <button type="button" class="setup-status__link" @click="showBatch">
            查看详情
          </button>
          <span v-if="skillSummary.showLiveHint" class="setup-status__hint">
            会话在后台保持，不会因返回改表而中断
          </span>
        </div>
        <ConfigUnifiedFormPanel @start-batch="goBatch" />
      </template>
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

.setup-status {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  padding: 8px 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface);
  font-size: 12px;
}

.setup-status--ok { border-color: color-mix(in srgb, var(--ok, #16a34a) 35%, var(--line)); }
.setup-status--warn { border-color: color-mix(in srgb, var(--warn, #d97706) 40%, var(--line)); }
.setup-status--err { border-color: color-mix(in srgb, var(--err, #dc2626) 40%, var(--line)); }
.setup-status--info { border-color: color-mix(in srgb, var(--accent) 40%, var(--line)); }

.setup-status__loading,
.setup-status__hint {
  color: var(--muted);
}

.setup-status__link {
  border: none;
  background: none;
  padding: 0;
  margin-left: auto;
  color: var(--accent);
  font: inherit;
  font-weight: 700;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}
</style>
