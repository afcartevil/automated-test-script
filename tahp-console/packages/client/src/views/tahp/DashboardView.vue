<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { NCard, NGrid, NGi, NButton, NStatistic } from 'naive-ui'
import { useRouter } from 'vue-router'
import { useTahpModulesStore } from '@/stores/tahp/modules'
import { listBugTasks } from '@/api/tahp/bug-analysis'
import { listTaskReports } from '@/api/tahp/reports'

const router = useRouter()
const modulesStore = useTahpModulesStore()

interface DashTask {
  task_id: string
  status: 'completed' | 'failed' | 'running' | 'pending' | 'cancelled'
  started_at?: string
}

const dashTasks = ref<DashTask[]>([])
const loading = ref(false)

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

const moduleCards = computed(() =>
  modulesStore.modules.map(m => ({
    name: m.name,
    label: MODULE_LABELS[m.name] || m.name,
    domains: m.domains,
  }))
)

const stats = computed(() => {
  const total = dashTasks.value.length
  const completed = dashTasks.value.filter(t => t.status === 'completed').length
  const failed = dashTasks.value.filter(t => t.status === 'failed').length
  const running = dashTasks.value.filter(t => t.status === 'running' || t.status === 'pending').length
  const successRate = total > 0 ? Math.round((completed / total) * 100) : 0
  const moduleCount = modulesStore.modules.length
  const domainCount = modulesStore.modules.reduce((acc, m) => acc + m.domains.length, 0)
  return { total, completed, failed, running, successRate, moduleCount, domainCount }
})

const trendData = computed(() => {
  const days: { label: string; count: number; completed: number; failed: number }[] = []
  const now = new Date()
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now)
    d.setDate(d.getDate() - i)
    const dateStr = `${d.getMonth() + 1}/${d.getDate()}`
    const dayStart = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
    const dayEnd = dayStart + 86400000
    const dayTasks = dashTasks.value.filter(t => {
      const ts = t.started_at ? new Date(t.started_at).getTime() : 0
      return ts >= dayStart && ts < dayEnd
    })
    days.push({
      label: dateStr,
      count: dayTasks.length,
      completed: dayTasks.filter(t => t.status === 'completed').length,
      failed: dayTasks.filter(t => t.status === 'failed').length,
    })
  }
  return days
})

const trendMax = computed(() => Math.max(...trendData.value.map(d => d.count), 1))

async function refresh() {
  loading.value = true
  try {
    const [bugs, reports] = await Promise.all([listBugTasks(), listTaskReports()])
    const bugDash: DashTask[] = bugs.map(t => ({
      task_id: t.task_id,
      status: t.status === 'cancelled' ? 'failed' : t.status,
      started_at: t.started_at,
    }))
    const reportIds = new Set(bugDash.map(t => t.task_id))
    const adaptDash: DashTask[] = reports
      .filter(r => !reportIds.has(r.task_id))
      .map(r => ({
        task_id: r.task_id,
        status: 'completed' as const,
        started_at: r.started_at,
      }))
    dashTasks.value = [...bugDash, ...adaptDash]
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await Promise.all([modulesStore.refresh(), refresh()])
})

function gotoRoute(moduleName?: string, domain?: string) {
  if (domain === 'bug_analysis') {
    router.push({ name: 'tahp.bug-analysis', query: moduleName ? { module: moduleName } : {} })
    return
  }
  if (domain && domain !== 'bug_analysis') {
    router.push({ name: 'tahp.adapt-debug', query: { module: moduleName, domain } })
    return
  }
  router.push({ name: 'tahp.bug-analysis' })
}
</script>

<template>
  <div class="tahp-dashboard">
    <div class="page-header">
      <div class="header-left">
        <h1>EasyAdapter 控制台</h1>
        <p class="subtitle">传音 Android 底软集成部 · Agent + Skill 平台</p>
      </div>
      <NButton type="primary" @click="gotoRoute()">
        <template #icon>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
        </template>
        智能诊断
      </NButton>
    </div>

    <NGrid :cols="4" :x-gap="16" :y-gap="16" class="stat-grid" responsive="screen" :item-responsive="true">
      <NGi span="1">
        <NCard class="stat-card" :bordered="false">
          <NStatistic label="总任务数" :value="stats.total" />
          <div class="stat-sub">运行中 <strong>{{ stats.running }}</strong></div>
        </NCard>
      </NGi>
      <NGi span="1">
        <NCard class="stat-card success-card" :bordered="false">
          <NStatistic label="成功率" :value="stats.successRate" suffix="%" />
          <div class="stat-sub">完成 <strong>{{ stats.completed }}</strong> / 失败 <strong>{{ stats.failed }}</strong></div>
        </NCard>
      </NGi>
      <NGi span="1">
        <NCard class="stat-card info-card" :bordered="false">
          <NStatistic label="业务模块" :value="stats.moduleCount" />
          <div class="stat-sub">能力域 <strong>{{ stats.domainCount }}</strong></div>
        </NCard>
      </NGi>
      <NGi span="1">
        <NCard class="stat-card warn-card" :bordered="false">
          <NStatistic label="近期失败" :value="stats.failed" />
          <div class="stat-sub">
            <NButton text type="primary" size="tiny" @click="router.push({ name: 'tahp.reports' })">查看报告</NButton>
          </div>
        </NCard>
      </NGi>
    </NGrid>

    <NGrid :cols="5" :x-gap="16" :y-gap="16" style="margin-top: 16px" responsive="screen" :item-responsive="true">
      <NGi span="3">
        <NCard title="近 7 天任务趋势" :bordered="false">
          <div class="trend-chart">
            <div v-for="day in trendData" :key="day.label" class="trend-col">
              <div class="bar-stack">
                <div
                  v-if="day.completed"
                  class="bar bar-success"
                  :style="{ height: `${(day.completed / trendMax) * 120}px` }"
                  :title="`完成 ${day.completed}`"
                />
                <div
                  v-if="day.failed"
                  class="bar bar-error"
                  :style="{ height: `${(day.failed / trendMax) * 120}px` }"
                  :title="`失败 ${day.failed}`"
                />
                <div
                  v-if="day.count - day.completed - day.failed > 0"
                  class="bar bar-info"
                  :style="{ height: `${((day.count - day.completed - day.failed) / trendMax) * 120}px` }"
                  :title="`运行中 ${day.count - day.completed - day.failed}`"
                />
              </div>
              <div class="bar-label">{{ day.label }}</div>
              <div class="bar-count">{{ day.count }}</div>
            </div>
          </div>
          <div class="chart-legend">
            <span class="legend-dot success"></span>完成
            <span class="legend-dot error"></span>失败
            <span class="legend-dot info"></span>运行中
          </div>
        </NCard>
      </NGi>

      <NGi span="2">
        <NCard title="模块矩阵" :bordered="false">
          <div v-if="!moduleCards.length" class="no-modules">暂无模块数据</div>
          <div v-else class="module-grid">
            <div v-for="m in moduleCards" :key="m.name" class="module-cell">
              <div class="module-name">{{ m.label }}</div>
              <div class="module-domains">
                <span
                  v-for="d in m.domains"
                  :key="d.domain"
                  class="domain-tag"
                  @click="gotoRoute(m.name, d.domain)"
                >{{ DOMAIN_LABELS[d.domain] || d.domain }}</span>
              </div>
            </div>
          </div>
        </NCard>
      </NGi>
    </NGrid>
  </div>
</template>

<style scoped>
.tahp-dashboard { padding: 24px; max-width: 1400px; margin: 0 auto; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.header-left h1 { margin: 0 0 4px; font-size: 22px; font-weight: 600; }
.subtitle { color: #888; margin: 0; font-size: 13px; }
.stat-card { border-radius: 8px; }
.stat-card.success-card { background: linear-gradient(135deg,rgba(24,160,88,.08),rgba(24,160,88,.02)); }
.stat-card.info-card { background: linear-gradient(135deg,rgba(32,128,240,.08),rgba(32,128,240,.02)); }
.stat-card.warn-card { background: linear-gradient(135deg,rgba(240,160,32,.08),rgba(240,160,32,.02)); }
.stat-sub { margin-top: 6px; font-size: 12px; color: #888; }

.trend-chart { display: flex; align-items: flex-end; gap: 10px; padding: 8px 0 0; }
.trend-col { display: flex; flex-direction: column; align-items: center; gap: 2px; flex: 1; }
.bar-stack { display: flex; flex-direction: column-reverse; align-items: center; gap: 1px; min-height: 8px; }
.bar { width: 20px; border-radius: 3px 3px 0 0; transition: height .3s; min-height: 4px; }
.bar-success { background: #18a058; }
.bar-error { background: #d03050; }
.bar-info { background: #2080f0; }
.bar-label { font-size: 11px; color: #888; margin-top: 4px; }
.bar-count { font-size: 11px; font-weight: 600; color: #444; }
.chart-legend { display: flex; align-items: center; gap: 12px; margin-top: 12px; font-size: 12px; color: #666; }
.legend-dot { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; }
.legend-dot.success { background: #18a058; }
.legend-dot.error { background: #d03050; }
.legend-dot.info { background: #2080f0; }

.module-grid { display: flex; flex-direction: column; gap: 10px; }
.module-cell { padding: 10px 12px; background: var(--n-color-modal, rgba(0,0,0,.03)); border-radius: 6px; }
.module-name { font-weight: 600; font-size: 13px; margin-bottom: 6px; }
.module-domains { display: flex; flex-wrap: wrap; gap: 4px; }
.domain-tag {
  display: inline-block; padding: 2px 8px; border-radius: 12px;
  font-size: 11px; background: rgba(32,128,240,.1); color: #2080f0;
  cursor: pointer; transition: background .2s;
}
.domain-tag:hover { background: rgba(32,128,240,.22); }
.no-modules { color: #888; font-size: 13px; padding: 20px 0; text-align: center; }
</style>
