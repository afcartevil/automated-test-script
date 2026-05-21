<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { NCard, NGrid, NGi, NTag, NSpin, NEmpty, NButton, NSpace } from 'naive-ui'
import { useRouter } from 'vue-router'
import { useTahpTasksStore } from '@/stores/tahp/tasks'
import { useTahpModulesStore } from '@/stores/tahp/modules'

const router = useRouter()
const tasksStore = useTahpTasksStore()
const modulesStore = useTahpModulesStore()

const MODULE_LABELS: Record<string, string> = {
  telephony: '通信 (Telephony)',
  'kernel-driver': '内核驱动 (Kernel Driver)',
  'power-mgmt': '功耗管理 (Power Mgmt)',
  shared: '共享 (Shared)',
}

const DOMAIN_LABELS: Record<string, string> = {
  bug_analysis: 'Bug 分析',
  code_adaptation: '代码适配',
  version_adaptation: '版本适配',
  carrier_porting: '运营商移植',
}

const moduleCards = computed(() => {
  return modulesStore.modules.map(m => ({
    name: m.name,
    label: MODULE_LABELS[m.name] || m.name,
    domains: m.domains,
    hasModuleYaml: m.hasModuleYaml,
  }))
})

const recentTasks = computed(() => tasksStore.recent)

onMounted(async () => {
  await Promise.all([modulesStore.refresh(), tasksStore.refresh()])
  tasksStore.ensureSocket()
})

function gotoModule(name: string) {
  router.push({ name: 'tahp.modules', query: { module: name } })
}

function gotoExecutor(moduleName?: string, domain?: string) {
  router.push({ name: 'tahp.executor', query: { module: moduleName, domain } })
}
</script>

<template>
  <div class="tahp-dashboard">
    <div class="page-header">
      <h1>TAHP 控制台</h1>
      <p class="subtitle">传音 Android 底软集成部 · 双引擎 AI 平台</p>
    </div>

    <NSpace vertical size="large">
      <NCard title="模块概览" :bordered="false">
        <template #header-extra>
          <NButton size="small" @click="modulesStore.refresh">刷新</NButton>
        </template>
        <NSpin :show="modulesStore.loading">
          <NEmpty v-if="!moduleCards.length" description="未检测到 constraints/ 目录或模块" />
          <NGrid v-else :cols="2" :x-gap="16" :y-gap="16" responsive="screen">
            <NGi v-for="m in moduleCards" :key="m.name">
              <NCard
                hoverable
                :title="m.label"
                size="small"
                @click="gotoModule(m.name)"
              >
                <template #header-extra>
                  <NTag v-if="m.hasModuleYaml" type="success" size="small">已配置</NTag>
                  <NTag v-else type="warning" size="small">缺 module.yaml</NTag>
                </template>
                <div class="domain-list">
                  <NTag
                    v-for="d in m.domains"
                    :key="d.domain"
                    size="small"
                    type="info"
                    style="margin-right: 6px; margin-bottom: 6px"
                  >
                    {{ DOMAIN_LABELS[d.domain] || d.domain }}
                  </NTag>
                  <div v-if="!m.domains.length" style="color: #999">尚无 domain yaml</div>
                </div>
                <div class="card-actions">
                  <NButton size="tiny" @click.stop="gotoExecutor(m.name)">
                    启动任务
                  </NButton>
                </div>
              </NCard>
            </NGi>
          </NGrid>
        </NSpin>
      </NCard>

      <NCard title="最近任务" :bordered="false">
        <template #header-extra>
          <NSpace>
            <NButton size="small" @click="tasksStore.refresh()">刷新</NButton>
            <NButton size="small" type="primary" @click="gotoExecutor()">
              启动新任务
            </NButton>
          </NSpace>
        </template>
        <NSpin :show="tasksStore.loading">
          <NEmpty v-if="!recentTasks.length" description="还没有任务记录" />
          <div v-else class="recent-tasks">
            <div
              v-for="t in recentTasks"
              :key="(t.task_id || t.taskId || '') as string"
              class="task-row"
              @click="router.push({ name: 'tahp.tasks', query: { task_id: t.task_id || t.taskId } })"
            >
              <div class="task-meta">
                <strong>{{ t.module || '-' }}</strong>
                <span class="dim"> · {{ DOMAIN_LABELS[t.domain || ''] || t.domain }}</span>
                <span class="dim"> · {{ t.document_path }}</span>
              </div>
              <div class="task-status">
                <NTag
                  size="small"
                  :type="t.status === 'completed' ? 'success' : t.status === 'failed' ? 'error' : 'info'"
                >
                  {{ t.phase || t.status || 'pending' }}
                </NTag>
              </div>
            </div>
          </div>
        </NSpin>
      </NCard>
    </NSpace>
  </div>
</template>

<style scoped>
.tahp-dashboard { padding: 24px; max-width: 1280px; margin: 0 auto; }
.page-header { margin-bottom: 24px; }
.page-header h1 { margin: 0 0 6px; font-size: 24px; }
.subtitle { color: #888; margin: 0; }
.domain-list { min-height: 32px; }
.card-actions { margin-top: 12px; text-align: right; }
.recent-tasks { display: flex; flex-direction: column; gap: 8px; }
.task-row { display: flex; justify-content: space-between; padding: 12px; border-radius: 6px; background: var(--n-color-modal); cursor: pointer; }
.task-row:hover { background: var(--n-action-color); }
.task-meta strong { font-weight: 600; }
.task-meta .dim { color: #999; margin-left: 6px; }
</style>
