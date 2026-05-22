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
    await tasksStore.correct(correctTarget.value, correctFeedback.value)
    message.success('纠偏指令已下发')
    showCorrect.value = false
  } catch (err) {
    message.error((err as Error).message)
  }
}

const selectedTaskStream = computed(() => {
  const tid = selectedTask.value?.task_id || selectedTask.value?.taskId
  return tid ? tasksStore.getStream(String(tid)) : []
})

function statusType(task: TaskInfo): 'success' | 'error' | 'warning' | 'info' | 'default' {
  if (task.status === 'completed' || task.phase === 'COMPLETED') return 'success'
  if (task.status === 'failed' || task.phase === 'FAILED') return 'error'
  return 'info'
}

function isRunning(task: TaskInfo) {
  return statusType(task) === 'info'
}

function formatTs(ts: number): string {
  return new Date(ts).toLocaleTimeString()
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
    render: r => (r.task_id || r.taskId || '-') as string,
    width: 200,
    ellipsis: { tooltip: true },
  },
  { title: '模块', key: 'module', width: 120 },
  {
    title: '域',
    key: 'domain',
    width: 130,
    render: r => (DOMAIN_LABELS[r.domain || ''] || r.domain || '-') as string,
  },
  { title: '设计文档', key: 'document_path', ellipsis: { tooltip: true } },
  {
    title: '状态',
    key: 'phase',
    width: 140,
    render: r => h(NTag, { size: 'small', type: statusType(r) }, () => r.phase || r.status || '-'),
  },
  {
    title: '进度',
    key: 'progress',
    width: 110,
    render: r => {
      const pct = typeof r.progress === 'number' ? Math.round((r.progress as number) * 100) : null
      if (pct === null) return '-'
      return h(NProgress, {
        type: 'line',
        percentage: pct,
        height: 8,
        borderRadius: 4,
        status: statusType(r) === 'success' ? 'success' : statusType(r) === 'error' ? 'error' : 'default',
      })
    },
  },
  {
    title: '操作',
    key: 'actions',
    width: 200,
    render: r => {
      const tid = (r.task_id || r.taskId) as string | undefined
      if (!tid) return h('span', '-')
      return h(NSpace, { size: 'small' }, () => [
        h(NButton, { size: 'small', onClick: () => openDetail(r) }, () => '详情'),
        h(NButton, {
          size: 'small', type: 'warning',
          disabled: !isRunning(r),
          onClick: () => openCorrect(tid),
        }, () => '纠偏'),
        h(NButton, {
          size: 'small',
          onClick: () => router.push({ name: 'tahp.reports' }),
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
              :percentage="Math.round((selectedTask.progress as number) * 100)"
              :status="statusType(selectedTask) === 'success' ? 'success' : statusType(selectedTask) === 'error' ? 'error' : 'default'"
            />
            <span v-else>-</span>
          </NDescriptionsItem>
          <NDescriptionsItem v-if="selectedTask.error" label="错误">
            <span style="color:#d03050">{{ selectedTask.error }}</span>
          </NDescriptionsItem>
          <NDescriptionsItem v-if="selectedTask.created_at" label="创建时间">{{ selectedTask.created_at }}</NDescriptionsItem>
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
          <NButton type="warning" size="small" :disabled="!isRunning(selectedTask)"
            @click="openCorrect((selectedTask.task_id || selectedTask.taskId) as string)">
            发送纠偏
          </NButton>
          <NButton size="small" @click="router.push({ name: 'tahp.reports' })">查看报告</NButton>
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
