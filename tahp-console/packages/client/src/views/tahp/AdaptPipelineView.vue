<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NAlert, useMessage } from 'naive-ui'
import EaPageHead from '@/components/layout/EaPageHead.vue'
import EaInnerTabs from '@/components/layout/EaInnerTabs.vue'
import PipelineRunList from '@/components/tahp/pipeline/PipelineRunList.vue'
import PipelineRunDetail from '@/components/tahp/pipeline/PipelineRunDetail.vue'
import PipelineWorkflowEditor from '@/components/tahp/pipeline/PipelineWorkflowEditor.vue'
import PipelineCreateWizard from '@/components/tahp/pipeline/PipelineCreateWizard.vue'
import PipelineHumanPanel from '@/components/tahp/pipeline/PipelineHumanPanel.vue'
import { useAdaptPipelineStore } from '@/stores/tahp/adapt-pipeline'
import { CONFIG_ROUTE_NAME } from '@/utils/config-navigation'
import { fetchPipelineRun } from '@/api/tahp/adapt-pipeline'
import { buildWizardCloneSeed, isCloneableRunId, type WizardCloneSeed } from '@/utils/pipeline-clone'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const store = useAdaptPipelineStore()

const activeTab = ref('board')
const humanDrawerOpen = ref(false)
const narrow = ref(false)
const cloneSeed = ref<WizardCloneSeed | null>(null)
const wizardEpoch = ref(0)
const cloneBusy = ref(false)

const pageTabs = [
  { key: 'board', label: '运行看板' },
  { key: 'create', label: '新建运行' },
  { key: 'workflow', label: '流程编排' },
]

const timeline = computed(() => store.selectedTimeline)
const selectedNodeKey = computed(() => {
  const q = route.query.node
  if (typeof q === 'string' && q) return q
  return timeline.value?.current_node ?? null
})

function syncRouteRun(runId: string | null) {
  const nextQuery = { ...route.query }
  if (runId) nextQuery.run = runId
  else delete nextQuery.run
  router.replace({ query: nextQuery })
}

async function handleSelectRun(runId: string) {
  syncRouteRun(runId)
  await store.selectRun(runId)
}

function handleSelectNode(key: string) {
  router.replace({ query: { ...route.query, node: key } })
}

function handleCreateClick() {
  cloneSeed.value = null
  wizardEpoch.value += 1
  activeTab.value = 'create'
  void store.checkRuntimeReadiness()
}

async function handleCloneRun(runId: string) {
  if (!isCloneableRunId(runId)) {
    message.warning('预览数据无法复制配置，请先创建真实运行')
    return
  }
  if (cloneBusy.value) return
  cloneBusy.value = true
  try {
    const run = await fetchPipelineRun(runId)
    cloneSeed.value = buildWizardCloneSeed(run)
    wizardEpoch.value += 1
    activeTab.value = 'create'
    void store.checkRuntimeReadiness()
    message.success('已复制运行配置，请核对后启动')
  } catch (err) {
    message.error((err as Error).message || '复制配置失败')
  } finally {
    cloneBusy.value = false
  }
}

async function handleDiscardDraft(runId: string) {
  const next = await store.discardDraftRun(runId)
  syncRouteRun(next)
  message.success('草稿已删除')
}

function handleDiscarded(nextRunId: string | null) {
  syncRouteRun(nextRunId)
  message.success('草稿已删除')
}

function handleCreated(runId: string) {
  activeTab.value = 'board'
  syncRouteRun(runId)
}

function updateNarrow() {
  narrow.value = window.innerWidth < 1400
}

onMounted(async () => {
  updateNarrow()
  window.addEventListener('resize', updateNarrow)
  await store.start()
  const runFromRoute = typeof route.query.run === 'string' ? route.query.run : null
  if (runFromRoute) {
    await handleSelectRun(runFromRoute)
  } else if (store.runItems.length > 0) {
    await handleSelectRun(store.runItems[0].run_id)
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', updateNarrow)
  store.stop()
})

watch(() => route.query.run, async (runId) => {
  if (typeof runId === 'string' && runId && runId !== store.selectedRunId) {
    await store.selectRun(runId)
  }
})

watch(() => store.error, (err) => {
  if (err) message.error(err)
})
</script>

<template>
  <div class="pipeline-page">
    <EaPageHead title="适配流水线" subtitle="选项目 → 拉前置 → AI 适配 → 编译 → 烧录 → 自检 → 审核 → 提交 Gerrit">
      <template #actions>
        <button
          v-if="narrow && store.pendingHumanTotal > 0"
          type="button"
          class="pending-badge btn-badge"
          @click="humanDrawerOpen = true"
        >
          ⚠ {{ store.pendingHumanTotal }} 项待人工处理
        </button>
        <span v-else-if="store.pendingHumanTotal > 0" class="pending-badge">
          ⚠ {{ store.pendingHumanTotal }} 项待人工处理
        </span>
        <EaInnerTabs v-model="activeTab" :tabs="pageTabs" align="end" />
      </template>
    </EaPageHead>

    <NAlert v-if="!store.centralConfigured" type="warning" :bordered="false" class="top-alert">
      未配置 TAHP 中心连接，无法拉取项目前置。
      <router-link :to="{ name: CONFIG_ROUTE_NAME }" class="alert-link">前往配置</router-link>
    </NAlert>
    <NAlert v-if="activeTab === 'create' && !store.bridgeRunning" type="error" :bordered="false" class="top-alert">
      Agent Bridge 未就绪，适配阶段将失败。请确认本机 Console 服务已启动且日志中有 <code>[agent-bridge] ready</code>。
    </NAlert>

    <div v-if="activeTab === 'board'" class="board">
      <PipelineRunList
        :items="store.runItems"
        :selected-id="store.selectedRunId"
        :loading="store.listLoading"
        :busy="store.runActionBusy || cloneBusy"
        @select="handleSelectRun"
        @create="handleCreateClick"
        @discard="handleDiscardDraft"
        @clone="handleCloneRun"
      />

      <div class="board-main">
        <div v-if="!store.runItems.length && !store.listLoading" class="board-empty card">
          <h2>还没有运行记录</h2>
          <p>创建第一条适配流水线运行，开始从项目选择到 Gerrit 提交的完整流程。</p>
          <button type="button" class="ea-btn-primary" @click="handleCreateClick">新建运行</button>
        </div>

        <div v-else-if="!store.selectedRunId" class="board-empty card">
          <h2>还没有选中运行</h2>
          <p>从左侧选择一条运行，或新建运行开始适配流水线。</p>
          <button type="button" class="ea-btn-primary" @click="handleCreateClick">新建运行</button>
        </div>

        <template v-else>
          <PipelineRunDetail
            v-if="timeline"
            :timeline="timeline"
            :selected-node-key="selectedNodeKey"
            :store="store"
            :human-drawer="narrow"
            @select-node="handleSelectNode"
            @open-human="humanDrawerOpen = true"
            @discarded="handleDiscarded"
          />

          <NAlert
            v-if="!store.socketConnected"
            type="warning"
            :bordered="false"
            class="poll-hint"
          >
            Socket 未连接，已降级为每 5 秒轮询 timeline。
          </NAlert>
        </template>
      </div>
    </div>

    <PipelineCreateWizard
      v-else-if="activeTab === 'create'"
      :key="`wizard-${wizardEpoch}`"
      :store="store"
      :clone-seed="cloneSeed"
      @created="handleCreated"
    />

    <PipelineWorkflowEditor v-else :store="store" />

    <Teleport to="body">
      <div v-if="humanDrawerOpen && narrow" class="drawer-backdrop" @click.self="humanDrawerOpen = false">
        <div class="drawer-panel card">
          <div class="drawer-head">
            <strong>人工介入</strong>
            <button type="button" class="drawer-close" @click="humanDrawerOpen = false">×</button>
          </div>
          <PipelineHumanPanel
            v-if="store.selectedRunId && timeline"
            :run-id="store.selectedRunId"
            :nodes="timeline.nodes"
            :store="store"
          />
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped lang="scss">
.pipeline-page {
  max-width: 1320px;
  margin: 0 auto;
}

.top-alert {
  margin-bottom: 12px;
}
.alert-link {
  margin-left: 8px;
  color: var(--accent);
  font-weight: 700;
}

.pending-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--warn-soft);
  color: var(--warn);
  border: 1px solid color-mix(in srgb, var(--warn) 22%, transparent);
  padding: 7px 12px;
  border-radius: 999px;
  font-size: 12.5px;
  font-weight: 700;
  margin-right: 12px;
  animation: breathe 1.8s ease-in-out infinite;
}
.btn-badge {
  cursor: pointer;
  border: 1px solid color-mix(in srgb, var(--warn) 22%, transparent);
}

.board {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 14px;
  align-items: stretch;
  min-height: calc(100dvh - 160px);
}

.board-main {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  min-height: 0;
  height: 100%;
}

.card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 20px;
  box-shadow: var(--shadow);
}

.board-empty {
  flex: 1;
  padding: 48px 24px;
  text-align: center;

  h2 { margin: 0 0 8px; font-size: 18px; }
  p { margin: 0 0 16px; color: var(--muted); }
}

.poll-hint { margin-top: 4px; }

.drawer-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 18, 28, 0.35);
  z-index: 1000;
  display: flex;
  justify-content: flex-end;
}
.drawer-panel {
  width: min(360px, 92vw);
  height: 100%;
  padding: 16px;
  overflow: auto;
  border-radius: 20px 0 0 20px;
}
.drawer-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.drawer-close {
  border: none;
  background: none;
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
  color: var(--muted);
}

@keyframes breathe {
  50% { opacity: 0.78; }
}

@media (max-width: 960px) {
  .board {
    grid-template-columns: 1fr;
    min-height: 0;
  }
}
</style>
