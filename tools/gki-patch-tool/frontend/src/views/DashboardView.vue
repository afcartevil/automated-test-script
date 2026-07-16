<template>
  <section>
    <div class="topbar">
      <div>
        <p class="eyebrow">Dashboard</p>
        <h1 class="page-title">看板</h1>
        <p v-if="!isEmbedded" class="page-desc">汇总分析任务、升级任务和 patch 数据库状态，快速掌握当前工作进展。</p>
      </div>
      <div v-if="!isEmbedded" class="toolbar">
        <RouterLink to="/analysis" class="btn primary">开始分析</RouterLink>
        <RouterLink to="/patches" class="btn">浏览数据库</RouterLink>
      </div>
    </div>

    <div class="grid grid-4">
      <div class="card metric">
        <div class="metric-label">分析任务</div>
        <div class="metric-value">{{ tasks.length }}</div>
        <div class="metric-note">最近 50 条</div>
      </div>
      <div class="card metric">
        <div class="metric-label">升级任务</div>
        <div class="metric-value">{{ upgradeJobs.length }}</div>
        <div class="metric-note">最近 50 条</div>
      </div>
      <div class="card metric">
        <div class="metric-label">Patch 数量</div>
        <div class="metric-value">{{ patchTotal }}</div>
        <div class="metric-note">数据库总量</div>
      </div>
      <div class="card metric">
        <div class="metric-label">模块分类</div>
        <div class="metric-value">{{ moduleStats.length }}</div>
        <div class="metric-note">已识别开发模块</div>
      </div>
    </div>

    <div class="grid grid-2" style="margin-top: 18px">
      <div class="card card-pad">
        <div class="section-title">
          <div>
            <h2>{{ isEmbedded ? '分析任务' : '最近分析' }}</h2>
            <p>实时任务与历史结果</p>
          </div>
          <RouterLink to="/analysis" class="btn" @click="onLinkClick($event, '/analysis')">查看全部</RouterLink>
        </div>
        <div v-if="tasks.length" class="list">
          <RouterLink
            v-for="task in tasks.slice(0, 7)"
            :key="task.id"
            class="list-item split"
            :to="{ path: '/analysis', query: { task: task.id } }"
            @click="onLinkClick($event, '/analysis', { task: task.id })"
          >
            <div>
              <strong>{{ taskTitle(task) }}</strong>
              <div class="muted mono">{{ shortId(task.id) }}</div>
            </div>
            <span class="pill" :class="statusTone(task.status)">{{ task.status || '-' }}</span>
          </RouterLink>
        </div>
        <div v-else class="empty">暂无分析任务</div>
      </div>

      <div class="card card-pad">
        <div class="section-title">
          <div>
            <h2>{{ isEmbedded ? '升级任务' : '升级流程' }}</h2>
            <p>合入、冲突处理与构建状态</p>
          </div>
          <RouterLink to="/upgrade" class="btn" @click="onLinkClick($event, '/upgrade')">
            {{ isEmbedded ? '查看全部' : '进入升级' }}
          </RouterLink>
        </div>
        <div v-if="upgradeJobs.length" class="timeline">
          <RouterLink
            v-for="job in upgradeJobs.slice(0, 6)"
            :key="job.id || job.job_id"
            class="timeline-item"
            :to="{ path: '/upgrade', query: { job: job.id || job.job_id } }"
            @click="onLinkClick($event, '/upgrade', { job: String(job.id || job.job_id) })"
          >
            <span class="timeline-dot"></span>
            <span class="timeline-body split">
              <span>
                <strong>{{ job.from_tag || '-' }} -> {{ job.to_tag || '-' }}</strong>
                <span class="muted mono" style="display:block">{{ shortId(job.id || job.job_id) }}</span>
              </span>
              <span class="pill" :class="statusTone(job.status)">{{ job.status || '-' }}</span>
            </span>
          </RouterLink>
        </div>
        <div v-else class="empty">暂无升级任务</div>
      </div>
    </div>

    <div v-if="error" class="message error" style="margin-top: 18px">{{ error }}</div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, shortId, statusTone } from '../api'
import { useEmbeddedNav } from '../composables/useEmbeddedNav'

const { onLinkClick, isEmbedded } = useEmbeddedNav()

const tasks = ref<any[]>([])
const upgradeJobs = ref<any[]>([])
const moduleStats = ref<any[]>([])
const patchTotal = ref(0)
const error = ref('')

function taskTitle(task: any) {
  if (task.type === 'single') return task.sha || '单笔分析'
  return `${task.from_tag || '-'} -> ${task.to_tag || '-'}`
}

async function load() {
  error.value = ''
  try {
    const [taskData, upgradeData, patchData, moduleData] = await Promise.all([
      api.get<any>('/api/tasks?limit=50'),
      api.get<any>('/api/upgrade/jobs?limit=50'),
      api.get<any>('/api/patches?page=1&page_size=1'),
      api.get<any>('/api/patches/module-stats'),
    ])
    tasks.value = taskData.tasks || []
    upgradeJobs.value = upgradeData.jobs || []
    patchTotal.value = patchData.total || 0
    moduleStats.value = moduleData.stats || []
  } catch (err: any) {
    error.value = err.message || String(err)
  }
}

onMounted(load)
</script>
