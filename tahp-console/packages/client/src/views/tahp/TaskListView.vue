<script setup lang="ts">
import { computed, onMounted, ref, h } from 'vue'
import {
  NCard, NDataTable, NButton, NSpace, NTag, NSpin, NModal, NInput,
  NDrawer, NDrawerContent, NDescriptions, NDescriptionsItem,
  NScrollbar, NEmpty, NDivider, NProgress, useMessage,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { useRouter } from 'vue-router'
import { useTahpTasksStore } from '@/stores/tahp/tasks'
import type { TaskInfo } from '@/api/tahp/tasks'

const router = useRouter()
const message = useMessage()
const tasksStore = useTahpTasksStore()

const showDrawer = ref(false)
const selectedTask = ref<TaskInfo | null>(null)

const showCorrect = ref(false)
const correctFeedback = ref('')
const correctTarget = ref<string | null>(null)

const DOMAIN_LABELS: Record<string, string> = {
  bug_analysis: 'Bug 分析',
  code_adaptation: '代码适配',
  version_adaptation: '版本适配',
  carrier_porting: '运营商移植',
}

onMounted(() => {
  tasksStore.refresh()
  tasksStore.ensureSocket()
})

function openDetail(task: TaskInfo) {
  selectedTask.value = task
  showDrawer.value = true
}

function openCorrect(taskId: string) {
  correctTarget.value = taskId
  correctFeedback.value = ''
  showCorrect.value = true
}

async function submitCorrect() {
  if (!correctTarget.value || !correctFeedback.value.trim()) return
  try {
    const newTask = await tasksStore.correct(correctTarget.value, correctFeedback.value)
    showCorrect.value = false
    if (newTask) {
      // 自动切换到新的纠偏任务详情
      selectedTask.value = newTask
      message.success('纠偏任务已启动，正在重新执行...')
    } else {
      message.success('纠偏指令已下发')
    }
  } catch (err) {
    message.error((err as Error).message)
  }
}

const selectedTaskStream = computed(() => {
  const tid = selectedTask.value?.task_id || selectedTask.value?.taskId
  return tid ? tasksStore.getStream(String(tid)) : []
})

function statusType(task: TaskInfo): 'success' | 'error' | 'warning' | 'info' | 'default' {
  const s = task.status?.toLowerCase() || ''
  const p = task.phase?.toUpperCase() || ''
  if (s === 'completed' || p === 'COMPLETED') return 'success'
  if (s === 'failed'    || p === 'FAILED')    return 'error'
  if (s === 'running'   || s === 'starting')  return 'info'
  return 'default'
}

const STATUS_LABEL: Record<string, string> = {
  starting: '启动中', running: '执行中', completed: '已完成',
  failed: '失败', COMPLETED: '已完成', FAILED: '失败',
  LOADING_CONSTRAINTS: '加载约束', ANALYZING_DOCUMENT: '分析文档',
  GENERATING_PLAN: '生成计划', EXECUTING_PIPELINE: '执行中',
  RUNNING_GATE_CHECK: '门禁检查',
}

function statusLabel(task: TaskInfo): string {
  const p = task.phase || ''
  const s = task.status || ''
  return STATUS_LABEL[p] || STATUS_LABEL[s] || p || s || '-'
}

function isRunning(task: TaskInfo) {
  return statusType(task) === 'info'
}

function formatTs(ts: number): string {
  return new Date(ts).toLocaleTimeString()
}

function formatTime(iso?: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return `${d.getMonth()+1}/${d.getDate()} ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}:${d.getSeconds().toString().padStart(2,'0')}`
}

function formatDuration(task: TaskInfo): string {
  if (!task.started_at || !task.completed_at) return '-'
  const ms = new Date(task.completed_at).getTime() - new Date(task.started_at).getTime()
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms/1000).toFixed(1)}s`
  return `${Math.floor(ms/60000)}m${Math.floor((ms%60000)/1000)}s`
}

function eventColor(type: string): 'default' | 'success' | 'error' | 'warning' | 'info' {
  if (type.endsWith('.failed')) return 'error'
  if (type.endsWith('.completed')) return 'success'
  if (type.endsWith('.correction')) return 'warning'
  return 'info'
}

function formatPayload(payload: Record<string, unknown>): string {
  const msg = payload?.message || payload?.content || payload?.text
  if (typeof msg === 'string') return msg
  return JSON.stringify(payload, null, 2)
}

const columns = computed<DataTableColumns<TaskInfo>>(() => [
  {
    title: 'Task ID',
    key: 'task_id',
    width: 160,
    ellipsis: { tooltip: true },
    render: r => (r.task_id || r.taskId || '-') as string,
  },
  { title: '模块', key: 'module', width: 80 },
  {
    title: '域', key: 'domain', width: 100,
    render: r => (DOMAIN_LABELS[r.domain || ''] || r.domain || '-') as string,
  },
  {
    title: '状态', key: 'phase', width: 100,
    render: r => h(NTag, { size: 'small', type: statusType(r) }, () => statusLabel(r)),
  },
  {
    title: '进度', key: 'progress', width: 100,
    render: r => {
      const st = statusType(r)
      if (st === 'success') return h(NProgress, { type: 'line', percentage: 100, height: 8, borderRadius: 4, status: 'success', showIndicator: false })
      if (st === 'error')   return h(NProgress, { type: 'line', percentage: 100, height: 8, borderRadius: 4, status: 'error',   showIndicator: false })
      const pct = typeof r.progress === 'number' ? Math.min(100, Math.round(r.progress)) : 0
      if (!pct) return h('span', { style: 'color:#bbb;font-size:12px' }, '-')
      return h(NProgress, { type: 'line', percentage: pct, height: 8, borderRadius: 4, showIndicator: false })
    },
  },
  {
    title: '启动时间', key: 'started_at', width: 110,
    render: r => h('span', { style: 'font-size:12px;color:#888' }, formatTime(r.started_at as string)),
  },
  {
    title: '耗时', key: 'duration', width: 70,
    render: r => h('span', { style: 'font-size:12px;color:#888' }, formatDuration(r)),
  },
  {
    title: '操作', key: 'actions', width: 180,
    render: r => {
      const tid = (r.task_id || r.taskId) as string | undefined
      if (!tid) return h('span', '-')
      return h(NSpace, { size: 'small' }, () => [
        h(NButton, { size: 'small', onClick: () => openDetail(r) }, () => '详情'),
        h(NButton, { size: 'small', type: 'warning', onClick: () => openCorrect(tid) }, () => '纠偏'),
        h(NButton, {
          size: 'small', type: 'primary', ghost: true,
          disabled: statusType(r) !== 'success',
          onClick: () => router.push({ name: 'tahp.reports', query: { task_id: tid } }),
        }, () => '报告'),
      ])
    },
  },
])
</script>

<template>
  <div class="tahp-tasks">
    <div class="page-header">
      <h1>任务列表</h1>
      <p class="subtitle">所有 TAHP 执行任务的历史与状态（双击行查看详情）</p>
    </div>

    <NCard :bordered="false">
      <template #header-extra>
        <NSpace>
          <NButton size="small" @click="tasksStore.refresh(true)">刷新</NButton>
          <NButton size="small" type="primary" @click="router.push({ name: 'tahp.executor' })">启动新任务</NButton>
        </NSpace>
      </template>
      <NSpin :show="tasksStore.loading">
        <NDataTable
          :columns="columns"
          :data="tasksStore.tasks"
          :pagination="{ pageSize: 20 }"
          :row-key="(r: TaskInfo) => (r.task_id || r.taskId || '') as string"
          :row-props="(r: TaskInfo) => ({ style: 'cursor:pointer', onDblclick: () => openDetail(r) })"
        />
      </NSpin>
    </NCard>

    <NDrawer v-model:show="showDrawer" :width="560" placement="right">
      <NDrawerContent v-if="selectedTask" closable>
        <template #header>
          <span>任务详情</span>
          <NTag size="small" :type="statusType(selectedTask)" style="margin-left:10px">
            {{ selectedTask.phase || selectedTask.status || '-' }}
          </NTag>
        </template>

        <NDescriptions :column="1" label-placement="left" size="small" bordered>
          <NDescriptionsItem label="Task ID">
            <code style="font-size:12px;word-break:break-all">{{ selectedTask.task_id || selectedTask.taskId }}</code>
          </NDescriptionsItem>
          <NDescriptionsItem label="模块">{{ selectedTask.module || '-' }}</NDescriptionsItem>
          <NDescriptionsItem label="域">{{ DOMAIN_LABELS[selectedTask.domain || ''] || selectedTask.domain || '-' }}</NDescriptionsItem>
          <NDescriptionsItem label="文档路径">{{ selectedTask.document_path || '-' }}</NDescriptionsItem>
          <NDescriptionsItem label="进度">
            <NProgress
              v-if="typeof selectedTask.progress === 'number'"
              type="line"
              :percentage="Math.min(100, Math.round(selectedTask.progress as number))"
              :status="statusType(selectedTask) === 'success' ? 'success' : statusType(selectedTask) === 'error' ? 'error' : 'default'"
            />
            <span v-else>-</span>
          </NDescriptionsItem>
          <NDescriptionsItem label="启动时间">{{ formatTime(selectedTask.started_at as string) }}</NDescriptionsItem>
          <NDescriptionsItem label="完成时间">{{ formatTime(selectedTask.completed_at as string) }}</NDescriptionsItem>
          <NDescriptionsItem label="耗时">{{ formatDuration(selectedTask) }}</NDescriptionsItem>
          <NDescriptionsItem v-if="selectedTask.files_modified?.length" label="已修改文件">
            <div v-for="f in (selectedTask.files_modified as string[])" :key="f"
              style="font-size:11px;font-family:monospace;color:#10b981">{{ f }}</div>
          </NDescriptionsItem>
          <NDescriptionsItem v-if="selectedTask.error" label="错误">
            <span style="color:#d03050">{{ selectedTask.error }}</span>
          </NDescriptionsItem>
        </NDescriptions>

        <NDivider style="margin:16px 0 12px">执行事件流 ({{ selectedTaskStream.length }})</NDivider>

        <NEmpty v-if="!selectedTaskStream.length" description="暂无事件记录" size="small" />
        <NScrollbar v-else style="max-height:420px">
          <div class="detail-event-list">
            <div v-for="(ev, i) in selectedTaskStream" :key="i"
              class="detail-event-row" :class="`ev-${eventColor(ev.type)}`">
              <div class="ev-header">
                <NTag size="tiny" :type="eventColor(ev.type)">{{ ev.type }}</NTag>
                <span class="ev-ts">{{ formatTs(ev.ts) }}</span>
              </div>
              <pre class="ev-body">{{ formatPayload(ev.payload) }}</pre>
            </div>
          </div>
        </NScrollbar>

        <NDivider style="margin:16px 0 12px" />
        <NSpace>
          <NButton type="primary" size="small"
            @click="router.push({ name: 'tahp.executor', query: { module: selectedTask.module, domain: selectedTask.domain } })">
            以相同参数重新执行
          </NButton>
          <NButton type="warning" size="small"
            @click="openCorrect((selectedTask.task_id || selectedTask.taskId) as string)">
            发送纠偏
          </NButton>
          <NButton size="small" type="primary" ghost
            @click="router.push({ name: 'tahp.reports', query: { task_id: selectedTask.task_id || selectedTask.taskId } })">
            查看报告
          </NButton>
        </NSpace>
      </NDrawerContent>
    </NDrawer>

    <NModal v-model:show="showCorrect" preset="dialog" title="纠偏反馈"
      positive-text="发送" negative-text="取消" @positive-click="submitCorrect">
      <div style="margin-bottom:8px;font-size:13px;color:#888">Task: <code>{{ correctTarget }}</code></div>
      <NInput v-model:value="correctFeedback" type="textarea" placeholder="描述需要调整的内容..."
        :autosize="{ minRows: 4, maxRows: 10 }" />
    </NModal>
  </div>
</template>

<style scoped>
.tahp-tasks { padding: 24px; max-width: 1400px; margin: 0 auto; }
.page-header { margin-bottom: 20px; }
.page-header h1 { margin: 0 0 4px; font-size: 22px; font-weight: 600; }
.subtitle { color: #888; margin: 0; font-size: 13px; }
.detail-event-list { display: flex; flex-direction: column; gap: 6px; padding-right: 8px; }
.detail-event-row { padding: 8px 10px; border-radius: 5px; background: var(--n-color-modal,rgba(0,0,0,.03)); border-left: 3px solid transparent; }
.detail-event-row.ev-success { border-left-color: #18a058; }
.detail-event-row.ev-error { border-left-color: #d03050; background: rgba(208,48,80,.05); }
.detail-event-row.ev-warning { border-left-color: #f0a020; }
.detail-event-row.ev-info { border-left-color: #2080f0; }
.ev-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.ev-ts { color: #999; font-size: 11px; font-family: monospace; }
.ev-body { margin: 0; font-size: 12px; white-space: pre-wrap; word-break: break-all; color: var(--n-text-color,#333); line-height: 1.5; }
</style>
